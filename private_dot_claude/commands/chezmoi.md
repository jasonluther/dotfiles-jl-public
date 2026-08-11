# Chezmoi Sync

Analyze and resolve differences between chezmoi source and destination.

## Steps

### 1. Get status

Run `chezmoi status` and `chezmoi diff --no-pager`. If there are no differences, say
so and stop.

### 2. Categorize each changed file

For each file in the status output, determine the situation from the two-column status
code. Below, `·` marks a space — i.e. _no change_ in that column. Column 1 = the
destination was edited locally since the last apply; column 2 = the destination differs
from the target (source) state.

| Status | Meaning                                                                       | Action                                                                                                                                                                                                                                     |
| ------ | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `·M`   | Destination matches source, but target state differs (template/config change) | Review diff, suggest `chezmoi apply <path>`                                                                                                                                                                                                |
| `M·`   | Destination was modified after last apply (local edits)                       | Review diff, suggest `chezmoi re-add <path>` to pull changes into source — **but not for `.tmpl` sources** (see Templates & repos)                                                                                                         |
| `MM`   | Both source and destination changed                                           | Show both sides; merge into the **source** by hand, then `chezmoi apply --force <path>`. A clean `git status` in the source repo means the source just moved ahead and was never applied here — adopt it with `apply`, not a real conflict |
| `·A`   | New file in target state                                                      | Suggest `chezmoi apply <path>`                                                                                                                                                                                                             |
| `A·`   | File was created locally                                                      | Suggest `chezmoi add <path>` if it should be managed                                                                                                                                                                                       |
| `·D`   | File will be deleted by apply                                                 | Confirm with user before applying                                                                                                                                                                                                          |
| `D·`   | Managed file was deleted locally                                              | Suggest `chezmoi apply <path>` to restore or `chezmoi forget <path>` to stop managing                                                                                                                                                      |
| `·R`   | Script will be run                                                            | Show the script content, ask user if they want to run it                                                                                                                                                                                   |
| `R·`   | Script was run since last apply                                               | Informational only                                                                                                                                                                                                                         |

### 3. Present a summary

Group files by category. For each file show:

- The path
- A one-line description of what changed (from the diff)
- The recommended action

### 4. Audit Claude Code permissions

Compare the current project's `.claude/settings.json` and `.claude/settings.local.json`
against the user-level settings in `~/.claude/settings.json` (managed by chezmoi from
the dotfiles source).

- Read all three files (skip any that don't exist).
- Find permissions in the project or local settings that are **not** in the user-level
  settings.
- Account for broad user-level globs: `Bash(git:*)` already covers `Bash(git cherry:*)`
  and `Bash(git worktree:*)`; `Bash(gh:*)` covers `Bash(gh pr checks:*)`. Don't propose
  promoting a narrower entry that a user-level glob already grants.
- For each genuinely-new permission, decide if it's project-specific (e.g. a project's
  custom test runner) or general-purpose (e.g. `Bash(make:*)`, common skills).
- Propose general-purpose additions to the user-level settings. Show the user what you'd
  add and why.
- If the user approves, edit the **chezmoi source** (not the destination) and run
  `chezmoi apply --force ~/.claude/settings.json`.

### 5. Act on user input

If `$ARGUMENTS` is provided, filter to only those paths or categories. Otherwise show
all and ask what the user wants to do.

When the user picks an action, run it. For `re-add`, remind the user to commit the
source repo afterward.

## Templates & repos

- **Find the source for any file** with `chezmoi source-path <path>` (pass an absolute
  path — it resolves relative to CWD, so a bare `.claude/...` from a project dir misses).
- **Two source repos.** The active chezmoi source is `~/.local/share/chezmoi`
  (`dotfiles-jl-public`); the private `dotfiles-jl` (`~/Code/gh/dotfiles-jl`) is a
  separate source tree (ssh, Library, private Brewfile). `source-path` tells you which
  one a file lives in — commit and push there.
- **Templated sources (`.tmpl`).** Files like `settings.json.tmpl` contain
  `{{ .chezmoi.homeDir }}` and other directives. **Never `chezmoi re-add` a `.tmpl`** —
  it overwrites the template body with the rendered literal and destroys the `{{ }}`.
  Edit the `.tmpl` by hand, then `chezmoi apply`.
- **A format-on-edit hook reformats markdown** (e.g. this file) on every edit — keep
  content formatter-stable (hence the `·` space placeholders in the table above). The
  hook **refuses to format** when git conflict markers are present; prettier on
  Markdown otherwise rewrites `>>>>>>>` into nested blockquotes and destroys the
  conflict.

## Important

- Never run `chezmoi apply` without user confirmation — it overwrites local files.
- `chezmoi apply` refuses to overwrite a locally-modified destination interactively; in a
  non-interactive (agent) shell it errors with "could not open a new TTY". Use
  `chezmoi apply --force <path>` once the user has confirmed.
- For `MM` conflicts, read both versions and help the user merge rather than picking a
  side blindly.
- Scripts (`R` status) can have side effects — always show their content before running.
