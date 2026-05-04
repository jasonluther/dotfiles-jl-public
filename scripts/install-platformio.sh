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

failed=()
while IFS= read -r line; do
  line="${line%%#*}"
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  [[ -z "$line" ]] && continue
  echo "==> pio pkg install --global --platform $line"
  # Don't abort on a single platform failure: PlatformIO doesn't publish
  # toolchain-gccarmnoneeabi for arm64 Linux yet, so any platform needing
  # ARM toolchain (atmelsam, raspberrypi, parts of espressif32) fails on
  # that host. Other hosts/platforms shouldn't suffer for it.
  if ! pio pkg install --global --platform "$line"; then
    failed+=("$line")
  fi
done <"$list"

if [[ ${#failed[@]} -gt 0 ]]; then
  printf '\033[1;33mwarning:\033[0m platform install failed for: %s\n' "${failed[*]}" >&2
  printf '  (PlatformIO may not publish a toolchain build for this host arch.)\n' >&2
fi
