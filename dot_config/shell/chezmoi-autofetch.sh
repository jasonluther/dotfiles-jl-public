# Background fast-forward fetch of the chezmoi source repo.
# Sourced from ~/.zshrc via the dot_config/shell/ fragment loader.
#
# Why a shell fragment instead of launchd/systemd:
#   The rest of this repo prefers portable shell + chezmoi over per-OS
#   service units, and a shell-startup trigger covers the "I just opened a
#   terminal" case that's the actual habit we're replacing. The work runs
#   detached so it never blocks the prompt, and a timestamp gate keeps it
#   from hammering GitHub on every new shell.
#
# What it does NOT do:
#   - No `chezmoi apply`. The existing dot_zshrc drift warning already
#     tells us when to apply, and a silent apply could clobber in-progress
#     local edits to deployed files.
#   - No fetch over a non-FF source. If origin diverged from local, we
#     log and bail — the user resolves it manually.

# Skip non-interactive shells (cron, scp, sftp, plain `ssh host cmd`).
case $- in
  *i*) ;;
  *) return 0 2>/dev/null || exit 0 ;;
esac

# Refuse to run as root: the source dir is owned by $USER, and a root-run
# fetch would leave .git/ objects with mixed ownership.
[ "$(id -u)" -ne 0 ] || return 0 2>/dev/null || exit 0

_chezmoi_autofetch_src="${CHEZMOI_SOURCE_DIR:-$HOME/.local/share/chezmoi}"
[ -d "$_chezmoi_autofetch_src/.git" ] || {
  unset _chezmoi_autofetch_src
  return 0 2>/dev/null
}

_chezmoi_autofetch_state="${XDG_STATE_HOME:-$HOME/.local/state}/chezmoi-autofetch"
_chezmoi_autofetch_stamp="$_chezmoi_autofetch_state/last-run"
_chezmoi_autofetch_log="$_chezmoi_autofetch_state/log"
# Once every 6h. Long enough that opening 20 terminals doesn't fan out 20
# fetches; short enough that a once-a-day login picks up yesterday's push.
_chezmoi_autofetch_interval=21600

mkdir -p "$_chezmoi_autofetch_state" 2>/dev/null || {
  unset _chezmoi_autofetch_src _chezmoi_autofetch_state \
    _chezmoi_autofetch_stamp _chezmoi_autofetch_log \
    _chezmoi_autofetch_interval
  return 0 2>/dev/null
}

# Cheap rate-limit gate: stat the stamp file. If it's newer than the
# interval, skip the whole subshell. Done in the parent so we don't even
# pay the fork cost on most shell starts.
if [ -f "$_chezmoi_autofetch_stamp" ]; then
  _chezmoi_autofetch_now=$(date +%s)
  _chezmoi_autofetch_then=$(
    stat -f %m "$_chezmoi_autofetch_stamp" 2>/dev/null ||
      stat -c %Y "$_chezmoi_autofetch_stamp" 2>/dev/null ||
      echo 0
  )
  if [ $((_chezmoi_autofetch_now - _chezmoi_autofetch_then)) -lt "$_chezmoi_autofetch_interval" ]; then
    unset _chezmoi_autofetch_src _chezmoi_autofetch_state \
      _chezmoi_autofetch_stamp _chezmoi_autofetch_log \
      _chezmoi_autofetch_interval _chezmoi_autofetch_now \
      _chezmoi_autofetch_then
    return 0 2>/dev/null
  fi
  unset _chezmoi_autofetch_now _chezmoi_autofetch_then
fi

