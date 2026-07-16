#!/usr/bin/env bash
# Install baseline prerequisites needed before chezmoi apply: curl,
# ca-certificates, git, gnupg, gh, claude. Idempotent.

set -euo pipefail

# No leading `apt-get update` — install.sh just ran one before invoking
# setup.sh, and the gh-install branch below runs another after adding the
# upstream apt source. apt-get install is idempotent on already-present
# packages, so re-listing the set here is the standalone-use safety net.
#
# gnupg: the run_onchange_before_00-* chezmoiscripts (1password-cli,
# google-chrome) pipe `curl | sudo gpg --dearmor` to install apt signing
# keys, and they run before install-packages.sh can install anything —
# so gpg must already be present at apply time. debian:*-slim ships
# without it (full installs happen to have it, which masked this).
sudo apt-get install -y --no-install-recommends \
  git \
  curl \
  ca-certificates \
  gnupg

# GitHub CLI from upstream apt repo.
if ! command -v gh >/dev/null 2>&1; then
  sudo install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
    | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null
  sudo chmod 0644 /etc/apt/keyrings/githubcli-archive-keyring.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null
  sudo apt-get update -y
  sudo apt-get install -y gh
fi

if ! command -v claude >/dev/null 2>&1; then
  curl -fsSL https://claude.ai/install.sh | bash
fi

# Match macOS, where zsh is the default login shell. Without this the dotfiles'
# zshrc/zprofile (which add ~/.local/bin to PATH) never run, and tools installed
# there — including claude above — appear missing.
if ! command -v zsh >/dev/null 2>&1; then
  sudo apt-get install -y zsh
fi
zsh_path="$(command -v zsh)"
# `$USER` isn't always set (Docker containers, su -, some launchd contexts);
# `id -un` is reliable everywhere.
current_user="$(id -un)"
current_shell="$(getent passwd "$current_user" | cut -d: -f7)"
if [[ "$current_shell" != "$zsh_path" ]]; then
  sudo chsh -s "$zsh_path" "$current_user"
  echo "==> Default shell changed to zsh. Log out and back in, or run 'exec zsh', to use it." >&2
fi
