---
description: Run all linters that feed the VSCode "Problems" panel and propose fixes
allowed-tools: Bash, Read, Edit, Write, Glob, Grep
---

Run the `lint-problems` script to gather all linter output for the current
project (the same checks that populate the VSCode Problems panel), then:

1. Run `lint-problems` in the current working directory.
2. Review the output and group issues by linter and severity.
3. For each issue, decide:
   - **Fix it** if it's a clear quality issue (unused imports, missing newlines,
     broken links, real prose problems).
   - **Suppress it** with a project-level config edit if the rule is wrong for
     this project (e.g. add to `.markdownlintrc` or `.vale.ini`).
   - **Skip it** if it's noise (e.g. spelling for a domain term — add to the
     dictionary or vocab file instead).
4. Make the fixes in batches by linter, showing diffs as you go.
5. Re-run `lint-problems` at the end to confirm the issues are gone.

Argument hint: `$ARGUMENTS` (optional path, defaults to current directory)

Notes:

- Ruff is the source of truth for Python; don't suggest Black/isort/flake8.
- Vale prose suggestions are often opinions — only enforce ones the user clearly
  cares about (passive voice, weasel words, jargon).
- For markdownlint, prefer disabling a rule project-wide over scattering inline
  `<!-- markdownlint-disable -->` comments.
- **Spelling is owned by `/spellcheck`.** Don't manage the Vale accept-list here — for
  spelling findings (or to triage typos vs. legitimate terms), defer to `/spellcheck`,
  which owns the dictionary workflow. Fix only non-spelling Vale issues in this command.
