#!/usr/bin/env bash
# Run Linux-specific bootstrap modules before chezmoi apply.
#
# Invoked by ../../install.sh on Linux hosts. Can also be re-run directly
# from the chezmoi source dir to re-apply a subset of modules:
#
#   bash ~/.local/share/chezmoi/bootstrap/linux/setup.sh ssh-keys
#
# Modules are scripts in modules/ named <name>.sh. Each must be idempotent
# and may rely on $REPO_DIR pointing at this directory.

set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODULES_DIR="$REPO_DIR/modules"

# Order matters: ssh-keys runs before base so authorized_keys is populated
# before base.sh hardens sshd (PasswordAuthentication=no). On a re-run where
# openssh-server is already installed, this prevents a window where keys
# haven't synced yet but password auth is already off.
DEFAULT_MODULES=(ssh-keys base tailscale)

modules=("$@")
if [[ ${#modules[@]} -eq 0 ]]; then
  modules=("${DEFAULT_MODULES[@]}")
fi

for m in "${modules[@]}"; do
  if [[ ! "$m" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
    echo "error: invalid module name '$m' (allowed: lowercase letters, digits, hyphen)" >&2
    exit 1
  fi
  script="$MODULES_DIR/${m}.sh"
  if [[ ! -f "$script" ]]; then
    echo "error: unknown module '$m' (looked for $script)" >&2
    exit 1
  fi
  echo "==> $m"
  REPO_DIR="$REPO_DIR" bash "$script"
done

echo "✓ linux bootstrap complete"
