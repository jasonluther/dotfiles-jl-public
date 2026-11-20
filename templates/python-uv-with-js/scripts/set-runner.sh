#!/usr/bin/env bash
# Toggle the GitHub Actions runner used by PR workflows in this repo.
#
# Usage:
#   ./scripts/set-runner.sh self-hosted   # use local macOS runner pool
#   ./scripts/set-runner.sh github        # use ubuntu-latest
#
# Self-hosted is for private repos only: a public repo's CI ignores
# RUNS_ON and runs on GitHub-hosted runners (free for public repos, and
# outside pull requests never reach the local machines), so this refuses
# to set it there.

set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <self-hosted|github>" >&2
  exit 1
fi

case "$1" in
  self-hosted)
    # Assigned on its own line so a gh failure (not logged in, no remote)
    # stops the script under set -e instead of reading as "public".
    is_private="$(gh repo view --json isPrivate --jq .isPrivate)"
    if [[ "$is_private" != "true" ]]; then
      echo "Error: this repo is public. Public repos run CI on GitHub-hosted" >&2
      echo "runners only; RUNS_ON is not set (the workflows ignore it there)." >&2
      exit 1
    fi
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
