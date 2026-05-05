#!/usr/bin/env bash
# Install Mac App Store apps listed in mas.txt that aren't already in /Applications.
#
# Why filesystem check instead of `mas list`:
#   `mas list` is unreliable on recent macOS (Apple changed the StoreKit APIs);
#   it often returns stale or empty results, which causes brew bundle to retry
#   `mas install` for already-installed apps and trigger an Apple ID auth loop.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
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

# Install one at a time so an "unpurchased" / region-locked app doesn't take
# down the rest of the batch. `mas install` prints "No downloads initiated for
# ADAM ID …" for apps that aren't in the signed-in Apple ID's purchase
# history; treat those as a soft skip rather than a script-level failure.
declare -a unpurchased=()
declare -a failed=()
for i in "${!missing_ids[@]}"; do
  id="${missing_ids[$i]}"
  name="${missing_names[$i]}"
  echo "==> mas install $id ($name)"
  output=$(mas install "$id" 2>&1) && status=0 || status=$?
  printf '%s\n' "$output"
  if ((status == 0)); then
    continue
  fi
  if [[ "$output" == *"No downloads initiated"* ]]; then
    unpurchased+=("$name ($id)")
  else
    failed+=("$name ($id)")
  fi
done

if ((${#unpurchased[@]} > 0)); then
  printf '\033[1;33mskipped (not purchased on this Apple ID):\033[0m\n' >&2
  for n in "${unpurchased[@]}"; do printf '  - %s\n' "$n" >&2; done
fi
if ((${#failed[@]} > 0)); then
  printf '\033[1;31mfailed to install:\033[0m\n' >&2
  for n in "${failed[@]}"; do printf '  - %s\n' "$n" >&2; done
  exit 1
fi
