#!/usr/bin/env bash
# Smoke test for the copier project templates under templates/ — used to
# scaffold new Python (and Python+JS) project repos via `copier copy`.
# Renders each flavor into a scratch dir, bootstraps a minimal project
# skeleton, and runs pre-commit twice in the rendered project (first
# pass may auto-fix; second must be clean).
#
# Replaces the former .github/workflows/scaffold-precommit.yml workflow.
# Run locally before pushing changes to copier.yml or templates/**.
#
# Usage:
#   scripts/test-project-templates.sh                 # both flavors
#   scripts/test-project-templates.sh python-uv       # one flavor
#   SMOKE_DIR=/tmp/foo scripts/test-project-templates.sh   # override scratch dir

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRATCH="${SMOKE_DIR:-${TMPDIR:-/tmp}/dotfiles-smoke}"
FLAVORS=("${@:-python-uv python-uv-with-js}")
# shellcheck disable=SC2206  # word-splitting the default is intentional
FLAVORS=(${FLAVORS[@]})

require() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "error: '$1' not on PATH — install it first" >&2
    exit 1
  }
}
require uv
require git

if ! command -v copier >/dev/null 2>&1; then
  echo "==> installing copier via uv"
  uv tool install copier
fi
if ! command -v vale >/dev/null 2>&1; then
  echo "warning: vale not on PATH; pre-commit hooks that use vale may fail" >&2
fi

run_one() {
  local flavor="$1"
  local dest="$SCRATCH/$flavor"

  echo "============================================================"
  echo "==> smoke: $flavor → $dest"
  echo "============================================================"
  rm -rf "$dest"
  mkdir -p "$dest"

  copier copy "$SRC" "$dest" \
    --data flavor="$flavor" \
    --data project_name=smoke-test \
    --data project_slug=smoke_test \
    --data description="local smoke test scaffold" \
    --defaults

  (
    cd "$dest"
    git init -q -b main
    git config user.email "smoke@example.com"
    git config user.name "smoke"
    mkdir -p src/smoke_test tests
    touch src/smoke_test/__init__.py
    printf 'def test_placeholder():\n    assert True\n' >tests/test_placeholder.py
    uv sync --group dev
    if [[ "$flavor" == "python-uv-with-js" ]]; then
      npm install
    fi
    uv run pre-commit install
    git add -A
    uv run pre-commit run --all-files || true
    git add -A
    uv run pre-commit run --all-files
  )

  echo "==> $flavor: clean"
}

for f in "${FLAVORS[@]}"; do
  run_one "$f"
done

echo "==> all flavors passed"
