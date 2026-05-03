# dotfiles-jl-public

Jason Luther's portable dotfiles. Works on a fresh macOS or apt-based Linux machine.

## Install

`install.sh` detects macOS vs apt-based Linux and does the right thing for each. Use whichever downloader is on the box — `curl` is preinstalled on macOS; `wget` is preinstalled on minimal Debian and `curl` often isn't:

```sh
# curl
bash -c "$(curl -fsSL https://raw.githubusercontent.com/jasonluther/dotfiles-jl-public/main/install.sh)"

# wget
bash -c "$(wget -qO- https://raw.githubusercontent.com/jasonluther/dotfiles-jl-public/main/install.sh)"
```

The `bash -c "$(...)"` form fully downloads the body before bash starts parsing — a dropped connection cannot run a truncated script.

On either OS the wrapper installs chezmoi (if missing) and runs `chezmoi apply`. You'll be prompted for a git name and email on first run.

On Linux it additionally runs bootstrap modules from [`scripts/linux/`](scripts/linux/) before the apply:

| module          | what it does                                                                                                                |
| --------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `ssh-keys`      | syncs keys from `https://github.com/$GH_USER.keys` (default `jasonluther`) into `~/.ssh/authorized_keys` (revocation-aware) |
| `harden-sshd`   | drops a hardened `sshd_config.d/` snippet (key-only auth) and installs `openssh-server`                                     |
| `sudo-nopasswd` | grants the current user passwordless sudo via `/etc/sudoers.d`, validated by `visudo`                                       |
| `base`          | installs the prereqs chezmoi and the dotfiles need: `git`, `curl`, `ca-certificates`, `gh`, `claude`                        |
| `tailscale`     | installs tailscale and enables `tailscaled` (does **not** run `tailscale up`)                                               |

After it finishes:

```sh
sudo tailscale up --ssh
```

To re-run a subset of modules later:

```sh
bash ~/.local/share/chezmoi/scripts/linux/setup.sh ssh-keys
```

### ⚠️ If you are SSH'd in over password right now

`harden-sshd` disables password authentication. Existing sessions persist, but new logins will require a key. **Make sure your key is in `https://github.com/$GH_USER.keys` (default `jasonluther`; export `GH_USER=youruser` before running to override) or run from console.** Otherwise you can lock yourself out if the script fails between sshd reload and `ssh-keys` running.

### Skip the wrapper

If you'd rather invoke chezmoi directly (no Linux bootstrap modules):

```sh
sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply jasonluther/dotfiles-jl-public
```

## What's included

- zsh, tmux, vim, fzf, ripgrep, vale, markdownlint configs
- macOS Homebrew bootstrap (Brewfile, MAS apps)
- Linux fresh-host bootstrap (apt prep, sshd hardening, key sync, tailscale)
- Claude Code commands, hooks, and base settings
- Personal shell utilities under `~/.local/bin`
- Copier templates for new Python projects

## What's NOT included

Host-specific items (SSH config, internal hostnames, work-machine state) live in a private overlay.

## Related repos

- [`remote-work`](https://github.com/jasonluther/remote-work) — LXD container provisioning toolkit for isolated work environments.
- [`dotfiles-jl`](https://github.com/jasonluther/dotfiles-jl) — Private overlay (SSH config, internal hostnames, machine-local Claude settings). Personal machines only.
