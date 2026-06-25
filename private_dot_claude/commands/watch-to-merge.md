---
allowed-tools: Bash(git *), Bash(gh pr *), Bash(gh pr checks*), Bash(gh run *), Bash(gh repo view*), Bash(sleep *)
description: Arm auto-merge then watch a PR through to actual MERGED, recovering stalls
---

Drive a PR to **`state == MERGED`** — not just "auto-merge armed." Armed auto-merge
stalls silently (a required LLM review never posts, the PR falls `BEHIND` another merge,
`BLOCKED`/`DIRTY` states), so "armed" is **not** done. This skill arms auto-merge and then
**stays resident**, polling until the PR actually lands or hits a stall it can't safely
recover from.

Use this instead of `/rebase-arm-automerge` (which arms and walks away) whenever the task
isn't finished until the PR is merged.

**See also:** `/rebase-arm-automerge` (arm-and-leave, for queues/overnight); `/pr merge`
(synchronous merge of an already-green PR); `/open-docs-pr` (Markdown-only fast path).

## Arguments

`$ARGUMENTS` is optional: a PR number. If omitted, act on the PR for the current branch.

## Prerequisites

- An **open** PR must exist for the target — refuse if none.
- Working tree clean (a rebase may be needed). Refuse if there are uncommitted changes.
- You must be authorized to merge this PR — the repo's workflow permits it, or the user
  asked you to land it. If unsure, confirm before arming. Respect the repo's merge policy
  (check CLAUDE.md); never use `--admin` to bypass checks — rebase + `--force-with-lease`
  only.

## Steps

### 1. Identify PR, base branch, merge strategy, and required checks

```bash
gh pr view $ARGUMENTS --json number,state,headRefName,baseRefName,mergeStateStatus,isDraft,url
gh repo view --json defaultBranchRef,rebaseMergeAllowed,squashMergeAllowed,mergeCommitAllowed
```

- If state is not `OPEN`, stop and explain.
- If the PR is a **draft**, stop — a draft never runs `claude-review` and never merges.
  Tell the user to mark it ready first (`gh pr ready <n>`), or do so if the task is done.
- Pick the merge flag from repo convention (check CLAUDE.md): prefer `--rebase`, else
  `--squash`, else `--merge`. This repo is **rebase-only**.

### 2. Rebase if behind, then arm auto-merge

If `mergeStateStatus` is `BEHIND`, rebase onto the latest base branch first (strict
branch protection requires up-to-date):

```bash
git fetch origin <baseRef>
git rebase origin/<baseRef>      # STOP and show conflicts if any — never auto-resolve
git push --force-with-lease origin HEAD
```

> **After a rebase, hooks did NOT run** (rebase skips pre-commit). If CI then fails fast
> (<60s on a self-hosted shard), it's almost certainly a lint/format slip — run
> `make format` locally and re-push, don't assume an e2e flake.

Then arm:

```bash
gh pr merge $ARGUMENTS --rebase --auto    # use the flag chosen in step 1
```

### 3. Poll until MERGED

Loop. Each iteration: read state, branch on `mergeStateStatus`, then sleep ~30–60s
before the next check (this is a long-lived watch — minutes, sometimes longer, because
the LLM review is slow by design). Prefer a backgrounded watch loop so the session isn't
blocked; surface a one-line status each iteration.

```bash
gh pr view $ARGUMENTS --json state,mergeStateStatus,mergeable,statusCheckRollup \
  --jq '{state, mergeStateStatus, checks: [.statusCheckRollup[] | {name: (.name // .context), status, conclusion}]}'
```

Branch on the result:

| Signal                                      | Meaning                                 | Action                                                         |
| ------------------------------------------- | --------------------------------------- | -------------------------------------------------------------- |
| `state == "MERGED"`                         | Done                                    | **Exit success.** Proceed to step 4.                           |
| `state == "CLOSED"`                         | PR closed without merging               | Stop, report.                                                  |
| `mergeStateStatus == "BEHIND"`              | Another PR landed first (strict policy) | Rebase + `--force-with-lease` + re-arm (step 2), keep polling. |
| `mergeStateStatus == "DIRTY"`               | Merge conflicts                         | **Stop** — show conflicting files, ask the user.               |
| `mergeStateStatus == "BLOCKED"`             | A required check not yet passing        | Inspect `statusCheckRollup` (below) — wait or act.             |
| `mergeStateStatus == "UNSTABLE"`            | Non-required check failing              | Usually still merges; keep polling, note it.                   |
| `mergeStateStatus == "CLEAN"`/`"HAS_HOOKS"` | All good, merge imminent                | Keep polling briefly.                                          |

When `BLOCKED`, read the rollup per required check (`ci`, `claude-review`):

- A required check `SKIPPED` (docs-only PRs skip `ci` matrix and `claude-review`
  entirely) → **treat as pass**, not a stall. A skipped required check still satisfies
  branch protection.
- `claude-review` still `PENDING`/`IN_PROGRESS` → **wait** (it's an LLM pass, several
  minutes is normal). Only flag it as stuck if it's been pending well beyond ~15 min with
  no run progressing — then check `gh run list --workflow claude-code-review.yml`.
- Any required check `FAILURE` → **stop**, show the failing job
  (`gh run view <id> --log-failed`), don't keep looping.

Add a sane overall bound (e.g. give up after ~30 min of no forward progress) and report
where it stalled rather than looping forever.

### 4. Post-merge

Once `MERGED`:

- Report the merge commit (`gh pr view $ARGUMENTS --json mergeCommit --jq .mergeCommit.oid`)
  — that SHA in the base branch's log is the proof the work shipped.
- The remote head branch auto-deletes (`delete_branch_on_merge`). Remind the user the
  local worktree/branch can be cleaned up (`git worktree remove <path>` then
  `git branch -D <branch>`), but **do not remove the current worktree** if you're inside
  it — that kills the session.
- If the strict up-to-date policy is on, offer to rebase the next queued PR
  (`gh pr list --author "@me" --state open`), matching the `/pr merge` queue behavior.
