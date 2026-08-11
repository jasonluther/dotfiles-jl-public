"""Unit tests for the format-on-edit PostToolUse hook.

Focuses on the conflict-marker guard: formatters (prettier on Markdown in
particular) rewrite ``>>>>>>>`` into nested blockquotes, so the hook must
refuse to run when markers are present rather than hoping a formatter flag
preserves them.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path

HOOK_SRC = (
    Path(__file__).resolve().parent.parent
    / "private_dot_claude/hooks/executable_format-on-edit.sh"
)


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


hook = _load("format_on_edit_hook", HOOK_SRC)


def test_has_conflict_markers_detects_standard_markers(tmp_path: Path):
    p = tmp_path / "conflict.md"
    p.write_text("preface\n<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> branch\n")
    assert hook.has_conflict_markers(str(p)) is True


def test_has_conflict_markers_detects_diff3_ancestor_marker(tmp_path: Path):
    p = tmp_path / "conflict.md"
    p.write_text(
        "<<<<<<< HEAD\n"
        "ours\n"
        "||||||| parent of abc\n"
        "base\n"
        "=======\n"
        "theirs\n"
        ">>>>>>> abc\n"
    )
    assert hook.has_conflict_markers(str(p)) is True


def test_has_conflict_markers_detects_marker_alone_on_line(tmp_path: Path):
    # Some tools emit the marker with no trailing label.
    p = tmp_path / "conflict.py"
    p.write_text("x = 1\n<<<<<<<\ny = 2\n>>>>>>>\n")
    assert hook.has_conflict_markers(str(p)) is True


def test_has_conflict_markers_clean_file_is_false(tmp_path: Path):
    p = tmp_path / "clean.md"
    p.write_text("# Title\n\nA paragraph with > blockquote and === text.\n")
    assert hook.has_conflict_markers(str(p)) is False


def test_has_conflict_markers_ignores_inline_lookalikes(tmp_path: Path):
    # Markers only count at column 0. An indented or mid-line lookalike is
    # content, not a conflict.
    p = tmp_path / "lookalike.md"
    p.write_text(
        "Talk about <<<<<<< in a sentence.\n"
        "    >>>>>>> indented\n"
        "code fence example: |||||||\n"
    )
    assert hook.has_conflict_markers(str(p)) is False


def test_has_conflict_markers_missing_file_is_false(tmp_path: Path):
    assert hook.has_conflict_markers(str(tmp_path / "nope.md")) is False


def test_main_skips_formatter_when_markers_present(tmp_path: Path, monkeypatch):
    p = tmp_path / "conflict.md"
    p.write_text("<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> branch\n")
    calls: list[str] = []

    def boom(_path: str) -> None:
        calls.append("ran")
        raise AssertionError("formatter must not run on a conflicted file")

    monkeypatch.setitem(hook.HANDLERS, ".md", boom)

    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(p)}})
    monkeypatch.setattr(hook.sys, "stdin", __import__("io").StringIO(payload))
    hook.main()
    assert calls == []


def test_main_runs_formatter_on_clean_file(tmp_path: Path, monkeypatch):
    p = tmp_path / "clean.md"
    p.write_text("# hi\n")
    calls: list[str] = []

    def record(path: str) -> None:
        calls.append(path)

    monkeypatch.setitem(hook.HANDLERS, ".md", record)

    payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": str(p)}})
    monkeypatch.setattr(hook.sys, "stdin", __import__("io").StringIO(payload))
    hook.main()
    assert calls == [str(p)]


def test_main_ignores_non_edit_tools(tmp_path: Path, monkeypatch):
    p = tmp_path / "clean.md"
    p.write_text("# hi\n")
    calls: list[str] = []
    monkeypatch.setitem(hook.HANDLERS, ".md", lambda path: calls.append(path))

    payload = json.dumps({"tool_name": "Bash", "tool_input": {"file_path": str(p)}})
    monkeypatch.setattr(hook.sys, "stdin", __import__("io").StringIO(payload))
    hook.main()
    assert calls == []


def test_main_ignores_missing_file(tmp_path: Path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setitem(hook.HANDLERS, ".md", lambda path: calls.append(path))

    missing = tmp_path / "gone.md"
    payload = json.dumps(
        {"tool_name": "Edit", "tool_input": {"file_path": str(missing)}}
    )
    monkeypatch.setattr(hook.sys, "stdin", __import__("io").StringIO(payload))
    hook.main()
    assert calls == []
    # And the path really is missing — don't create it as a side effect.
    assert not missing.exists()


def test_shebang_file_is_importable():
    # The hook is named *.sh for chezmoi's executable_ prefix convention but
    # is a Python script; keep that invariant underfoot so a future rename
    # to a real shell script fails the suite instead of silently breaking
    # the PostToolUse hook.
    assert HOOK_SRC.read_text().startswith("#!/usr/bin/env python3")
    assert os.access(HOOK_SRC, os.X_OK)
