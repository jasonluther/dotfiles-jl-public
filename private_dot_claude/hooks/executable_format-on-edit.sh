#!/usr/bin/env python3
"""Auto-format files after Claude edits them.

Reads PostToolUse JSON from stdin (matcher: Edit|Write|MultiEdit). Picks a
formatter based on file extension and runs it in-place. Silent on failure —
formatter errors should not interrupt Claude's workflow; the user can re-run
formatters manually.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT = 15


def which(*names: str) -> str | None:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def run(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, capture_output=True, timeout=TIMEOUT)
    except (subprocess.SubprocessError, OSError):
        pass


def find_pyproject(path: Path) -> Path | None:
    for parent in [path.parent, *path.parent.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return None


def format_python(path: str) -> None:
    """ruff format + ruff check --fix. Fall back to `uv run ruff` for projects."""
    if ruff := which("ruff"):
        run([ruff, "format", path])
        run([ruff, "check", "--fix", path])
        return
    project = find_pyproject(Path(path).resolve())
    if project and which("uv"):
        run(["uv", "run", "--project", str(project), "ruff", "format", path])
        run(["uv", "run", "--project", str(project), "ruff", "check", "--fix", path])


def format_markdown(path: str) -> None:
    if prettier := which("prettier"):
        run([prettier, "--write", "--log-level", "silent", path])
    elif mdformat := which("mdformat"):
        run([mdformat, path])
    if mdlint := which("markdownlint"):
        run([mdlint, "--fix", path])


def format_with_prettier(path: str) -> None:
    if prettier := which("prettier"):
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

    ext = os.path.splitext(file_path)[1].lower()
    if handler := HANDLERS.get(ext):
        handler(file_path)


if __name__ == "__main__":
    main()
