#!/usr/bin/env python3
"""Sync all GitHub repos for the authenticated user into the gh/ directory.

By default, also pushes a per-host snapshot of each PRIVATE repo's working
state to a `wip/<hostname>` branch on origin (`wip/<hostname>@<dirname>` from
a linked worktree), so work-in-progress flows between machines without
relying on Syncthing replicating .git/. Only what origin lacks is pushed
(local changes, or commits on no remote branch); a clean checkout deletes its
own wip ref. Secrets (.env*, .envrc, *.pem, *.key), agent tool installs and
nested clones are never snapshotted. Pass --no-push-wip to disable. Public
repos are never auto-pushed (GitHub is asked; the folder isn't trusted);
archived, detached-HEAD, and mid-rebase/merge/cherry-pick repos are skipped.

A clone in the wrong folder for its status (public, archived) is moved to the
right one, and its linked worktrees are repaired so they keep working.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

# Bounds on every subprocess that can touch the network. A connection reset
# mid-transfer leaves git blocked on a read with no timeout of its own; without
# these a single wedged repo hangs the whole run, and because launchd will not
# restart a still-running agent, every later scheduled run is silently skipped
# too. (This is exactly how wip-sync stopped snapshotting for 10 days.)
NET_TIMEOUT = 300
RUN_TIMEOUT = 1800

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

# Roots scanned by --wip-only for working-tree snapshots (no GitHub API). Private
# repos directly under GH_DIR push to a wip branch; everything else bundles.
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


def _config_path(name="orgs"):
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "sync-gh" / name


def _parse_org_list(text):
    """Parse org logins: comma/whitespace-separated, '#' comments ignored."""
    orgs = []
    for line in text.splitlines():
        orgs.extend(line.split("#", 1)[0].replace(",", " ").split())
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
        timeout=NET_TIMEOUT,
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
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=True, timeout=NET_TIMEOUT
    )
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
        check=False,
        capture_output=True,
        text=True,
        timeout=NET_TIMEOUT,
    )


def pull_repo(name, dest):
    """Pull latest changes for an existing repo."""
    result = subprocess.run(
        # --prune: a branch deleted on origin must not still count as "on origin".
        ["git", "-C", str(dest), "pull", "--ff-only", "--prune"],
        check=False,
        capture_output=True,
        text=True,
        timeout=NET_TIMEOUT,
    )
    if result.returncode != 0:
        print(f"  {name}: pull failed ({result.stderr.strip()})")
        return False
    if "Already up to date" not in result.stdout:
        print(f"  {name}: updated")
    return True


def in_progress_op(dest):
    """Return marker name if a git operation is in-flight, else None."""
    # A linked worktree's .git is a file; its markers live in its own git dir.
    found = _git(dest, ["rev-parse", "--absolute-git-dir"]).stdout.strip()
    if not found:
        return None
    git_dir = Path(found)
    for marker in IN_PROGRESS_MARKERS:
        if (git_dir / marker).exists():
            return marker
    return None


def _git(dest, args, env=None, check=False, timeout=NET_TIMEOUT, input=None):
    """Run `git -C dest ...`, capturing output. Thin wrapper for brevity.

    A timed-out call comes back as a normal failed CompletedProcess (rc 124) so
    callers that already branch on returncode report it and carry on to the next
    repo, rather than the run dying on one unreachable remote.
    """
    cmd = ["git", "-C", str(dest), *args]
    try:
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            check=check,
            timeout=timeout,
            input=input,
        )
    except subprocess.TimeoutExpired:
        if check:
            raise
        return subprocess.CompletedProcess(cmd, 124, "", f"timed out after {timeout}s")


def has_head(dest):
    """True if HEAD resolves to a commit (repo has at least one commit)."""
    return _git(dest, ["rev-parse", "--verify", "--quiet", "HEAD"]).returncode == 0


def wip_exclude_owners():
    """GitHub owners whose repos never get WIP snapshots (no wip/ branch, no
    bundle), read from $XDG_CONFIG_HOME/sync-gh/wip-exclude (same format as
    the orgs file). Lowercased; empty when the file is absent.
    """
    cfg = _config_path("wip-exclude")
    if not cfg.is_file():
        return set()
    return {o.lower() for o in _parse_org_list(cfg.read_text())}


def origin_slug(dest):
    """Lowercased 'owner/name' from origin's GitHub URL (https or ssh), else None."""
    res = _git(dest, ["remote", "get-url", "origin"])
    if res.returncode != 0:
        return None
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", res.stdout.strip())
    return f"{m.group(1)}/{m.group(2)}".lower() if m else None


