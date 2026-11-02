#!/usr/bin/env bash
# Add mise's apt repo (mise.jdx.dev/deb) so install-packages can apt-install it.
#
# mise is the per-project runtime manager: `mise activate` in .zshenv puts
# the Node a repo pins in .nvmrc first on PATH, while NodeSource's system
# node stays the default elsewhere. Debian and Ubuntu don't package mise,
# hence the vendor repo.
#
# Idempotent: re-running with the repo file and keyring present is a no-op.

set -euo pipefail

LIST=/etc/apt/sources.list.d/mise.list
KEYRING=/etc/apt/keyrings/mise-archive-keyring.gpg

if [[ -f "$LIST" ]] && [[ -f "$KEYRING" ]]; then
  echo "mise: apt repo already configured"
  exit 0
fi

echo "==> mise: configuring apt repo"
sudo install -d -m 0755 /etc/apt/keyrings
curl -fsSL https://mise.jdx.dev/gpg-key.pub | sudo gpg --dearmor --yes -o "$KEYRING"
sudo chmod 0644 "$KEYRING"
echo "deb [signed-by=$KEYRING arch=$(dpkg --print-architecture)] https://mise.jdx.dev/deb stable main" \
  | sudo tee "$LIST" >/dev/null
sudo apt-get update -qq
