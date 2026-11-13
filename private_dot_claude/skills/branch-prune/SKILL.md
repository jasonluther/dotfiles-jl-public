---
name: branch-prune
description:
  Delete remote branches, and local worktrees and branches, whose work is already merged
  into the default branch. Rebase-safe (patch-equivalence via git cherry, not ahead
  counts). Dry run by default; "--apply" deletes. Use for "prune merged branches", "clean
  up stale worktrees".
allowed-tools: Bash(git *), Bash(gh pr *), Bash(gh repo view*), Bash(xargs *)
---

# Prune merged branches and worktrees

Delete remote branches, and local worktrees and branches, whose commits are **already on
the default branch**, using patch-equivalence rather than ancestry. With rebase or squash
merging, a merged branch keeps showing commits in `git rev-list main..branch` because the
merge rewrote its SHAs, so "ahead" counts lie. `git cherry` compares patches instead and
reports work that landed as the **same patch**. It cannot see work that landed
**re-authored**; see step 2a before trusting a `+`.

## Arguments

`$ARGUMENTS` is optional:

- empty → **dry run**: list what would be deleted and what is kept; delete nothing.
- `--apply` → delete the merged remote branches, and remove the merged local worktrees and
  their branches.

## Prerequisites

- Run from inside the repo, **from the primary checkout** (the main, non-linked worktree).
  A worktree cannot be removed from inside itself.
- Deleting remote branches is outward-facing. Unless the project or user has durably
  authorized pruning, show the dry-run report and get a yes before `--apply`. `--apply`
  acts on the PRUNE and REMOVE lists only.
- If the project has its own `branch-prune` skill or pruning rules (protected ref
  namespaces, standing authorizations), those take precedence. Look for them first:
  `git grep -n -i -E 'prun|merged branch|standing authori' -- '*.md'`.

## Steps

### 1. Determine the default branch and the branches to protect

```bash
git fetch --prune origin
base=$(gh repo view --json defaultBranchRef --jq .defaultBranchRef.name)   # usually main
gh pr list --state open --json headRefName --jq '.[].headRefName'           # never prune these
```

Without `gh`, use `git symbolic-ref --short refs/remotes/origin/HEAD` for the base and skip
the open-PR check only after telling the user.

Always protect:

- `$base`, and any `release*`, `production`, `develop` or similar long-lived branch.
- Every open PR's head branch.
- **Ref namespaces owned by automation** (sync daemons, snapshot or backup refs, bot
  branches such as `wip/*`, `gh-pages`, `dependabot/*` with open PRs). Such refs are
  force-pushed continuously; one can match `$base` at the moment you look and so read as
  "merged", but deleting it only makes the tool recreate it and can race whoever is
  writing it. If the repo has such a namespace, ask or check its docs before touching it.

### 2. Classify every remote branch by patch-equivalence

For each `origin/<branch>` that is not protected:

```bash
git cherry origin/$base origin/<branch> | grep -c '^+'
```

- `0` outstanding (`+`) commits → **fully merged**, safe to delete.
- `>0` → no identical patch on `$base` → **keep** (a hypothesis, not a verdict; step 2a).

