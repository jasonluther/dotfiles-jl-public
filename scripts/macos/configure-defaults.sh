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
killall Dock || true

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
