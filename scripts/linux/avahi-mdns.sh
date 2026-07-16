#!/usr/bin/env bash
# Publish this host as <hostname>.local via avahi, IPv4-only, so other
# LAN machines can `ssh <hostname>.local` reliably.
#
# IPv4-only is deliberate: avahi 0.8 misreads its own IPv6 temp-address
# churn (SLAAC privacy addresses arriving seconds after startup) as a
# competing claim on the hostname and renames itself <hostname>-2.local
# on ~every boot/resume — after which <hostname>.local resolves to
# nothing. Publishing AAAA records was independently flaky too: temp
# addresses rotate daily, so a client preferring AAAA can cache a dead
# address. The stable DHCP A record is all ssh needs. Host IPv6 itself
# is untouched — this only affects what avahi announces.
#
# Machine-local lines in /etc/avahi/avahi-daemon.conf (e.g. a dual-homed
# host pinning mDNS to one NIC with allow-interfaces=) are preserved;
# only the two keys below are owned by this module.
#
# libnss-mdns is the client half: it wires mdns4_minimal into
# nsswitch.conf so *this* host can resolve other machines' .local names.

set -euo pipefail

sudo apt-get install -y --no-install-recommends avahi-daemon avahi-utils libnss-mdns

conf=/etc/avahi/avahi-daemon.conf

# avahi 0.8 has no conf.d support, so edit keys in place. Drop every
# existing occurrence (set, commented-out default, or stray duplicate from
# an earlier hand edit) and insert exactly one line under the section
# header — converges to the same file no matter the starting state.
set_key() {
  local section="$1" key="$2" value="$3"
  sudo sed -i -E "/^#?${key}=/d" "$conf"
  sudo sed -i "/^\[${section}\]/a ${key}=${value}" "$conf"
}

set_key server use-ipv6 no
set_key publish publish-aaaa-on-ipv4 no

# `/run/systemd/system` is the canonical "systemd is PID 1" check (sd_booted).
# In containers/chroots the config is still written; units start on real boot.
if [ ! -d /run/systemd/system ]; then
  echo "avahi-mdns: systemd not running (container/chroot?) — config written, skipping restart/verify" >&2
  exit 0
fi

sudo systemctl enable avahi-daemon
sudo systemctl restart avahi-daemon
sleep 3

# Verify avahi kept the real hostname. A conflict rename (<hostname>-2.local)
# is exactly the failure this module exists to prevent, so fail loudly on it;
# a plain resolve miss (no multicast-capable NIC — cloud VM) is only a warning.
expected="$(hostname).local"
addr="$(avahi-resolve -4 -n "$expected" 2>/dev/null | awk '{print $2}')"
if [ -n "$addr" ]; then
  echo "avahi-mdns: $expected -> $addr"
elif journalctl -u avahi-daemon --since '30 sec ago' 2>/dev/null | grep -q 'Host name conflict'; then
  echo "error: avahi renamed this host (name conflict) — something else on the LAN claims $expected" >&2
  exit 1
else
  echo "avahi-mdns: warning: could not resolve $expected locally (no multicast-capable interface?)" >&2
fi
