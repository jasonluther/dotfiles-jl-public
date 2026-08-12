#!/usr/bin/env bash
# Regression: identity derivation must ignore poisoned ci@example.com from
# global git config and from git log HEAD (CI/self-hosted runner fallout),
# and fall through to a real author in the source history.
#
# Usage: scripts/test-chezmoi-identity-skip-ci.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

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

work=$(mktemp -d -t chezmoi-identity.XXXXXX)
trap 'rm -rf "$work"' EXIT

src="$work/src"
home="$work/home"
mkdir -p "$src" "$home"

# Minimal chezmoi source: only the config template under test + a git history
# with a real author followed by a poisoned ci HEAD.
cp "$ROOT/.chezmoi.toml.tmpl" "$src/.chezmoi.toml.tmpl"
git -C "$src" init -q
git -C "$src" config user.name "Real User"
git -C "$src" config user.email "real@example.com"
git -C "$src" add .chezmoi.toml.tmpl
git -C "$src" commit -q -m "real author commit"
git -C "$src" config user.name "ci"
git -C "$src" config user.email "ci@example.com"
# Touch so there is a distinct ci commit on tip.
echo "# ci tip" >>"$src/.chezmoi.toml.tmpl"
git -C "$src" add .chezmoi.toml.tmpl
git -C "$src" commit -q -m "ci poison tip"
# Restore template body to the repo version for init (commit content can stay).
cp "$ROOT/.chezmoi.toml.tmpl" "$src/.chezmoi.toml.tmpl"

# Poison global git identity the way a previous bad apply would.
mkdir -p "$home"
git config --file "$home/.gitconfig" user.name "ci"
git config --file "$home/.gitconfig" user.email "ci@example.com"

echo "==> chezmoi init with poisoned global + ci HEAD (no CHEZMOI_* override)"
# Unset CHEZMOI_* so derivation walks global → git log.
env -u CHEZMOI_NAME -u CHEZMOI_EMAIL \
  HOME="$home" \
  XDG_CONFIG_HOME="$home/.config" \
  XDG_CACHE_HOME="$home/.cache" \
  XDG_DATA_HOME="$home/.local/share" \
  GIT_CONFIG_GLOBAL="$home/.gitconfig" \
  PATH="$PATH" \
  chezmoi --source="$src" init

toml="$home/.config/chezmoi/chezmoi.toml"
echo "==> generated:"
cat "$toml"

fail=0
if grep -q 'ci@example.com' "$toml"; then
  red "FAIL  chezmoi.toml still has ci@example.com"
  fail=1
fi
if grep -q 'name = "ci"' "$toml"; then
  red "FAIL  chezmoi.toml still has name = \"ci\""
  fail=1
fi
if ! grep -q 'real@example.com' "$toml"; then
  red "FAIL  chezmoi.toml missing real@example.com"
  fail=1
fi
if ! grep -q 'Real User' "$toml"; then
  red "FAIL  chezmoi.toml missing Real User"
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi
green "ok    identity skipped ci poison and recovered Real User"
