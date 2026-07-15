#!/usr/bin/env bash
# macOS System Preferences Setup
# Idempotent — re-run anytime to reapply preferences.

set -euo pipefail

# Dock
defaults write com.apple.dock autohide -bool true
defaults write com.apple.dock show-recents -bool false
# Dock: don't rearrange spaces, group Mission Control by app
defaults write com.apple.dock mru-spaces -bool false
defaults write com.apple.dock expose-group-apps -bool true

# Dock: pin exactly these apps, in this order. Apps not yet installed
# (e.g. Slack on a fresh bootstrap before mas-apps runs) are skipped with
# a warning — rerun this script after the missing app installs to backfill.
pinned_apps=(
  "/Applications/Safari.app"
  "/System/Applications/Utilities/Terminal.app"
  "/Applications/Slack.app"
  "/System/Applications/Calendar.app"
  "/System/Applications/Reminders.app"
  "/Applications/Google Chrome.app"
  "/System/Applications/Messages.app"
)
dock_tile() {
  printf '<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>file://%s/</string><key>_CFURLStringType</key><integer>15</integer></dict></dict></dict>' "$1"
}
tiles=()
missing=()
for app in "${pinned_apps[@]}"; do
  if [[ -d "$app" ]]; then
    # Resolve symlinks so Safari (which lives in /System/Cryptexes/...
    # with a symlink at /Applications/Safari.app) doesn't render with
    # the Dock's "alias" badge. Other apps are not symlinks; pwd -P is
    # a no-op for them.
    real_app="$(cd "$app" && pwd -P)"
    tiles+=("$(dock_tile "$real_app")")
  else
    missing+=("$app")
  fi
