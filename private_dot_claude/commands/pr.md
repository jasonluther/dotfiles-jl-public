---
allowed-tools: Bash(git *), Bash(gh pr *), Bash(gh pr checks*), Bash(gh run *), Bash(make pre-commit), Bash(make quick-check), Bash(open *), Skill(code-review)
description: Open a pull request with review, squash, and monitoring
---

Open a pull request for the current branch with review, squash, and monitoring.

If `$ARGUMENTS` is `merge`, skip to the [Merge flow](#merge-flow) section instead.

## Arguments

`$ARGUMENTS` is optional: additional context for the PR title/body (e.g., "fixes the
timer bug" or a specific PR title). The special value `merge` triggers the merge flow.

## Prerequisites

- Must NOT be on `main` — refuse and explain if so.
- Working tree must be clean — refuse if there are uncommitted changes.

## Steps

### 1. Load project context

Check if `.claude/pr-context.md` exists in the project root. If it does, read it — it
contains project-specific PR configuration (deployment URLs, extra checks, PR body
sections, etc.). Apply its instructions throughout the remaining steps.

### 2. Rebase onto main

```bash
git fetch origin main
git rebase origin/main
```

If there are conflicts, **stop and show the conflicts**. Do not attempt to resolve them
automatically — ask the user for guidance.

### 3. Code review the branch diff

**Always run this step** — even if a code review was already performed earlier in the
conversation. The rebase in step 2 may have changed the diff, and pre-commit fixes in
step 5 may require a re-review.

Run `/code-review` (no arguments — it defaults to reviewing the current branch vs main).
Fix any real issues it finds. If fixes are made, commit them with an appropriate message.

### 4. Update documentation

Review the changes on this branch (`git diff origin/main`) and check whether any
project documentation needs updating — e.g. README, CLAUDE.md, doc files, inline usage
comments, or config examples. Only update docs that are directly affected by the changes;
don't touch unrelated docs. If updates are needed, make them and commit.

### 5. Run pre-commit checks

```bash
make pre-commit
```

If anything fails, fix it, commit the fix, and re-run until clean. If the project doesn't
have a `make pre-commit` target, skip this step.

### 6. Squash commits

Look at the commit log since `origin/main`. Group related commits into logical units:

- If there's only 1-2 clean commits, leave them as-is.
- If there are many small commits (fixups, "wip", review fixes), squash them into
  coherent commits that each represent a meaningful change.
- Preserve distinct logical changes as separate commits (e.g., keep "feat: add timer"
  and "test: timer tests" separate if they're clean).
- Follow the project's commit message style (check CLAUDE.md or recent git log).

To squash non-interactively, use `git reset --soft <base>` then re-commit, or use
`GIT_SEQUENCE_EDITOR="sed -i ..." git rebase -i origin/main` to mark fixups.
Show the user the final commit list and **wait for confirmation** before proceeding.

### 7. Check existing PR state and force-push

Before pushing, check if a PR already exists for this branch and whether it's been merged
or closed:

```bash
gh pr view --json number,url,state 2>/dev/null
```

- If the PR state is `MERGED` or `CLOSED`, the branch name is stale. Create a **new
  branch** before pushing (e.g., append `-v2` or use a descriptive name), so you don't
  push commits to a merged PR's branch:

  ```bash
  git checkout -b <new-branch-name>
  ```

- If the PR state is `OPEN` or no PR exists, push to the current branch:

  ```bash
  git push --force-with-lease origin HEAD
  ```

### 8. Create or update PR

If a PR exists and its state is `OPEN`, update its title/body if needed. Otherwise create
a new PR:

- Title: derive from the branch name and commits, or use `$ARGUMENTS` if provided.
  Keep under 70 chars.
- Body: start with a `## Summary` section with bullet points, then a `## Test plan`
  checklist. If `pr-context.md` specifies additional body sections (e.g., deployment
  links), include those too.

### 9. Post-PR actions

If `pr-context.md` defines post-PR actions (e.g., opening a deployment URL), execute
them now.

### 10. Watch CI

Open the PR in the system browser, then watch the fast CI checks (lint/build/test).
Do NOT wait for slow automated review workflows (e.g., "Claude Code Review") — they
take much longer and are useless if CI fails.

```bash
open <PR_URL>    # macOS — use xdg-open on Linux
```

Find the CI workflow run (not review workflows) for this branch and watch it:

```bash
gh run list --branch <branch> --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId'
gh run watch <run-id> --exit-status
```

If the repo doesn't have a `ci.yml`, look for the equivalent fast-check workflow by
listing workflows with `gh workflow list` and picking the one that isn't a review bot.

- If CI **fails**: show the failing job details with `gh run view <run-id>`. Investigate
  the failures, fix them, commit, push, and re-watch CI. Do NOT wait for the review
  workflow — it'll be stale after the fix anyway.
- If CI **passes**: report success, then watch the review workflow in the background.
  Find its run and watch it:

  ```bash
  gh run list --branch <branch> --workflow claude-code-review.yml --limit 1 --json databaseId --jq '.[0].databaseId'
  ```

  Then in a background task (`run_in_background: true`):

  ```bash
  gh run watch <run-id>; gh pr view --comments
  ```

  When it completes, report any review comments to the user. If there are actionable
  comments, summarize them.

**Do NOT remove the worktree or delete the branch.** The worktree stays open until the
PR merges — you may need to push follow-up commits after review feedback or CI failures.

---

## Merge flow

Triggered when `$ARGUMENTS` is `merge`. Merges the current branch's PR, monitors CI on
main, and rebases the next oldest PR to keep the queue moving.

### M1. Verify PR is mergeable

```bash
gh pr view --json number,url,state,mergeable,statusCheckRollup
```

- If state is not `OPEN`, stop and explain.
- If mergeable is not `MERGEABLE`, rebase onto main, force-push, and wait for checks to
  pass by watching the run with `gh run watch <run-id> --exit-status`.
- If any required checks have failed, stop and show the failures.

### M2. Merge the PR

If all required checks are already green, merge directly:

```bash
gh pr merge --rebase --delete-branch
```

If merge fails because a required check is still pending/blocked (e.g. a slow LLM
`claude-review`, or the PR fell `BEHIND` another merge), **do not give up** — hand off to
`/watch-to-merge`, which arms auto-merge and polls to `state == MERGED`, recovering
`BEHIND` (rebase + re-arm), waiting out the slow review, and treating a `SKIPPED` required
check as pass. Only a genuine `DIRTY` conflict or check `FAILURE` should stop the flow.

### M2.5. Return to main

After a successful merge, the feature branch is deleted. Switch back to main so the user
isn't stranded on a dead branch:

```bash
git checkout main
git pull origin main
```

If running inside a **git worktree** (check: `git rev-parse --git-common-dir` differs
from `git rev-parse --git-dir`):

- Do **NOT** remove or delete the worktree — that will kill the user's terminal session.
- Switch to main within the worktree so the working directory remains valid.
- Tell the user: "PR merged. This worktree is no longer needed — when you're ready, exit
  this session and clean it up with `git worktree remove <path>`."

### M3. Monitor main CI

After merge, find the CI workflow run (not review workflows) on main and watch it:

```bash
gh run list --branch main --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId'
gh run watch <run-id> --exit-status
```

Report the result to the user. If it fails, show the failing jobs with
`gh run view <run-id>`.

### M4. Rebase the oldest open PR

Find the oldest open PR in the repo by the current user:

```bash
gh pr list --author "@me" --state open --json number,headRefName,url --jq 'sort_by(.number) | .[0]'
```

If there are no other open PRs, skip this step and report that the queue is empty.

If a PR is found:

1. Fetch and rebase its branch onto the updated main:

   ```bash
   git fetch origin main <branch>
   git checkout <branch>
   git rebase origin/main
   ```

2. If there are conflicts, **stop and show them** — do not auto-resolve. Tell the user
   which PR has conflicts and on which files.
3. Force-push the rebased branch:

   ```bash
   git push --force-with-lease origin <branch>
   ```

4. Switch back to the original branch (or main if the worktree was cleaned up).
5. Report: "Rebased PR #N (`<branch>`) onto main and force-pushed. CI will run on the
   updated branch."

### M5. Done

Report the merge result, main CI status, and rebase status. Open any failing CI runs in
the browser if applicable.

If in a worktree, remind the user to clean it up when they're done:
`git worktree remove <path>` from the main checkout.
