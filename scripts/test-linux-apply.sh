#!/usr/bin/env bash
# Local-dev smoke test: spin up a fresh debian:bookworm-slim container,
# mount the chezmoi source tree read-only, run `chezmoi init` + `apply`,
# and assert a small fixed set of generic invariants.
#
# Goal: a `git checkout <any-branch> && scripts/test-linux-apply.sh`
# workflow for sanity-checking that chezmoi apply works on Linux without
# bricking. Run locally before pushing changes that touch chezmoi
# behavior. Not in CI because Docker-in-Docker on GitHub Actions adds
# friction; the chezmoiscripts job in lint.yml covers static template
# validation.
#
# Image is pinned to debian:bookworm-slim — matches the apt-based Linux
# target documented in install.sh.
#
# Usage:
#   scripts/test-linux-apply.sh             # run, assert, exit
#   scripts/test-linux-apply.sh --shell     # post-apply, drop into bash
#   scripts/test-linux-apply.sh --keep      # don't --rm the container

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="debian:bookworm-slim"

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: '$1' not on PATH — install it first (OrbStack or Docker Desktop on macOS)" >&2
    exit 1
  }
}
require docker

shell_after=0
keep=0
for arg in "$@"; do
  case "$arg" in
    --shell) shell_after=1 ;;
    --keep) keep=1 ;;
    -h | --help)
      sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

# Unique tmp HOME per run so a previous broken state can't bleed in.
tmp_home="$(mktemp -d -t chezmoi-smoke-home.XXXXXX)"
trap 'rm -rf "$tmp_home"' EXIT

docker_args=(run -v "$SRC:/src:ro" -v "$tmp_home:/root" -w /root)
if [ "$keep" -eq 0 ]; then
  docker_args+=(--rm)
fi
if [ "$shell_after" -eq 1 ]; then
  docker_args+=(-it)
fi
docker_args+=("$IMAGE" bash -c)

# Inner script. Runs inside the container.
inner=$(
  cat <<'INNER'
set -euo pipefail

red()   { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }

echo "==> apt: install prerequisites"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
# `sudo` is required because scripts/install-packages.sh shells out to
# `sudo apt-get …` unconditionally on apt-based distros. We're already
# root in this container, so sudo is a no-op pass-through, but it has
# to exist on PATH for the script not to bail.
apt-get install -y --no-install-recommends curl ca-certificates git sudo >/dev/null

echo "==> install chezmoi"
sh -c "$(curl -fsLS get.chezmoi.io)" -- -b /usr/local/bin

export CHEZMOI_NAME='Smoke Test'
export CHEZMOI_EMAIL='smoke@test.local'

echo "==> chezmoi init (resolves .chezmoi.toml.tmpl → ~/.config/chezmoi/chezmoi.toml)"
chezmoi --source=/src init

echo "==> first apply"
if ! chezmoi --source=/src apply; then
  red "chezmoi apply failed"
  exit 1
fi

# Marker for idempotency check: any file under $HOME modified after this
# point on the second apply will be newer than this marker.
sleep 1
touch /tmp/firstapply
sleep 1

fail=0
check() {
  local label="$1"
  shift
  if "$@"; then
    green "ok    $label"
  else
    red   "FAIL  $label"
    fail=1
  fi
}

echo "==> assertions"
check "~/.gitconfig exists"                      test -f "$HOME/.gitconfig"
check "~/.zshrc exists"                          test -f "$HOME/.zshrc"
check "~/.local/bin/start-work-setup exists"     test -f "$HOME/.local/bin/start-work-setup"
check "~/.local/bin/start-work-setup executable" test -x "$HOME/.local/bin/start-work-setup"
check "macOS-only ~/Library absent"              test ! -e "$HOME/Library"

echo "==> second apply (idempotency)"
if ! chezmoi --source=/src apply -v; then
  red "second apply failed"
  fail=1
fi

# After a clean second apply nothing under $HOME should be newer than
# the marker. If anything is, the apply isn't idempotent.
mutated=$(find "$HOME" -type f -newer /tmp/firstapply 2>/dev/null || true)
if [ -n "$mutated" ]; then
  red "FAIL  idempotency — files mutated on second apply:"
  printf '  %s\n' "$mutated" >&2
  fail=1
else
  green "ok    idempotency (no files mutated on second apply)"
fi

if [ "$fail" -ne 0 ]; then
  red "==> SMOKE FAILED"
  exit 1
fi
green "==> SMOKE OK"
INNER
)

if [ "$shell_after" -eq 1 ]; then
  inner="$inner"$'\n''echo "==> dropping into bash (apply complete)"; exec bash -i'
fi

echo "==> running smoke in $IMAGE (HOME=$tmp_home)"
if docker "${docker_args[@]}" "$inner"; then
  echo "==> smoke: PASS"
else
  rc=$?
  echo "==> smoke: FAIL (exit $rc)" >&2
  exit "$rc"
fi
