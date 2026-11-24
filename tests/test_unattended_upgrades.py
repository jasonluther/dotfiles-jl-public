"""The unattended-upgrades config never reboots a host by itself (overnight agent sessions die)."""

import re
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "linux" / "unattended-upgrades.sh"
)


def test_automatic_reboot_is_off():
    text = SCRIPT.read_text()
    settings = re.findall(
        r'^Unattended-Upgrade::Automatic-Reboot(?:-\w+)?\s+"([^"]*)";',
        text,
        re.MULTILINE,
    )
    assert settings == ["false"], settings
