#!/usr/bin/env python3
"""Sync all GitHub repos for the authenticated user into the gh/ directory.

By default, also pushes a per-host snapshot of each PRIVATE repo's working
state to a `wip/<hostname>` branch on origin, so work-in-progress flows
between machines without relying on Syncthing replicating .git/. Pass
--no-push-wip to disable. Public repos are never auto-pushed; archived,
detached-HEAD, and mid-rebase/merge/cherry-pick repos are skipped.
"""

import argparse
import json
import re
import shutil
import socket
import subprocess
from pathlib import Path

# Branch-name-safe sanitizer for hostnames (covers macOS names with
# apostrophes/spaces like "Jason's MBP").
_BRANCH_SAFE = re.compile(r"[^A-Za-z0-9_.-]+")

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


def get_repos():
    """Get all repos for the authenticated user via gh CLI."""
    result = subprocess.run(
        [
            "gh",
            "repo",
            "list",
            "--limit",
            "500",
            "--json",
            "name,url,isArchived,isPrivate",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


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


def push_wip(name, dest, hostname):
    """Push a snapshot of working state to wip/<hostname> on origin.

    Uses `git stash create` to capture tracked changes + index without
    modifying the working tree. Untracked files are intentionally not
    included — they're more likely to be local junk than work to share.
    Force-push because wip refs always replace the previous snapshot.
    Skips: detached HEAD, mid-rebase/merge/cherry-pick (state isn't a
    coherent snapshot to share).
    """
    op = in_progress_op(dest)
    if op:
        print(f"  {name}: skipping wip (in-progress {op})")
        return

    head = subprocess.run(
        ["git", "-C", str(dest), "symbolic-ref", "-q", "HEAD"],
        capture_output=True,
        text=True,
    )
    if head.returncode != 0:
        return  # detached HEAD

    dirty = subprocess.run(
        ["git", "-C", str(dest), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    if dirty:
        snap = subprocess.run(
            ["git", "-C", str(dest), "stash", "create"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        ref = snap or "HEAD"
    else:
        ref = "HEAD"

    branch = f"wip/{hostname}"
    push = subprocess.run(
        [
            "git",
            "-C",
            str(dest),
            "push",
            "--force",
            "origin",
            f"{ref}:refs/heads/{branch}",
        ],
        capture_output=True,
        text=True,
    )
    if push.returncode != 0:
        print(f"  {name}: wip push failed ({push.stderr.strip()})")
    else:
        suffix = " (snapshot of dirty tree)" if dirty else ""
        print(f"  {name}: pushed → {branch}{suffix}")


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
    return ap.parse_args()


def sanitized_hostname():
    """Hostname suitable for use as a git ref component."""
    raw = socket.gethostname().split(".")[0]
    safe = _BRANCH_SAFE.sub("-", raw).strip("-.")
    return safe or "unknown-host"


def main():
    args = parse_args()
    hostname = sanitized_hostname()

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
