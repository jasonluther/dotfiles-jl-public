#!/usr/bin/env bash
# Register Google's apt repo so install-packages.sh can install
# `google-chrome-stable`. Debian/Ubuntu don't ship Chrome, and the
# self-hosted CI runners need the real branded Chrome: the partygame e2e
# suite launches Playwright with channel=chrome for user fidelity — and on
# Ubuntu 26.04 the bundled Playwright Chromium isn't even supported, so
# system Chrome is the only chromium lane that works there.
#
# amd64-only: Google publishes no linux arm64 Chrome build. On other
# arches this skips and install-packages.sh filters the package out (no
# install candidate), so nothing breaks.
#
# Idempotent: re-running is a no-op once both keyring and sources file are
# in place. The list file deliberately uses the same name Chrome's own
# postinst manages (google-chrome.list), so the package doesn't add a
# duplicate source after install.

set -euo pipefail

if [[ "$(dpkg --print-architecture)" != "amd64" ]]; then
  echo "google-chrome: no Google build for $(dpkg --print-architecture); skipping"
  exit 0
fi

LIST=/etc/apt/sources.list.d/google-chrome.list
KEYRING=/usr/share/keyrings/google-chrome.gpg

if [[ -f "$LIST" ]] && [[ -f "$KEYRING" ]]; then
  echo "google-chrome: apt repo already configured"
  exit 0
fi

echo "==> google-chrome: configuring apt repo"
curl -fsSL https://dl.google.com/linux/linux_signing_key.pub \
  | sudo gpg --dearmor --yes -o "$KEYRING"
sudo chmod 0644 "$KEYRING"

echo "deb [arch=amd64 signed-by=${KEYRING}] https://dl.google.com/linux/chrome/deb/ stable main" \
  | sudo tee "$LIST" >/dev/null

sudo apt-get update -qq