Build two lists: PRUNE (count 0, no open PR, not protected) and KEEP (everything else, with
the reason: open PR #, unmerged commit count, or protected).

### 2a. Check the KEEP list for re-authored work

`git cherry` compares **patch IDs**, so it only recognizes work that landed as the same
patch. Work that landed **re-authored** (a later PR rewrote the same idea) reports `+`
forever. The asymmetry matters:

- `-` is a **verdict**: that patch is on `$base`. Safe to delete.
- `+` is a **hypothesis**: "no identical patch found", not "this work is missing".

So the PRUNE test stays as written; the extra check goes on the KEEP list.

For each KEEP branch with **no open PR** whose last commit is **older than 7 days**
(`git log -1 --format=%cr <ref>`):

1. List what the branch touched:
   `git diff --name-only $(git merge-base origin/$base <ref>) <ref>`
2. Pick 2-4 **distinctive identifiers** from that diff: a new test name, a new symbol, a
   heading, a unique sentence.
3. Grep `$base`'s **current content** for each:
   `git show origin/$base:<path> | grep -n '<identifier>'`
   (or `git grep <identifier> origin/$base` if the file may have moved).

If every identifier is already on `$base`, report
**`KEEP-SUSPECT: possibly re-authored onto $base; verify before reviving or deleting`**,
with each identifier and where it was found. If any is missing, it stays a plain KEEP.

Seven days is a tripwire for a human read, not a deletion criterion; tune it freely.

**KEEP-SUSPECT never deletes.** A false positive would destroy the only copy of unmerged
work, so a human reads the evidence and deletes by hand.

**Trap: `git diff` does not answer this.** On a branch far behind, `git diff
origin/$base <ref>` shows the base branch's whole divergence. Three-dot
`git diff origin/$base...<ref>` also misleads: content both sides changed after the
merge-base reads as a pure addition even when `$base` already has it. Only comparing the
named files' current content on both sides answers the question.

### 3. Report

Print both lists with counts: how many will be deleted, and each kept branch with its
reason (KEEP-SUSPECT with its evidence). This makes over-deletion easy to spot and keeps a
re-authored branch from sitting in KEEP forever unexplained.

### 4. Delete remote branches (only with `--apply`)

Delete the PRUNE list in batches. zsh does **not** word-split unquoted variables, so use
`xargs`, not `git push origin --delete $list`:

```bash
printf '%s\n' "${prune[@]}" | xargs -n 20 git push origin --delete
```

Then `git fetch --prune origin` and list the remaining remote branches to confirm.

### 5. Classify local worktrees the same way

Linked worktrees pile up the same way: a PR merges (and the rebase rewrites its SHAs) but
the worktree and local branch stay. Classify them with the same patch-equivalence test.

```bash
git worktree list --porcelain
```

For every worktree except the primary checkout (never touch that one):

1. **Dirty check first, always.** If `git -C <path> status --porcelain` prints anything,
   the worktree is **KEEP: dirty**, whatever its merge status. Never discard uncommitted
   work.
2. **Open-PR check.** If its branch is an open PR head from step 1: **KEEP: open PR #N**.
3. **Patch-equivalence.** On a named branch: `git cherry origin/$base <branch>`. In
   **detached HEAD** (common once the PR branch was deleted upstream): try
   `git merge-base --is-ancestor <sha> origin/$base` first, then fall back to
   `git cherry origin/$base <sha>`. `0` outstanding → **MERGED**, safe to remove. `>0` →
   **KEEP: N outstanding commits**.
4. **Re-authored check.** A `+` here is the same hypothesis as in step 2. With no open PR
   and a last commit older than 7 days, run the step 2a check and report **KEEP-SUSPECT**
   instead of a bare count. Still never removed by `--apply`.

Two worktrees can point at the same branch or SHA (one on the branch, one detached at the
same commit). Dedupe branch names so `git branch -D` runs once per name.

Local branches with no worktree can be classified the same way
(`git for-each-ref --format='%(refname:short)' refs/heads/`), skipping `$base` and the
current branch.

### 6. Report local worktrees and branches

Print REMOVE (path, branch or `(detached)`, "merged") and KEEP (path, reason: dirty / open
PR # / N outstanding commits / KEEP-SUSPECT with evidence), with counts, as in step 3.

### 7. Remove local worktrees and branches (only with `--apply`)

For each REMOVE entry, from the primary checkout:

```bash
git worktree remove <path>   # refuses if dirty; re-check rather than --force through it
git branch -D <branch>       # named branches only, once per name
```

`-D`, not `-d`: after a rebase or squash merge git does not see the rewritten branch as
merged. Then `git worktree prune` to clear stale entries, and `git worktree list` to
confirm the survivors match the KEEP list.

### 8. The durable fix

If the repo does not already have it, GitHub's "Automatically delete head branches"
(`delete_branch_on_merge`) removes a merged PR's remote branch by itself; suggest it, but
changing repo settings is the owner's call, not this skill's. Local worktrees and branches
still need steps 5-7.
