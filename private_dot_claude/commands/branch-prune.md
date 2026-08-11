---
allowed-tools: Bash(git *), Bash(gh pr *), Bash(gh repo view*), Bash(xargs *)
description: Delete remote branches, and local worktrees/branches, whose work is already merged (rebase-safe, via git cherry)
---

Delete remote branches — and local worktrees/branches — whose commits are **already on the
default branch**, using patch-equivalence rather than ancestry. This is rebase-safe: with
rebase or squash merging, a merged branch keeps showing commits in
`git rev-list main..branch` because the merge rewrote its SHAs — so "ahead" counts lie.
`git cherry` compares patches instead and correctly reports merged work.

## Arguments

`$ARGUMENTS` is optional:

- empty → **dry run**: list what would be deleted and what's kept, delete nothing.
- `--apply` → actually delete the merged remote branches, and remove the merged local
  worktrees + their branches.

## Prerequisites

- Run from inside the repo, **from the primary (non-bare) `partygame` checkout** — worktree
  removal must run from outside the worktree being removed.

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
the sync system, which prunes its own stale ones (10-day orphan-pruning). Deleting one just
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

### 5. Classify local worktrees the same way

Sibling worktrees (`../partygame-<feature>`) accumulate the same way remote branches do —
a PR merges (rebase rewrites its SHAs) but the worktree and local branch are never cleaned
up. Classify them with the same patch-equivalence test, not `git rev-list`/ahead counts.

```bash
git worktree list --porcelain
```

For every worktree except the primary (the entry whose path is the bare `partygame` dir,
with no `-<feature>` suffix — never touch that one, see
[Worktree Workflow](../../CLAUDE.md#worktree-workflow)):

1. **Dirty check first, always.** `git -C <path> status --porcelain` — if this prints
   anything (uncommitted changes, untracked files), the worktree is **KEEP: dirty**,
   full stop, regardless of merge status. Never discard uncommitted work.
2. **Open-PR check.** If the worktree's branch is in the open-PR list from step 1,
   **KEEP: open PR #N**.
3. **Patch-equivalence.** If the worktree is on a named branch:
   `git cherry origin/$base <branch>`. If it's in **detached HEAD** (common after a PR
   branch was already deleted upstream but the worktree lingered): first try
   `git merge-base --is-ancestor <sha> origin/$base` (cheap ancestor check); if that's
   false, fall back to `git cherry origin/$base <sha>`. `0` outstanding → **MERGED**,
   safe to remove. `>0` → **KEEP: N outstanding commits**.

Note two worktrees can point at the same branch/SHA (one checked out on the branch, one
left detached at the same commit after a stale checkout) — dedupe branch names before the
delete step so `git branch -D` isn't run twice on the same name.

### 6. Report local worktrees

Print REMOVE (path, branch or `(detached)`, "merged") and KEEP (path, reason: dirty / open
PR # / N outstanding commits) lists with counts, same as the remote-branch report.

### 7. Delete local worktrees + branches (only with `--apply`)

For each REMOVE entry, from the primary worktree:

```bash
git worktree remove <path>          # fails loudly (does not force) if dirty — re-check, don't --force through it
git branch -D <branch>              # only if it was on a named branch, and only once per branch name
```

Then `git worktree prune` to clear any stale administrative entries, and
`git worktree list` to confirm the survivors match the KEEP list.

### 8. Suggest the durable fix

If the repo doesn't already auto-delete merged PR branches, suggest enabling it so this
chore doesn't recur:

```bash
gh api -X PATCH repos/<owner>/<repo> -f delete_branch_on_merge=true
```

(Requires admin; it only deletes the **remote** head branch on merge — steps 5-7 above are
what actually clean up the local worktree/branch side.)
