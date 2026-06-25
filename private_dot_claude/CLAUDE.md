# Global guidelines (Jason)

User-wide defaults across all projects. A project's own `CLAUDE.md` always takes
precedence over anything here.

## Git & branches

- **After rebase- or squash-merge, "ahead" counts lie.** The merge rewrites SHAs, so a
  branch that already landed still shows commits in `git rev-list main..branch` and keeps a
  stale worktree/branch around. Before redoing work, assuming a branch is unmerged, or
  acting on a stale-looking TODO/branch, check patch-equivalence:
  `git cherry origin/main origin/<branch>` — `-` = already on main (skip it), `+` =
  genuinely outstanding.
- Deleting a merged local branch after a rebase-merge needs `git branch -D` (not `-d`):
  git doesn't see the rewritten SHAs as "merged".
- Use `/rebase-arm-automerge` to land a PR hands-off and `/branch-prune` to clean up
  merged remote branches (both are rebase-safe). Prefer enabling repo `delete_branch_on_merge`
  so the pileup doesn't recur.
- **Auto-merge armed ≠ merged.** Armed auto-merge stalls silently — a slow required check
  never posting, the PR falling behind another merge, or a blocked/dirty state. Don't call
  a task done at "auto-merge armed": watch the PR through to `state == MERGED` (use
  `/watch-to-merge`, which polls and recovers those stalls). Only a merge commit in the
  base branch's log proves the work shipped.

## Working safely

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

## Cross-platform

- This config is shared between macOS and Linux. Use `open` on macOS, `xdg-open` on Linux
  (check `uname`). Note `zsh` does not word-split unquoted variables — use `xargs` or
  `${=var}` when you need splitting.
