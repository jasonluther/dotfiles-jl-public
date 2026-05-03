#!/usr/bin/env bash
# Install pinned Python versions via pyenv and upgrade pip in each.
# Idempotent — pyenv install --skip-existing + pip --upgrade.

set -euo pipefail

if ! command -v pyenv >/dev/null 2>&1; then
  echo "pyenv not on PATH; install via brew first." >&2
  exit 0
fi

PYTHON_VERSIONS="3.13 3.14"
for version in $PYTHON_VERSIONS; do
  pyenv install --skip-existing "$(pyenv latest "$version" 2>/dev/null || echo "$version")"
done

# Upgrade pip for all pyenv-managed versions
for version in $(pyenv versions --bare); do
  echo "Upgrading pip for Python $version..."
  "$HOME/.pyenv/versions/$version/bin/python" -m pip install --upgrade pip
done
