#!/usr/bin/env python3
"""Sync all GitHub repos for the authenticated user into the gh/ directory.

By default, also pushes a per-host snapshot of each PRIVATE repo's working
state to a `wip/<hostname>` branch on origin (`wip/<hostname>@<dirname>` from
a linked worktree), so work-in-progress flows between machines without
relying on Syncthing replicating .git/. Pass --no-push-wip to disable. Public
repos are never auto-pushed; archived, detached-HEAD, and
mid-rebase/merge/cherry-pick repos are skipped.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

# Branch-name-safe sanitizer for hostnames (covers macOS names with
# apostrophes/spaces like "Jason's MBP").
_BRANCH_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")

# Flattens a repo path into a collision-free bundle-filename key.
_KEY_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def bundle_key(dest):
    """Stable, collision-free bundle basename for a repo.

    Uses the repo's path relative to $HOME with separators flattened, so repos
    that merely share a directory name (e.g. ~/Code/gh/public/notes vs
    ~/Projects/notes) never collide on the same bundle file. Paths are identical
    across the fleet (all ~/…), so the key matches on the receiving machine too.
    """
    dest = Path(dest).resolve()
    try:
        rel = dest.relative_to(Path.home().resolve())
    except ValueError:
        rel = Path(*dest.parts[1:])  # outside home: drop the leading '/'
    return _KEY_SAFE.sub("-", str(rel)).strip("-") or "repo"


# Files/dirs whose presence indicates an in-progress operation that we
# should not snapshot (state isn't a coherent point-in-time view).
IN_PROGRESS_MARKERS = (
    "rebase-merge",
    "rebase-apply",
    "MERGE_HEAD",
    "CHERRY_PICK_HEAD",
    "REVERT_HEAD",
    "BISECT_LOG",
)

GH_DIR = Path.home() / "Code" / "gh"
ARCHIVED_DIR = GH_DIR / "archived"
PUBLIC_DIR = GH_DIR / "public"
ARCHIVED_PUBLIC_DIR = ARCHIVED_DIR / "public"

# --wip-only writes bundles for repos with no private GitHub origin here. It's
# a Syncthing-synced, non-git folder — one bundle file per repo per host, so
# it rides Syncthing without the .git/ conflict storms.
WIP_BUNDLE_DIR = Path.home() / ".local" / "share" / "wip-bundles"

# Roots scanned by --wip-only for working-tree snapshots (no GitHub API). Repos
# directly under GH_DIR push to a wip branch; PUBLIC_DIR and ~/Projects bundle.
WIP_SCAN_ROOTS = [GH_DIR, PUBLIC_DIR, Path.home() / "Projects"]

# Heartbeat touched at the end of every --wip-only run so the backup monitor
# can tell WIP protection is alive (its mtime = last successful sweep).
WIP_STATUS_FILE = Path.home() / ".local" / "var" / "wip-sync.status"

# Where to look for an explicit org list, in precedence order:
#   1. $SYNC_GH_ORGS env var
#   2. $XDG_CONFIG_HOME/sync-gh/orgs (default ~/.config/sync-gh/orgs)
#   3. fallback: every org the authenticated user belongs to
# In (1) and (2), orgs are comma/whitespace/newline separated and '#' starts a
# comment. An explicitly set but empty value means "personal repos only".
ENV_ORGS = "SYNC_GH_ORGS"


def _config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "sync-gh" / "orgs"


def _parse_org_list(text):
    """Parse org logins: comma/whitespace-separated, '#' comments ignored."""
    orgs = []
    for line in text.splitlines():
        for tok in line.split("#", 1)[0].replace(",", " ").split():
            orgs.append(tok)
    return orgs


def get_orgs():
    """Resolve which orgs to sync alongside the user's personal repos.

    `gh repo list` with no owner only returns personal repos, so orgs are
    fetched separately. Precedence: SYNC_GH_ORGS env var, then
    ~/.config/sync-gh/orgs, then every org the user belongs to. An explicitly
    set-but-empty env var or config file means "personal repos only".
    """
    env = os.environ.get(ENV_ORGS)
    if env is not None:
        return _parse_org_list(env)
    cfg = _config_path()
    if cfg.is_file():
        return _parse_org_list(cfg.read_text())
    result = subprocess.run(
        ["gh", "api", "user/orgs", "-q", ".[].login"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.split()


def _list_repos(owner=None):
    """List repos for `owner` (or the authenticated user if None) via gh CLI."""
    cmd = ["gh", "repo", "list"]
    if owner:
        cmd.append(owner)
    cmd += [
        "--limit",
        "500",
        "--json",
        "name,nameWithOwner,url,isArchived,isPrivate",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def get_repos():
    """Get repos for the authenticated user plus the configured orgs.

    Deduplicated by nameWithOwner in case membership causes overlap.
    """
    repos = []
    seen = set()
    for owner in (None, *get_orgs()):
        for repo in _list_repos(owner):
            key = repo["nameWithOwner"]
            if key not in seen:
                seen.add(key)
                repos.append(repo)
    return repos


def clone_repo(name, url, dest):
    """Clone a repo."""
    print(f"  Cloning {name}...")
    subprocess.run(
        ["gh", "repo", "clone", url, str(dest)],
        capture_output=True,
        text=True,
    )


def pull_repo(name, dest):
    """Pull latest changes for an existing repo."""
    result = subprocess.run(
        ["git", "-C", str(dest), "pull", "--ff-only"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  {name}: pull failed ({result.stderr.strip()})")
        return False
    if "Already up to date" not in result.stdout:
        print(f"  {name}: updated")
    return True


def in_progress_op(dest):
    """Return marker name if a git operation is in-flight, else None."""
    git_dir = Path(dest) / ".git"
    for marker in IN_PROGRESS_MARKERS:
        if (git_dir / marker).exists():
            return marker
    return None


def _git(dest, args, env=None, check=False):
    """Run `git -C dest ...`, capturing output. Thin wrapper for brevity."""
    return subprocess.run(
        ["git", "-C", str(dest), *args],
        capture_output=True,
        text=True,
        env=env,
        check=check,
    )


def has_head(dest):
    """True if HEAD resolves to a commit (repo has at least one commit)."""
    return _git(dest, ["rev-parse", "--verify", "--quiet", "HEAD"]).returncode == 0


def has_origin(dest):
    """True if the repo has an `origin` remote."""
    return _git(dest, ["remote", "get-url", "origin"]).returncode == 0


def wip_ref_suffix(dest):
    """'@<dirname>' when dest is a linked worktree, else ''.

    Sibling worktrees share the repo's origin and ref storage, so an
    unsuffixed name would make every worktree of a repo write the SAME
    wip/<host> ref — the last one scanned wins, silently replacing the main
    checkout's snapshot. Suffixing by worktree dirname keeps each checkout's
    snapshot distinct ('@' can't appear in a sanitized hostname or dirname,
    so parsing on the receive side stays unambiguous, and 'wip/<host>' plus
    'wip/<host>@<dir>' never collide in the ref namespace the way a '/'
    separator would). A linked worktree is detected by its .git being a
    gitdir-pointer file rather than a directory.
    """
    dest = Path(dest)
    if (dest / ".git").is_file():
        name = _BRANCH_SAFE.sub("-", dest.name).strip("-.")
        return f"@{name or 'worktree'}"
    return ""


# Orphaned wip snapshots (worktree removed after merging, repo deleted) are
# kept this long before pruning — a recovery window in case a checkout was
# removed while still carrying unmerged WIP.
WIP_PRUNE_GRACE_DAYS = 30
WIP_PRUNE_INTERVAL = 86400  # prune at most daily; the sweep runs every 5 min


def _checkout_dirs(dest):
    """Existing checkout dirs of this repo: main worktree + linked worktrees.

    `git worktree list` still reports a worktree whose directory was deleted
    (until `git worktree prune`), so filter on directory existence — a
    deleted worktree must count as gone.
    """
    out = _git(dest, ["worktree", "list", "--porcelain"]).stdout
    return [
        Path(line.removeprefix("worktree "))
        for line in out.splitlines()
        if line.startswith("worktree ")
        and Path(line.removeprefix("worktree ")).is_dir()
    ]


def prune_wip_refs(dest, hostname):
    """Delete this host's orphaned wip/<host>@* refs on origin.

    A ref is orphaned when no existing checkout produces it any more —
    typically the worktree was removed after its branch merged. Only refs
    past WIP_PRUNE_GRACE_DAYS (by snapshot committer date, which freezes
    once the checkout stops re-snapshotting) are deleted; other hosts' refs
    are never touched, and the unsuffixed wip/<host> isn't listed at all —
    it belongs to the main checkout this runs from. Throttled to daily via
    a stamp file so the 5-minute sweep isn't an ls-remote per repo.
    """
    git_dir = Path(_git(dest, ["rev-parse", "--absolute-git-dir"]).stdout.strip())
    stamp = git_dir / f"wip-prune-{hostname}.stamp"
    now = time.time()
    if stamp.is_file() and now - stamp.stat().st_mtime < WIP_PRUNE_INTERVAL:
        return
    listing = _git(dest, ["ls-remote", "origin", f"refs/heads/wip/{hostname}@*"])
    if listing.returncode != 0:
        return  # origin unreachable — retry next sweep, don't write the stamp
    stamp.touch()
    expected = {
        f"refs/heads/wip/{hostname}{wip_ref_suffix(d)}" for d in _checkout_dirs(dest)
    }
    cutoff = now - WIP_PRUNE_GRACE_DAYS * 86400
    for line in listing.stdout.splitlines():
        _, _, ref = line.partition("\t")
        if not ref or ref in expected:
            continue
        # Age-gate on the snapshot's committer date, read via FETCH_HEAD.
        if _git(dest, ["fetch", "-q", "origin", ref]).returncode != 0:
            continue
        when = _git(dest, ["log", "-1", "--format=%ct", "FETCH_HEAD"]).stdout.strip()
        if when and int(when) < cutoff:
            short = ref.removeprefix("refs/heads/")
            if _git(dest, ["push", "origin", "--delete", short]).returncode == 0:
                print(f"  {dest.name}: pruned orphaned {short}")


def prune_wip_bundles(hostname, roots, bundle_dir):
    """Delete this host's bundles for repos that no longer exist locally.

    Bundle filenames key on the repo path, so a deleted or renamed repo
    leaves its last bundle behind forever — and Syncthing replicates it to
    every machine. Gate on the bundle's mtime (frozen once the source repo
    stops re-bundling) with the same grace as ref pruning. The '@<host>'
    filename boundary means other hosts' bundles are never touched.
    """
    if not bundle_dir.is_dir():
        return
    live = {bundle_key(d) for d in iter_local_repos(roots)}
    cutoff = time.time() - WIP_PRUNE_GRACE_DAYS * 86400
    suffix = f"@{hostname}.bundle"
    for bundle in bundle_dir.glob(f"*{suffix}"):
        key = bundle.name.removesuffix(suffix)
        if key in live:
            continue
        if bundle.stat().st_mtime < cutoff:
            bundle.unlink(missing_ok=True)
            print(f"  pruned orphaned bundle {bundle.name}")


def snapshot_commit(dest, message):
    """Commit the full working tree without disturbing the repo.

    Captures tracked modifications, the staged index, AND untracked-but-not-
    ignored files (a brand-new file you haven't `git add`ed is exactly the WIP
    you'd hate to lose). Returns the new commit SHA, or None if the working
    tree already matches HEAD (nothing to snapshot).

    Works through a throwaway index via GIT_INDEX_FILE, so the user's real
    staging area and working tree are never touched. `git add -A` in that index
    honours .gitignore, so build junk / node_modules stay out of the snapshot.
    """
    git_dir = _git(dest, ["rev-parse", "--absolute-git-dir"]).stdout.strip()
    if not git_dir:
        return None
    fd, tmp_index = tempfile.mkstemp(prefix="wip-index-", dir=git_dir)
    os.close(fd)
    # Remove the 0-byte file: git errors on an empty index file but happily
    # creates a fresh one at a non-existent path (read-tree / add -A).
    os.unlink(tmp_index)
    env = {**os.environ, "GIT_INDEX_FILE": tmp_index}
    head = has_head(dest)
    try:
        if head:
            _git(dest, ["read-tree", "HEAD"], env=env, check=True)
        _git(dest, ["add", "-A"], env=env, check=True)
        tree = _git(dest, ["write-tree"], env=env, check=True).stdout.strip()
        if head and tree == _git(dest, ["rev-parse", "HEAD^{tree}"]).stdout.strip():
            return None  # working tree identical to HEAD
        parent = ["-p", "HEAD"] if head else []
        return _git(
            dest, ["commit-tree", tree, *parent, "-m", message], check=True
        ).stdout.strip()
    finally:
        try:
            os.unlink(tmp_index)
        except FileNotFoundError:
            pass


def push_wip(name, dest, hostname):
    """Push a snapshot of working state to wip/<hostname> on origin.

    Captures tracked changes, the index, and untracked-but-not-ignored files
    via snapshot_commit. When the tree is clean, points wip/<host> at HEAD so
    unpushed *commits* are captured too. Force-push because wip refs always
    replace the previous snapshot. Linked worktrees push to a suffixed
    wip/<host>@<dirname> branch so siblings never clobber each other's
    snapshot. Skips detached HEAD and mid-rebase/merge/cherry-pick (state
    isn't a coherent snapshot to share).
    """
    op = in_progress_op(dest)
    if op:
        print(f"  {name}: skipping wip (in-progress {op})")
        return

    if _git(dest, ["symbolic-ref", "-q", "HEAD"]).returncode != 0:
        return  # detached HEAD

    branch = f"wip/{hostname}{wip_ref_suffix(dest)}"
    snap = snapshot_commit(dest, f"wip snapshot ({hostname})")

    if snap is None:
        # Clean tree: capture unpushed commits by pointing wip at HEAD, but
        # skip if origin/wip/<host> already matches HEAD (redundant push). The
        # cached remote ref was just refreshed by the prior `git pull`, so a
        # stale read only risks a harmless extra push.
        head_sha = _git(dest, ["rev-parse", "HEAD"]).stdout.strip()
        cached = _git(
            dest, ["rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}"]
        )
        if cached.returncode == 0 and cached.stdout.strip() == head_sha:
            return  # nothing new
        ref, suffix = "HEAD", ""
    else:
        ref, suffix = snap, " (snapshot of working tree)"

    push = _git(dest, ["push", "--force", "origin", f"{ref}:refs/heads/{branch}"])
    if push.returncode != 0:
        print(f"  {name}: wip push failed ({push.stderr.strip()})")
    else:
        print(f"  {name}: pushed → {branch}{suffix}")


def bundle_wip(name, dest, hostname, bundle_dir):
    """Snapshot working state into a per-host git bundle in bundle_dir.

    For repos with no private GitHub origin (local-only, public, or under
    ~/Projects). A bundle is a single file, so it rides Syncthing without the
    many-small-mutating-files conflicts that syncing .git/ directly causes. The
    working-tree snapshot (incl. new files) is stored on a local refs/wip/<host>
    ref and bundled alongside all branches/tags.

    Per-host filename (`<repo>@<host>.bundle`) so two machines never write the
    same file. Skips re-bundling when nothing changed since the last run.
    """
    op = in_progress_op(dest)
    if op:
        print(f"  {name}: skipping bundle (in-progress {op})")
        return

    snap = snapshot_commit(dest, f"wip snapshot ({hostname})")
    target = snap or ("HEAD" if has_head(dest) else None)
    if target is None:
        return  # empty repo, nothing to bundle

    # Suffixed per worktree: refs/wip/* lives in the SHARED repo storage, so
    # a sibling worktree writing the same name between our update-ref and the
    # bundle create below would bundle the wrong tree under this repo's key.
    wip_ref = f"refs/wip/{hostname}{wip_ref_suffix(dest)}"
    _git(dest, ["update-ref", wip_ref, target], check=True)

    # Change detection: signature over the wip ref + all branch/tag tips. Skip
    # the (relatively expensive) bundle write when nothing moved since last time.
    sig = _git(
        dest,
        [
            "for-each-ref",
            "--format=%(refname) %(objectname)",
            "refs/heads",
            "refs/tags",
            wip_ref,
        ],
    ).stdout
    git_dir = _git(dest, ["rev-parse", "--absolute-git-dir"]).stdout.strip()
    sig_file = Path(git_dir) / f"wip-bundle-{hostname}.sig"
    bundle_path = bundle_dir / f"{bundle_key(dest)}@{hostname}.bundle"
    prev = sig_file.read_text() if sig_file.is_file() else None
    if prev == sig and bundle_path.is_file():
        return  # unchanged and bundle already present

    bundle_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = bundle_path.with_name(bundle_path.name + ".tmp")
    res = _git(dest, ["bundle", "create", str(tmp_path), "--all", wip_ref])
    if res.returncode != 0:
        print(f"  {name}: bundle failed ({res.stderr.strip()})")
        tmp_path.unlink(missing_ok=True)
        return
    os.replace(tmp_path, bundle_path)  # atomic; Syncthing only ever sees a whole file
    sig_file.write_text(sig)
    print(f"  {name}: bundled → {bundle_path.name}")


def classify_repo(dest):
    """Route a local repo: 'push' (private GitHub), 'bundle', or 'skip'.

    Only repos directly under ~/Code/gh (private-by-convention) with an origin
    are pushed to a wip branch — we never push WIP to a public remote. Public
    repos, ~/Projects repos, and remoteless/local-only repos are bundled.
    Archived repos are skipped.
    """
    dest = Path(dest)
    if not (dest / ".git").exists():
        return "skip"
    parent = dest.parent
    if parent in (ARCHIVED_DIR, ARCHIVED_PUBLIC_DIR):
        return "skip"
    if parent == GH_DIR and has_origin(dest):
        return "push"
    return "bundle"


def iter_local_repos(roots):
    """Yield git working-copy dirs one level under each root."""
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / ".git").exists():
                yield child


def wip_only_main(hostname, roots, bundle_dir):
    """Fast, network-light path: snapshot every local repo's working tree and
    push (private GitHub repos) or bundle (everything else). No GitHub API.
    Intended to run every few minutes from a launchd agent.
    """
    for dest in iter_local_repos(roots):
        # Isolate each repo: a single bad one (no committer identity, read-only
        # mount, corrupt object) must not skip the rest — nor the heartbeat
        # below, which the monitor reads as "WIP protection is alive".
        try:
            kind = classify_repo(dest)
            if kind == "push":
                push_wip(dest.name, dest, hostname)
                # Prune from the main checkout only, so sibling worktrees
                # don't repeat the (throttled) ls-remote.
                if not wip_ref_suffix(dest):
                    prune_wip_refs(dest, hostname)
            elif kind == "bundle":
                bundle_wip(dest.name, dest, hostname, bundle_dir)
        except Exception as exc:  # noqa: BLE001 — daemon robustness, keep sweeping
            print(f"  {dest.name}: wip snapshot failed ({exc})")
    try:
        prune_wip_bundles(hostname, roots, bundle_dir)
    except Exception as exc:  # noqa: BLE001
        print(f"  bundle prune failed ({exc})")
    # No summary line: push_wip/bundle_wip already log only when they act, so a
    # quiet machine writes nothing to the launchd log (which appends forever).
    # The heartbeat below is the "it ran" signal the monitor checks.
    try:
        WIP_STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
        WIP_STATUS_FILE.write_text(
            datetime.datetime.now().isoformat(timespec="seconds") + "\n"
        )
    except OSError as exc:
        print(f"wip-only: could not write heartbeat {WIP_STATUS_FILE}: {exc}")


def repo_dir(repo):
    """Return the correct local directory for a repo based on archived/public status."""
    archived = repo["isArchived"]
    public = not repo["isPrivate"]
    if archived:
        return ARCHIVED_PUBLIC_DIR if public else ARCHIVED_DIR
    return PUBLIC_DIR if public else GH_DIR


# All directories where repos may live (for scanning local-only repos)
ALL_REPO_DIRS = [GH_DIR, PUBLIC_DIR, ARCHIVED_DIR, ARCHIVED_PUBLIC_DIR]


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument(
        "--no-push-wip",
        dest="push_wip",
        action="store_false",
        help="Disable the default per-host wip-branch push for private repos.",
    )
    ap.add_argument(
        "--wip-only",
        action="store_true",
        help="Fast path: snapshot local repos' WIP and push (private GitHub) "
        "or bundle (everything else) WITHOUT hitting the GitHub API. Intended "
        "for the periodic launchd agent.",
    )
    return ap.parse_args()


def sanitized_hostname():
    """Hostname suitable for use as a git ref component."""
    raw = socket.gethostname().split(".")[0]
    safe = _BRANCH_SAFE.sub("-", raw).strip("-.")
    return safe or "unknown-host"


def main():
    args = parse_args()
    hostname = sanitized_hostname()

    if args.wip_only:
        wip_only_main(hostname, WIP_SCAN_ROOTS, WIP_BUNDLE_DIR)
        return

    for d in ALL_REPO_DIRS:
        d.mkdir(parents=True, exist_ok=True)

    print("Fetching repo list from GitHub...")
    repos = get_repos()
    print(f"Found {len(repos)} repos on GitHub.\n")

    # Move repos to the correct location based on archived/public status
    for repo in repos:
        name = repo["name"]
        correct_dir = repo_dir(repo)
        correct_path = correct_dir / name

        # Check all other dirs for a misplaced copy
        for d in ALL_REPO_DIRS:
            candidate = d / name
            if candidate.is_dir() and d != correct_dir:
                label_parts = []
                if repo["isArchived"]:
                    label_parts.append("archived")
                if not repo["isPrivate"]:
                    label_parts.append("public")
                label = ", ".join(label_parts) or "active/private"
                print(f"  Moving {name} to {label}...")
                shutil.move(str(candidate), str(correct_path))
                break

    # Build set of all local repo names
    skip = {"archived", "public"}
    all_local = set()
    for d in ALL_REPO_DIRS:
        if d.is_dir():
            all_local |= {
                item.name
                for item in d.iterdir()
                if item.is_dir() and item.name not in skip
            }

    remote_names = {r["name"] for r in repos}
    local_only = all_local - remote_names
    if local_only:
        print(f"Local-only (not on GitHub): {', '.join(sorted(local_only))}\n")

    to_clone = []
    to_pull = []
    to_push_wip = []
    for repo in repos:
        name = repo["name"]
        dest = repo_dir(repo) / name
        if dest.is_dir():
            if not repo["isArchived"]:
                to_pull.append((name, dest))
                # Only auto-push for PRIVATE repos — public stays user-driven.
                if args.push_wip and repo["isPrivate"]:
                    to_push_wip.append((name, dest))
        else:
            to_clone.append((repo, dest))

    if to_clone:
        print(f"Cloning {len(to_clone)} new repos:")
        for repo, dest in to_clone:
            clone_repo(repo["name"], repo["url"], dest)
        print()

    if to_pull:
        print(f"Pulling {len(to_pull)} active repos:")
        for name, dest in sorted(to_pull):
            pull_repo(name, dest)
        print()

    if to_push_wip:
        print(f"Pushing wip/{hostname} for {len(to_push_wip)} private repos:")
        for name, dest in sorted(to_push_wip):
            push_wip(name, dest, hostname)
        print()

    archived_count = sum(1 for r in repos if r["isArchived"])
    public_count = sum(1 for r in repos if not r["isPrivate"])
    active_count = len(repos) - archived_count
    print(
        f"Done. {active_count} active, {archived_count} archived, {public_count} public."
    )


if __name__ == "__main__":
    main()
