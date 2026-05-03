#!/usr/bin/env bash
# Install base packages (git, gh, openssh-server) with hardened sshd config.
#
# Order matters two ways:
#   1. setup.sh runs ssh-keys before base so ~/.ssh/authorized_keys is populated
#      before sshd gets PasswordAuthentication=no. The check below enforces that.
#   2. The sshd_config drop-in is written *before* openssh-server is installed,
#      so the daemon's first start uses PasswordAuthentication=no — there is no
#      window in which a fresh sshd accepts password logins.

set -euo pipefail

sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
  git \
  curl \
  ca-certificates

# Passwordless sudo for jason. Validated with visudo before install so a
# malformed file can never replace the live one and lock sudo out.
sudoers_tmp="$(mktemp)"
trap 'rm -f "$sudoers_tmp"' EXIT
printf 'jason ALL=(ALL) NOPASSWD:ALL\n' >"$sudoers_tmp"
sudo visudo -cf "$sudoers_tmp" >/dev/null
sudo install -m 0440 -o root -g root "$sudoers_tmp" /etc/sudoers.d/jason-nopasswd

# Refuse non-fast-forward pulls — surfaces divergence instead of silently
# creating merge commits.
git config --global pull.ff only

# Refuse to harden sshd if there are no keys to log in with. setup.sh runs
# ssh-keys before base for this reason; if base is invoked standalone before
# keys are synced, abort instead of locking ourselves out. ALLOW_NO_KEYS=1
# bypasses the check (e.g. console-only hosts where SSH is unused).
authorized="$HOME/.ssh/authorized_keys"
if [[ "${ALLOW_NO_KEYS:-0}" != "1" ]] && [[ ! -s "$authorized" ]]; then
  echo "error: $authorized is empty or missing — refusing to disable password auth." >&2
  echo "       Run the ssh-keys module first, or set ALLOW_NO_KEYS=1 to override." >&2
  exit 1
fi

# Pre-stage hardened sshd config so the daemon never starts with defaults.
# Filename kept as 00-first-time.conf for back-compat with hosts originally
# bootstrapped via the (now-retired) jasonluther/first-time repo.
sudo install -d -m 0755 /etc/ssh/sshd_config.d
sudo tee /etc/ssh/sshd_config.d/00-first-time.conf >/dev/null <<'EOF'
# Managed by jasonluther/dotfiles-jl-public bootstrap/linux. Edit upstream, not here.
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

# GitHub CLI from upstream apt repo.
if ! command -v gh >/dev/null 2>&1; then
  sudo install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg |
    sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null
  sudo chmod 0644 /etc/apt/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" |
    sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y gh
fi

# Claude
if ! command -v claude >/dev/null 2>&1; then
  curl -fsSL https://claude.ai/install.sh | bash
fi
