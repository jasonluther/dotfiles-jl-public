"""Unit tests for the `fix-cmd` clipboard/command cleanup helper."""

import importlib.machinery
import importlib.util
from pathlib import Path

FIX_CMD_SRC = (
    Path(__file__).resolve().parent.parent / "dot_local/bin/executable_fix-cmd"
)


def _load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    m = importlib.util.module_from_spec(spec)
    loader.exec_module(m)
    return m


fix_cmd = _load("fix_cmd_tool", FIX_CMD_SRC)


def test_clean_joins_wrapped_indented_lines():
    raw = "  ! gh auth login --hostname github.com\n    --git-protocol https --web\n"
    assert (
        fix_cmd.clean(raw)
        == "gh auth login --hostname github.com --git-protocol https --web"
    )


def test_clean_strips_bang_without_space():
    assert fix_cmd.clean("!ls -la") == "ls -la"


def test_clean_keeps_bang_not_at_start():
    assert fix_cmd.clean("echo hi !\n") == "echo hi !"


def test_clean_honours_backslash_continuations():
    raw = "docker run \\\n  --rm \\\n  alpine echo ok\n"
    assert fix_cmd.clean(raw) == "docker run --rm alpine echo ok"


def test_clean_drops_blank_lines():
    assert fix_cmd.clean("\n\n  ls\n\n") == "ls"


def test_clean_single_line_unchanged():
    assert fix_cmd.clean("git status") == "git status"


def test_clean_empty_and_bang_only():
    assert fix_cmd.clean("") == ""
    assert fix_cmd.clean("  !  \n") == ""
