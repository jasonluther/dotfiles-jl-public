# Files by role

This dotfiles repo is laid out flat at the chezmoi level (chezmoi requires this for files that target `~/`). Files are grouped by role here, with one-liners describing what each does.

## Shell (interactive zsh experience)

- `dot_zshrc` — entry point; sets PATH, history, plugin loader; sources fragments from `~/.config/shell/`.
- `dot_zprofile` — login-shell environment (Homebrew, pyenv init).
- `dot_config/shell/aliases.sh` — aliases and helper functions (`psg`, `web-server`, `root`, `random-password`, `start-work`, `loop_until_*`).
- `dot_config/shell/fzf.sh` — fzf integration (auto-detects bash vs zsh).
- `dot_config/shell/modern-cli.sh` — modern-CLI tool config (bat, eza, fd, ripgrep, zoxide, tldr).

## Editor

- `dot_vim/vimrc` — minimal vim config (2-space tabs).
- `dot_ripgreprc` — ripgrep defaults.
- `dot_vale.ini` — vale prose-linting config (global fallback).
- `dot_markdownlintrc` — markdownlint config.

## Terminal

- `dot_tmux.conf` — tmux config.

## Git / version control

- `dot_gitconfig.tmpl` — identity (templated `{{ .name }}` / `{{ .email }}`), init, push/pull/fetch defaults, credential helpers, URL rewrites; pulls aliases and delta config via [include].
- `dot_config/git/aliases` — git aliases (s, cm, aa, co, cob, p, pl, pu, undo, amend, wip, save).
- `dot_config/git/delta` — delta pager config (navigate, line-numbers, syntax theme).

## macOS bootstrap

- `Brewfile` — essential Homebrew formulae, casks, and VS Code extensions.
- `mas.txt` — essential Mac App Store apps.
- `.chezmoiscripts/run_onchange_before_install-packages.sh.tmpl` — Xcode CLI tools + `brew bundle`.
- `.chezmoiscripts/run_onchange_after_install-mas-apps.sh.tmpl` — `mas install` per `mas.txt`.
- `.chezmoiscripts/run_onchange_after_configure-macos-defaults.sh.tmpl` — `defaults write` for Finder, Dock, Terminal, etc.
- `.chezmoiscripts/run_onchange_after_enable-touch-id-sudo.sh.tmpl` — Touch ID for sudo via `/etc/pam.d/sudo_local`.
- `.chezmoiscripts/run_onchange_after_setup-python.sh.tmpl` — pyenv-managed Python versions.
- `.chezmoiscripts/run_once_after_setup-hardware-dev.py.tmpl` — Arduino CLI cores, PlatformIO, CircuitPython tools.

## Claude Code

- `private_dot_claude/settings.json.tmpl` — base settings (templated for `{{ .chezmoi.homeDir }}` so paths resolve per-machine).
- `private_dot_claude/commands/*.md` — slash command definitions (chezmoi, code-review, icloud-cleanup, lint-problems, pr).
- `private_dot_claude/hooks/executable_block-main-edits.sh` — PreToolUse hook blocking edits on main.
- `private_dot_claude/hooks/executable_format-on-edit.sh` — PostToolUse formatter (ruff, shfmt, prettier).

## Personal CLI utilities (`~/.local/bin/`)

- `private_dot_local/bin/executable_gh-init` — scaffold a copier-templated project on GitHub.
- `private_dot_local/bin/executable_git-cleanup-branches` — prune merged/abandoned local branches.
- `private_dot_local/bin/executable_lint-problems` — run all linters that feed VSCode's Problems panel.
- `private_dot_local/bin/executable_reset-hostname` — set macOS ComputerName/HostName/LocalHostName/NetBIOSName (requires hostname arg).
- `private_dot_local/bin/executable_review-diff` — show a structured review of recent git diffs.
- `private_dot_local/bin/executable_start-work-setup` — bring up a dev session (worktree + claude).
- `private_dot_local/bin/executable_sync-gh.py` — keep `~/Code/gh/` in sync with starred/owned GitHub repos.

## Project scaffolding

- `templates/python-uv/` — copier template for Python-only projects (uv + ruff + hatchling).
- `templates/python-uv-with-js/` — Python + JS variant.
- `copier.yml` — copier root selecting between flavors.

## Bootstrap entry points

- `install.sh` — one-line bootstrap (`bash -c "$(curl …)"`), installs chezmoi if missing, runs `chezmoi init --apply`.
- `.chezmoi.toml.tmpl` — prompts for git identity at `chezmoi init`.
- `.chezmoiexternal.toml` — pulls zsh-autoswitch-virtualenv plugin.
- `.chezmoiignore` — skip macOS-only files on non-Darwin platforms.

## Docs

- `README.md` — project overview, install command, related repos.
- `docs/by-role.md` — this file.
- `docs/python-toolset.md` — current vs legacy Python tooling reference.

## CI

- `.github/workflows/templates-smoke.yml` — scaffold both copier flavors, run pre-commit twice (auto-fix then verify clean).