def origin_owner(dest):
    """Lowercased GitHub owner from origin's URL (https or ssh), else None."""
    slug = origin_slug(dest)
    return slug.split("/")[0] if slug else None


# How long a repo's GitHub visibility answer is reused. A repo made public is
# caught within this window; until then its snapshot is still pushed.
VISIBILITY_TTL = 3600
PROBE_TIMEOUT = 15
# Set once a probe gets no answer: a network that swallows requests would
# otherwise cost PROBE_TIMEOUT per repo and stretch one sweep past 20 minutes.
_probe_failed = False


def _probe_visibility(slug):
    """'public' if github.com/<slug> loads without signing in, 'private' on 404,
    None when GitHub can't be asked (offline, rate-limited)."""
    req = urllib.request.Request(f"https://github.com/{slug}", method="HEAD")
    try:
        urllib.request.urlopen(req, timeout=PROBE_TIMEOUT).close()
        return "public"
    except urllib.error.HTTPError as exc:
        return "private" if exc.code == 404 else None
    except (urllib.error.URLError, OSError):
        return None


def github_visibility(dest):
    """'public', 'private' or None for origin's GitHub repo, cached per repo.

    Asks anonymously (no GitHub API, no token), so --wip-only stays cheap.
    An unknown answer is never cached.
    """
    slug = origin_slug(dest)
    if not slug:
        return None
    common = _git(dest, ["rev-parse", "--path-format=absolute", "--git-common-dir"])
    cache = Path(common.stdout.strip()) / "wip-visibility"
    try:
        if time.time() - cache.stat().st_mtime < VISIBILITY_TTL:
            return cache.read_text().strip()
    except OSError:
        pass
    global _probe_failed
    if _probe_failed:
        return None
    vis = _probe_visibility(slug)
    if vis:
        cache.write_text(vis + "\n")
    else:
        _probe_failed = True
    return vis


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
WIP_PRUNE_GRACE_DAYS = 10
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


# Never snapshotted, whatever the repo's .gitignore says. A tracked one keeps
# its committed version, so a snapshot never carries a newer secret.
SECRET_KEEP = (".env.example", ".env.sample", ".env.template")
# Agent tool installs: left out unless the repo already tracks the path.
NOISE_DIRS = (".agents/", ".claude/skills/", ".claude/worktrees/")
NOISE_FILES = ("skills-lock.json", ".claude/settings.local.json")
# An index that stages the deletion of this many files still on disk, and
# more than half of HEAD's files, is a broken index, not work in progress.
MASS_DELETE_MIN = 50


def is_secret_path(path):
    name = path.rsplit("/", 1)[-1].lower()
    if name in SECRET_KEEP:
        return False
    return name.startswith(".env") or name.endswith((".pem", ".key"))


def noise_prefix(path):
    """The agent-install entry `path` falls in (the folder's first-level
    entry, e.g. .claude/skills/<name>), or the noise file itself; else None."""
    p = "/" + path
    for d in NOISE_DIRS:
        at = p.find("/" + d)
        if at >= 0:
            start = at + len(d)
            end = path.find("/", start)
            return path if end < 0 else path[:end]
    return path if any(p.endswith("/" + f) for f in NOISE_FILES) else None


def _index_changes(dest, base, env=None):
    """(old mode, new mode, old sha, new sha, status, path) per index entry
    that differs from tree `base`."""
    out = _git(
        dest,
        ["diff-index", "--cached", "-z", "--no-renames", base],
        env=env,
        check=True,
    ).stdout
    fields = out.split("\0")
    changes = []
    for meta, path in zip(fields[::2], fields[1::2]):
        old_mode, new_mode, old_sha, new_sha, status = meta.lstrip(":").split()
        changes.append((old_mode, new_mode, old_sha, new_sha, status[0], path))
    return changes


