---
name: pr-batch
description:
  Clear a PR backlog by combining several open PRs (default 4) into one new PR, resolving
  conflicts, parking the originals as drafts, watching the combined PR to MERGED, then
  closing the originals. One repair attempt on failure, then it restores the originals and
  notifies the owner. Use for "batch the PR backlog", "combine 4 PRs into one", "/pr-batch".
allowed-tools: Bash(git *), Bash(gh pr *), Bash(gh run *), Bash(gh repo view*), Bash(standup *)
---

# Batch PRs into one

Each PR in a backlog pays for its own CI run and its own rebase after every merge. One
combined PR pays once. Use it when the backlog is the bottleneck, never on a PR someone is
still changing.

**The point is fewer open PRs.** A batch lowers the count, so a repo's open-PR cap never
holds one back: open the combined PR at the cap, even though it reads one over until the
originals close, and do not wait for a slot.

## Arguments

`$ARGUMENTS`: `[N | <pr> <pr> ...] [--dry-run]`.

- `N` (default **4**): take the N oldest eligible PRs. A list of numbers takes exactly
  those, still checked for eligibility; say which were refused and why.
- `--dry-run`: build and gate the combined branch locally; push nothing, change nothing on
  GitHub, and report what a real run would do.

## 0. Before you start

- The repo's own rules win where stricter: worktree layout, the board claim, the pre-PR
  review, the gates. This skill exempts nothing.
- If `standup` is installed, run `standup list` and post your goal. A PR an active session
  is **changing** (rebasing, fixing, committing to it) is **ineligible**: that agent would
  fight you. Name each PR skipped this way. One merely being watched or armed is fine: step
  3's draft and comment tell its watcher to stand down.
- **Claim the batch before picking**: `standup claim 'PR batch: <repo>'`. Exit 1 means
  another session's batch is in flight: stop. Re-check just before pushing that no
  chosen PR was parked as a draft meanwhile (2026-11-15: two sessions built the same
  batch because the first never claimed). Post `done` when the batch merges or gives up.
- Learn the merge method: `gh repo view --json rebaseMergeAllowed,squashMergeAllowed,mergeCommitAllowed`.
  Rebase-only keeps every commit, so the combined PR carries each PR's commits as they are.

## 1. Pick the PRs

```bash
gh pr list --state open --base <base> --limit 100 \
  --json number,title,headRefName,headRefOid,isDraft,createdAt,autoMergeRequest,statusCheckRollup,labels,isCrossRepository \
  --jq 'sort_by(.createdAt)'
```

Eligible: not a draft, not from a fork, no `do-not-batch` label, head commit older than 30
min (`gh api repos/{owner}/{repo}/commits/<sha> --jq .commit.committer.date`: a fresher PR
is still being worked on or about to merge alone, and batching it saves nothing), whose
head's CI run **will run the tests but has not started them** (below), and no required
check **failed** on its head (a red PR poisons the batch; leave it to its owner). Pending
checks are fine. Fewer than 2 eligible: stop and say so.

Read the tests' state off the head's latest run:

```bash
gh run view <id> --json jobs --jq '[.jobs[] | select(.name == "test" or (.name | startswith("test ("))) | .conclusion // .status]
  | if any(. == "skipped") then "quick" elif all(. == "queued" or . == "waiting") then "waiting" else "started" end'
```

- `waiting`: eligible. No `test` job listed counts too, while the run is still going: a job
  is listed only once the jobs it `needs` finish, so a PR held in an admission queue shows
  none. A run that ended without listing them (cancelled early) tells nothing: leave it out.
- `started`: ineligible. Cancelling a started run throws its work away; let it finish alone.
- `quick`: ineligible. CI skipped the suite (a docs-only diff, or a tree that already
  passed), so the PR merges alone in minutes and a batch would only slow it. List these as
  "left to merge alone".

**Sort by what CI does, never by the title or commit type.** A `docs:` PR that edits a
comment in a code file runs the full suite like any code PR and belongs in the batch; a
`chore:` PR that touches only Markdown may skip it.

**Record for each chosen PR** its number, head branch, head SHA and whether auto-merge was
armed, in a scratchpad file. Restoring and closing both key on these.

## 2. Build the combined branch

```bash
git fetch origin
git worktree add ../<repo>-batch -b batch/<date>-<n1>-<n2>... origin/<base>
```

