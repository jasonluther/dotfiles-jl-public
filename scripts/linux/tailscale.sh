#!/usr/bin/env bash
# Install tailscale via the official installer and enable the daemon.
# Bringing up the node (sudo tailscale up) is left as a manual step so
# the operator can choose flags (--ssh, --advertise-tags, etc.).

set -euo pipefail

if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi

sudo systemctl enable --now tailscaled

cat <<'EOF'

tailscale installed. To join your tailnet, run:

  sudo tailscale up --ssh

Common flags: --hostname=<name>, --advertise-tags=tag:server
EOF