def _worth_keeping(change, is_install=lambda path: False):
    old_mode, new_mode, old_sha, new_sha, status, path = change
    added = old_mode == "000000"
    if status == "U" or is_secret_path(path):
        return False
    if added and (new_mode == "160000" or is_install(path)):
        return False  # a nested clone (gitlink) or an agent tool install
    return not (status == "M" and old_sha == new_sha)  # mode-only change


def _install_check(dest, staged_paths):
    """is_install(path) for working-tree files: a new file in an agent-install
    folder, unless it is staged or HEAD already tracks that folder."""
    tracked = {}

    def is_install(path):
        prefix = noise_prefix(path)
        if prefix is None or path in staged_paths:
            return False
        if prefix not in tracked:
            out = _git(dest, ["ls-tree", "-r", "--name-only", "HEAD", "--", prefix])
            tracked[prefix] = bool(out.stdout.strip())
        return not tracked[prefix]

    return is_install


def _tree_with(dest, git_dir, head, changes):
    """Tree of HEAD (or empty) with `changes` applied, via a throwaway index."""
    fd, tmp_index = tempfile.mkstemp(prefix="wip-index-", dir=git_dir)
    os.close(fd)
    os.unlink(tmp_index)  # git refuses an empty index file, creates a missing one
    env = {**os.environ, "GIT_INDEX_FILE": tmp_index}
    # Mode 0 removes the entry; a deletion's sha is already the null sha.
    lines = [f"{int(mode, 8):o} {sha}\t{path}" for _, mode, _, sha, _, path in changes]
    try:
        if head:
            _git(dest, ["read-tree", "HEAD"], env=env, check=True)
        if lines:
            _git(
                dest,
                ["update-index", "-z", "--index-info"],
                env=env,
                check=True,
                input="\0".join(lines) + "\0",
            )
        return _git(dest, ["write-tree"], env=env, check=True).stdout.strip()
    finally:
        try:
            os.unlink(tmp_index)
        except FileNotFoundError:
            pass


def _only_nested_repo_errors(dest, stderr):
    """True when every `git add` error names a nested repo (one with no
    commit can't be added as a gitlink), so no real edit was dropped."""
    errors = [line for line in stderr.splitlines() if line.startswith("error:")]
    for line in errors:
        m = re.search(r"'(.+)/'", line)
        if not m or not (Path(dest) / m.group(1) / ".git").exists():
            return False
    return bool(errors)


def _working_tree_changes(dest, git_dir, base, head):
    """Changes from base to the working tree, untracked-but-not-ignored files
    included, read through a throwaway index so the real one is untouched."""
    fd, tmp_index = tempfile.mkstemp(prefix="wip-index-", dir=git_dir)
    os.close(fd)
    os.unlink(tmp_index)
    env = {**os.environ, "GIT_INDEX_FILE": tmp_index}
    try:
        if head:
            _git(dest, ["read-tree", "HEAD"], env=env, check=True)
        # --ignore-errors: a nested repo with no commit fails only itself (rc 1).
        added = _git(dest, ["add", "-A", "--ignore-errors"], env=env)
        if added.returncode and not _only_nested_repo_errors(dest, added.stderr):
            raise subprocess.CalledProcessError(
                added.returncode, added.args, added.stdout, added.stderr
            )
        return _index_changes(dest, base, env=env)
    finally:
        try:
            os.unlink(tmp_index)
        except FileNotFoundError:
            pass


def _mass_deletion(dest, changes, head):
    """(deleted, total) when the index stages the deletion of most of HEAD's
    files while they are still on disk, else None."""
    gone = [
        c for c in changes if c[1] == "000000" and os.path.lexists(Path(dest) / c[5])
    ]
    if not head or len(gone) < MASS_DELETE_MIN:
        return None
    total = _git(dest, ["ls-tree", "-r", "-z", "--name-only", "HEAD"]).stdout.count(
        "\0"
    )
    return (len(gone), total) if len(gone) * 2 > total else None


