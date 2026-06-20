---
description: Spell-check the repo with Vale, triage findings, fix typos, and accept legitimate terms
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
---

Run a spell check across the current repo, then **triage** the findings into real
typos (which you fix) vs. legitimate unknown technical terms (which you add to the
project dictionary). Safe to run repeatedly — it converges as terms get accepted.

This command is project-agnostic: it auto-detects the spell-check tooling rather
than assuming any one repo's layout.

## 1. Detect the tooling

Work out, in this order, what the current repo provides. Don't assume paths —
discover them:

- **Vale config:** look for `.vale.ini` at the repo root. If present, Vale
  (`vale --output=JSON`) is the prose checker.
- **Project vocabulary (accept list):** find Vale's accept file, typically
  `.vale/styles/config/vocabularies/*/accept.txt`
  (`find . -path '*/vocabularies/*/accept.txt' -not -path '*/node_modules/*'`).
  This is where legitimate-but-unknown terms get added, alphabetically.
- **cspell sync script:** look for a script that mirrors the Vale vocab into the
  editor's cspell dictionary, e.g. `scripts/sync_vale_to_cspell.py` (search:
  `git ls-files | grep -iE 'sync.*cspell|cspell.*sync'`). Run it after editing the
  accept list so VS Code stays in sync. If there is no such script, skip that step.
- **Content / domain checkers:** look for repo-specific spell scripts beyond docs,
  e.g. `scripts/content_spellcheck.py` (search `git ls-files | grep -iE
'content_spellcheck|spellcheck'`). Run any you find — they usually cover
  user-facing strings (game content, UI copy) that plain Vale can't read.

If none of the above exist, tell the user the repo has no spell-check setup and
stop (offer to scaffold one only if they ask).

## 2. Gather findings

- **Docs/prose:** run Vale on the tracked text files, JSON output, keep only
  `Vale.Spelling` checks. Mirror the repo's own exclusions — if a
  `vale_spelling_gate.py` or pre-commit `exclude:` pattern exists, respect the same
  excluded paths (authored artifacts, archives, vendored files) so you don't
  re-triage things the repo deliberately ignores. A convenient path: run the
  repo's existing spelling-gate script if it has one (e.g.
  `python3 scripts/vale_spelling_gate.py <files>`) and read its report
  (`spelling-warnings.txt`).
- **Content/domain:** run each repo-specific checker found in step 1 and capture
  its report.

Collect every unique flagged word with its source location.

## 3. Triage each unique flagged word

Sort flagged words into three buckets. **Be conservative — when unsure, ask the
user rather than guessing.**

- **Real typo** → a genuine misspelling of an ordinary word
  (`recieve`, `lookng`, `seperate`). FIX it by editing the source file. Fix every
  occurrence. Never fix by adding the misspelling to the dictionary.
- **Legitimate term** → a correctly-spelled proper noun, brand, domain term, or
  deliberately unusual word (`Rihanna`, `Pikachu`, `Petrichor`, an API name, a
  person's surname). ADD it to the accept list. For game/quiz content, intentionally
  obscure words are expected — accept them.
- **Ambiguous** → could be either (an unusual product name, an invented word, a
  possible-but-odd spelling). List these for the user and ask before acting.

## 4. Apply fixes

- **Typos:** edit the source files directly. Show the diffs.
- **Legitimate terms:** append them to the accept list, then re-sort it so it stays
  **alphabetical** (case-insensitive). If a sort/sync script exists, prefer letting
  it sort (it runs on the next commit anyway); otherwise sort the file yourself.
- **cspell sync:** run the sync script found in step 1 so the editor dictionary
  picks up the new terms.

## 5. Re-run and summarize

- Re-run the checkers to confirm the typos are resolved and the newly-accepted
  terms no longer flag.
- Summarize:
  - **Typos fixed** — word, file, the correction.
  - **Terms accepted** — count and the list (or a sample if long).
  - **Left for the user** — ambiguous words you didn't act on, and why.
- Do **not** commit unless the user asks. If they do, follow the repo's commit
  conventions (and let pre-commit hooks run).

Argument hint: `$ARGUMENTS` (optional path or area to scope the check; defaults to
the whole repo)

Notes:

- This is a cleanup tool, not a gate. Many repos run the spelling check as
  advisory-only precisely because most flags are legitimate names — your job is the
  human-in-the-loop triage that a blocking hook can't do.
- Never silence a real typo by accepting it into the dictionary.
- Adding a word to the accept list must keep the file alphabetical; an out-of-order
  accept list will fail the repo's own sort check.
