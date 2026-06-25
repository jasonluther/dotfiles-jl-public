---
allowed-tools: Bash(jq *), Bash(grep *), Bash(find *), Bash(wc *), Bash(sort *), Bash(uniq *), Bash(awk *), Bash(ls *), Bash(du *), Read, Edit, Task
description: Mine recent chat transcripts for recurring directives/corrections and propose CLAUDE.md/MEMORY.md updates
---

Mine this project's Claude Code transcripts for **recurring directives and corrections** —
things the user has had to say more than once, or pointed corrections of Claude's
behavior — and propose codifying them into CLAUDE.md / memory so they stop recurring.

The corpus is large (often 100+ JSONL files, 100+ MB). Reading it whole is wasteful.
The key economy: **human turns are ~0.4% of the bytes** (the rest is tool output and
assistant messages), and directives live almost entirely in human turns. So the funnel is
**jq (extract) → grep (profile) → one cheap-model pass (cluster)** — never feed raw
transcripts to a model.

## Arguments

`$ARGUMENTS` is optional:

- a number of days to look back (default `7`), and/or
- `report` to only surface findings without proposing edits.

## Steps

### 1. Locate the transcript corpus

Transcripts live at `~/.claude/projects/<slug>/*.jsonl`, where `<slug>` is the cwd with
`/` → `-` (e.g. `/Users/me/Code/myproject` → `-Users-me-Code-myproject`).
Scope it and the per-day file list:

```bash
DIR=~/.claude/projects/$(pwd | sed 's#/#-#g')
ls -1 "$DIR"/*.jsonl | wc -l; du -sh "$DIR"
```

### 2. Extract human turns (the cheap 0.4%)

Pull only genuine typed human turns from top-level transcripts (skip `subagents/` — those
are Claude-to-subagent), last N days. Exclude `isMeta` and tool-result blocks:

```bash
DIR=~/.claude/projects/$(pwd | sed 's#/#-#g')
OUT=$(mktemp)
find "$DIR" -maxdepth 1 -name '*.jsonl' -mtime -${DAYS:-7} | while read -r f; do
  jq -rc 'select(.type=="user" and (.isMeta|not)) | .message.content as $c
    | if ($c|type)=="string" then $c
      elif ($c|type)=="array" then ($c|map(select(.type=="text").text)|join("\n"))
      else empty end
    | select(. != null and (.|test("^\\s*$")|not))' "$f" 2>/dev/null
done \
 | grep -vE '^\s*<(command-|local-command|/?(command|bash|system-reminder)|user-(prompt|memory))' \
 | grep -vE '^\s*(Caveat:|This session is being continued|<summary>|<result>)' \
 | awk 'NF' > "$OUT"
echo "$OUT"; wc -l < "$OUT"
```

This should yield a few hundred KB / a few thousand lines — small enough to hand to a
cheap model.

### 3. Profile for correction language (near-zero cost)

Corrections are where _repeated_ directives hide. Count matches for directive/correction
keywords to find the dominant themes before any model call:

```bash
for kw in "again" "never" "don'?t" "always" "make sure" "instead" "stop " \
          "watch" "merge" "rebase" "worktree" "isolated" "flake" "simplif" \
          "data-driven|state-name" "dead code|unused|duplicat" "scope|out of scope"; do
  printf "%4d  %s\n" "$(grep -icE "$kw" "$OUT")" "$kw"; done | sort -rn
```

Pull verbatim lines for the top themes (`grep -iE "<kw>" "$OUT" | awk 'length<260' | sort -u`)
so the model sees real phrasing, not just counts.

### 4. Cluster with ONE cheap-model pass

Dispatch a single subagent **on a cheap model (haiku)** pointed at the extract file. Tell
it to identify recurring **behavioral/process** directives and **architecture/simplicity
adherence** corrections (state-name gating, dead code, abstraction churn, scope creep) —
not one-off feature requests. For each theme: one-line description, rough frequency,
1–3 trimmed verbatim quotes, and a guess at whether it's already standard/documented.
Sort by frequency. The subagent reads only the extract file — never the raw corpus.

### 5. Cross-check against what's already codified

For each surfaced theme, check whether it's already in:

- the project `CLAUDE.md` (and `~/.claude/CLAUDE.md`),
- the project memory index `~/.claude/projects/<slug>/memory/MEMORY.md` and its
  `feedback_*.md` / `project_*.md` notes.

Keep only themes that are **missing, weakly stated, or repeatedly violated despite being
documented** — those are the ones worth acting on. A theme already well-documented and
obeyed is noise.

### 6. Propose edits (unless `report`)

For each kept theme, propose a concrete, **concise** addition (one line per concept —
CLAUDE.md is part of the prompt) routed to the right home:

- process/workflow rule → project `CLAUDE.md`,
- a fact/preference that should persist across sessions → a memory file + a `MEMORY.md`
  pointer line (follow the memory format: frontmatter + `**Why:**`/`**How to apply:**`),
- a repeatable procedure → suggest a new/edited skill.

Show each as a labelled diff with a one-line rationale and a verbatim quote as evidence.
**Apply only what the user approves** (mirrors `/revise-claude-md`'s approval gate). If
invoked with `report`, stop after presenting findings.

> Editing `CLAUDE.md` in a repo that blocks edits on `main` requires a worktree + PR.
> Memory files and global skills (chezmoi-managed) can be edited directly.
