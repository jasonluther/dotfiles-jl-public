# Detached, rate-limited fast-forward fetch of the chezmoi source repo.
# Sourced from ~/.zshrc via the dot_config/shell/ fragment loader.
#
# Stays out of the prompt path: the parent shell only does cheap builtin
# checks before deciding to fork the worker, and the worker itself runs
# in a fully-detached subshell.
#
# Does NOT run `chezmoi apply` — the dot_zshrc drift warning surfaces
# pending changes, and a silent apply could clobber in-progress edits.
# Skips on dirty trees, detached HEAD, or non-FF divergence.

# Skip non-interactive shells (cron, scp, sftp, plain `ssh host cmd`).
case $- in
  *i*) ;;
  *) return 0 2>/dev/null || exit 0 ;;
esac

# Root would write .git objects with mixed ownership.
[ "${EUID:-$(id -u)}" -ne 0 ] || return 0 2>/dev/null || exit 0

_caf_src="${CHEZMOI_SOURCE_DIR:-$HOME/.local/share/chezmoi}"
_caf_state="${XDG_STATE_HOME:-$HOME/.local/state}/chezmoi-autofetch"
_caf_stamp="$_caf_state/last-run"
_caf_log="$_caf_state/log"
# 6h: opening 20 terminals doesn't fan out 20 fetches; once-a-day login
# still picks up yesterday's push.
_caf_interval=21600

# GNU `stat -c` first, BSD `stat -f` fallback. The reverse order silently
# misbehaves on Linux: GNU stat has both flags, but `-f` means "filesystem
# info" not "format" — `-f %m` returns a mount-point path, breaking the
# arithmetic on line 50.
_caf_mtime() { stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0; }
_caf_size() { stat -c %s "$1" 2>/dev/null || stat -f %z "$1" 2>/dev/null || echo 0; }
_caf_now() { echo "${EPOCHSECONDS:-$(date +%s)}"; }

_caf_cleanup() {
  unset _caf_src _caf_state _caf_stamp _caf_log _caf_interval
  unset -f _caf_mtime _caf_size _caf_now _caf_cleanup 2>/dev/null
}

[ -d "$_caf_src/.git" ] || {
  _caf_cleanup
  return 0 2>/dev/null
}
[ -d "$_caf_state" ] || mkdir -p "$_caf_state" 2>/dev/null \
  || {
    _caf_cleanup
    return 0 2>/dev/null
  }

# Rate-limit gate: bail before forking the worker if we ran recently.
if [ -f "$_caf_stamp" ] \
  && [ $(($(_caf_now) - $(_caf_mtime "$_caf_stamp"))) -lt "$_caf_interval" ]; then
  _caf_cleanup
  return 0 2>/dev/null
fi

(
  # mkdir is atomic across POSIX (no flock on stock macOS). Reap a stale
  # lock from a crashed previous run.
  _lock="$_caf_state/lock.d"
  if [ -d "$_lock" ] \
    && [ $(($(_caf_now) - $(_caf_mtime "$_lock"))) -gt 3600 ]; then
    rmdir "$_lock" 2>/dev/null
  fi
  mkdir "$_lock" 2>/dev/null || exit 0
  trap 'rmdir "$_lock" 2>/dev/null' EXIT INT TERM HUP

  [ "$(_caf_size "$_caf_log")" -gt 65536 ] && : >"$_caf_log"

  _log() { printf '[%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$*" >>"$_caf_log"; }
  _stamp_and_exit() {
    : >"$_caf_stamp"
    exit 0
  }

  cd "$_caf_src" 2>/dev/null || exit 0

  # A stash + pop would race the user's editor. The dot_zshrc drift
  # warning already nags about uncommitted source-repo work.
  if ! git diff --quiet HEAD 2>/dev/null \
    || [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    _log "skip: working tree dirty"
    _stamp_and_exit
  fi

  _branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null) || {
    _log "skip: detached HEAD"
    _stamp_and_exit
  }
  _upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null) || {
    _log "skip: '$_branch' has no upstream"
    _stamp_and_exit
  }
  _remote="${_upstream%%/*}"

  # GIT_HTTP_LOW_SPEED_* keep a flaky link from wedging a locked worker.
  GIT_TERMINAL_PROMPT=0 \
    GIT_HTTP_LOW_SPEED_LIMIT=1000 \
    GIT_HTTP_LOW_SPEED_TIME=15 \
    git fetch --quiet --prune "$_remote" 2>>"$_caf_log" || {
    _log "fetch failed (network? auth?) — exit clean"
    _stamp_and_exit
  }

  _local=$(git rev-parse HEAD 2>/dev/null)
  _remote_head=$(git rev-parse "$_upstream" 2>/dev/null)
  if [ "$_local" = "$_remote_head" ]; then
    _log "up to date at $(echo "$_local" | cut -c1-12)"
  elif git merge-base --is-ancestor HEAD "$_upstream" 2>/dev/null; then
    if git merge --ff-only --quiet "$_upstream" 2>>"$_caf_log"; then
      _log "fast-forwarded $(echo "$_local" | cut -c1-12) -> $(echo "$_remote_head" | cut -c1-12)"
    else
      _log "ff merge failed unexpectedly"
    fi
  else
    _log "skip: local diverged from $_upstream"
  fi

  _stamp_and_exit
) </dev/null >/dev/null 2>&1 &
disown 2>/dev/null || true

_caf_cleanup