def snapshot_commit(dest, message):
    """Commit the working tree and the real index without disturbing the repo.

    The snapshot's tree is the working tree, untracked-but-not-ignored files
    included. Its first parent is HEAD; when the real index holds something the
    working tree doesn't (a staged version since edited, a staged file since
    deleted), a commit of the index is the second parent, the way `git stash`
    keeps it (in a repo with no commit yet, the index commit is the only
    parent). Secrets, agent tool installs, nested clones and mode-only changes
    are left out, and so is an index that stages the deletion of most files
    still on disk. Returns the commit SHA, or None when nothing is left to
    snapshot.
    """
    git_dir = _git(dest, ["rev-parse", "--absolute-git-dir"]).stdout.strip()
    if not git_dir:
        return None
    head = has_head(dest)
    head_tree = (
        _git(dest, ["rev-parse", "HEAD^{tree}"]).stdout.strip()
        if head
        else _tree_with(dest, git_dir, False, [])
    )
    staged = [c for c in _index_changes(dest, head_tree) if _worth_keeping(c)]
    is_install = _install_check(dest, {c[5] for c in staged})
    work = [
        c
        for c in _working_tree_changes(dest, git_dir, head_tree, head)
        if _worth_keeping(c, is_install)
    ]
    mass = _mass_deletion(dest, staged, head)
    if mass:
        print(
            f"  {Path(dest).name}: index stages deletion of {mass[0]} of {mass[1]}"
            " files still on disk; leaving the index out of the snapshot"
        )
        staged = []
    tree = _tree_with(dest, git_dir, head, work)
    index_tree = _tree_with(dest, git_dir, head, staged)
    if tree == head_tree and index_tree == head_tree:
        return None
    parents = ["-p", "HEAD"] if head else []
    if index_tree not in (head_tree, tree):
        subject = message.split("\n", 1)[0]
        index_commit = _git(
            dest,
            ["commit-tree", index_tree, *parents, "-m", f"index of {subject}"],
            check=True,
        ).stdout.strip()
        parents += ["-p", index_commit]
    return _git(
        dest, ["commit-tree", tree, *parents, "-m", message], check=True
    ).stdout.strip()


def snapshot_message(dest, hostname):
    """Subject kept as before (older readers match it); the body says where
    the snapshot came from."""
    dest = Path(dest)
    branch = _git(dest, ["symbolic-ref", "-q", "--short", "HEAD"]).stdout.strip()
    upstream = _git(
        dest, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]
    ).stdout.strip()
    try:
        checkout = str(dest.resolve().relative_to(GH_DIR.resolve()))
    except ValueError:
        checkout = str(dest)
    return (
        f"wip snapshot ({hostname})\n\n"
        f"branch: {branch or '(detached)'}\n"
        f"checkout: {checkout}\n"
        f"upstream: {upstream or 'none'}\n"
    )


def origin_has_real_branch(dest):
    """True when origin already holds a branch other than wip/*.

    GitHub makes the first branch pushed to an empty repo its default, so a
    wip push into a just-created repo would become the default branch (and
    PRs would target it). Checks the local remote-tracking refs first, so the
    usual case costs no network call; only a repo with nothing fetched yet
    asks origin directly.
    """
    local = _git(dest, ["for-each-ref", "--format=%(refname)", "refs/remotes/origin/"])
    refs = local.stdout.split()
    if any(
        not r.startswith("refs/remotes/origin/wip/") and r != "refs/remotes/origin/HEAD"
        for r in refs
    ):
        return True
    remote = _git(dest, ["ls-remote", "--heads", "origin"])
    if remote.returncode != 0:
        return False
    heads = [
        line.split("\t", 1)[1] for line in remote.stdout.splitlines() if "\t" in line
    ]
    return any(not h.startswith("refs/heads/wip/") for h in heads)


def _snapshot_trees(dest, ref):
    """Trees of the snapshot and of its parents other than HEAD (the index
    commit), for comparing two snapshots; [] when ref doesn't exist."""
    shown = _git(dest, ["show", "-s", "--format=%T %P", ref, "--"])
    if shown.returncode != 0:
        return []
    tree, *parents = shown.stdout.split()
    head = _git(dest, ["rev-parse", "-q", "--verify", "HEAD"]).stdout.strip()
    trees = [tree]
    for p in parents:
        if p != head:
            trees.append(_git(dest, ["rev-parse", f"{p}^{{tree}}"]).stdout.strip())
    return trees


def _origin_branches_with(dest, rev="HEAD"):
    """{name: sha} of origin's remote-tracking branches (not wip/*) that
    contain rev."""
    out = _git(
        dest,
        [
            "for-each-ref",
            "--contains",
            rev,
            "--format=%(refname:strip=3) %(objectname)",
            "refs/remotes/origin/",
        ],
    ).stdout
    found = dict(line.split(" ", 1) for line in out.splitlines() if " " in line)
    return {
        n: sha for n, sha in found.items() if n != "HEAD" and not n.startswith("wip/")
    }


