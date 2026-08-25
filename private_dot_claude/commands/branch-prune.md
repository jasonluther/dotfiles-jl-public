---
allowed-tools: Bash(git *), Bash(gh pr *), Bash(gh repo view*), Bash(xargs *)
description: Delete remote branches, and local worktrees/branches, whose work is already merged (rebase-safe, via git cherry)
---

Delete remote branches — and local worktrees/branches — whose commits are **already on the
default branch**, using patch-equivalence rather than ancestry. This is rebase-safe: with
rebase or squash merging, a merged branch keeps showing commits in
`git rev-list main..branch` because the merge rewrote its SHAs — so "ahead" counts lie.
`git cherry` compares patches instead and correctly reports work that landed as the **same
patch**. It cannot see work that landed **re-authored** — see step 2a before trusting a
`+`.

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
- `>0` → no identical patch on `$base` → **keep** (a hypothesis, not a verdict — step 2a).

Build two lists: PRUNE (count 0, no open PR, not protected) and KEEP (everything else,
with the reason: open PR #, unmerged commit count, or protected).

### 2a. Verify the KEEP list for re-authored work (staleness-triggered)

`git cherry` compares **patch IDs**, so it only recognizes work that landed as the *same
patch*. Work that landed **re-authored** — a later PR that rewrote the same idea from
scratch — reports `+` forever and is never reclaimed. The asymmetry is the whole point:

- `-` is a **verdict**: that patch really is on `$base`. Safe to delete.
- `+` is a **hypothesis**: "no identical patch found" — *not* "this work is missing".

So the PRUNE test above stays exactly as written (its `-` is sound). The verification goes
on the KEEP list.

For each KEEP branch with **no open PR** whose last commit is **older than 7 days**
(`git log -1 --format=%cr <ref>`), do not stop at "N outstanding commits":

1. List what the branch touched:
   `git diff --name-only $(git merge-base origin/$base <ref>) <ref>`
2. Pull 2-4 **distinctive identifiers** from that diff — a new test function name, a new
   symbol, a docstring heading, a unique sentence of prose.
3. Grep `$base`'s **current content** for each:
   `git show origin/$base:<path> | grep -n '<identifier>'`
   (use `git grep <identifier> origin/$base` if the file may have been renamed).

If every identifier is already on `$base`, report it as
**`KEEP-SUSPECT: possibly re-authored onto $base — verify content before reviving`**, with
the identifiers and where each was found. If any is missing, it stays a plain KEEP.

Why 7 days: long enough that an actively-developed branch is never flagged, short enough to
catch one a later PR overtook. It is a **tripwire for a human read, not a deletion
criterion** — nothing keys off the exact number, so tune it freely.

**KEEP-SUSPECT never deletes.** `--apply` acts on the PRUNE list only; suspicion alone must
never delete anything. A false positive here would destroy the only copy of unmerged work,
so a human reads the evidence and deletes by hand.

**Trap: `git diff` will not answer this.** On a branch many days behind, `git diff
origin/$base HEAD` shows the *base branch's* entire divergence (~57KB of unrelated CI and
`CLAUDE.md` churn in the case below) — useless. Three-dot `git diff origin/$base...HEAD` is
**also** misleading: it showed a docstring block as a pure addition even though `$base`
already had that content, because both sides edited that region after the merge-base. Only
comparing the **named files' current content** on the two sides answers the question.

**Worked example (branch dated 2026-08-13, checked 2026-08-25).**
`chore/component-registration-completeness-guard` in `partygame`: 3 commits, clean worktree,
no PR ever opened, all 3 reported `+`. Every contribution was already on `main` in a
further-developed form — the `registry.py` seven-module checklist (with richer guard
annotations), the `components.md` deferral entry (as the 4th "Known data-driven boundary"),
and the completeness-guard **test module** (landed as `937d64e26`, carrying one *extra*
test the branch lacked — `test_projector_chain_precedence_holds`). Merging the
branch would have been a **regression**: strictly fewer tests than `main` already had. It
was deleted after checking the content by hand.

### 3. Report

Always print both lists with counts: how many will be deleted, and the kept branches with
their reason (flagging any KEEP-SUSPECT with its evidence). This makes silent
over-deletion impossible to miss, and stops a re-authored branch from sitting in KEEP
forever with no explanation.

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
4. **Re-authored check.** A `+` here is the same hypothesis as in step 2. If the branch has
   no open PR and its last commit is older than 7 days, run the step 2a content check and
   report **KEEP-SUSPECT** instead of a bare commit count. Still never removed by
   `--apply` — the worked example in step 2a was exactly this shape: a stale local branch,
   no PR, three `+` commits, all of it already on `main`.

Note two worktrees can point at the same branch/SHA (one checked out on the branch, one
left detached at the same commit after a stale checkout) — dedupe branch names before the
delete step so `git branch -D` isn't run twice on the same name.

### 6. Report local worktrees

Print REMOVE (path, branch or `(detached)`, "merged") and KEEP (path, reason: dirty / open
PR # / N outstanding commits / KEEP-SUSPECT + evidence) lists with counts, same as the
remote-branch report.

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
