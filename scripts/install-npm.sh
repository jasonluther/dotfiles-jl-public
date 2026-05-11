#!/usr/bin/env bash
# Install global npm packages from packages/npm.txt.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
list="$SRC/packages/npm.txt"
[[ -f "$list" ]] || exit 0

if ! command -v npm >/dev/null 2>&1; then
  echo "npm not on PATH; skipping npm.txt" >&2
  exit 0
fi

pkgs=()
while IFS= read -r line; do
  line="${line%%#*}"
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -n "$line" ]] && pkgs+=("$line")
done <"$list"

if [[ ${#pkgs[@]} -gt 0 ]]; then
  # Install into ~/.npm-global so apt-installed node doesn't need sudo for -g.
  # dot_zshrc puts ~/.npm-global/bin on PATH.
  prefix="$HOME/.npm-global"
  install -d "$prefix"
  npm config set prefix "$prefix" >/dev/null
  echo "==> npm install -g (${#pkgs[@]} packages, prefix=$prefix)"
  npm install -g "${pkgs[@]}"
fi