def on_a_remote_branch(dest, rev="HEAD"):
    """True when one of origin's branches (as last fetched) contains rev."""
    return bool(_origin_branches_with(dest, rev))


def _confirmed_on_origin(dest):
    """Ask origin whether a branch that contained HEAD when last fetched is
    still there at that commit (or one past it). None when origin can't be
    asked."""
    cached = _origin_branches_with(dest)
    listing = _git(dest, ["ls-remote", "--heads", "origin"])
    if listing.returncode != 0:
        return None
    for line in listing.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        name = ref.removeprefix("refs/heads/")
        if name in cached and (
            sha == cached[name]
            or _git(dest, ["merge-base", "--is-ancestor", "HEAD", sha]).returncode == 0
        ):
            return True
    return False


def origin_default_branch(dest):
    """origin's default branch as a remote-tracking ref, or None."""
    for name in ("HEAD", "main", "master"):
        ref = f"refs/remotes/origin/{name}"
        if (
            _git(dest, ["rev-parse", "-q", "--verify", f"{ref}^{{commit}}"]).returncode
            == 0
        ):
            return ref
    return None


def head_on_origin(dest, hostname):
    """True when origin has HEAD, False when not, None when it can't be asked.

    Tracking refs go stale when a branch is deleted on origin (--wip-only never
    fetches), so outside origin's default branch origin itself is asked, once
    per HEAD commit (a stamp in the git dir remembers a yes).
    """
    if not on_a_remote_branch(dest):
        return False
    default = origin_default_branch(dest)
    if (
        default
        and _git(dest, ["merge-base", "--is-ancestor", "HEAD", default]).returncode == 0
    ):
        return True
    head = _git(dest, ["rev-parse", "HEAD"]).stdout.strip()
    git_dir = _git(dest, ["rev-parse", "--absolute-git-dir"]).stdout.strip()
    stamp = Path(git_dir) / f"wip-on-origin-{hostname}"
    try:
        if stamp.read_text().strip() == head:
            return True
    except OSError:
        pass
    confirmed = _confirmed_on_origin(dest)
    if confirmed:
        stamp.write_text(head + "\n")
    return confirmed


