#!/usr/bin/env bash
# Run Linux-specific bootstrap modules before chezmoi apply.
#
# Invoked by ../../install.sh on Linux hosts. Can also be re-run directly
# from the chezmoi source dir to re-apply a subset of modules:
#
#   bash ~/.local/share/chezmoi/scripts/linux/setup.sh ssh-keys
#
# Each module is a sibling script named <name>.sh and must be idempotent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Order matters: ssh-keys must populate authorized_keys before harden-sshd
# disables password auth, otherwise a fresh host would refuse all logins.
DEFAULT_MODULES=(ssh-keys harden-sshd sudo-nopasswd base tailscale unattended-upgrades avahi-mdns)

modules=("$@")
if [[ ${#modules[@]} -eq 0 ]]; then
  modules=("${DEFAULT_MODULES[@]}")
fi

for m in "${modules[@]}"; do
  if [[ ! "$m" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    echo "error: invalid module name '$m' (allowed: lowercase letters, digits, hyphen)" >&2
    exit 1
  fi
  script="$SCRIPT_DIR/${m}.sh"
  if [[ ! -f "$script" ]]; then
    echo "error: unknown module '$m' (looked for $script)" >&2
    exit 1
  fi
  echo "==> $m"
  bash "$script"
done

echo "✓ linux bootstrap complete"
