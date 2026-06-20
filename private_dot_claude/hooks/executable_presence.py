#!/usr/bin/env python3
"""Agent presence board client — stdlib only (no third-party deps).

Subcommands (via sys.argv[1]):

  register    — read SessionStart/etc. hook JSON from stdin; POST this
                session to the presence server; print other active sessions
                in the same repo to stdout for context injection.

  deregister  — read SessionEnd hook JSON from stdin; DELETE this session
                from the presence server.

FAIL-SAFE CONTRACT
  • Every network call has a 3-second timeout.
  • All exceptions are swallowed — presence outages must never delay a session.
  • Every code path exits 0.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants / defaults
# ---------------------------------------------------------------------------

DEFAULT_PRESENCE_URL = "https://agent-presence-production.up.railway.app"
CONFIG_PATH = Path.home() / ".config" / "agent-presence" / "config"
NETWORK_TIMEOUT = 3  # seconds


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_config() -> dict[str, str]:
    """Parse ~/.config/agent-presence/config (shell KEY=value format).

    Returns a dict with whatever keys are present.  Missing file → empty dict.
    """
    cfg: dict[str, str] = {}
    try:
        text = CONFIG_PATH.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            cfg[key.strip()] = value.strip()
    except OSError:
        pass
    return cfg


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git(cwd: str, *args: str) -> str:
    """Run a git command and return stdout, or '' on any error."""
    try:
        result = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def get_repo(cwd: str) -> str:
    """Return the basename of the git toplevel, or '' if not a git repo."""
    toplevel = _git(cwd, "rev-parse", "--show-toplevel")
    return Path(toplevel).name if toplevel else ""


def get_branch(cwd: str) -> str:
    """Return the current branch name, or '' on failure."""
    return _git(cwd, "branch", "--show-current")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _request(
    method: str,
    url: str,
    token: str,
    body: dict | None = None,
) -> dict | None:
    """Send an HTTP request; return the parsed JSON response or None on error."""
    try:
        data = json.dumps(body).encode() if body is not None else None
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=NETWORK_TIMEOUT) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            return json.loads(text) if text.strip() else {}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Age formatting
# ---------------------------------------------------------------------------


def _age_str(registered_at: float) -> str:
    """Return a human-friendly age string like '5m ago' or '2h ago'."""
    delta = int(time.time() - registered_at)
    if delta < 60:
        return f"{delta}s ago"
    if delta < 3600:
        return f"{delta // 60}m ago"
    if delta < 86400:
        return f"{delta // 3600}h ago"
    return f"{delta // 86400}d ago"


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_register() -> None:
    """Read SessionStart hook JSON from stdin and upsert into presence server."""
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    session_id: str = data.get("session_id", "")
    cwd: str = data.get("cwd", "")
    if not session_id or not cwd:
        return

    cfg = load_config()
    token: str = cfg.get("PRESENCE_TOKEN", "")
    if not token:
        return  # No token → silent no-op

    url: str = cfg.get("PRESENCE_URL", DEFAULT_PRESENCE_URL).rstrip("/")

    repo = get_repo(cwd)
    if not repo:
        return  # Not a git repo → no-op

    branch = get_branch(cwd)

    # Upsert this session.
    _request(
        "POST",
        f"{url}/sessions",
        token,
        {
            "session_id": session_id,
            "machine": socket.gethostname(),
            "repo": repo,
            "branch": branch,
        },
    )

    # Fetch peer sessions in the same repo and print to stdout.
    resp = _request("GET", f"{url}/sessions?repo={repo}", token)
    if not resp:
        return

    sessions = resp.get("sessions", [])
    others = [s for s in sessions if s.get("session_id") != session_id]
    if not others:
        return

    lines = [f"Other active sessions in {repo}:"]
    for s in others:
        machine = s.get("machine", "?")
        branch_ = s.get("branch", "?")
        age = _age_str(s.get("registered_at", time.time()))
        lines.append(f"  • {machine}  {branch_}  ({age})")
    print("\n".join(lines))


def cmd_deregister() -> None:
    """Read SessionEnd hook JSON from stdin and DELETE from presence server."""
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    session_id: str = data.get("session_id", "")
    if not session_id:
        return

    cfg = load_config()
    token: str = cfg.get("PRESENCE_TOKEN", "")
    if not token:
        return  # No token → silent no-op

    url: str = cfg.get("PRESENCE_URL", DEFAULT_PRESENCE_URL).rstrip("/")
    _request("DELETE", f"{url}/sessions/{session_id}", token)


# ---------------------------------------------------------------------------
# Entry point — wrap everything so no uncaught exception can reach the caller
# ---------------------------------------------------------------------------


def main() -> None:
    try:
        subcommand = sys.argv[1] if len(sys.argv) > 1 else ""
        if subcommand == "register":
            cmd_register()
        elif subcommand == "deregister":
            cmd_deregister()
        # Unknown subcommand → silent no-op
    except Exception:
        pass


if __name__ == "__main__":
    main()
