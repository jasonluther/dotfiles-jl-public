# shellcheck shell=bash
# GitHub sign-in. The owner's own gh login (gh auth login --expiring) stays his; agent
# sessions (Claude Code sets CLAUDECODE and AI_AGENT) sign in as the repo owner's App
# through `keys` (kilotronic/keys): ~/.local/bin/gh routes their gh calls, and git asks
# `keys git-credential`. Which App serves which owner (KEYS_GH_APPS) and the default owner
# are set in ~/.config/keys/apps.sh, kept in the private dotfiles; without it agents have
# no App and are refused. Design: jasonluther/auditor practices/key-rotation.md.
# shellcheck source=/dev/null
[ -r "$HOME/.config/keys/apps.sh" ] && . "$HOME/.config/keys/apps.sh"

# Loaded from both .zshenv (every zsh, scripts included) and .zshrc: apply once.
# Not gated on keys being installed: without it the helper fails and git stops, never
# falling back to the owner's own login.
if [[ -n "${CLAUDECODE:-}${AI_AGENT:-}" && -z "${_KEYS_GIT_SET:-}" ]]; then
  export _KEYS_GIT_SET=1
  # Reset github.com's helpers (an empty value clears the list), then ask keys, with the
  # repo path so it can pick the owner's installation.
  _n=${GIT_CONFIG_COUNT:-0}
  export "GIT_CONFIG_KEY_$_n=credential.https://github.com.helper" "GIT_CONFIG_VALUE_$_n="
  export "GIT_CONFIG_KEY_$((_n + 1))=credential.https://github.com.helper" \
    "GIT_CONFIG_VALUE_$((_n + 1))=!keys git-credential"
  export "GIT_CONFIG_KEY_$((_n + 2))=credential.https://github.com.useHttpPath" \
    "GIT_CONFIG_VALUE_$((_n + 2))=true"
  export GIT_CONFIG_COUNT=$((_n + 3))
  unset _n
fi
