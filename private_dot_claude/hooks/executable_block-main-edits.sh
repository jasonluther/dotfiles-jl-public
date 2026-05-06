#!/usr/bin/env python3
"""Block Claude from editing files in the main worktree when it's on main/master.

Reads tool input from stdin; exits 2 to block Edit/Write calls targeting
files inside the main worktree. Best-effort — won't catch every Bash
side-effect, but prevents the most common accidents.
"""

import json
import os
import subprocess
import sys

TRUNK_BRANCHES = {"main", "master"}


def run(cmd: list[str]) -> str:
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout.strip()


def realpath(path: str) -> str:
    return os.path.realpath(path) if path else ""


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    # Only interested in Edit and Write.
    tool_name = data.get("tool_name", "")
    if tool_name not in ("Edit", "Write"):
        return

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if not project_dir:
        return

    # Find the main worktree (first entry in `git worktree list`).
    worktree_output = run(["git", "-C", project_dir, "worktree", "list", "--porcelain"])
    if not worktree_output:
        return

    main_worktree = ""
    for line in worktree_output.splitlines():
        if line.startswith("worktree "):
            main_worktree = line.removeprefix("worktree ")
            break

    if not main_worktree:
        return

    main_real = realpath(main_worktree)

    # Extract the file_path from tool input.
    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path:
        return
    file_real = realpath(file_path)

    # Check if the main worktree is on a trunk branch.
    branch = run(["git", "-C", main_worktree, "rev-parse", "--abbrev-ref", "HEAD"])
    if branch not in TRUNK_BRANCHES:
        return

    # Allow edits inside nested worktrees.
    for line in worktree_output.splitlines():
        if not line.startswith("worktree "):
            continue
        wt = line.removeprefix("worktree ")
        wt_real = realpath(wt)
        if wt_real == main_real:
            continue
        if file_real.startswith(wt_real + "/"):
            return

    # Allow edits to gitignored files (local-only, no risk of committing).
    rel = os.path.relpath(file_real, main_real)
    result = subprocess.run(
        ["git", "-C", main_worktree, "check-ignore", "-q", rel],
        capture_output=True,
    )
    if result.returncode == 0:
        return

    # Block if the target file lives inside the main worktree.
    if file_real.startswith(main_real + "/"):
        project = os.path.basename(main_real)
        worktree_home = os.environ.get("WORKTREE_HOME", "$HOME/Code/worktrees")
        worktree_path = f"{worktree_home}/{project}/<branch>"
        print(
            f"Blocked: {file_path} is inside the main worktree ({main_worktree}) "
            f"which is on {branch}. Create a worktree first: "
            f"git worktree add {worktree_path} -b <branch>",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
