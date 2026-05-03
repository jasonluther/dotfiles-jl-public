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
- SSH client config (`~/.ssh/config`) — 1Password agent on macOS, OrbStack include, drop-in `~/.ssh/config.d/*`
- Claude Code commands, hooks, and base settings
- VSCode user settings (incl. cspell custom-dictionary stub at `~/.config/cspell/personal-words.txt`)
- Personal shell utilities under `~/.local/bin`
- Copier templates for new Python projects
- On-demand hardware dev setup — run `setup-hardware-dev` to install/update arduino-cli, PlatformIO, AVR/ARM toolchains, esphome/esptool, and the cores/libraries listed in `packages/arduino-*.txt` and `packages/platformio.txt`. Not installed by default.
- macOS Terminal.app profile (run `~/.local/share/chezmoi/scripts/macos/install-terminal-profile.sh` once with Terminal quit)

## What's NOT included

- The cspell personal-words list — kept in iCloud Drive at
  `~/Library/Mobile Documents/com~apple~CloudDocs/dotfiles/cspell-words.txt`
  and symlinked into `~/.config/cspell/personal-words.txt` on macOS. Drop a
  copy into iCloud once on a fresh Mac and chezmoi creates the symlink on
  apply. Linux machines skip cspell.
- The `check-backups` symlink — installed by the
  [backup-plans](https://github.com/jasonluther/backup-plans) repo's
  `backup-check/install.sh`.

## Related repos

- [`remote-work`](https://github.com/jasonluther/remote-work) — LXD container provisioning toolkit for isolated work environments.
- [`backup-plans`](https://github.com/jasonluther/backup-plans) — Personal backup-monitoring scripts and launchd agent.
