#!/usr/bin/env bash
# Install tailscale from its signed apt repository and enable the daemon.
# Bringing up the node (sudo tailscale up) is left as a manual step so
# the operator can choose flags (--ssh, --advertise-tags, etc.).

set -euo pipefail

# Tailscale's apt repository, set up the way its installer does for
# Debian and Ubuntu (a keyring plus a source list), so apt checks the
# package signatures instead of a script running unchecked.
if ! command -v tailscale >/dev/null 2>&1; then
  # shellcheck source=/dev/null
  . /etc/os-release
  # Ubuntu derivatives (Mint, Pop!_OS) use Ubuntu's repo by UBUNTU_CODENAME;
  # Debian derivatives fall back to Debian's when their own ID has no repo.
  if [[ -n "${UBUNTU_CODENAME:-}" ]]; then
    repo="https://pkgs.tailscale.com/stable/ubuntu/${UBUNTU_CODENAME}"
  elif [[ "$ID" == debian || "$ID" == ubuntu ]]; then
    repo="https://pkgs.tailscale.com/stable/${ID}/${VERSION_CODENAME}"
  else
    repo="https://pkgs.tailscale.com/stable/debian/${VERSION_CODENAME}"
  fi
  sudo install -d -m 0755 /usr/share/keyrings
  curl -fsSL "${repo}.noarmor.gpg" \
    | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
  curl -fsSL "${repo}.tailscale-keyring.list" \
    | sudo tee /etc/apt/sources.list.d/tailscale.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y tailscale
fi

sudo systemctl enable --now tailscaled

cat <<'EOF'

tailscale installed. To join your tailnet, run:

  sudo tailscale up --ssh

Common flags: --hostname=<name>, --advertise-tags=tag:server
EOF
