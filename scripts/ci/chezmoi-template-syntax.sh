#!/usr/bin/env bash
# Chezmoi template-syntax check for CI (lint.yml).
#
# Isolates chezmoi's config/cache under a temp HOME so `chezmoi init` cannot
# overwrite the self-hosted runner operator's ~/.config/chezmoi/chezmoi.toml
# (which would poison git identity on the next chezmoi update --force).
#
# Expects:
#   GITHUB_WORKSPACE  — repo checkout (absolute)
#   CHEZMOI_NAME / CHEZMOI_EMAIL — optional; defaults to ci / ci@example.com
#   chezmoi on PATH
#
# Usage (from repo root or any cwd):
#   GITHUB_WORKSPACE=/path/to/checkout scripts/ci/chezmoi-template-syntax.sh

set -euo pipefail

workspace="${GITHUB_WORKSPACE:-}"
if [[ -z "$workspace" ]]; then
  echo "error: GITHUB_WORKSPACE is required" >&2
  exit 1
fi
if [[ ! -d "$workspace" ]]; then
  echo "error: GITHUB_WORKSPACE is not a directory: $workspace" >&2
  exit 1
fi
if ! command -v chezmoi >/dev/null 2>&1; then
  echo "error: chezmoi not on PATH" >&2
  exit 1
fi

chezmoi_bin="$(command -v chezmoi)"
export CHEZMOI_NAME="${CHEZMOI_NAME:-ci}"
export CHEZMOI_EMAIL="${CHEZMOI_EMAIL:-ci@example.com}"

ci_home=$(mktemp -d -t chezmoi-ci-home.XXXXXX)
cleanup() { rm -rf "$ci_home"; }
trap cleanup EXIT

# Subshell so the runner's real HOME / XDG_* stay untouched.
(
  export HOME="$ci_home"
  export XDG_CONFIG_HOME="$ci_home/.config"
  export XDG_CACHE_HOME="$ci_home/.cache"
  export XDG_DATA_HOME="$ci_home/.local/share"
  # Keep the already-resolved chezmoi binary; don't rely on ~/.local/bin under
  # the temp HOME.
  path_prefix="$(dirname "$chezmoi_bin")"
  export PATH="$path_prefix:/usr/bin:/bin"

  cd "$workspace"
  # Global --source (before the subcommand) is required: under an isolated
  # HOME the default ~/.local/share/chezmoi does not exist, and `init
  # --source=…` alone does not rebind execute-template's source dir.
  chezmoi --source="$workspace" init

  shopt -s nullglob
  files=(.chezmoiscripts/*.tmpl)
  if [[ ${#files[@]} -eq 0 ]]; then
    echo "no .chezmoiscripts templates"
    exit 0
  fi

  fail=0
  for f in "${files[@]}"; do
    echo "==> $f"
    if ! chezmoi --source="$workspace" execute-template <"$f" | bash -n /dev/stdin; then
      echo "FAIL: $f"
      fail=1
    fi
  done
  exit "$fail"
)
