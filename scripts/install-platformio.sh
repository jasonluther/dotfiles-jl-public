#!/usr/bin/env bash
# Install PlatformIO platforms from packages/platformio.txt.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
list="$SRC/packages/platformio.txt"
[[ -f "$list" ]] || exit 0

if ! command -v pio >/dev/null 2>&1; then
  echo "pio not on PATH; skipping platformio.txt" >&2
  exit 0
fi

while IFS= read -r line; do
  line="${line%%#*}"
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -z "$line" ]] && continue
  echo "==> pio pkg install --global --platform $line"
  pio pkg install --global --platform "$line"
done <"$list"
