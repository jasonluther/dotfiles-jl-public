"""`private_dot_claude/settings.json.tmpl` must render the way Claude Code saves the file.

Claude Code rewrites ~/.claude/settings.json as JSON.stringify(value, null, 2), keeping the key order it
read. A template that renders any other layout (an object on one line, a private entry with its keys
sorted by name) differs from the saved file on every `chezmoi diff` although nothing changed. The order of
the template's own top-level keys follows what Claude last saved and no test can know that.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

TEMPLATE = (
    Path(__file__).resolve().parent.parent / "private_dot_claude/settings.json.tmpl"
)

# In the order Claude writes a marketplace it added: source before autoUpdate, source.source first.
PRIVATE_PLUGINS = """{
  "extraKnownMarketplaces": {
    "zz-private": {
      "source": { "source": "github", "repo": "example/zz-private" },
      "autoUpdate": true
    }
  },
  "enabledPlugins": { "zz@zz-private": true }
}
"""
AUTOMODE = '{\n  "allow": [\n    "$defaults",\n    "Run `x` on <owner>/<repo> & more"\n  ]\n}\n'

# The template names the machine's auto-mode file; read the name from it.
AUTOMODE_FILE = re.search(
    r'"(\.claude/automode-[^"]+\.json)"', TEMPLATE.read_text()
).group(1)


def _render(home: Path) -> str:
    chezmoi = shutil.which("chezmoi")
    if chezmoi is None:
        if os.environ.get("GITHUB_ACTIONS"):
            pytest.fail("chezmoi is not installed in CI")
        pytest.skip("chezmoi is not installed")
    return subprocess.run(
        [chezmoi, "execute-template"],
        stdin=TEMPLATE.open(),
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")},
    ).stdout


def _as_claude_saves(text: str) -> str:
    return json.dumps(json.loads(text), indent=2, ensure_ascii=False) + "\n"


def test_renders_as_claude_saves_it_without_private_files(tmp_path: Path) -> None:
    out = _render(tmp_path)
    assert out == _as_claude_saves(out)


def test_renders_as_claude_saves_it_with_private_files(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude/plugins-private.json").write_text(PRIVATE_PLUGINS)
    (tmp_path / ".claude/permissions-allow-private.json").write_text(
        '["Skill(zz:pr)"]\n'
    )
    (tmp_path / AUTOMODE_FILE).write_text(AUTOMODE)
    out = _render(tmp_path)
    assert out == _as_claude_saves(out)
    settings = json.loads(out)
    private = settings["extraKnownMarketplaces"]["zz-private"]
    assert list(private) == ["source", "autoUpdate"]
    assert list(private["source"]) == ["source", "repo"]
    assert settings["enabledPlugins"]["zz@zz-private"] is True
    assert "Skill(zz:pr)" in settings["permissions"]["allow"]
    assert settings["autoMode"] == json.loads(AUTOMODE)
