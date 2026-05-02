#!/usr/bin/env bash
# Toggle the GitHub Actions runner used by PR workflows in this repo.
#
# Usage:
#   ./scripts/set-runner.sh self-hosted   # use local macOS runner pool
#   ./scripts/set-runner.sh github        # use ubuntu-latest

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <self-hosted|github>" >&2
  exit 1
fi

case "$1" in
  self-hosted)
    gh variable set RUNS_ON --body self-hosted
    echo "Set RUNS_ON=self-hosted. PR workflows will use the local runner pool."
    echo "Push-to-main and Dependabot PRs always use ubuntu-latest."
    ;;
  github)
    gh variable delete RUNS_ON 2>/dev/null || true
    echo "Cleared RUNS_ON. All workflows will use ubuntu-latest."
    ;;
  *)
    echo "Error: unknown choice '$1'. Use 'self-hosted' or 'github'." >&2
    exit 1
    ;;
esac