done
if ((${#missing[@]} > 0)); then
  printf 'dock pin: skipping (not installed): %s\n' "${missing[@]}" >&2
fi
defaults write com.apple.dock persistent-apps -array "${tiles[@]}"

# Dock: keep Downloads on the right side as a stack sorted by Date Added so
# the most-recently-downloaded file is on top. arrangement=2 (Date Added),
# displayas=0 (Stack), showas=0 (Automatic — fan when small, grid when large).
downloads_tile='<dict><key>tile-data</key><dict><key>arrangement</key><integer>2</integer><key>displayas</key><integer>0</integer><key>file-data</key><dict><key>_CFURLString</key><string>file://'"${HOME}"'/Downloads/</string><key>_CFURLStringType</key><integer>15</integer></dict><key>file-type</key><integer>2</integer><key>showas</key><integer>0</integer></dict><key>tile-type</key><string>directory-tile</string></dict>'
defaults write com.apple.dock persistent-others -array "$downloads_tile"

# Hot corners: disable all four. macOS Tahoe defaults Quick Note into the
# bottom-right corner, so leaving these unset is not a clean slate — they
# must be explicitly written to 1 (no action).
for corner in tl tr bl br; do
  defaults write com.apple.dock "wvous-${corner}-corner" -int 1
  defaults write com.apple.dock "wvous-${corner}-modifier" -int 0
done

killall Dock || true

# Defer password autofill to the 1Password browser extensions.
# Safari's preference file lives inside its TCC-protected container; the
# write succeeds only if the terminal running this script has Full Disk
# Access (System Settings > Privacy & Security > Full Disk Access). Soft-
# fail so the rest of the script still runs on a fresh Mac; the user can
# grant FDA and re-run.
if ! defaults write com.apple.Safari AutoFillPasswords -bool false 2>/dev/null; then
  echo "warn: couldn't disable Safari AutoFillPasswords — grant Full Disk Access to your terminal and re-run." >&2
fi
# Chrome: disable the built-in password manager. Chrome's PolicyLoaderMac
# reads policies via MCX/Managed Preferences, NOT from the per-user
# defaults domain — so a plain `defaults write com.google.Chrome ...`
# is silently ignored. Write to the system-wide plist with sudo instead;
# CFPreferences then surfaces it as a policy. A cloud-managed Google
# account can still override; in that case the setting needs to be
# changed on the policy side.
sudo defaults write /Library/Preferences/com.google.Chrome PasswordManagerEnabled -bool false

# Expand save panel by default
defaults write NSGlobalDomain NSNavPanelExpandedStateForSaveMode -bool true
defaults write NSGlobalDomain NSNavPanelExpandedStateForSaveMode2 -bool true
# Expand print panel by default
defaults write NSGlobalDomain PMPrintingExpandedStateForPrint -bool true
defaults write NSGlobalDomain PMPrintingExpandedStateForPrint2 -bool true
# Save to disk (not to iCloud) by default
defaults write NSGlobalDomain NSDocumentSaveNewDocumentsToCloud -bool false
# Automatically quit printer app once the print jobs complete
defaults write com.apple.print.PrintingPrefs "Quit When Finished" -bool true
# Enable full keyboard access for all controls (e.g. Tab in modal dialogs)
defaults write NSGlobalDomain AppleKeyboardUIMode -int 3
# Enable the automatic update check
defaults write com.apple.SoftwareUpdate AutomaticCheckEnabled -bool true
# Check for software updates daily, not just once per week
defaults write com.apple.SoftwareUpdate ScheduleFrequency -int 1
# Download newly available updates in background
defaults write com.apple.SoftwareUpdate AutomaticDownload -bool true
# Install security responses automatically
defaults write com.apple.SoftwareUpdate CriticalUpdateInstall -bool true
# Install system data files (XProtect, MRT, etc.)
defaults write com.apple.SoftwareUpdate ConfigDataInstall -bool true
# Turn on app auto-update
defaults write com.apple.commerce AutoUpdate -bool true

# Disable "smart" text munging that breaks code/markdown
defaults write NSGlobalDomain NSAutomaticCapitalizationEnabled -bool false
defaults write NSGlobalDomain NSAutomaticDashSubstitutionEnabled -bool false
defaults write NSGlobalDomain NSAutomaticPeriodSubstitutionEnabled -bool false
defaults write NSGlobalDomain NSAutomaticQuoteSubstitutionEnabled -bool false
defaults write NSGlobalDomain NSAutomaticSpellingCorrectionEnabled -bool false

# Finder
defaults write com.apple.finder AppleShowAllFiles -bool true
defaults write com.apple.finder ShowPathbar -bool true
defaults write com.apple.finder ShowStatusBar -bool true
defaults write com.apple.finder FXDefaultSearchScope -string "SCcf"
defaults write com.apple.finder FXEnableExtensionChangeWarning -bool false
defaults write NSGlobalDomain AppleShowAllExtensions -bool true
killall Finder || true

# Screenshot
defaults write com.apple.screencapture show-thumbnail -bool true
mkdir -p "${HOME}/Desktop/Screenshots"
defaults write com.apple.screencapture location -string "${HOME}/Desktop/Screenshots"
defaults write com.apple.screencapture type -string "png"
defaults write com.apple.screencapture disable-shadow -bool true

# Scroll bars
defaults write NSGlobalDomain AppleShowScrollBars -string "WhenScrolling"

# Power Management (requires sudo)
sudo pmset -a womp 1
# Power Nap is always-on and not configurable on Apple Silicon — only set on Intel
if [[ "$(uname -m)" == "x86_64" ]]; then
  sudo pmset -a powernap 1
fi
# Idle sleep after 15 minutes (all power sources). Pinned because a stray
# `sleep 1` on one machine idle-slept it mid-CI-run — macOS sleeps regardless
# of CPU load, and a slept host suspends OrbStack's VM, wedging every
# container-backed test until a human wakes it (partygame, 2026-07-15).
# Long-running work holds its own assertions (caffeinate in with_ci_slot.py
# and the runner job hooks), so 15 minutes here means truly idle.
sudo pmset -a sleep 15
