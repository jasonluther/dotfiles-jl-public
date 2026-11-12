# Global guidelines (Jason)

User-wide defaults across all projects. A project's own `CLAUDE.md` always takes
precedence over anything here.

## Git & branches

- **After rebase- or squash-merge, "ahead" counts lie.** The merge rewrites SHAs, so a
  branch that already landed still shows commits in `git rev-list main..branch` and keeps a
  stale worktree/branch around. Before redoing work, assuming a branch is unmerged, or
  acting on a stale-looking TODO/branch, check patch-equivalence:
  `git cherry origin/main origin/<branch>` — `-` = already on main (skip it), `+` = **no
  identical patch found**, which is not proof the work is missing: work that landed
  **re-authored** reports `+` forever, so grep main for the branch's distinctive
  identifiers before reviving a stale branch.
- Deleting a merged local branch after a rebase-merge needs `git branch -D` (not `-d`):
  git doesn't see the rewritten SHAs as "merged".
- **Auto-merge armed ≠ merged**: it stalls silently, so only a merge commit in the base
  branch's log proves the work shipped.

## Working safely

- **No polling watchers on GitHub.** Every session on one account shares GitHub's 5,000-an-hour API
  limit. One-off `gh` calls are fine; a loop that re-checks PRs, runs or deploys every few
  minutes is what exhausts it. Wait on a run with one `gh run watch` or `gh pr checks
  --watch --interval 60`, or check once when it should be done; prefer GitHub auto-merge.
- **Verify before claiming done.** Run the command and read the output before saying a test
  passes, a fix works, or a deploy is live — evidence before assertions. If something is
  skipped or failing, say so plainly.
- **Confirm outward-facing / hard-to-reverse actions** before doing them unless durably
  authorized: force-pushing shared branches, mass-deleting branches, changing repo/CI
  settings, publishing to a public repo or external service. Approval in one context doesn't
  carry to the next.
- Don't trust a summary (mine or a doc's) over the code. When reconciling docs or removing a
  TODO, verify the claim in the actual source/git first.
- **Read the actual failure output — don't infer cause from a check's name or red/green.**
  Diagnose from the log, not the title (a fast-failing CI shard is usually a lint/format
  slip, not a flaky test). Green tests prove behavior works, not that the change is at the
  right layer — review the diff against the project's architecture and simplicity goals too.
- **Behavior/UI changes need real-app verification.** Passing tests don't prove a button
  works. For changes to user-facing flow, run the app and exercise the actual path before
  claiming done.
- **A passing `curl`/`fetch` is not a passing browser navigation.** For CDN/edge or
  SPA-fallback routing (e.g. Cloudflare Static Assets `not_found_handling`, service
  workers, redirect interstitials), a non-navigation request can take a different code
  path than a real browser navigation — so a green status code proves nothing about what a
  user actually sees. Drive an actual browser navigation, not just a status check.

## Cross-platform

- This config is shared between macOS and Linux. Use `open` on macOS, `xdg-open` on Linux
  (check `uname`). Note `zsh` does not word-split unquoted variables — use `xargs` or
  `${=var}` when you need splitting. `GID`, `UID` and `status` are special in zsh (assigning
  one changes ids or fails): name a variable something else.

<!-- Machine-local memory overlay: created empty by default; private overlays may
     fill it with host- or tool-specific guidance. Safe to leave empty. -->

@~/.claude/CLAUDE.local.md
