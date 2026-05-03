#!/usr/bin/env bash
# Sync the operator's GitHub-published SSH keys into ~/.ssh/authorized_keys.
# GitHub serves them at https://github.com/<user>.keys with no auth required.
#
# Keys are managed inside a marked block so revocations on GitHub propagate to
# the host on re-run. Anything outside the block (e.g. keys you added manually)
# is preserved.

set -euo pipefail

GH_USER="${GH_USER:-jasonluther}"
SRC_URL="https://github.com/${GH_USER}.keys"
DEST="$HOME/.ssh/authorized_keys"
# Block markers kept verbatim for back-compat with hosts originally bootstrapped
# via the (now-retired) jasonluther/first-time repo. Changing them would orphan
# the existing block and append a duplicate on re-run.
BEGIN="# BEGIN first-time"
END="# END first-time"

mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
touch "$DEST"
chmod 600 "$DEST"

tmp="$(mktemp)"
filtered="$(mktemp)"
trap 'rm -f "$tmp" "$filtered"' EXIT
curl -fsSL "$SRC_URL" -o "$tmp"

if [[ ! -s "$tmp" ]]; then
  echo "error: $SRC_URL returned no keys; upload at least one SSH key to GitHub first" >&2
  exit 1
fi

# Drop any existing managed block from the destination.
awk -v B="$BEGIN" -v E="$END" '
  $0 == B          { in_block = 1; next }
  in_block && $0 == E { in_block = 0; next }
  !in_block        { print }
' "$DEST" >"$filtered"

# Trim trailing whitespace/newlines so the rewritten file stays tidy.
content="$(cat "$filtered")"
content="${content%"${content##*[![:space:]]}"}"

count=0
{
  [[ -n "$content" ]] && printf '%s\n' "$content"
  printf '%s\n' "$BEGIN"
  printf '# Source: %s\n' "$SRC_URL"
  while IFS= read -r line; do
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    printf '%s\n' "$line"
    count=$((count + 1))
  done <"$tmp"
  printf '%s\n' "$END"
} >"$DEST"
chmod 600 "$DEST"

echo "authorized_keys: synced $count key(s) from $SRC_URL"
