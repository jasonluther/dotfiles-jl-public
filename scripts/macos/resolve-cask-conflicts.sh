#!/usr/bin/env bash
# Detect Brewfile casks that collide with apps already installed by another
# source (manual drag-install, vendor .pkg, Mac App Store) and resolve the
# collision before `brew bundle` runs:
#
#   1. brew already manages the cask -> nothing to do.
#   2. Matching .app exists on disk -> try `brew install --cask --adopt`,
#      which takes ownership in place when the bytes match the cask.
#   3. Adoption fails -> print a remediation hint and emit the cask name on
#      stdout so the caller can exclude it from `brew bundle` (otherwise the
#      bundle run would abort on the same conflict).
#
# Usage: resolve-cask-conflicts.sh <Brewfile>
# Stdout: one cask name per line for unresolved conflicts (caller filters).
# Stderr: human-readable progress + warnings.

set -euo pipefail

brewfile="${1:?usage: $0 <Brewfile>}"
[[ -f "$brewfile" ]] || exit 0
command -v brew >/dev/null 2>&1 || exit 0
if ! command -v jq >/dev/null 2>&1; then
  echo "resolve-cask-conflicts: jq missing; skipping conflict detection." >&2
  exit 0
fi

# Collect candidate .app filenames a cask would create. Drag-install casks
# expose them in artifacts[].app; pkg-based casks (e.g. tailscale-app) don't,
# so fall back to the human-readable .name field.
cask_app_candidates() {
  brew info --cask --json=v2 "$1" 2>/dev/null | jq -r '
    .casks[]? | (
      (.artifacts[]? | objects | .app[]? | select(type == "string")),
      (.name[]? | "\(.).app")
    )
  '
}

while IFS= read -r cask; do
  [[ -z "$cask" ]] && continue
  brew list --cask "$cask" >/dev/null 2>&1 && continue

  mapfile -t apps < <(cask_app_candidates "$cask")

  conflict=""
  for app in "${apps[@]:-}"; do
    [[ -z "$app" ]] && continue
    if [[ -d "/Applications/$app" || -d "$HOME/Applications/$app" ]]; then
      conflict="$app"
      break
    fi
  done
  [[ -z "$conflict" ]] && continue

  echo "==> $cask: '$conflict' already installed, attempting --adopt..." >&2
  if brew install --cask --adopt "$cask" >/dev/null 2>&1; then
    echo "    adopted by brew." >&2
  else
    printf '\033[1;33m    skipped: %s differs from cask. Remove it manually or run: brew install --cask --force %s\033[0m\n' \
      "$conflict" "$cask" >&2
    echo "$cask"
  fi
done < <(awk -F'"' '/^[[:space:]]*cask "/ {print $2}' "$brewfile")
