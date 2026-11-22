# Global guidelines (Jason)

User-wide defaults across all projects. A project's own `CLAUDE.md` always takes
precedence over anything here.

The shared rules (git and branches, working safely, cross-platform) load at every session
start from a work plugin that the private overlay turns on (`~/.claude/plugins-private.json`);
change them there. The generic git and GitHub guards come from the public `guards` plugin
(kilotronic/claude-guards); personal skills and private hooks come from the `jl` plugin
(`plugins/jl` in jasonluther/auditor), which `settings.json` turns on.

## Personal

- **Once Jason approves an action, run it yourself** (scripts, tofu, `op` with his Touch ID
  prompt) instead of handing him commands to type. infra/bootstrap stays his to apply by hand.

<!-- Machine-local memory overlay: created empty by default; private overlays may
     fill it with host- or tool-specific guidance. Safe to leave empty. -->

@~/.claude/CLAUDE.local.md
