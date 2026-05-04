# dotfiles-jl-public

Jason Luther's portable dotfiles for macOS and apt-based Linux.

## Install

```sh
# curl (macOS)
bash -c "$(curl -fsSL https://raw.githubusercontent.com/jasonluther/dotfiles-jl-public/main/install.sh)"

# wget (minimal Debian)
bash -c "$(wget -qO- https://raw.githubusercontent.com/jasonluther/dotfiles-jl-public/main/install.sh)"
```

`install.sh` detects the OS, installs Homebrew (macOS) or apt prereqs (Linux), then runs `chezmoi apply`. Git identity and GitHub username are derived from the source repo, so a fork Just Works for its owner. Override with `CHEZMOI_NAME`, `CHEZMOI_EMAIL`, or `GH_USER`.

On Linux it also runs bootstrap modules from [`scripts/linux/`](scripts/linux/): `ssh-keys`, `harden-sshd`, `sudo-nopasswd`, `base`, `tailscale`. Re-run a subset later:

```sh
bash ~/.local/share/chezmoi/scripts/linux/setup.sh ssh-keys
```

### ⚠️ If you are SSH'd in over password right now

`harden-sshd` disables password authentication. Make sure your key is at `https://github.com/<gh-user>.keys` before running, or you can lock yourself out.

## What's included

- zsh, tmux, vim, fzf, ripgrep, vale, markdownlint configs
- macOS Homebrew bootstrap (Brewfile, MAS apps)
- Linux fresh-host bootstrap (sshd hardening, key sync, tailscale)
- SSH client config with 1Password agent on macOS
- Claude Code commands, hooks, and settings
- VSCode user settings
- Personal shell utilities under `~/.local/bin`
- Copier templates for new Python projects
- On-demand hardware dev setup via `setup-hardware-dev`
