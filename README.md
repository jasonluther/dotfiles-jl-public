# dotfiles-jl-public

Initial setup and chezmoi for macOS and Debian.

## Install

### curl (macOS)

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/jasonluther/dotfiles-jl-public/main/install.sh)"
```

### wget (minimal Debian)

```sh
bash -c "$(wget -qO- https://raw.githubusercontent.com/jasonluther/dotfiles-jl-public/main/install.sh)"
```

`install.sh` detects the OS, installs Homebrew (macOS) or apt prereqs
(Linux), then runs `chezmoi apply`.

Identity is derived from the source repo. Override with `CHEZMOI_NAME`, `CHEZMOI_EMAIL`, or `GH_USER`.

### ⚠️ SSH password auth gets disabled

`harden-sshd` disables password authentication. Ensure your key is at
`https://github.com/<gh-user>.keys` before running.

### ⚠️ Nightly auto-updates and reboots

`unattended-upgrades` installs updates from **all** configured apt origins
nightly and reboots at 04:00 when required — even with users logged in.
