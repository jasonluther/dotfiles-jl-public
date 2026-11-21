# shellcheck shell=bash
# GitHub sign-in. The owner's own gh login (gh auth login --expiring) stays his; agent
# sessions (Claude Code sets CLAUDECODE and AI_AGENT) sign in as the kilotronic-agents App
# through `keys` (kilotronic/keys): ~/.local/bin/gh routes their gh calls, and git asks
# `keys git-credential`. Design: jasonluther/auditor practices/key-rotation.md.
export KEYS_GH_APP=kilotronic-agents
export KEYS_GH_DEFAULT_OWNER=jasonluther

# Loaded from both .zshenv (every zsh, scripts included) and .zshrc: apply once.
if [[ -n "${CLAUDECODE:-}${AI_AGENT:-}" && -z "${_KEYS_GIT_SET:-}" ]] && command -v keys &>/dev/null; then
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
