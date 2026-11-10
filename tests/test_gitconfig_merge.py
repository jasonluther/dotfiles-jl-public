"""Tests for `modify_dot_gitconfig.tmpl`, the merge of the managed gitconfig into
the machine's existing ~/.gitconfig.

The template is rendered by substituting its few chezmoi expressions, then run
with the existing file on stdin, as chezmoi runs a modify_ script.
"""

import os
import re
import subprocess
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "modify_dot_gitconfig.tmpl"

EXISTING = """\
[user]
\tname = Someone Else
\tsigningkey = ABC123
[safe]
\tdirectory = /srv/one
\tdirectory = /srv/Two
[Maintenance]
\trepo = /Users/me/Code/x
[core]
\teditor = vim
"""


def _render(tmp_path: Path) -> Path:
    text = TEMPLATE.read_text()
    text = text.replace("{{ .name | quote }}", '"Test Name"')
    text = text.replace("{{ .email | quote }}", '"test@example.com"')
    text = re.sub(r'\{\{ lookPath "gh" \}\}', "/usr/bin/gh", text)
    assert "{{" not in text, "an unhandled template expression is left"
    script = tmp_path / "modify_gitconfig.sh"
    script.write_text(text)
    return script


def _run(tmp_path: Path, stdin: str, extra_path: Path | None = None) -> str:
    env = dict(os.environ)
    if extra_path is not None:
        env["PATH"] = f"{extra_path}:{env['PATH']}"
    result = subprocess.run(
        ["bash", str(_render(tmp_path))],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def _get_all(tmp_path: Path, config: str, key: str) -> list[str]:
    path = tmp_path / "out.gitconfig"
    path.write_text(config)
    result = subprocess.run(
        ["git", "config", "-f", str(path), "--get-all", key],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.splitlines()


def test_managed_keys_win_and_unmanaged_keys_survive(tmp_path: Path) -> None:
    out = _run(tmp_path, EXISTING)
    assert _get_all(tmp_path, out, "user.name") == ["Test Name"]
    assert _get_all(tmp_path, out, "user.signingkey") == ["ABC123"]
    assert _get_all(tmp_path, out, "safe.directory") == ["/srv/one", "/srv/Two"]
    assert _get_all(tmp_path, out, "maintenance.repo") == ["/Users/me/Code/x"]
    assert _get_all(tmp_path, out, "core.editor") == ["vim"]


def test_an_empty_existing_file_gets_the_managed_config(tmp_path: Path) -> None:
    out = _run(tmp_path, "")
    assert _get_all(tmp_path, out, "user.email") == ["test@example.com"]
    assert _get_all(tmp_path, out, "core.editor") == []


def test_the_merge_does_not_depend_on_sort_order(tmp_path: Path) -> None:
    # macOS's UTF-8 collation can order lines differently from what `comm`
    # expects ("comm: file 1 is not in sorted order"); a reversing `sort`
    # stands in for it.
    shim = tmp_path / "bin"
    shim.mkdir()
    fake_sort = shim / "sort"
    fake_sort.write_text('#!/bin/sh\n/usr/bin/env -i PATH=/usr/bin:/bin sort -r "$@"\n')
    fake_sort.chmod(0o755)
    out = _run(tmp_path, EXISTING, extra_path=shim)
    assert _get_all(tmp_path, out, "user.signingkey") == ["ABC123"]
    assert _get_all(tmp_path, out, "safe.directory") == ["/srv/one", "/srv/Two"]
