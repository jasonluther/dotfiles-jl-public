#!/usr/bin/env bash
# Switch the login shell to zsh if it isn't already.
#
# Idempotent — exits 0 when the current login shell already points at zsh,
# or when zsh isn't installed (the packages installer will pick it up on a
# later run; the chezmoi wrapper re-fires on script changes only, so users
# get one more nudge whenever this script is edited).
#
# Requires sudo on Linux: chsh edits /etc/passwd. On macOS the user can
# usually chsh without sudo, but using sudo there too keeps the script
# uniform and survives MDM-managed accounts.

set -euo pipefail

if ! zsh_path="$(command -v zsh)"; then
  echo "chsh-to-zsh: zsh not installed yet — skipping" >&2
  exit 0
fi

# `$USER` isn't always set (Docker containers, su -, some launchd contexts);
# `id -un` is reliable everywhere.
current_user="${USER:-$(id -un)}"

case "$(uname)" in
  Darwin)
    current="$(dscl . -read "/Users/$current_user" UserShell 2>/dev/null | awk '{print $2}')"
    ;;
  *)
    current="$(getent passwd "$current_user" | cut -d: -f7)"
    ;;
esac

if [[ "$current" == "$zsh_path" ]]; then
  echo "chsh-to-zsh: login shell already $zsh_path"
  exit 0
fi

# /etc/shells must list zsh or chsh refuses. Debian's zsh postinst adds it,
# but be defensive in case zsh was installed via a path /etc/shells doesn't know.
if [[ -f /etc/shells ]] && ! grep -qxF "$zsh_path" /etc/shells; then
  echo "chsh-to-zsh: adding $zsh_path to /etc/shells"
  echo "$zsh_path" | sudo tee -a /etc/shells >/dev/null
fi

echo "==> chsh -s $zsh_path $current_user (was $current)"
sudo chsh -s "$zsh_path" "$current_user"
