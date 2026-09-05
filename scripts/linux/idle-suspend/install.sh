#!/bin/bash
# Install idle-suspend system-wide: script to /usr/local/sbin, units to
# /etc/systemd/system, default conf to /etc/idle-suspend.conf. An existing
# conf is moved to /etc/idle-suspend.conf.bak and rewritten from the shipped
# template, carrying forward any values already set locally — so new keys and
# comments land without clobbering your tuning. Then enable the timer and WoL.
#
# Usage: sudo ./install.sh --nic <iface>   (e.g. --nic enp129s0)
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
NIC=""

while [ $# -gt 0 ]; do
  case $1 in
    --nic)
      NIC=$2
      shift 2
      ;;
    *)
      echo "usage: sudo $0 --nic <iface>" >&2
      exit 2
      ;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "must run as root (sudo)" >&2
  exit 1
fi

install -m 755 "$HERE/idle-suspend" /usr/local/sbin/idle-suspend
install -m 644 "$HERE/idle-suspend.service" "$HERE/idle-suspend.timer" \
  "$HERE/wol-enable.service" /etc/systemd/system/

# Without this, logind's polkit default (auth_admin_keep for callers with no
# active session) silently denies every suspend call the timer-triggered
# service makes — see the rule file's own header for the failure mode.
install -d -m 755 /etc/polkit-1/rules.d
install -m 644 "$HERE/50-idle-suspend.rules" /etc/polkit-1/rules.d/

# Debian's default install masks sleep.target/suspend.target/hibernate.target/
# hybrid-sleep.target (server images assume a host should never sleep
# unattended) — seen on an affected host, dated to its initial provisioning and
# so long predating idle-suspend's opt-in. A masked suspend.target makes every
# suspend attempt fail with "Access denied" — the same symptom as the polkit
# gap above, but a different and unrelated cause; unmask is idempotent.
systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target

# A graphical login screen is a SECOND, uninterlocked suspender. GNOME's greeter
# session runs gsd-power with its own idle policy (sleep-inactive-ac-type=suspend
# at 900s by default) and calls logind's Suspend() directly, so a host sitting at
# the greeter suspends on GNOME's timer regardless of what the check script above
# decided — none of the SSH/process/load interlocks apply to it. Measured on a CI
# runner: the box suspended mid-job while idle-suspend was logging "busy" on every
# tick; systemd-sleep froze the whole user slice, and the job died hours later
# against a service that had long since given up on it. Hardening logind is not
# enough either — IdleAction governs logind's own timer, not this caller.
#
# idle-suspend is meant to be the only thing that suspends this machine, so turn
# the greeter's own policy off. Best-effort: a host with no GDM just skips it.
if command -v dbus-run-session >/dev/null 2>&1; then
  for gdm_user in Debian-gdm gdm; do
    id -u "$gdm_user" >/dev/null 2>&1 || continue
    for key in sleep-inactive-ac-type sleep-inactive-battery-type; do
      runuser -u "$gdm_user" -- dbus-run-session -- \
        gsettings set org.gnome.settings-daemon.plugins.power "$key" nothing \
        >/dev/null 2>&1 || true
    done
    # A dconf write reaches a RUNNING greeter only over that greeter's own session
    # bus, which this throwaway bus is not — so a greeter started before this ran
    # keeps the old value in memory until it restarts. Deliberately NOT restarting
    # gdm here: that would kill an active desktop session. (Learned the hard way —
    # reading the value back showed the new setting while the live daemon went on
    # suspending the box. Reading a setting back proves the setting, not that
    # anything reloaded it.)
    if systemctl is-active --quiet gdm3 2>/dev/null \
      || systemctl is-active --quiet gdm 2>/dev/null; then
      echo "greeter auto-suspend disabled — takes effect after 'systemctl restart gdm3' or a reboot"
    fi
    break
  done
fi

CONF=/etc/idle-suspend.conf
if [ -e "$CONF" ]; then
  # Refresh from the shipped template, but carry forward every value already
  # set locally so new keys/comments land without losing tuning. The old file
  # is preserved at $CONF.bak. --nic, if given, overrides WOL_NIC.
  mv "$CONF" "$CONF.bak"
  while IFS= read -r line; do
    if [[ $line =~ ^([A-Za-z_][A-Za-z0-9_]*)= ]]; then
      key=${BASH_REMATCH[1]}
      if [ "$key" = WOL_NIC ] && [ -n "$NIC" ]; then
        line="WOL_NIC=$NIC"
      else
        prev=$(grep -E "^${key}=" "$CONF.bak" | head -n1 || true)
        [ -n "$prev" ] && line=$prev
      fi
    fi
    printf '%s\n' "$line"
  done <"$HERE/idle-suspend.conf" >"$CONF"
  echo "updated $CONF (previous saved to $CONF.bak)"
else
  [ -n "$NIC" ] || {
    echo "--nic <iface> required for first install" >&2
    exit 2
  }
  sed "s/^WOL_NIC=.*/WOL_NIC=$NIC/" "$HERE/idle-suspend.conf" \
    >"$CONF"
  echo "wrote $CONF (WOL_NIC=$NIC)"
fi

systemctl daemon-reload
systemctl enable --now wol-enable.service
systemctl enable --now idle-suspend.timer

echo "installed. next checks:"
echo "  ethtool \$(. /etc/idle-suspend.conf; echo \$WOL_NIC) | grep Wake-on"
echo "  systemctl list-timers idle-suspend.timer"
echo "  journalctl -u idle-suspend.service -f"
