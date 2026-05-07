#!/usr/bin/env python3
"""Recover from Syncthing-induced .git/ sync-conflict files.

Walks every git repo under --root (default ~/Code), classifies each
*.sync-conflict-* file inside .git/, and applies a safe resolution:

  objects/XX/<sha>.sync-conflict-...:
    - canonical absent          -> rename to canonical (recovers stranded object)
    - canonical present, equal  -> delete conflict
    - canonical present, differs -> SURFACE (shouldn't happen for content-
                                    addressed loose objects; investigate)

  index, FETCH_HEAD, ORIG_HEAD, logs/**:
    - delete (regenerable / stale)

  refs/**, HEAD, packed-refs, config:
    - leave in place and SURFACE — needs human judgment about which side
      wins. The chosen side may differ per repo.

Always backs up every conflict file to /tmp/git-sync-conflicts-recovery-<stamp>/
before mutating anything. Then runs `git fsck` per touched repo and reports
dangling/unreachable objects.

Idempotent. Safe to run periodically (e.g. as a launchd timer) to repair
ongoing low-grade Syncthing damage.
"""

from __future__ import annotations

import argparse
import filecmp
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CONFLICT_RE = re.compile(r"\.sync-conflict-\d{8}-\d{6}-[A-Z0-9]+$")


def canonical_of(path: Path) -> Path:
    """Strip the .sync-conflict-YYYYMMDD-HHMMSS-XXXXX suffix."""
    return path.parent / CONFLICT_RE.sub("", path.name)


def classify(rel_in_git: Path) -> str:
    """Return one of: object, index, ephemeral_ref, log, ref, config, other."""
    parts = rel_in_git.parts
    if parts[0] == "objects" and len(parts) >= 3 and parts[1] != "pack":
        return "object"
    if rel_in_git.name.startswith("index"):
        return "index"
    if rel_in_git.name.startswith(("FETCH_HEAD", "ORIG_HEAD", "MERGE_HEAD")):
        return "ephemeral_ref"
    if parts[0] == "logs":
        return "log"
    if parts[0] == "refs" or rel_in_git.name.startswith(("HEAD", "packed-refs")):
        return "ref"
    if rel_in_git.name.startswith("config"):
        return "config"
    return "other"


SKIP_DIR_NAMES = {".stversions", "node_modules", ".venv"}


def find_repos(root: Path) -> list[Path]:
    """Return repo roots (dirs containing a real .git/ subdir) under root.

    Skips Syncthing's .stversions archive (stale snapshots, not live repos)
    and common dependency dirs that may shadow .git directories.
    """
    repos: set[Path] = set()
    for p in root.rglob(".git"):
        if not p.is_dir():
            continue
        if any(part in SKIP_DIR_NAMES for part in p.parts):
            continue
        repos.add(p.parent)
    return sorted(repos)


def find_conflicts(repo: Path) -> list[Path]:
    return sorted(p for p in (repo / ".git").rglob("*") if CONFLICT_RE.search(p.name))


def back_up(conflict: Path, repo: Path, backup_root: Path) -> None:
    rel = conflict.relative_to(repo)
    dest = backup_root / repo.name / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(conflict, dest)


def resolve_one(conflict: Path, repo: Path, dry_run: bool) -> tuple[str, str]:
    """Apply the safe resolution. Return (action, detail)."""
    rel_in_git = conflict.relative_to(repo / ".git")
    kind = classify(rel_in_git)
    canon = canonical_of(conflict)

    if kind == "object":
        if not canon.exists():
            if not dry_run:
                conflict.rename(canon)
            return "recover", f"renamed → {canon.relative_to(repo)}"
        if filecmp.cmp(conflict, canon, shallow=False):
            if not dry_run:
                conflict.unlink()
            return "delete", "duplicate of canonical"
        return "surface", "object differs from canonical (unexpected!)"

    if kind in ("index", "ephemeral_ref", "log"):
        if not dry_run:
            conflict.unlink()
        return "delete", f"{kind}, regenerable"

    # ref / config / other → surface, never auto-mutate
    if canon.exists():
        try:
            same = filecmp.cmp(conflict, canon, shallow=False)
        except OSError:
            same = False
        if same:
            if not dry_run:
                conflict.unlink()
            return "delete", f"{kind} identical to canonical"
    return "surface", f"{kind}: needs manual review"


def fsck(repo: Path) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), "fsck", "--no-progress"],
        capture_output=True,
        text=True,
    )
    return (r.stdout + r.stderr).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--root", type=Path, default=Path.home() / "Code")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without mutating anything (still writes backups).",
    )
    ap.add_argument(
        "--no-fsck", action="store_true", help="Skip post-recovery git fsck."
    )
    args = ap.parse_args()

    if not args.root.is_dir():
        print(f"error: {args.root} not a directory", file=sys.stderr)
        return 2

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = Path(f"/tmp/git-sync-conflicts-recovery-{stamp}")

    print(f"Scanning {args.root} for git repos with sync-conflict files...")
    affected: list[tuple[Path, list[Path]]] = []
    for repo in find_repos(args.root):
        confs = find_conflicts(repo)
        if confs:
            affected.append((repo, confs))

    if not affected:
        print("No sync-conflict files found in any repo.")
        return 0

    total = sum(len(c) for _, c in affected)
    print(f"Found {total} conflict file(s) across {len(affected)} repo(s).")
    print(f"Backup dir: {backup_root}{' (dry-run)' if args.dry_run else ''}\n")

    surfaced: list[tuple[Path, Path, str]] = []
    counts = {"recover": 0, "delete": 0, "surface": 0}

    for repo, confs in affected:
        print(f"== {repo} ({len(confs)} conflicts)")
        for c in confs:
            back_up(c, repo, backup_root)
            action, detail = resolve_one(c, repo, args.dry_run)
            counts[action] += 1
            rel = c.relative_to(repo)
            tag = {"recover": "RECOVER", "delete": "delete ", "surface": "REVIEW "}[
                action
            ]
            print(f"   {tag}  {rel}  — {detail}")
            if action == "surface":
                surfaced.append((repo, rel, detail))
        print()

    print(
        f"Summary: {counts['recover']} recovered, "
        f"{counts['delete']} deleted, {counts['surface']} need review."
    )

    if surfaced:
        print("\nFiles needing manual review:")
        for repo, rel, detail in surfaced:
            print(f"  {repo}/{rel}  ({detail})")
            print(
                f"    -> compare: diff <(cat {rel}) <(cat {rel.parent}/{canonical_of(repo / rel).name})"
            )

    if not args.no_fsck and not args.dry_run:
        print("\nRunning git fsck on touched repos...")
        for repo, _ in affected:
            out = fsck(repo)
            if out:
                print(f"\n-- {repo}\n{out}")
            else:
                print(f"  {repo}: clean")

    return 0


if __name__ == "__main__":
    sys.exit(main())
