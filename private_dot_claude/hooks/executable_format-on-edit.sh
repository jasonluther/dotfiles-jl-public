#!/usr/bin/env python3
"""Auto-format files after Claude edits them.

Reads PostToolUse JSON from stdin (matcher: Edit|Write|MultiEdit). Picks a
formatter based on file extension and runs it in-place. Silent on failure —
formatter errors should not interrupt Claude's workflow; the user can re-run
formatters manually.

Skips the file entirely when git conflict markers are present. Formatters
(especially prettier on Markdown) rewrite markers into ordinary syntax —
``>>>>>>>`` becomes nested blockquotes — which destroys the conflict and
leaves a file that still looks "clean" to a later marker grep. There is no
prettier flag that preserves them; refusing to format is the fix.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT = 15

# Git conflict markers at line start. Includes the diff3/zdiff3 ancestor
# marker (``|||||||``). ``=======`` alone is also a setext H1 underline in
# Markdown, so a bare seven-equals line is a known false-positive risk —
# acceptable here: worst case we skip formatting one heading, vs. corrupting
# a conflict. The distinctive ``<<<<<<<`` / ``>>>>>>>`` / ``|||||||`` markers
# never appear in legitimate content and are enough on their own.
CONFLICT_MARKER_RE = re.compile(
    r"^(<<<<<<<|>>>>>>>|\|\|\|\|\|\|\|)( |\t|$)|^=======\s*$",
    re.MULTILINE,
)


def which(*names: str) -> str | None:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def which_node_tool(path: str, name: str) -> str | None:
    """Resolve an npm-provided formatter against the PROJECT, not just PATH.

    npm tools are pinned per project (``package.json`` + ``node_modules``),
    and a global install drifts from that pin on its own schedule. For
    prettier that drift is destructive rather than cosmetic: a stale global
    rewrites Markdown the pinned version leaves alone, turning underscores
    inside identifiers into emphasis (``end_condition`` -> ``end*condition``)
    hundreds of lines away from the edit. Pre-commit runs the *pinned*
    binary, so it re-formats the damage as legitimate content and the commit
    passes — only reading the diff catches it.

    Resolution order, most trustworthy first:

    1. the nearest ``node_modules/.bin/<name>`` above the edited file — the
       exact version the project pins, which is what pre-commit will use;
    2. nothing, when a ``package.json`` above the file declares the tool but
       its ``node_modules`` is absent (a fresh worktree that has not run
       ``npm ci``). Formatting is skipped deliberately: leaving the file
       untouched for the pinned pre-commit run is strictly safer than
       letting a mismatched global rewrite it;
    3. PATH, for files outside any project that pins the tool.
    """
    resolved = Path(path).resolve()
    parents = [resolved.parent, *resolved.parent.parents]

    for parent in parents:
        candidate = parent / "node_modules" / ".bin" / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)

    for parent in parents:
        package_json = parent / "package.json"
        if not package_json.exists():
            continue
        try:
            manifest = json.loads(package_json.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        pinned = {
            *manifest.get("dependencies", {}),
            *manifest.get("devDependencies", {}),
        }
        # The nearest manifest decides: an outer one cannot un-pin it.
        return None if name in pinned else shutil.which(name)

    return shutil.which(name)


def has_conflict_markers(path: str) -> bool:
    """True when ``path`` contains git conflict markers.

    Mid-resolution edits are the hazard: a format-on-edit hook that rewrites
    the markers makes the file look resolved to any subsequent marker check
    while still being garbled. Refuse to format rather than risk that.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return CONFLICT_MARKER_RE.search(text) is not None


def run(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, capture_output=True, timeout=TIMEOUT, check=False)
    except (subprocess.SubprocessError, OSError):
        pass


def find_pyproject(path: Path) -> Path | None:
    for parent in [path.parent, *path.parent.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return None


def format_python(path: str) -> None:
    """ruff format + ruff check --fix. Fall back to `uv run ruff` for projects.

    ``--unfixable F401`` keeps the hook from deleting unused imports mid-edit
    (e.g. an import added a step before its first use). They are still reported
    and enforced by the full ``ruff check`` at commit time.
    """
    if ruff := which("ruff"):
        run([ruff, "format", path])
        run([ruff, "check", "--fix", "--unfixable", "F401", path])
        return
    project = find_pyproject(Path(path).resolve())
    if project and which("uv"):
        run(["uv", "run", "--project", str(project), "ruff", "format", path])
        run(
            [
                "uv",
                "run",
                "--project",
                str(project),
                "ruff",
                "check",
                "--fix",
                "--unfixable",
                "F401",
                path,
            ]
        )


def format_markdown(path: str) -> None:
    if prettier := which_node_tool(path, "prettier"):
        run([prettier, "--write", "--log-level", "silent", path])
    elif not which("prettier") and (mdformat := which("mdformat")):
        # Only when this machine has no prettier at all. A deliberate skip
        # (project pins prettier, node_modules absent) must NOT fall through
        # to a different formatter with a different house style.
        run([mdformat, path])
    if mdlint := which_node_tool(path, "markdownlint"):
        run([mdlint, "--fix", path])


def format_with_prettier(path: str) -> None:
    if prettier := which_node_tool(path, "prettier"):
        run([prettier, "--write", "--log-level", "silent", path])


def format_shell(path: str) -> None:
    if shfmt := which("shfmt"):
        # Match the flags used by .pre-commit-config.yaml's shfmt hook so
        # format-on-edit output doesn't bounce when pre-commit re-runs shfmt.
        run([shfmt, "-w", "-i", "2", "-ci", "-bn", path])


def format_toml(path: str) -> None:
    if taplo := which("taplo"):
        run([taplo, "format", path])


HANDLERS: dict[str, callable] = {
    ".py": format_python,
    ".md": format_markdown,
    ".markdown": format_markdown,
    ".mdx": format_markdown,
    ".json": format_with_prettier,
    ".jsonc": format_with_prettier,
    ".yaml": format_with_prettier,
    ".yml": format_with_prettier,
    ".sh": format_shell,
    ".bash": format_shell,
    ".zsh": format_shell,
    ".toml": format_toml,
}


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        return

    file_path = data.get("tool_input", {}).get("file_path", "")
    if not file_path or not os.path.exists(file_path):
        return

    if has_conflict_markers(file_path):
        return

    ext = os.path.splitext(file_path)[1].lower()
    if handler := HANDLERS.get(ext):
        handler(file_path)


if __name__ == "__main__":
    main()
