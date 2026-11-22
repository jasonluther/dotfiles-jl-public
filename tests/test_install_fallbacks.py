"""The checksum-checked ruff and uv fallbacks in scripts/install-packages.sh report a failed install.

The functions are loaded from the script (from `fetch_checked` up to `fallback_yq`), with a fake `curl`
and `uname` on PATH, and run the way the script's callers run them: `fallback_x || failed+=(x)`.
"""

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts/install-packages.sh"


def _functions() -> str:
    text = SCRIPT.read_text()
    start = text.index("# fetch_checked <url>")
    end = text.index("fallback_yq() {")
    return text[start:end]


def _fake(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/bin/bash\n" + body + "\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _run(tmp_path: Path, tool: str, curl_body: str) -> subprocess.CompletedProcess:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    home = tmp_path / "home"
    (home / ".local/bin").mkdir(parents=True)
    _fake(bin_dir, "uname", "echo x86_64")
    _fake(bin_dir, "curl", curl_body)
    if not any(
        (Path(d) / "sha256sum").exists() for d in os.environ["PATH"].split(":")
    ):  # macOS: shasum stands in
        _fake(bin_dir, "sha256sum", 'exec shasum -a 256 "$@"')
    # Only the fakes and the basic tools: the real ruff or uv must not be found.
    path = f"{bin_dir}:/usr/bin:/bin"
    script = (
        "set -euo pipefail\n"
        + _functions()
        + f"\nfailed=()\nfallback_{tool} || failed+=({tool})\n"
        + 'echo "failed=${failed[*]:-}"\n'
    )
    return subprocess.run(
        ["bash", "-c", script],
        env={"PATH": path, "HOME": str(home)},
        capture_output=True,
        text=True,
        check=False,  # the script's own status is not what these tests read
    )


@pytest.mark.parametrize("tool", ["ruff", "uv"])
def test_a_failed_download_is_reported(tmp_path, tool):
    r = _run(tmp_path, tool, "exit 22")
    assert f"failed={tool}" in r.stdout, r.stdout + r.stderr
    assert "checksum mismatch" not in r.stderr


@pytest.mark.parametrize("tool", ["ruff", "uv"])
def test_a_checksum_mismatch_is_reported(tmp_path, tool):
    # curl -fsSL -o <file> <url>: write something that is not the release.
    r = _run(tmp_path, tool, 'printf "not the release" >"$3"')
    assert f"failed={tool}" in r.stdout, r.stdout + r.stderr
    assert re.search(r"checksum mismatch", r.stderr)
    assert not list((tmp_path / "home/.local/bin").iterdir())
