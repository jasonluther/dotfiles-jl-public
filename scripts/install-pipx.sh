#!/usr/bin/env bash
# Install Python CLI tools from packages/pipx.txt via pipx.
# Idempotent — skips entries already installed.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
list="$SRC/packages/pipx.txt"
[[ -f "$list" ]] || exit 0

if ! command -v pipx >/dev/null 2>&1; then
  echo "pipx not on PATH; skipping pipx.txt" >&2
  exit 0
fi

installed=$(pipx list --short 2>/dev/null | awk '{print $1}')

while IFS= read -r line; do
  line="${line%%#*}"
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -z "$line" ]] && continue
  name="${line%%[<>=~!]*}"
  if echo "$installed" | grep -qx "$name"; then
    continue
  fi
  echo "==> pipx install $line"
  pipx install "$line"
done <"$list"
