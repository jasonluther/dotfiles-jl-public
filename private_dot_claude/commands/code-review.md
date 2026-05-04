---
allowed-tools: Bash(review-diff *), Bash(review-diff), Bash(git blame:*), Bash(make quick-check)
description: Code review uncommitted changes, a branch diff, or recent commits
---

Code review changes — uncommitted work, branch diffs, or commits in a time range.

## Arguments

`$ARGUMENTS` is optional and passed directly to `review-diff`:

- (empty) — review uncommitted changes if any, otherwise branch vs main
- `<branch>` — review all changes on `<branch>` vs main
- `--since <timespec>` — review commits since a time (e.g. `--since "3 days ago"`)
- `<branch> --since <timespec>` — review commits on `<branch>` since a time

## Instructions

Follow these steps precisely:

### 1. Gather diff and context

Run `review-diff $ARGUMENTS` to get the diff, changed files, and context in one call.
`review-diff` is a system-installed CLI tool (in `~/.local/bin`), not in the project repo — just run it directly.

`review-diff` auto-detects the right mode: if there are uncommitted changes (staged,
unstaged, or untracked), it reviews those. Otherwise it reviews the branch vs main.

Parse the JSON output. Key fields: `diff`, `commits`, `changed_files`, `diffstat`,
`claude_md_files`, `review_context`. Check `mode` in the output — if set to
`"uncommitted"`, the review covers working tree changes (and `commit_count` will be 0,
which is expected).

If the output has an `error` field, tell the user and stop.
For branch mode: also stop if `commit_count` is 0.

If `review_context` is set, read that file — it contains repo-specific review checks
that must be incorporated as additional review agents in step 3.

### 2. Summarize

Use a Haiku agent to read the diff (and commit log, if present), then return a brief summary of what changed.

### 3. Parallel review

Launch 5 parallel Sonnet agents to independently review the diff. Each agent receives the full diff, the commit log (if any), and the list of CLAUDE.md files. Each returns a list of issues with reasons:

a. **Agent 1 — CLAUDE.md compliance**: Audit changes against CLAUDE.md guidance. Not all instructions apply during review (some are authoring-time only).
b. **Agent 2 — Bug scan**: Shallow scan for obvious bugs in the changed lines only. Focus on significant bugs, skip nitpicks. Ignore likely false positives.
c. **Agent 3 — Historical context**: Read `git blame` and history of modified files. In branch mode, find bugs visible only with historical context. In uncommitted mode, check whether changes conflict with the intent of surrounding code or undo previous deliberate decisions.
d. **Agent 4 — Code comments**: Read code comments in modified files and verify the changes comply with any guidance in those comments.
e. **Agent 5 — Cross-cutting concerns**: Check for security issues (OWASP top 10), broken abstractions, missing error handling at system boundaries, and inconsistencies across the changed files.

**Repo-specific agents**: If `review_context` was set in step 1, launch additional parallel Sonnet agents for each check defined there. Give each agent the same diff, commit log, and CLAUDE.md context, plus the specific review instructions from the context file.

### 4. Score issues

For each issue found in step 3, launch a parallel Haiku agent that scores confidence 0-100. Give each agent the issue, the diff context, and the CLAUDE.md list. Use this rubric verbatim:

- **0**: False positive that doesn't survive light scrutiny, or a pre-existing issue.
- **25**: Might be real, might be false positive. Unverified. Stylistic issues not explicitly in CLAUDE.md.
- **50**: Verified real issue, but a nitpick or rarely hit in practice. Not important relative to the rest of the changes.
- **75**: Double-checked and very likely real. Will be hit in practice. The existing approach is insufficient. Directly impacts functionality or is explicitly mentioned in CLAUDE.md.
- **100**: Confirmed real issue that will happen frequently. Evidence directly confirms it.

### 5. Filter and report

Filter out issues scoring below 50. Present the results.

For **branch mode**:

---

### Code review: `<branch>` vs `main`

Reviewed N commits (M files changed).

**Summary**: <1-2 sentence summary from step 3>

Found K issues:

1. **<file:line>** — <brief description> (confidence: <score>)
   Reason: <why this was flagged>

---

For **uncommitted mode**:

---

### Code review: uncommitted changes on `<branch>`

Reviewed uncommitted changes (M files changed).

**Summary**: <1-2 sentence summary from step 3>

Found K issues:

1. **<file:line>** — <brief description> (confidence: <score>)
   Reason: <why this was flagged>

---

Or if no issues meet the threshold:

---

### Code review: ...

**Summary**: <1-2 sentence summary>

No significant issues found. Checked for bugs, CLAUDE.md compliance, security, and code comment adherence.

---

## False positive guidance

These are false positives and should be scored low:

- Pre-existing issues not introduced by these changes
- Things that look like bugs but aren't
- Pedantic nitpicks a senior engineer wouldn't flag
- Issues a linter, typechecker, or compiler would catch (imports, types, formatting)
- General quality concerns (test coverage, docs) unless CLAUDE.md requires them
- Issues silenced by lint-ignore comments
- Intentional functionality changes related to the broader change
- Issues on lines not modified in this diff
