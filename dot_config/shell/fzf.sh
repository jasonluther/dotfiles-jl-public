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

# `fzf --zsh` / `fzf --bash` are fzf 0.48+ (Feb 2024). Debian bookworm
# ships 0.38, Ubuntu 24.04 ships 0.44 — both reject the flag and emit
# "unknown option" at every shell startup. Feature-detect and fall back
# to the legacy keybinding/completion files the apt package still ships.
_fzf_legacy_dirs=(/usr/share/fzf /usr/share/doc/fzf/examples)
if [ -n "${ZSH_VERSION:-}" ]; then
  if fzf --zsh </dev/null >/dev/null 2>&1; then
    source <(fzf --zsh)
  else
    for _d in "${_fzf_legacy_dirs[@]}"; do
      [ -r "$_d/key-bindings.zsh" ] && source "$_d/key-bindings.zsh"
      [ -r "$_d/completion.zsh" ] && source "$_d/completion.zsh"
    done
  fi
elif [ -n "${BASH_VERSION:-}" ]; then
  if fzf --bash </dev/null >/dev/null 2>&1; then
    eval "$(fzf --bash)"
  else
    for _d in "${_fzf_legacy_dirs[@]}"; do
      [ -r "$_d/key-bindings.bash" ] && source "$_d/key-bindings.bash"
      [ -r "$_d/completion.bash" ] && source "$_d/completion.bash"
    done
  fi
fi
unset _fzf_legacy_dirs _d
