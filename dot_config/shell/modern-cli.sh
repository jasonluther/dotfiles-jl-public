#!/usr/bin/env zsh
# Modern CLI Tools Configuration
# Sourced from ~/.zshrc via the dot_config/shell/ fragment loader.

# ========================================
# ripgrep
# ========================================

export RIPGREP_CONFIG_PATH="$HOME/.ripgreprc"

# rg config is in ~/.ripgreprc (smart-case, colors)
alias rgf='rg --files-with-matches' # Show only filenames
alias rgi='rg --no-ignore'          # Include ignored files

# ========================================
# bat - Better cat
# ========================================

export BAT_THEME="TwoDark"
export BAT_STYLE="numbers,changes,header"

# Use bat as man pager
export MANPAGER="sh -c 'col -bx | bat -l man -p'"
export MANROFFOPT="-c"

alias cat='bat'
alias less='bat'
alias preview='bat --style=plain'

# ========================================
# eza - Better ls
# ========================================

# Git-aware listing
if command -v eza &>/dev/null; then
  alias lg='eza -l --git --git-ignore --icons'
fi

# ========================================
# delta - Git diff viewer
# ========================================
# (Configured in .gitconfig)

# ========================================
# Quick directory jumps
# ========================================

alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias -- -='cd -' # Go to previous directory

# ========================================
# Editor
# ========================================

export EDITOR='code --wait'
export VISUAL='code --wait'

# ========================================
# Misc defaults
# ========================================

export LESS='-R'         # Raw color codes in less
export GREP_COLOR='1;32' # Green grep matches
