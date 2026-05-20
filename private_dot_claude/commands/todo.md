# Todo

Capture a pending action for the user into the macOS Reminders app via the `reminders` CLI.

## Goal

The user typed `/todo`. Look at what we were just talking about, identify the action
_they_ still need to take (not something you're about to do), and add it to the
"Reminders" list — or update an existing entry if one is already there for this thing.

This is meant to be friction-free: the user types `/todo` mid-conversation and trusts
you to capture the right thing. Keep the round trip short.

## Steps

### 1. Identify the action

Scan recent conversation turns. The todo should be something _the user_ will do later
— a person to email, a decision to make, a system to check, a doc to read, a follow-up
to take. Skip anything you're already doing in this session.

If `$ARGUMENTS` is provided, use it verbatim as the todo text (or as a hint that
overrides your inference). With no arguments, derive the text yourself.

If nothing actionable is pending, say so and stop. Don't invent a todo.

### 2. Check for an existing match

Run `reminders show Reminders --format json` and look for an item covering the same
thing (fuzzy match — same person, same system, same topic). If found, prefer editing
it over creating a duplicate.

### 3. Write a good title

- Short, imperative, scannable in a list view ("email Andy re footlocker renewal",
  not "I should probably reach out to Andy at some point about the footlocker thing").
- Lead with the verb or the proper noun, whichever is more distinctive.
- Keep it under ~80 chars; put detail in `--notes`.

### 4. Add or update

```bash
# New todo
reminders add Reminders "<title>" --notes "<context: file paths, URLs, ticket IDs>"

# Update existing — get the index from `reminders show Reminders`
reminders edit Reminders <index> "<new title>" --notes "<merged notes>"
```

Use `--notes` to stash anything the future-user will need to pick the thread back up:
the file path we were looking at, a PR URL, a ticket ID, the relevant Slack thread, a
one-line summary of why this matters. Don't dump the whole transcript.

If a due date came up in conversation ("by Friday", "before the next release"), pass
`--due-date`. Otherwise leave it off.

### 5. Confirm

One line back to the user: `Added: <title>` or `Updated #N: <title>`. That's it.

## Notes

- Default list is "Reminders" unless `$ARGUMENTS` names a different one (e.g.
  `/todo list=Work email Andy`). Confirm the list exists with `reminders show-lists`
  before adding to a non-default list; create it with `reminders new-list <name>` only
  if the user explicitly asked for that list.
- Don't complete or delete reminders from this command — only add and edit.
- If the user's last message _is_ the action ("remind me to X"), take it literally and
  skip the inference step.
