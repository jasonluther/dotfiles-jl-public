#!/usr/bin/env bash
# Register 1Password's apt repo so install-packages.sh can install the
# `1password-cli` package (and verify it). 1Password publishes signed
# .deb releases at downloads.1password.com — Debian/Ubuntu don't ship it.
#
# Idempotent: re-running is a no-op once both keyring and sources file
# are in place. Edit the keyring URL only if 1Password rotates keys.

set -euo pipefail

LIST=/etc/apt/sources.list.d/1password.list
KEYRING=/usr/share/keyrings/1password-archive-keyring.gpg
DEBSIG_KEYRING_DIR=/usr/share/debsig/keyrings/AC2D62742012EA22
DEBSIG_POLICY_DIR=/etc/debsig/policies/AC2D62742012EA22

if [[ -f "$LIST" ]] && [[ -f "$KEYRING" ]]; then
  echo "1password-cli: apt repo already configured"
  exit 0
fi

echo "==> 1password-cli: configuring apt repo"
curl -fsSL https://downloads.1password.com/linux/keys/1password.asc \
  | sudo gpg --dearmor --yes -o "$KEYRING"
sudo chmod 0644 "$KEYRING"

arch="$(dpkg --print-architecture)"
echo "deb [arch=${arch} signed-by=${KEYRING}] https://downloads.1password.com/linux/debian/${arch} stable main" \
  | sudo tee "$LIST" >/dev/null

# debsig-verify policy — recommended by 1Password so installed .deb
# signatures are verified against their key on every apt operation.
sudo install -d -m 0755 "$DEBSIG_POLICY_DIR" "$DEBSIG_KEYRING_DIR"
curl -fsSL https://downloads.1password.com/linux/debian/debsig/1password.pol \
  | sudo tee "$DEBSIG_POLICY_DIR/1password.pol" >/dev/null
curl -fsSL https://downloads.1password.com/linux/keys/1password.asc \
  | sudo gpg --dearmor --yes -o "$DEBSIG_KEYRING_DIR/debsig.gpg"
sudo chmod 0644 "$DEBSIG_KEYRING_DIR/debsig.gpg"

sudo apt-get update -qq
