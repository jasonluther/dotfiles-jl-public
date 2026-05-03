#!/usr/bin/env bash
# Configure arduino-cli with board-manager URLs, then install cores and
# libraries from packages/arduino-{board-urls,cores,libraries}.txt.
# All arduino-cli operations are idempotent — re-run any time.
#
# arduino-cli itself comes from brew on macOS. On Linux it isn't in apt;
# this script will print install instructions and exit if it's missing.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
URLS="$SRC/packages/arduino-board-urls.txt"
CORES="$SRC/packages/arduino-cores.txt"
LIBS="$SRC/packages/arduino-libraries.txt"

if ! command -v arduino-cli >/dev/null 2>&1; then
  cat >&2 <<EOF
arduino-cli not found on PATH.

  macOS:   brew install arduino-cli
  Debian:  curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR="\$HOME/.local/bin" sh

Re-run this script after installing.
EOF
  exit 0
fi

read_list() {
  local arr_name="$1" path="$2" line
  eval "$arr_name=()"
  [[ -f "$path" ]] || return 0
  while IFS= read -r line; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -n "$line" ]] && eval "$arr_name+=(\"\$line\")"
  done <"$path"
}

declare -a urls cores libs
read_list urls "$URLS"
read_list cores "$CORES"
read_list libs "$LIBS"

if [[ ${#urls[@]} -gt 0 ]]; then
  echo "==> arduino-cli config — adding ${#urls[@]} board-manager URL(s)"
  for u in "${urls[@]}"; do
    arduino-cli config add board_manager.additional_urls "$u" 2>/dev/null || true
  done
fi

echo "==> arduino-cli core update-index"
arduino-cli core update-index

if [[ ${#cores[@]} -gt 0 ]]; then
  echo "==> arduino-cli core install (${#cores[@]} cores)"
  for c in "${cores[@]}"; do
    arduino-cli core install "$c" || true
  done
fi

if [[ ${#libs[@]} -gt 0 ]]; then
  echo "==> arduino-cli lib install (${#libs[@]} libraries)"
  for l in "${libs[@]}"; do
    arduino-cli lib install "$l" || true
  done
fi

echo "✓ arduino-cli setup complete"
