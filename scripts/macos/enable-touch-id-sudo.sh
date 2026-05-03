#!/usr/bin/env bash
# Enable Touch ID for sudo via Apple's built-in pam_tid.so.
# Uses /etc/pam.d/sudo_local which survives macOS updates (Sonoma+).
#
# Touch ID-only by design. Apple Watch sudo is intentionally not enabled
# because the biometric prompt is unified — when both are configured, the
# Watch responds first (tap is faster than fingerprint), and macOS exposes
# no preference order. If you want the Watch as a fallback, switch to
# the third-party pam_watchid module.
#
# Requires sudo: writes to /etc/pam.d/sudo_local. When run interactively
# outside chezmoi, expect a sudo password prompt.

set -euo pipefail

SUDO_LOCAL="/etc/pam.d/sudo_local"

if [ -f "$SUDO_LOCAL" ] && grep -q "pam_tid.so" "$SUDO_LOCAL"; then
  echo "Touch ID for sudo already configured."
  exit 0
fi

echo "Enabling Touch ID for sudo..."
sudo tee "$SUDO_LOCAL" >/dev/null <<'EOF'
auth       sufficient     pam_tid.so
EOF

echo "Touch ID for sudo enabled."
