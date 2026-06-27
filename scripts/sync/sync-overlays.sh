#!/usr/bin/env bash
# Pull AND apply every chezmoi overlay layered on top of the public source, so
# a plain `chezmoi apply` / `chezmoi update` deploys overlays automatically.
#
# Overlays are discovered by globbing ~/.local/share/chezmoi-* — the public
# source at ~/.local/share/chezmoi (no suffix) is never matched, so this can't
# recurse into the source it runs inside. Silent on public-only machines
# (empty glob = no-op).
#
# Each overlay applies with its OWN persistent-state DB. A nested `chezmoi
# apply` that shares the default state deadlocks ("timeout obtaining persistent
# state lock"), because the outer public apply still holds that lock while this
# run_after script executes. Per-overlay state files sidestep the lock and keep
# each overlay's run_onchange bookkeeping isolated.
#
# --force on the overlay apply: a fresh per-overlay state DB has no record of
# the shared private dirs (~/.claude, ~/.local, ~/.ssh) that the public source
# also manages, so without --force chezmoi would prompt ("has changed since
# chezmoi last wrote it") on them and abort under a non-interactive apply. The
# overlay owns the files it writes, so forcing them is safe.
#
# Fail-safe: a stuck pull or a failing overlay apply warns but never aborts the
# public apply.
set -uo pipefail

# Belt-and-braces: if an overlay ever ships this same script, the nested apply
# inherits this flag and skips, so overlays can't cascade into each other.
if [ "${CHEZMOI_OVERLAY_SYNC:-}" = "1" ]; then
  exit 0
fi
export CHEZMOI_OVERLAY_SYNC=1

state_dir="${XDG_CONFIG_HOME:-$HOME/.config}/chezmoi"
mkdir -p "$state_dir"

shopt -s nullglob
overlays=("$HOME"/.local/share/chezmoi-*)
shopt -u nullglob

for overlay in "${overlays[@]}"; do
  [ -d "$overlay/.git" ] || continue
  flavor="${overlay##*/chezmoi-}"

  if ! git -C "$overlay" pull --ff-only --quiet; then
    echo "warning: overlay $flavor: git pull --ff-only failed (resolve manually)" >&2
  fi

  if ! chezmoi --source "$overlay" \
    --persistent-state "$state_dir/chezmoistate-$flavor.boltdb" \
    apply --force; then
    echo "warning: overlay $flavor: chezmoi apply failed" >&2
  fi
done
