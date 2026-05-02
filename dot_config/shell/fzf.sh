# Setup fzf
# ---------
# Add fzf to PATH if Homebrew installed it (works on both AS and Intel).
if command -v brew >/dev/null 2>&1; then
  _fzf_prefix="$(brew --prefix fzf 2>/dev/null)"
  if [[ -n "$_fzf_prefix" && ! "$PATH" == *"$_fzf_prefix/bin"* ]]; then
    PATH="${PATH:+${PATH}:}$_fzf_prefix/bin"
  fi
  unset _fzf_prefix
fi

# Skip integration if fzf isn't installed yet (e.g. first login before brew bundle).
command -v fzf >/dev/null 2>&1 || return 0

if [ -n "${ZSH_VERSION:-}" ]; then
  source <(fzf --zsh)
elif [ -n "${BASH_VERSION:-}" ]; then
  eval "$(fzf --bash)"
fi
