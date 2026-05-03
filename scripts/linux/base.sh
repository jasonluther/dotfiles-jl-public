#!/usr/bin/env bash
# Install baseline prerequisites needed before chezmoi apply: curl,
# ca-certificates, git, gh, claude. Idempotent.

set -euo pipefail

# No leading `apt-get update` — install.sh just ran one before invoking
# setup.sh, and the gh-install branch below runs another after adding the
# upstream apt source. apt-get install is idempotent on already-present
# packages, so re-listing the trio here is the standalone-use safety net.
sudo apt-get install -y --no-install-recommends \
  git \
  curl \
  ca-certificates

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
