# Shell aliases and functions
# Sourced from ~/.zshrc via the dot_config/shell/ fragment loader.

# Useful aliases
# `ls -G` is BSD/macOS-only; GNU coreutils on Linux uses `--color=auto` and
# rejects -G. Feature-detect once at shell startup so each OS gets the right
# flag without an explicit `uname` branch.
if ls --color=auto / >/dev/null 2>&1; then
  alias ls='ls --color=auto'
else
  alias ls='ls -G'
fi
alias grep='grep --color=auto'
alias psg='ps axuw|grep'
alias web-server='python3 -m http.server'
alias root='cd $(git rev-parse --show-toplevel 2>/dev/null)'

# Generate a random password (usage: random-password [length])
random-password() {
  local length=${1:-30}
  export LC_ALL=C
  </dev/urandom tr -dc a-km-zA-HJ-NP-Z2-9_ | head -c"$length"
  echo
}

# Create a git worktree + branch, cd into it, and launch Claude Code
start-work() {
  if [[ -z "$1" ]]; then
    echo "Usage: start-work <branch-name> [claude prompt...]"
    return 1
  fi
  local root
  root=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "Not in a git repository"
    return 1
  }
  local worktree="${root}/../$(basename "$root")-$1"
  start-work-setup "$@" && cd "$worktree"
}

# Repeat a command until it fails/succeeds (useful for flaky tests)
loop_until_fail() {
  local i=0
  while "$@"; do
    echo "[$(date +%H:%M:%S)] iteration: $i"
    i=$(($i + 1))
  done
}
loop_until_success() {
  local i=0
  while ! "$@"; do
    echo "[$(date +%H:%M:%S)] iteration: $i"
    i=$(($i + 1))
  done
}
