#!/usr/bin/env bash
# Regression: the lint workflow's chezmoi template-syntax step must not
# overwrite the runner host's ~/.config/chezmoi/chezmoi.toml.
#
# Self-hosted runners share $HOME with the interactive user. A bare
# `chezmoi init` with CHEZMOI_NAME=ci therefore poisons real identity and
# the next `chezmoi update --force` writes ci@example.com into ~/.gitconfig.
#
# Usage: scripts/test-chezmoi-lint-isolate.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$ROOT/scripts/ci/chezmoi-template-syntax.sh"

red() { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: '$1' not on PATH" >&2
    exit 1
  }
}
require chezmoi
require git

if [[ ! -x "$SCRIPT" ]]; then
  red "FAIL  $SCRIPT missing or not executable"
  exit 1
fi

host_home=$(mktemp -d -t chezmoi-host-home.XXXXXX)
trap 'rm -rf "$host_home"' EXIT

mkdir -p "$host_home/.config/chezmoi"
cat >"$host_home/.config/chezmoi/chezmoi.toml" <<'EOF'
[data]
    name = "Real User"
    email = "real@example.com"
EOF
cp "$host_home/.config/chezmoi/chezmoi.toml" "$host_home/chezmoi.toml.before"

echo "==> run ci chezmoi-template-syntax under fake host HOME"
# Mimic a self-hosted runner: real identity already in $HOME/.config/chezmoi,
# CI env vars set, workspace = this repo.
env \
  HOME="$host_home" \
  USER="$USER" \
  PATH="$PATH" \
  CHEZMOI_NAME=ci \
  CHEZMOI_EMAIL=ci@example.com \
  GITHUB_WORKSPACE="$ROOT" \
  "$SCRIPT"

echo "==> assert host chezmoi.toml unchanged"
if ! diff -u "$host_home/chezmoi.toml.before" "$host_home/.config/chezmoi/chezmoi.toml"; then
  red "FAIL  host ~/.config/chezmoi/chezmoi.toml was modified"
  exit 1
fi

# Also refuse an accidental write under XDG default when XDG_CONFIG_HOME unset
# but a parallel config appeared with ci identity.
if [[ -f "$host_home/.config/chezmoi/chezmoi.toml" ]]; then
  if grep -q 'ci@example.com' "$host_home/.config/chezmoi/chezmoi.toml"; then
    red "FAIL  host chezmoi.toml contains ci@example.com"
    exit 1
  fi
fi

green "ok    host chezmoi.toml preserved (ci init was isolated)"
