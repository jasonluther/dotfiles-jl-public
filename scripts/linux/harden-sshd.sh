#!/usr/bin/env bash
# Install openssh-server with a hardened sshd_config drop-in.
#
# The drop-in is written *before* openssh-server is installed so the
# daemon's first start uses PasswordAuthentication=no — there is no window
# in which a fresh sshd accepts password logins.
#
# Refuses to harden if ~/.ssh/authorized_keys is empty: locking yourself
# out of a host you can't console into is bad. Run scripts/linux/ssh-keys.sh
# first, or set ALLOW_NO_KEYS=1 to bypass (e.g. console-only hosts).

set -euo pipefail

authorized="$HOME/.ssh/authorized_keys"
if [[ "${ALLOW_NO_KEYS:-0}" != "1" ]] && [[ ! -s "$authorized" ]]; then
  echo "error: $authorized is empty or missing — refusing to disable password auth." >&2
  echo "       Run ssh-keys.sh first, or set ALLOW_NO_KEYS=1 to override." >&2
  exit 1
fi

# Pre-stage hardened sshd config so the daemon never starts with defaults.
# Filename kept as 00-first-time.conf for back-compat with hosts originally
# bootstrapped via the (now-retired) jasonluther/first-time repo.
sudo install -d -m 0755 /etc/ssh/sshd_config.d
sudo tee /etc/ssh/sshd_config.d/00-first-time.conf >/dev/null <<'EOF'
# Managed by jasonluther/dotfiles-jl-public scripts/linux. Edit upstream, not here.
PasswordAuthentication no
PermitRootLogin prohibit-password
KbdInteractiveAuthentication no
EOF
sudo chmod 0644 /etc/ssh/sshd_config.d/00-first-time.conf

sudo apt-get install -y --no-install-recommends openssh-server

# Reload in case openssh-server was already installed and running with stock
# config; existing sessions persist across reload.
sudo systemctl reload ssh 2>/dev/null || sudo systemctl restart ssh
sudo systemctl enable --now ssh
