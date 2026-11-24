# Global guidelines (Jason)

User-wide defaults across all projects. A project's own `CLAUDE.md` always takes
precedence over anything here.

The shared rules (git and branches, working safely, cross-platform) load at every session
start from a work plugin that the private overlay turns on (`~/.claude/plugins-private.json`);
change them there. The generic git and GitHub guards come from the public `guards` plugin,
and the `goal` command from its `work` plugin (both kilotronic/claude-guards); personal
skills and private hooks come from the `jl` plugin (`plugins/jl` in jasonluther/auditor).
`settings.json` turns all three on.

## Personal

- **Once Jason approves an action, run it yourself** (scripts, `op` with his Touch ID prompt; never a tofu apply)
  instead of handing him commands to type.
- **Tofu: plan freely, never apply, even after an approval.** `tofu plan` (and `fmt`, `validate`)
  is fine to run. Applying happens only from merged configurations, by CI on merge or by Jason by
  hand (infra/bootstrap, access): open the pull request and say in it whether CI or Jason applies it.
