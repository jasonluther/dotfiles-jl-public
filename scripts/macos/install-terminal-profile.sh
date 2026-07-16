#!/bin/bash
# Install a Terminal profile and set it as the default.
#
# Run manually on a fresh machine after dotfiles bootstrap:
#   ~/.local/share/chezmoi/scripts/macos/install-terminal-profile.sh
#
# Pass a profile path to install a different one, e.g. the personal overlay's:
#   .../install-terminal-profile.sh ~/.local/share/chezmoi-personal/scripts/macos/"Jason 2026.terminal"
#
# Idempotent — re-running is safe.
#
# Quit Terminal.app first if it's running. macOS caches preferences in
# memory while Terminal is running and may overwrite our changes on its
# next quit. The script kills cfprefsd to flush the cache after writing,
# but won't help if Terminal.app itself is open.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Optional arg: path to a .terminal profile (default: the repo's own).
PROFILE_FILE="${1:-$SCRIPT_DIR/Terminal 2026.terminal}"
PROFILE_NAME="$(basename "$PROFILE_FILE" .terminal)"
TERM_PLIST="$HOME/Library/Preferences/com.apple.Terminal.plist"

if [ ! -f "$PROFILE_FILE" ]; then
  echo "Profile file not found: $PROFILE_FILE" >&2
  exit 1
fi

if pgrep -xq Terminal; then
  echo "Terminal.app is running. Quit it first, then re-run this script." >&2
  exit 1
fi

# Idempotent merge: delete-then-add so re-runs don't accumulate dupes.
/usr/libexec/PlistBuddy -c "Delete :'Window Settings':'$PROFILE_NAME'" "$TERM_PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :'Window Settings':'$PROFILE_NAME' dict" "$TERM_PLIST"
/usr/libexec/PlistBuddy -c "Merge '$PROFILE_FILE' :'Window Settings':'$PROFILE_NAME'" "$TERM_PLIST"

# Set as default for new and startup windows.
defaults write com.apple.Terminal "Default Window Settings" -string "$PROFILE_NAME"
defaults write com.apple.Terminal "Startup Window Settings" -string "$PROFILE_NAME"

# Flush prefs cache so Terminal picks up the new profile on next launch.
killall cfprefsd 2>/dev/null || true

echo "Installed and set default to: $PROFILE_NAME"