# Detached worker. Redirect everything before backgrounding so the job
# table stays clean and `wait` in subshells doesn't pick it up. `setsid`
# is preferred where available (Linux); on macOS we fall back to plain
# `&` plus `disown`, which is enough to survive shell exit.
(
  # mkdir is atomic across POSIX, so it works as a mutex without flock
  # (which doesn't exist on stock macOS). Stale lock from a crashed
  # previous run: clean it up if older than 1h.
  _lock="$_chezmoi_autofetch_state/lock.d"
  if [ -d "$_lock" ]; then
    _lock_age=$(($(date +%s) - $(stat -f %m "$_lock" 2>/dev/null || stat -c %Y "$_lock" 2>/dev/null || date +%s)))
    [ "$_lock_age" -gt 3600 ] && rmdir "$_lock" 2>/dev/null
  fi
  mkdir "$_lock" 2>/dev/null || exit 0
  trap 'rmdir "$_lock" 2>/dev/null' EXIT INT TERM HUP

  # Truncate the log if it's bigger than 64 KiB. We don't need rotation;
  # this is a debug trail, not an audit record.
  if [ -f "$_chezmoi_autofetch_log" ]; then
    _size=$(stat -f %z "$_chezmoi_autofetch_log" 2>/dev/null || stat -c %s "$_chezmoi_autofetch_log" 2>/dev/null || echo 0)
    [ "$_size" -gt 65536 ] && : >"$_chezmoi_autofetch_log"
  fi

  _log() { printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >>"$_chezmoi_autofetch_log"; }

  cd "$_chezmoi_autofetch_src" 2>/dev/null || exit 0

  # Bail on dirty trees. A stash + pop would race the user's editor; an
  # unstaged-aware merge just gets messy. The drift warning in dot_zshrc
  # already nags about uncommitted work.
  if ! git diff --quiet HEAD 2>/dev/null ||
    [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    _log "skip: working tree dirty"
    : >"$_chezmoi_autofetch_stamp"
    exit 0
  fi

  # Need an upstream to fast-forward against. Detached HEAD or branch with
  # no @{u} is fine — just nothing for us to do.
  _branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null) || {
    _log "skip: detached HEAD"
    : >"$_chezmoi_autofetch_stamp"
    exit 0
  }
  _upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null) || {
    _log "skip: '$_branch' has no upstream"
    : >"$_chezmoi_autofetch_stamp"
    exit 0
  }
  _remote="${_upstream%%/*}"

  # Hard timeouts on the network calls so a flaky link can't wedge a
  # locked worker for hours. GIT_HTTP_LOW_SPEED_* are git's built-in
  # equivalents of curl --max-time and work for ssh too via curl.
  GIT_TERMINAL_PROMPT=0 \
    GIT_HTTP_LOW_SPEED_LIMIT=1000 \
    GIT_HTTP_LOW_SPEED_TIME=15 \
    git fetch --quiet --prune "$_remote" 2>>"$_chezmoi_autofetch_log" || {
    _log "fetch failed (network? auth?) — exit clean"
    : >"$_chezmoi_autofetch_stamp"
    exit 0
  }

  _local=$(git rev-parse HEAD 2>/dev/null)
  _remote_head=$(git rev-parse "$_upstream" 2>/dev/null)
  if [ "$_local" = "$_remote_head" ]; then
    _log "up to date at $(echo "$_local" | cut -c1-12)"
  elif git merge-base --is-ancestor HEAD "$_upstream" 2>/dev/null; then
    if git merge --ff-only --quiet "$_upstream" 2>>"$_chezmoi_autofetch_log"; then
      _log "fast-forwarded $(echo "$_local" | cut -c1-12) -> $(echo "$_remote_head" | cut -c1-12)"
    else
      _log "ff merge failed unexpectedly"
    fi
  else
    # Local has commits origin doesn't, or the histories diverged. Either
    # way: not our problem to resolve; the dot_zshrc warning + manual
    # `git pull --rebase` cover it.
    _log "skip: local diverged from $_upstream (not fast-forwardable)"
  fi

  : >"$_chezmoi_autofetch_stamp"
) </dev/null >/dev/null 2>&1 &
disown 2>/dev/null || true

unset _chezmoi_autofetch_src _chezmoi_autofetch_state \
  _chezmoi_autofetch_stamp _chezmoi_autofetch_log \
  _chezmoi_autofetch_interval
