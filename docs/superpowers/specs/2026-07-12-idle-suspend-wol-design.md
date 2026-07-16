# idle-suspend + Wake-on-LAN design

**Date:** 2026-07-12
**Machine driving the design:** schroeder (MSI Aegis R2, Core Ultra 9 285, Ubuntu 26.04)
**Goal:** maximum power saving — the machine auto-suspends (deep sleep, ~1–2 W) when
nothing is using it, and wakes on a Wake-on-LAN magic packet to its wired NIC.

## Requirements

- Auto-suspend after a sustained idle period. "Busy" (blocks suspend) means any of:
  - established inbound SSH connections on `SSH_PORT` (plain sshd), or
  - Tailscale SSH sessions (counted as `tailscaled` children — they terminate in
    userspace and never open a kernel TCP socket on `SSH_PORT`), or
  - processes named in `BUSY_PROCS` (default `claude`; agents in tmux are
    network-bound and barely move the load average), or
  - 15-minute load average at or above a threshold (CI jobs, builds).

  > Original design counted only inbound SSH sockets + load; the SSH-socket check
  > silently missed Tailscale SSH (userspace) and idle-but-active claude sessions,
  > which suspended a machine mid-session. The extra signals above were added after.

- Wake-on-LAN enabled persistently on the wired NIC, surviving reboot and resume.
- Fail-safe: any error in the idle check means _stay awake_, never surprise-suspend.
- Manual override: a standard `systemd-inhibit --what=sleep` lock blocks suspension
  (free, because we suspend via `systemctl suspend`, which honors inhibitors).
- Reusable across machines: the tool is generic; per-machine facts (NIC, thresholds)
  live in `/etc/idle-suspend.conf`.

## Approach

A small shell script driven by a systemd timer — no daemon, no dependencies.

Alternatives rejected:

- **`autosuspend` (Ubuntu package):** upstream Python daemon with equivalent checkers,
  but a permanently running process and config surface out of proportion to two checks.
- **`systemd-logind IdleAction`:** logind's idle hints are unreliable for SSH/tmux
  workflows (long-lived sessions report idle while actively used).

## Components (`scripts/linux/idle-suspend/` in dotfiles-jl-public; originally in devtools)

- **`idle-suspend`** — the check script, installed to `/usr/local/sbin`. Reads
  `/etc/idle-suspend.conf` (`SSH_PORT`, `LOAD_THRESHOLD`, `IDLE_CHECKS_REQUIRED`,
  `WOL_NIC`). Counts established TCP connections to `SSH_PORT` and reads
  `/proc/loadavg`. If busy: reset the idle counter (kept in `/run/idle-suspend/`)
  and log why. If idle: increment the counter; when it reaches
  `IDLE_CHECKS_REQUIRED`, log and run `systemctl suspend`. `set -euo pipefail`
  so any failure exits without suspending.
- **`idle-suspend.service` + `idle-suspend.timer`** — oneshot service fired every
  5 minutes (`OnUnitActiveSec=5min`, `OnBootSec=10min` grace after boot).
- **`wol-enable.service`** — oneshot running `ethtool -s $WOL_NIC wol g` at boot
  and again after every resume (`WantedBy=multi-user.target suspend.target` with
  `After=suspend.target`), in case the driver drops the flag.
- **`install.sh`** — installs script + units + a default conf (not overwriting an
  existing one), takes `--nic <iface>`, enables the units. Run with
  `sudo scripts/linux/idle-suspend/install.sh --nic <iface>`.
- **`README.md`** — usage, tuning, wake instructions (phone app details, MAC),
  BIOS caveats (MSI: ErP off / "Resume By PCI-E Device" on if wake fails).

## schroeder-specific configuration (not in the repo)

- `/etc/idle-suspend.conf`: `SSH_PORT=22`, `LOAD_THRESHOLD=0.8`,
  `IDLE_CHECKS_REQUIRED=6` (6 × 5 min = 30 min), `WOL_NIC=enp129s0`.
- NetworkManager: `802-3-ethernet.wake-on-lan magic` on the `enp129s0` bridge-slave
  connection (the NIC sits under `br0`; WoL is a physical-NIC property and is
  unaffected by bridging).
- Deep suspend is already the kernel default (`mem_sleep: s2idle [deep]`).

## Waking the machine

- Phone on home Wi-Fi with any WoL app: MAC `34:5a:60:cf:7c:ba`, broadcast
  `255.255.255.255`, port 9.
- Any LAN device with `wakeonlan`/`etherwake` (documented option for
  wake-from-anywhere via an always-on hop; not built now).

## Testing

1. `ethtool enp129s0` reports `Wake-on: g`.
2. Manual run of the check script reports busy (active SSH) and logs to journal.
3. `sudo rtcwake -m mem -s 90` proves the suspend/resume path end to end.
4. User sends a magic packet from phone while suspended to confirm WoL wake.

Note: suspend tests freeze any session running on the machine itself; they are the
final step and coordinated with the user.
