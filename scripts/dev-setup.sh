#!/usr/bin/env bash
# One-shot setup for hacking on this dotfiles repo itself.
#
# Idempotent. Run from the repo root (or anywhere — paths resolve from
# this script's location):
#
#   scripts/dev-setup.sh
#
# Currently handles:
#   - `pre-commit install`, working around the "Cowardly refusing to install
#     hooks with `core.hooksPath` set" error when core.hooksPath happens to be
#     set redundantly to its default (`.git/hooks`).

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

if ! command -v pre-commit >/dev/null 2>&1; then
  echo "error: pre-commit not on PATH. Install via Homebrew (mac) or pipx." >&2
  exit 1
fi

# pre-commit refuses to install when core.hooksPath is set to *anything* —
# including the default `.git/hooks`, where unset and set-to-default behave
# identically. Drop the redundant local override; leave non-default values
# alone since those signal an intentional override (team shared hooks, etc.).
hooks_path="$(git config --local --get core.hooksPath || true)"
if [[ -n "$hooks_path" ]]; then
  if [[ "$hooks_path" == ".git/hooks" || "$hooks_path" == "$REPO/.git/hooks" ]]; then
    echo "==> Unsetting redundant local core.hooksPath ($hooks_path)..."
    git config --local --unset-all core.hooksPath
  else
    echo "error: local core.hooksPath is '$hooks_path' (non-default); refusing to unset." >&2
    echo "       If you want pre-commit to manage hooks here, unset it manually:" >&2
    echo "         git config --local --unset-all core.hooksPath" >&2
    exit 1
  fi
fi

echo "==> pre-commit install..."
pre-commit install