For each PR, oldest first, cherry-pick its own commits (authorship is kept):

```bash
git cherry-pick $(git merge-base origin/<base> <head sha>)..<head sha>
```

A pick that comes up empty means the PR already landed or merged meanwhile (`git cherry
origin/<base> <sha>` shows `-`): `git cherry-pick --skip` and drop it from the batch.

On a conflict, resolve each hunk by **both PRs' intent** (read both diffs and PR bodies),
not by picking a side; `zdiff3` markers show the base. Run the tests the two PRs touch
before `git cherry-pick --continue`. A conflict you cannot resolve with confidence (two
designs that contradict): `git cherry-pick --abort`, reset to before that PR, **drop it from
the batch**, say why. Fewer than 2 left: stop.

A generated file in conflict (lockfile, bundle, golden) is regenerated with the repo's
command, never hand-merged, in its own `chore:` commit.

Cherry-pick runs no pre-commit hooks: run the repo's formatter and hooks over the combined
diff (`prek run --from-ref origin/<base> --to-ref HEAD`, or the repo's equivalent) and its
local tests for the touched packages. Fix slips in a final commit.

`--dry-run` stops here: report the chosen PRs, the skipped ones and why, each conflict and
its resolution, and the gate results. Remove the worktree and `git branch -D` the branch.

## 3. Open it, then park the originals

Run the repo's pre-PR review on **the conflict resolutions and fix commits only**; each
original was reviewed in its own PR. Push and open it ready, the body listing each PR:

```text
Batches #a, #b, #c, #d, each reviewed in its own PR. Conflicts resolved: <file: how>.
The originals are parked as drafts and close when this merges.
```

GitHub's closing keywords do not close PRs, so step 5 closes them by hand. For each original
still `OPEN` with its recorded head SHA (one that merged or moved meanwhile: rebuild without it):

```bash
gh pr merge <n> --disable-auto        # only if it was armed
gh pr ready <n> --undo
gh pr comment <n> --body "Batched into #<combined>; parked as a draft, closes when that merges. Push here only to pull it out of the batch."
gh run list --branch <head> --json databaseId,status --jq '.[]|select(.status!="completed")|.databaseId' | xargs -rn1 gh run cancel
```

A draft keeps its CI running: cancel it, or the originals hold runners and stand ahead of the
combined PR in any admission queue ordered by PR age.

Arm and watch the combined PR to `state == MERGED`: `/watch-to-merge <combined>` where the
repo has it, otherwise an arm-and-poll loop (armed is not merged). At each wake, compare each
original's head SHA with the recorded one; a moved head means its owner pulled it back: note
it on the combined PR and leave that original out of step 5.

## 4. On failure: one repair, then give up

A failure is a required check failing, a conflict a rebase cannot clear, or ~30 min with no
progress. Waiting in an admission queue is progress while the line ahead moves: a batch is
the newest PR, so it waits behind every older one.

**The one repair**: read the failing log (`gh run view <id> --log-failed`), never the check's
name. Find which PR's commits or which resolution caused it, reproducing locally and bisecting
by PR if needed. Fix it in a commit, or rebuild without the guilty PR and restore that PR
alone (step 4.2). Push with `--force-with-lease`, re-arm, watch again.

**Second failure: give up**, leaving things as they were:

1. Disarm and close the combined PR, commenting what failed and both diagnoses.
2. For each original: `gh pr ready <n>`; re-arm (`gh pr merge <n> --<method> --auto`) only if
   it was armed before; marking it ready re-runs CI where the workflow triggers on `ready_for_review`, else
   rerun its cancelled run (`gh run rerun <id>`); comment "Batch #<combined> failed; back in the queue."
3. Notify the owner with a push notification in plain words: which PRs, what failed, what
   you tried, and that the originals are back as they were. Post the step to standup.

## 5. After MERGED: close the originals

Fetch and confirm the merge commit is in `git log origin/<base>`. For each original:

```bash
git cherry origin/<base> <recorded head sha>    # `-` = landed as the same patch
```

A `+` on a commit whose conflict you resolved is expected: grep the base for its distinctive
lines before calling it landed. Then:

```bash
gh pr close <n> --comment "Landed in #<combined> (<merge sha>)." --delete-branch
```

Leave open (undraft, comment) any original whose head moved or whose work is not on the
base. Remove the batch worktree, `git branch -D` it, report the merge commit and each PR's
fate, and post `done` to standup.