def push_wip(name, dest, hostname):
    """Push a snapshot of working state to wip/<hostname> on origin.

    Pushes only what origin lacks: local changes (snapshot_commit), or commits
    on no remote branch (wip points at HEAD). Otherwise deletes this checkout's
    own wip ref, which would only repeat what origin has. Force-push because
    wip refs always replace the previous snapshot. Linked worktrees push to a
    suffixed wip/<host>@<dirname> branch so siblings never clobber each other's
    snapshot. Skips detached HEAD and mid-rebase/merge/cherry-pick (state
    isn't a coherent snapshot to share).
    """
    op = in_progress_op(dest)
    if op:
        print(f"  {name}: skipping wip (in-progress {op})")
        return

    if _git(dest, ["symbolic-ref", "-q", "HEAD"]).returncode != 0:
        return  # detached HEAD

    if not origin_has_real_branch(dest):
        print(f"  {name}: skipping wip (origin has no branch yet; push one first)")
        return

    branch = f"wip/{hostname}{wip_ref_suffix(dest)}"
    cached_ref = f"refs/remotes/origin/{branch}"
    snap = snapshot_commit(dest, snapshot_message(dest, hostname))
    if snap:
        ref, suffix = snap, " (snapshot of working tree)"
    else:
        confirmed = head_on_origin(dest, hostname) if has_head(dest) else True
        if confirmed is None:
            return  # origin unreachable: decide next sweep
        if confirmed:
            if _git(dest, ["rev-parse", "--verify", "-q", cached_ref]).returncode:
                return  # nothing origin lacks, and no wip ref to delete
            done = _git(dest, ["push", "origin", "--delete", branch])
            if done.returncode == 0:
                print(f"  {name}: deleted {branch} (nothing origin lacks)")
            elif "remote ref does not exist" in done.stderr:
                _git(dest, ["update-ref", "-d", cached_ref])
            else:
                print(f"  {name}: could not delete {branch} ({done.stderr.strip()})")
            return
        ref, suffix = "HEAD", ""

    # Skip when origin's wip ref already holds these trees (the snapshot's and
    # its index parent's). Not SHAs: a snapshot commit's SHA changes every run
    # (fresh timestamp). The remote-tracking ref is updated by our own push; a
    # wip branch deleted on origin stays cached until a pruning fetch.
    if _snapshot_trees(dest, cached_ref) == _snapshot_trees(dest, ref):
        return  # nothing new

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

    snap = snapshot_commit(dest, snapshot_message(dest, hostname))
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

    Only repos directly under ~/Code/gh with an origin are pushed to a wip
    branch, and a GitHub origin must answer private: a public repo cloned into
    ~/Code/gh (or one whose visibility can't be checked) is bundled instead.
    Public-dir repos, ~/Projects repos, and remoteless repos are bundled.
    Archived repos and repos whose owner is in the wip-exclude file are skipped.
    """
    dest = Path(dest)
    if not (dest / ".git").exists():
        return "skip"
    parent = dest.parent
    if parent in (ARCHIVED_DIR, ARCHIVED_PUBLIC_DIR):
        return "skip"
    if origin_owner(dest) in wip_exclude_owners():
        return "skip"
    if parent == GH_DIR and has_origin(dest):
        if origin_slug(dest) and github_visibility(dest) != "private":
            return "bundle"
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
    """Hostname suitable for use as a git ref component.

    Prefers macOS's LocalHostName (stable, user-assigned) over
    socket.gethostname(), which follows DHCP/mDNS renames and can silently
    flip to "Mac" on some networks — forking a phantom host identity.
    """
    try:
        raw = subprocess.run(
            ["scutil", "--get", "LocalHostName"],
            check=False,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except OSError:
        raw = ""
    if not raw:
        raw = socket.gethostname().split(".")[0]
    safe = _BRANCH_SAFE.sub("-", raw).strip("-.")
    return safe or "unknown-host"


def repair_worktrees(name, dest):
    """Point linked worktrees back at a checkout that was just moved to dest.

    Each linked worktree's .git file names <old path>/.git/worktrees/<name>, so
    after a move every git command in it fails until `git worktree repair` runs
    from the new path. Run it straight after the move, before anything could
    prune the worktree records. A failure only warns: the run goes on.
    """
    done = _git(dest, ["worktree", "repair"], timeout=60)
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()
        reason = detail[-1] if detail else f"exit {done.returncode}"
        print(f"  {name}: warning: git worktree repair failed ({reason})")
        return
    for line in (done.stdout + done.stderr).splitlines():
        if line.startswith("repair: "):
            print(f"  {name}: repaired worktree {line.rsplit(': ', 1)[-1]}")


def _abort_run(signum, frame):
    """Hard cap on a single run, so the agent can never wedge indefinitely."""
    raise SystemExit(f"sync-gh: aborting run, exceeded {RUN_TIMEOUT}s budget")


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

        # Check all other dirs for a misplaced copy. Only a clone of THIS repo
        # counts: two owners can share a name (jasonluther/awth, kilotronic/awth),
        # and moving one into the other's folder nested it deeper every run.
        for d in ALL_REPO_DIRS:
            candidate = d / name
            if candidate.is_dir() and d != correct_dir:
                if origin_slug(candidate) != repo["nameWithOwner"].lower():
                    continue
                if correct_path.exists():
                    # shutil.move would nest candidate inside it; leave both.
                    print(
                        f"  {name}: misplaced copy at {candidate}, but "
                        f"{correct_path} already exists; resolve by hand"
                    )
                    break
                label_parts = []
                if repo["isArchived"]:
                    label_parts.append("archived")
                if not repo["isPrivate"]:
                    label_parts.append("public")
                label = ", ".join(label_parts) or "active/private"
                print(f"  Moving {name} to {label}...")
                shutil.move(str(candidate), str(correct_path))
                repair_worktrees(name, correct_path)
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
                # Same rule as --wip-only, so the two modes can't disagree.
                if args.push_wip and classify_repo(dest) == "push":
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
    signal.signal(signal.SIGALRM, _abort_run)
    signal.alarm(RUN_TIMEOUT)
    main()
