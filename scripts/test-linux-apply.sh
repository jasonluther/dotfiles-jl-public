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
# Pin amd64 so apt installs the same arch the operator's x86_64 hosts and
# `ubuntu-latest` CI run. On Apple Silicon, the default would be arm64,
# which still works but masks any amd64-only apt package issues.
PLATFORM="linux/amd64"

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

docker_args=(run --platform "$PLATFORM" -v "$SRC:/src:ro" -v "$tmp_home:/root" -w /root)
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

# Validate scripts/linux/base.sh — install.sh runs this before apply on
# real Linux hosts (gh repo + claude installer + zsh chsh). Running just
# the `base` module skips ssh-keys/harden-sshd/sudo-nopasswd/tailscale
# which need network identity and a real systemd to make sense.
echo "==> linux/setup.sh base (validates base.sh module)"
if ! bash /src/scripts/linux/setup.sh base; then
  red "base.sh failed"
  exit 1
fi

echo "==> first apply"
if ! chezmoi --source=/src apply; then
  red "chezmoi apply failed"
  exit 1
fi

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
check "git user.name from CHEZMOI_NAME"          [ "$(git config --global --get user.name)" = "Smoke Test" ]
check "git user.email from CHEZMOI_EMAIL"        [ "$(git config --global --get user.email)" = "smoke@test.local" ]
check "~/.zshrc exists"                          test -f "$HOME/.zshrc"
check "~/.local/bin/start-work-setup exists"     test -f "$HOME/.local/bin/start-work-setup"
check "~/.local/bin/start-work-setup executable" test -x "$HOME/.local/bin/start-work-setup"
check "macOS-only ~/Library absent"              test ! -e "$HOME/Library"

# base.sh outcomes
check "zsh installed"                            command -v zsh
check "gh installed (apt repo)"                  command -v gh
check "claude installer ran"                     test -x "$HOME/.local/bin/claude"
check "default shell is zsh"                    [ "$(getent passwd "$(id -un)" | cut -d: -f7)" = "$(command -v zsh)" ]

# Debian binary-name fixups from install-packages.sh
check "bat -> batcat symlink"                    test -L "$HOME/.local/bin/bat"

echo "==> second apply (idempotency, --dry-run)"
# `chezmoi apply --dry-run` emits a line per change it would make. A clean
# second apply should produce no output. We avoid a real second apply +
# mtime sweep because chezmoi mutates its own state files (boltdb, cache)
# even when no managed file changes — those would false-positive.
dry_out=$(chezmoi --source=/src apply --dry-run 2>&1 || true)
if [ -n "$dry_out" ]; then
  red "FAIL  idempotency — chezmoi apply --dry-run reports pending changes:"
  printf '  %s\n' "$dry_out" >&2
  fail=1
else
  green "ok    idempotency (chezmoi apply --dry-run is empty)"
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
