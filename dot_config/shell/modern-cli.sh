#!/usr/bin/env zsh
# Modern CLI Tools Configuration
# Sourced from ~/.zshrc via the dot_config/shell/ fragment loader.

# ========================================
# fzf - Fuzzy Finder
# ========================================

# (fzf keybindings/completions loaded by fzf.sh)

# fzf configuration
export FZF_DEFAULT_COMMAND='rg --files --hidden --follow --glob "!.git/*"'
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
export FZF_ALT_C_COMMAND='fd --type d --hidden --follow --exclude .git'

# fzf color scheme (match VSCode dark theme)
export FZF_DEFAULT_OPTS='
  --height 40%
  --layout=reverse
  --border
  --inline-info
  --color=fg:#c0caf5,bg:#1a1b26,hl:#7aa2f7
  --color=fg+:#c0caf5,bg+:#292e42,hl+:#7dcfff
  --color=info:#7aa2f7,prompt:#7dcfff,pointer:#7dcfff
  --color=marker:#9ece6a,spinner:#9ece6a,header:#9ece6a
'

# ========================================
# ripgrep Configuration
# ========================================

export RIPGREP_CONFIG_PATH="$HOME/.ripgreprc"

# ========================================
# bat - Better cat
# ========================================

export BAT_THEME="TwoDark"
export BAT_STYLE="numbers,changes,header"

# Use bat as man pager
export MANPAGER="sh -c 'col -bx | bat -l man -p'"
export MANROFFOPT="-c"

# # ========================================
# # eza - Better ls
# # ========================================

# # eza aliases
# alias ls='eza'
# alias ll='eza -l --git --icons'
# alias la='eza -la --git --icons'
# alias lt='eza --tree --level=2 --icons'
# alias lta='eza --tree --level=2 --icons -a'
# alias ltree='eza --tree --icons'

# Git-aware listing (requires eza: brew install eza)
if command -v eza &>/dev/null; then
  alias lg='eza -l --git --git-ignore --icons'
fi

# ========================================
# delta - Git diff viewer
# ========================================
# (Configured in .gitconfig)

# # ========================================
# # tldr - Simplified man pages
# # ========================================

# # Update tldr cache on first use
# if [[ ! -d "$HOME/.local/share/tldr" ]]; then
#   tldr --update
# fi

# ========================================
# Additional Helpful Aliases
# ========================================

# Search aliases
# rg config is in ~/.ripgreprc (smart-case, colors)
alias rgf='rg --files-with-matches' # Show only filenames
alias rgi='rg --no-ignore'          # Include ignored files

# File viewing
alias cat='bat'
alias less='bat'
alias preview='bat --style=plain'

# Quick directory jumps
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'
alias -- -='cd -' # Go to previous directory

# Git with fzf integrations
alias gch='git checkout $(git branch -a | fzf | sed "s/remotes\/origin\///")'
alias gbr='git branch | fzf'

# Find and edit
function fe() {
  local file
  file=$(fzf --preview="bat --color=always --line-range :500 {}")
  [[ -n "$file" ]] && ${EDITOR:-vim} "$file"
}

# Find in files and edit
function fr() {
  local file line
  read -r file line <<<$(rg --line-number "$1" | fzf --delimiter : --preview 'bat --color=always --highlight-line {2} {1}' | awk -F: '{print $1, $2}')
  [[ -n "$file" ]] && ${EDITOR:-vim} "+$line" "$file"
}

# Kill process with fzf
function fkill() {
  local pid
  pid=$(ps -ef | sed 1d | fzf -m | awk '{print $2}')
  if [ -n "$pid" ]; then
    echo "$pid" | xargs kill -${1:-9}
  fi
}

# Git log with fzf
function glog() {
  git log --oneline --color=always | fzf --ansi --preview="git show --color=always {1}" --bind="enter:execute(git show {1} | less -R)"
}

# ========================================
# Environment Variables
# ========================================

# Set editors
export EDITOR='code --wait'
export VISUAL='code --wait'

# Better defaults
export LESS='-R'         # Raw color codes in less
export GREP_COLOR='1;32' # Green grep matches
