"""Unit tests for the `fix-cmd` clipboard/command cleanup helper."""

import importlib.machinery
import importlib.util
import io
from pathlib import Path

import pytest

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


def test_clean_strips_the_bang_from_every_command():
    # Claude Code suggests several `! cmd` lines, each wrapped by the terminal.
    raw = (
        "  ! cd ~/Code/gh/auditor && env -u CLAUDECODE -u AI_AGENT -u GH_TOKEN -u\n"
        "  GITHUB_TOKEN python3 scripts/github_settings.py\n"
        "  !cd ~/Code/gh/auditor && env -u CLAUDECODE -u AI_AGENT -u GH_TOKEN -u\n"
        "  GITHUB_TOKEN python3 scripts/github_settings.py --apply\n"
    )
    cmd = "cd ~/Code/gh/auditor && env -u CLAUDECODE -u AI_AGENT -u GH_TOKEN -u GITHUB_TOKEN python3 scripts/github_settings.py"
    assert fix_cmd.clean(raw, width=74) == f"{cmd}\n{cmd} --apply"


def test_clean_starts_a_new_command_at_each_bang_when_the_copy_began_at_it():
    # Selecting from the first `!` drops its indent, so every later line looks
    # deeper; a `!` line still starts its own command.
    raw = (
        "! cd ~/Code/gh/auditor && env -u CLAUDECODE -u AI_AGENT -u GH_TOKEN -u\n"
        "  GITHUB_TOKEN python3 scripts/github_settings.py\n"
        "  ! cd ~/Code/gh/auditor && env -u CLAUDECODE -u AI_AGENT -u GH_TOKEN -u\n"
        "  GITHUB_TOKEN python3 scripts/github_settings.py --apply\n"
    )
    cmd = "cd ~/Code/gh/auditor && env -u CLAUDECODE -u AI_AGENT -u GH_TOKEN -u GITHUB_TOKEN python3 scripts/github_settings.py"
    assert fix_cmd.clean(raw, width=74) == f"{cmd}\n{cmd} --apply"


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


def _main(monkeypatch, argv, key):
    """Run main() on piped input with one fake keypress; return the exec'd argv, or None if aborted."""
    ran = []

    def read_key():
        if key is None:
            raise AssertionError("asked for a key")
        return key

    monkeypatch.setenv("SHELL", "/bin/sh")
    monkeypatch.setattr(fix_cmd.sys, "argv", ["fix-cmd", *argv])
    monkeypatch.setattr(fix_cmd.sys, "stdin", io.StringIO("! rm -rf build\n"))
    monkeypatch.setattr(fix_cmd, "read_key", read_key)
    monkeypatch.setattr(fix_cmd.os, "execv", lambda shell, args: ran.append(args))
    try:
        fix_cmd.main()
    except SystemExit as e:
        assert "aborted" in str(e.code)
        assert ran == []
        return None
    return ran[0]


def test_main_runs_the_cleaned_command_only_after_y(monkeypatch):
    assert _main(monkeypatch, [], "y") == ["/bin/sh", "-c", "rm -rf build"]


@pytest.mark.parametrize("key", ["n", "Y", "\n", " ", "\x1b"])
def test_main_aborts_on_any_other_key(monkeypatch, key):
    assert _main(monkeypatch, [], key) is None


def test_force_runs_without_asking(monkeypatch):
    assert _main(monkeypatch, ["-f"], None) == ["/bin/sh", "-c", "rm -rf build"]


def test_clean_keeps_separate_commands_on_separate_lines():
    # A pasted multi-line snippet was joined into one broken command.
    raw = (
        "R=owner/repo\n"
        "gh repo unarchive $R --yes\n"
        'for b in a b; do echo "$b"; done\n'
        "gh repo archive $R --yes\n"
    )
    assert fix_cmd.clean(raw, width=80) == raw.strip()


def test_clean_rejoins_a_terminal_word_wrap():
    # The terminal wrapped because "--yes" didn't fit in the 30 columns left.
    raw = "gh repo unarchive owner/repo\n--yes\necho done\n"
    assert (
        fix_cmd.clean(raw, width=30) == "gh repo unarchive owner/repo --yes\necho done"
    )


def test_clean_rejoins_a_wrap_back_to_the_block_indent():
    raw = "  gh api -X DELETE repos/o/r/git/refs/heads/x\n  --silent\n  echo ok\n"
    assert fix_cmd.clean(raw, width=48) == (
        "gh api -X DELETE repos/o/r/git/refs/heads/x --silent\necho ok"
    )


def test_clean_keeps_the_line_after_an_unwrapped_long_line():
    # A copied code block keeps a long line whole; wider than the terminal means
    # it was not wrapped there, so the next line is its own command.
    long = "for b in " + "x" * 120 + "; do echo $b; done"
    assert fix_cmd.clean(f"{long}\ngh repo archive o/r --yes\n", width=80) == (
        f"{long}\ngh repo archive o/r --yes"
    )


def test_clean_keeps_lines_when_the_copy_started_inside_the_indent():
    # The selection began one column into a 2-space block, so only the first
    # line lost a space; the others are not deeper continuations of it.
    raw = (
        " gh secret delete KEY -R o/site\n"
        "  gh secret list -R o/site\n"
        "  gh repo deploy-key list -R o/lamp\n"
    )
    assert fix_cmd.clean(raw, width=120) == (
        "gh secret delete KEY -R o/site\n"
        "gh secret list -R o/site\n"
        "gh repo deploy-key list -R o/lamp"
    )
