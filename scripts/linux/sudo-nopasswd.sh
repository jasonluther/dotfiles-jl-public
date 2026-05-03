#!/usr/bin/env bash
# Grant the current user passwordless sudo via a drop-in in /etc/sudoers.d.
# Validated with visudo before install so a malformed file can never
# replace the live one and lock sudo out.
#
# Operator-specific by design: the drop-in is keyed on $USER, so this only
# affects the account running the script.

set -euo pipefail

user="${SUDO_USER:-$USER}"
drop_in="/etc/sudoers.d/${user}-nopasswd"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
printf '%s ALL=(ALL) NOPASSWD:ALL\n' "$user" >"$tmp"
sudo visudo -cf "$tmp" >/dev/null
sudo install -m 0440 -o root -g root "$tmp" "$drop_in"
echo "sudo: passwordless sudo enabled for $user ($drop_in)"
