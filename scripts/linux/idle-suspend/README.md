# idle-suspend

Auto-suspend a machine after a sustained idle period, with Wake-on-LAN armed so
it can be woken remotely. Built for always-plugged-in desktops/servers that sit
idle most of the day (deep suspend draws ~1–2 W vs tens of watts idle).

## How it works

A systemd timer runs a small check script every 5 minutes. The machine is
**busy** (idle counter resets) if any of:

- established inbound SSH connections (`SSH_PORT`, default 22 — plain sshd
  over LAN or over the tailnet),
- **Tailscale SSH** sessions, counted as child processes of `tailscaled`
  (tailscale's SSH server terminates connections in userspace, so they
  never show up as kernel TCP connections to `SSH_PORT`; the process tree
  is used rather than `who`/utmp because utmp is empty on this setup),
- running processes named in `BUSY_PROCS` (default `claude` — agent
  sessions in detached tmux are network-bound and barely move the load
  average), or
- the 15-minute load average at or above `LOAD_THRESHOLD` (default 0.8 —
  keeps it awake through CI jobs and builds).

After `IDLE_CHECKS_REQUIRED` consecutive idle checks (default 6 → 30 minutes)
it runs `systemctl suspend`. Every decision is logged to the journal.

`wol-enable.service` asserts `ethtool -s $WOL_NIC wol g` at boot and after
every resume so the NIC always listens for magic packets.

Fail-safe by construction: any error in the check script exits without
suspending, and `systemctl suspend` honors inhibitor locks.

## Install

```sh
sudo ~/.local/share/chezmoi/scripts/linux/idle-suspend/install.sh --nic enp129s0
```

Re-run after `chezmoi update` pulls a new version — the installer is
idempotent and merges an existing `/etc/idle-suspend.conf` forward.

Tune `/etc/idle-suspend.conf` afterwards; changes take effect on the next
timer tick (WoL NIC changes need `systemctl restart wol-enable.service`).

If the machine is managed by NetworkManager, also make WoL persistent at the
network layer (works for bridge-slave connections too):

```sh
nmcli -g NAME,DEVICE connection show --active   # find the wired connection
sudo nmcli connection modify "<name>" 802-3-ethernet.wake-on-lan magic
```

## Deploying to a remote machine

From any machine with SSH access to the target:

```sh
ssh <host>
chezmoi update                      # dotfiles are already on every machine
ip -br link                         # find the wired NIC, e.g. enp3s0
sudo ~/.local/share/chezmoi/scripts/linux/idle-suspend/install.sh --nic <nic>

# If NetworkManager manages the NIC, persist WoL at that layer too:
nmcli -g NAME,DEVICE connection show --active
sudo nmcli connection modify "<connection-name>" 802-3-ethernet.wake-on-lan magic

# Verify:
sudo ethtool <nic> | grep Wake-on   # expect "Wake-on: g"
systemctl list-timers idle-suspend.timer
```

Then log out — with no SSH connections and low load it suspends after
30 minutes. Confirm the round trip with `wake <host>` (dotfiles bin;
host data in the private overlay's ~/.config/wake/hosts) from another
machine. If it doesn't wake, check BIOS (see below) — machines that
were never WoL-armed usually need that one-time BIOS change.

## Keeping it awake manually

```sh
systemd-inhibit --what=sleep --why="long download" sleep 7200 &
```

Any sleep inhibitor blocks the suspend; no tool-specific override needed.

## Waking it up

From any device on the same LAN, send a magic packet to the wired NIC's MAC:

- **Phone app** (home Wi-Fi): any WoL app — target MAC address of the NIC,
  broadcast address `255.255.255.255`, port 9.
- **Another Linux/macOS box:** `wakeonlan <mac>` or `etherwake <mac>`.
- **From anywhere:** SSH to any always-on device on that LAN (router, Pi,
  NAS) and send the packet from there. While suspended the machine's own
  Tailscale is down — the packet must originate on the LAN.

## If wake doesn't work

Work down the chain — each step isolates a layer:

- **Packet delivery:** while the target is awake, run
  `sudo tcpdump -i <nic> -nn 'udp and (dst port 9 or dst port 7)'` on it and
  send the wake from the actual sender you plan to use. Confirms MAC,
  broadcast address, and Wi-Fi→wired broadcast forwarding in one shot.
- **NIC armed:** `ethtool <nic> | grep Wake-on` must show `Wake-on: g` (not
  `d`). Some drivers lose the flag across suspend — `wol-enable.service`
  re-asserts it on resume; check `systemctl status wol-enable.service`.
- **Kernel wakeup chain:** the NIC _and_ its PCIe root port must be enabled:
  `cat /sys/class/net/<nic>/device/power/wakeup` and the matching entries in
  `/proc/acpi/wakeup` (follow the `pci:` sysfs nodes) should say `enabled`.
- **BIOS** (the usual culprit when all of the above pass but the machine
  still won't wake from deep sleep): enable wake-by-network. On MSI boards:
  **Wakeup Event Setup → Resume By PCI-E Device: Enabled**, and disable
  **ErP** (ErP cuts NIC power in sleep states).
- **Safe end-to-end test:** `sudo rtcwake -m mem -s 240` suspends with a
  guaranteed RTC wake after 4 minutes; send the magic packet mid-sleep. An
  early resume proves WoL; an on-time resume means it failed — with no risk
  of a machine stuck asleep.

## Uninstall

```sh
sudo systemctl disable --now idle-suspend.timer wol-enable.service
sudo rm /usr/local/sbin/idle-suspend /etc/idle-suspend.conf \
  /etc/systemd/system/{idle-suspend.service,idle-suspend.timer,wol-enable.service}
sudo systemctl daemon-reload
```
