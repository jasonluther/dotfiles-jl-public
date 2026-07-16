# Unattended upgrades for Linux hosts — design

2026-07-16. Approved in session.

## Goal

Linux (Debian-family) hosts managed by this repo should install **all** package
updates nightly via the native package manager, and reboot automatically when
an update requires it.

## Decisions

- **Scope: all configured origins**, not just security. Implemented with
  `Unattended-Upgrade::Origins-Pattern { "origin=*"; }` so distro `-updates`
  and every third-party repo (NodeSource, 1Password, Tailscale, future
  additions) are covered with zero list maintenance. The packaged
  `50unattended-upgrades` (security origins) still applies; the pattern is a
  superset.
- **Auto-reboot: on**, at 04:00 local (`Automatic-Reboot "true"`,
  `Automatic-Reboot-Time "04:00"`). Known trade-off: a host can reboot
  overnight with active sessions/tmux (`Automatic-Reboot-WithUsers` defaults
  true). Accepted.
- Also enable `Remove-Unused-Dependencies` and `Remove-Unused-Kernel-Packages`
  so /boot doesn't fill up over time.

## Components

1. `scripts/linux/unattended-upgrades.sh` — idempotent module in the existing
   `setup.sh` module style (`harden-sshd.sh` is the model):
   - `apt-get install unattended-upgrades`
   - Write drop-in `/etc/apt/apt.conf.d/52unattended-upgrades-local` (never
     edit the packaged `50unattended-upgrades`, avoiding dpkg conffile
     prompts on package upgrades)
   - Write `/etc/apt/apt.conf.d/20auto-upgrades` (`Update-Package-Lists "1"`,
     `Unattended-Upgrade "1"`) — present on Ubuntu by default, needed on
     minimal Debian
   - Enable `apt-daily.timer`, `apt-daily-upgrade.timer`,
     `unattended-upgrades.service`
2. Add `unattended-upgrades` to `DEFAULT_MODULES` in `scripts/linux/setup.sh`
   (order-independent; last).
3. `.chezmoiscripts/run_onchange_after_unattended-upgrades.sh.tmpl` — thin
   Linux-gated wrapper with a `sha256sum` include of the module, following the
   nodesource wrapper pattern, so existing hosts converge on their next
   `chezmoi apply`.

## Verification

- `shellcheck` clean.
- Run the module on a real host; confirm the drop-in exists and
  `unattended-upgrade --dry-run --debug` resolves `origin=*` and lists
  eligible packages.
