#!/bin/sh
# One-line bootstrap for dotfiles-jl-public.
# Usage:
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/jasonluther/dotfiles-jl-public/main/install.sh)"
set -eu

REPO="jasonluther/dotfiles-jl-public"

if ! command -v chezmoi >/dev/null 2>&1; then
  echo "==> Installing chezmoi..."
  BIN_DIR="${HOME}/.local/bin"
  mkdir -p "$BIN_DIR"
  sh -c "$(curl -fsLS get.chezmoi.io)" -- -b "$BIN_DIR"
  export PATH="$BIN_DIR:$PATH"
fi

echo "==> Applying $REPO..."
chezmoi init --apply "$REPO"

echo
echo "Public dotfiles installed."
echo "If you have a private overlay, layer it now via your overlay's bootstrap script."
