---
allowed-tools: Bash(git *), Bash(gh pr *), Bash(gh repo view*), Bash(xargs *)
description: Delete remote branches whose work is already merged (rebase-safe, via git cherry)
---

Delete remote branches whose commits are **already on the default branch**, using
patch-equivalence rather than ancestry. This is rebase-safe: with rebase or squash merging,
a merged branch keeps showing commits in `git rev-list main..branch` because the merge
rewrote its SHAs — so "ahead" counts lie. `git cherry` compares patches instead and
correctly reports merged work.

## Arguments

`$ARGUMENTS` is optional:

- empty → **dry run**: list what would be deleted and what's kept, delete nothing.
- `--apply` → actually delete the merged remote branches.

## Prerequisites

- Run from inside the repo. This only deletes **remote** branches; local branches/worktrees
  are left alone.

## Steps

### 1. Determine the default branch and open-PR branches to protect

```bash
git fetch --prune origin
base=$(gh repo view --json defaultBranchRef --jq .defaultBranchRef.name)   # usually main
gh pr list --state open --json headRefName --jq '.[].headRefName'           # never prune these
```

Also never prune `$base` or a `release`/`production` branch if one exists.

**Never prune `wip/*` refs** (`wip/<host>` and `wip/<host>@<worktree>`). These are the
fleet-sync WIP-snapshot refs written by `sync-gh.py` — live, continuously force-pushed refs,
not completed PR heads. `git cherry` will report many of them as `0` outstanding (that host's
snapshot happens to match `$base` right now), but they are moving targets owned entirely by
the sync system, which prunes its own stale ones (30-day orphan-pruning). Deleting one just
makes the daemon recreate it and can race concurrent agent sessions. Treat the whole `wip/*`
namespace as protected.

### 2. Classify every remote branch by patch-equivalence

For each `origin/<branch>` other than the protected ones (skip `wip/*` entirely — see above):

```bash
git cherry origin/$base origin/<branch> | grep -c '^+'
```

- `0` outstanding (`+`) commits → **fully merged**, safe to delete.
- `>0` → has genuinely unmerged work → **keep**.

Build two lists: PRUNE (count 0, no open PR, not protected) and KEEP (everything else,
with the reason: open PR #, unmerged commit count, or protected).

### 3. Report

Always print both lists with counts: how many will be deleted, and the kept branches with
their reason. This makes silent over-deletion impossible to miss.

### 4. Delete (only with `--apply`)

If `$ARGUMENTS` is `--apply`, delete the PRUNE list in batches (zsh does **not** word-split
unquoted vars, so use `xargs`, not `git push origin --delete $list`):

```bash
printf '%s\n' "${prune[@]}" | xargs -n 20 git push origin --delete
```

Then re-fetch with `--prune` and show the remaining remote branches to confirm.

### 5. Suggest the durable fix

If the repo doesn't already auto-delete merged PR branches, suggest enabling it so this
chore doesn't recur:

```bash
gh api -X PATCH repos/<owner>/<repo> -f delete_branch_on_merge=true
```

(Requires admin; it only deletes the **remote** head branch on merge — local
branches/worktrees still need manual cleanup.)
