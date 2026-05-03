# dotfiles-jl-public

Jason Luther's portable dotfiles. Works on a fresh macOS or apt-based Linux machine.

## Install

### macOS

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/jasonluther/dotfiles-jl-public/main/install.sh)"
```

Installs chezmoi (if missing) and applies the dotfiles. You'll be prompted for a git name and email on first run.

### Linux (apt-based)

`wget` is preinstalled on minimal Debian; `curl` often isn't. Either works:

```sh
bash -c "$(wget -qO- https://raw.githubusercontent.com/jasonluther/dotfiles-jl-public/main/install.sh)"
```

The `bash -c "$(...)"` form fully downloads the body before bash starts parsing — a dropped connection cannot run a truncated script.

In addition to the chezmoi apply, the Linux path runs bootstrap modules from [`bootstrap/linux/`](bootstrap/linux/):

| module      | what it does                                                                                              |
| ----------- | --------------------------------------------------------------------------------------------------------- |
| `base`      | drops a hardened `sshd_config.d/` snippet (key-only auth), installs `openssh-server`, `git`, `curl`, `gh` |
| `ssh-keys`  | syncs keys from `https://github.com/jasonluther.keys` into `~/.ssh/authorized_keys` (revocation-aware)    |
| `tailscale` | installs tailscale and enables `tailscaled` (does **not** run `tailscale up`)                             |

After it finishes:

```sh
sudo tailscale up --ssh
```

To re-run a subset of modules later:

```sh
bash ~/.local/share/chezmoi/bootstrap/linux/setup.sh ssh-keys
```

#### ⚠️ If you are SSH'd in over password right now

`base` disables password authentication. Existing sessions persist, but new logins will require a key. **Make sure your key is in `https://github.com/jasonluther.keys` before running, or run from console.** Otherwise you can lock yourself out if the script fails between sshd reload and `ssh-keys` running.

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
