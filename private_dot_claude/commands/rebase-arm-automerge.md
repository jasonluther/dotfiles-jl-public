---
allowed-tools: Bash(git *), Bash(gh pr *), Bash(gh pr checks*), Bash(gh repo view*)
description: Rebase the current PR branch onto the default branch and arm server-side auto-merge
---

Rebase the current branch onto the repo's default branch and arm GitHub's **server-side
auto-merge**, then return. Unlike `/pr merge` (which blocks, watches CI, and merges
synchronously), this is the **arm-and-walk-away** path: GitHub merges the PR itself once
required checks pass. Ideal when review checks are slow (e.g. an LLM review takes minutes),
when you have a queue of PRs, or for overnight/unattended runs.

## Arguments

`$ARGUMENTS` is optional: a PR number to act on. If omitted, act on the PR for the current
branch.

## Prerequisites

- Must be on a feature branch with an **open** PR — refuse if on the default branch or if
  no open PR exists.
- Working tree must be clean — refuse if there are uncommitted changes.

## Steps

### 0. Consult the presence board

Before rebasing or arming auto-merge, check whether another agent session is active on
this repo (possibly on another machine) — concurrent rebases/merges on the same repo race
each other, and an auto-merge armed here can land on top of work someone else is mid-flight.

```bash
~/.local/bin/presence list    # active sessions on the current repo
```

This is **advisory, not blocking**: the client exits 0 (and the board may be unconfigured
or down, printing nothing). If it lists other active sessions on this repo, surface them to
the user and ask whether to proceed before continuing — especially if a listed session names
a task that overlaps this PR. With no other sessions (or no board), continue normally.

### 1. Identify the PR, default branch, and allowed merge strategy

```bash
gh pr view $ARGUMENTS --json number,state,headRefName,baseRefName,mergeStateStatus
gh repo view --json defaultBranchRef,mergeCommitAllowed,squashMergeAllowed,rebaseMergeAllowed
```

- If PR state is not `OPEN`, stop and explain.
- Pick the merge flag from what the repo allows, preferring the project's convention
  (check CLAUDE.md): `--rebase` if rebase-merge is allowed, else `--squash`, else
  `--merge`.

### 2. Rebase onto the latest default branch

```bash
git fetch origin <baseRef>
git rebase origin/<baseRef>
```

If there are conflicts, **stop and show them** — do not auto-resolve. Tell the user which
PR and files conflict.

### 3. Force-push the rebased branch

```bash
git push --force-with-lease origin HEAD
```

### 4. Arm auto-merge

```bash
gh pr merge $ARGUMENTS --rebase --auto    # use the merge flag chosen in step 1
```

If the repo's branch protection requires the branch to be **up-to-date** (strict checks),
the rebase in step 2 satisfies that. If another PR merges first, this PR will fall behind
and auto-merge will stall — re-run this command to rebase and re-arm.

### 5. Report and stop

Report: the PR number, that auto-merge is armed, and which checks are still pending
(`gh pr checks $ARGUMENTS`). Do **not** block waiting for the merge — GitHub completes it
server-side. Do **not** remove the worktree or delete the branch; with
`delete_branch_on_merge` enabled the remote branch auto-deletes on merge, but the local
branch/worktree remain for you to clean up later (and a stalled auto-merge may need a
re-arm).
