#!/usr/bin/env python3
"""Sync all GitHub repos for the authenticated user into the gh/ directory."""

import json
import shutil
import subprocess
from pathlib import Path

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


def repo_dir(repo):
    """Return the correct local directory for a repo based on archived/public status."""
    archived = repo["isArchived"]
    public = not repo["isPrivate"]
    if archived:
        return ARCHIVED_PUBLIC_DIR if public else ARCHIVED_DIR
    return PUBLIC_DIR if public else GH_DIR


# All directories where repos may live (for scanning local-only repos)
ALL_REPO_DIRS = [GH_DIR, PUBLIC_DIR, ARCHIVED_DIR, ARCHIVED_PUBLIC_DIR]


def main():
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
    for repo in repos:
        name = repo["name"]
        dest = repo_dir(repo) / name
        if dest.is_dir():
            if not repo["isArchived"]:
                to_pull.append((name, dest))
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

    archived_count = sum(1 for r in repos if r["isArchived"])
    public_count = sum(1 for r in repos if not r["isPrivate"])
    active_count = len(repos) - archived_count
    print(
        f"Done. {active_count} active, {archived_count} archived, {public_count} public."
    )


if __name__ == "__main__":
    main()
