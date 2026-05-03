#!/usr/bin/env bash
# Install Mac App Store apps listed in mas.txt that aren't already in /Applications.
#
# Why filesystem check instead of `mas list`:
#   `mas list` is unreliable on recent macOS (Apple changed the StoreKit APIs);
#   it often returns stale or empty results, which causes brew bundle to retry
#   `mas install` for already-installed apps and trigger an Apple ID auth loop.

set -euo pipefail

[[ "$(uname -s)" == "Darwin" ]] || exit 0

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mas_file="$SRC/mas.txt"

[[ -f "$mas_file" ]] || exit 0

if ! command -v mas >/dev/null 2>&1; then
  echo "mas not installed; run brew bundle first." >&2
  exit 1
fi

missing_ids=()
missing_names=()
while IFS=' ' read -r id name; do
  [[ -z "${id:-}" || "$id" == \#* ]] && continue
  if [[ -d "/Applications/${name}.app" || -d "${HOME}/Applications/${name}.app" ]]; then
    continue
  fi
  missing_ids+=("$id")
  missing_names+=("$name")
done <"$mas_file"

if [[ ${#missing_ids[@]} -eq 0 ]]; then
  echo "All Mac App Store apps already installed."
  exit 0
fi

echo "Installing ${#missing_ids[@]} Mac App Store app(s):"
for n in "${missing_names[@]}"; do echo "  - $n"; done

mas install "${missing_ids[@]}"
