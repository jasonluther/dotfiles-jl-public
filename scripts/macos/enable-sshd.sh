#!/usr/bin/env bash
# Enable Remote Login (sshd) on macOS with key-only, no-password auth.
#
# Mirrors scripts/linux/harden-sshd.sh, minus the install: macOS already ships
# sshd, so this only writes the hardened sshd_config drop-in and flips Remote
# Login on. macOS launches sshd per-connection via launchd, so the drop-in is
# read on the next connection — no daemon restart needed.
#
# Refuses to enable if ~/.ssh/authorized_keys is empty: a passwordless daemon
# with no authorized keys is a host you can't log into. On a Mac with the
# private dotfiles applied, modify_private_authorized_keys.tmpl has already
# merged authorized_keys.shared, so the gate passes. Set ALLOW_NO_KEYS=1 to
# override (e.g. a host you'll add keys to by hand afterward).

set -euo pipefail

authorized="$HOME/.ssh/authorized_keys"
if [[ "${ALLOW_NO_KEYS:-0}" != "1" ]] && [[ ! -s "$authorized" ]]; then
  echo "error: $authorized is empty or missing — refusing to enable a passwordless sshd." >&2
  echo "       Apply the private dotfiles (authorized_keys.shared) first, or set ALLOW_NO_KEYS=1." >&2
  exit 1
fi

# macOS >= Ventura ships sshd_config with `Include /etc/ssh/sshd_config.d/*`.
# Warn (don't fail) if it's missing so the drop-in is still written and the
# operator knows to wire the Include manually on an older host.
if ! grep -qE '^[[:space:]]*Include[[:space:]]+/etc/ssh/sshd_config\.d/' /etc/ssh/sshd_config 2>/dev/null; then
  echo "warning: /etc/ssh/sshd_config has no Include for sshd_config.d; the drop-in" >&2
  echo "         may be ignored until you add: Include /etc/ssh/sshd_config.d/*" >&2
fi

conf=/etc/ssh/sshd_config.d/00-hardening.conf
sudo install -d -m 0755 /etc/ssh/sshd_config.d
sudo tee "$conf" >/dev/null <<'EOF'
# Managed by jasonluther/dotfiles-jl-public scripts/macos. Edit upstream, not here.
PasswordAuthentication no
PermitRootLogin prohibit-password
KbdInteractiveAuthentication no
EOF
sudo chmod 0644 "$conf"

# Enable Remote Login if it isn't already. `systemsetup -getremotelogin` needs
# admin rights, but sudo is already primed by the drop-in write above, so this
# won't re-prompt. On Ventura+ toggling this also requires the calling terminal
# to have Full Disk Access; surface that clearly rather than failing cryptically.
if [[ "$(sudo systemsetup -getremotelogin 2>/dev/null)" == *On* ]]; then
  echo "Remote Login already enabled."
else
  echo "Enabling Remote Login…"
  if ! sudo systemsetup -setremotelogin on; then
    echo "error: could not enable Remote Login." >&2
    echo "       On macOS Ventura+ this needs Full Disk Access for your terminal:" >&2
    echo "       System Settings → Privacy & Security → Full Disk Access → enable your terminal," >&2
    echo "       then re-run: chezmoi apply  (or bash scripts/macos/enable-sshd.sh)" >&2
    exit 1
  fi
fi

echo "✓ sshd enabled (key-only, no passwords)."
