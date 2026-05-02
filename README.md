# dotfiles-jl-public

Jason Luther's portable dotfiles. Works on a fresh macOS machine.

## Install

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/jasonluther/dotfiles-jl-public/main/install.sh)"
```

This installs chezmoi (if missing) and applies the dotfiles. You'll be prompted for a git name and email on first run.

If you'd rather skip the wrapper:

```sh
sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply jasonluther/dotfiles-jl-public
```

## What's included

- zsh, tmux, vim, fzf, ripgrep, vale, markdownlint configs
- macOS Homebrew bootstrap (Brewfile, MAS apps)
- Claude Code commands, hooks, and base settings
- Personal shell utilities under `~/.local/bin`
- Copier templates for new Python projects

## What's NOT included

Host-specific items (SSH config, internal hostnames, work-machine state) live in a private overlay.

## Related repos

- [`first-time`](https://github.com/jasonluther/first-time) — Linux-server bootstrap (apt, sshd hardening, key sync, tailscale). Calls this repo as its `chezmoi` module.
- [`remote-work`](https://github.com/jasonluther/remote-work) — LXD container provisioning toolkit for isolated work environments.
- [`dotfiles-jl`](https://github.com/jasonluther/dotfiles-jl) — Private overlay (SSH config, internal hostnames, machine-local Claude settings). Personal machines only.
