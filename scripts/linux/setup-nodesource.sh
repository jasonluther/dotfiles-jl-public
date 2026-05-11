#!/usr/bin/env bash
# Pin Node.js to v24 LTS via NodeSource (deb.nodesource.com).
#
# Ubuntu's apt nodejs lags upstream — 24.04 still ships v18, resolute ships
# v22. Modern npm packages already require >=20 (e.g. @devcontainers/cli)
# and that gap widens. NodeSource is the official Node.js team's apt repo
# and tracks a single major version per repo file.
#
# Idempotent: re-running with the same NODE_MAJOR is a no-op. To bump
# versions, edit NODE_MAJOR below — the chezmoi wrapper re-fires on script
# changes so the new repo file is written and apt resync'd on next apply.
# install-packages.sh then upgrades nodejs because the candidate version
# moved.
#
# Replaces the apt `npm` package: NodeSource's nodejs bundles npm
# (unlike Debian's split packaging), so it's been removed from apt.txt.

set -euo pipefail

NODE_MAJOR=24

LIST=/etc/apt/sources.list.d/nodesource.list
KEYRING=/etc/apt/keyrings/nodesource.gpg

if [[ -f "$LIST" ]] && grep -q "node_${NODE_MAJOR}\.x" "$LIST" && [[ -f "$KEYRING" ]]; then
  echo "nodesource: node_${NODE_MAJOR}.x repo already configured"
  exit 0
fi

echo "==> nodesource: configuring node_${NODE_MAJOR}.x apt repo"
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
  | sudo gpg --dearmor --yes -o "$KEYRING"
sudo chmod 0644 "$KEYRING"
echo "deb [signed-by=$KEYRING] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
  | sudo tee "$LIST" >/dev/null
sudo apt-get update -qq
