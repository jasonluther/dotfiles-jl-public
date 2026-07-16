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
