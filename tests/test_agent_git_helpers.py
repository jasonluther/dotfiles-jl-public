"""In an agent shell (CLAUDECODE set), git never reaches the owner's gh login.

gh.sh resets the github.com helper to `keys git-credential`; gist.github.com has no App
(an App token cannot use gists), so its helper is cleared and git fails closed there.
"""

import subprocess
from pathlib import Path

GH_SH = Path(__file__).resolve().parent.parent / "dot_config" / "shell" / "gh.sh"


def _helpers(tmp_path: Path, url: str) -> list[str]:
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        '[credential "https://github.com"]\n\thelper =\n\thelper = !/opt/homebrew/bin/gh auth git-credential\n'
        '[credential "https://gist.github.com"]\n\thelper =\n\thelper = !/opt/homebrew/bin/gh auth git-credential\n'
    )
    script = f'. "{GH_SH}"; git config --get-all credential.{url}.helper'
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "CLAUDECODE": "1",
        "GIT_CONFIG_GLOBAL": str(gitconfig),
    }
    out = subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True, check=True
    ).stdout
    values = out.split("\n")[:-1]
    # An empty value resets the list: only what follows the last one is used.
    return values[len(values) - values[::-1].index("") :] if "" in values else values


def test_github_asks_keys(tmp_path: Path) -> None:
    assert _helpers(tmp_path, "https://github.com") == ["!keys git-credential"]


def test_gist_has_no_helper(tmp_path: Path) -> None:
    assert _helpers(tmp_path, "https://gist.github.com") == []
