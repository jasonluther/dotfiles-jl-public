# Chezmoi Sync

Analyze and resolve differences between chezmoi source and destination.

## Steps

### 1. Get status

Run `chezmoi status` and `chezmoi diff --no-pager`. If there are no differences, say
so and stop.

### 2. Categorize each changed file

For each file in the status output, determine the situation from the two-column status
code:

| Status | Meaning | Action |
|--------|---------|--------|
| ` M` | Destination matches source, but target state differs (template/config change) | Review diff, suggest `chezmoi apply <path>` |
| `M ` | Destination was modified after last apply (local edits) | Review diff, suggest `chezmoi re-add <path>` to pull changes into source |
| `MM` | Both source and destination changed | Show both sides, help user merge manually then `chezmoi re-add` |
| ` A` | New file in target state | Suggest `chezmoi apply <path>` |
| `A ` | File was created locally | Suggest `chezmoi add <path>` if it should be managed |
| ` D` | File will be deleted by apply | Confirm with user before applying |
| `D ` | Managed file was deleted locally | Suggest `chezmoi apply <path>` to restore or `chezmoi forget <path>` to stop managing |
| ` R` | Script will be run | Show the script content, ask user if they want to run it |
| `R ` | Script was run since last apply | Informational only |

### 3. Present a summary

Group files by category. For each file show:
- The path
- A one-line description of what changed (from the diff)
- The recommended action

### 4. Audit Claude Code permissions

Compare the current project's `.claude/settings.json` and `.claude/settings.local.json`
against the user-level settings in `~/.claude/settings.json` (managed by chezmoi from
the dotfiles repo).

- Read all three files (skip any that don't exist).
- Find permissions in the project or local settings that are **not** in the user-level
  settings.
- For each, decide if it's project-specific (e.g. a project's custom test runner) or
  general-purpose (e.g. `Bash(make:*)`, common skills).
- Propose general-purpose additions to the user-level `~/.claude/settings.json`. Show
  the user what you'd add and why.
- If the user approves, edit the **chezmoi source** file (in the dotfiles repo, not the
  destination) and run `chezmoi apply ~/.claude/settings.json`.

### 5. Act on user input

If `$ARGUMENTS` is provided, filter to only those paths or categories. Otherwise show
all and ask what the user wants to do.

When the user picks an action, run it. For `re-add`, remind the user to commit the
source repo afterward.

## Important

- Never run `chezmoi apply` without user confirmation — it overwrites local files.
- For `MM` conflicts, read both versions and help the user merge rather than picking a
  side blindly.
- Scripts (`R` status) can have side effects — always show their content before running.
