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

### ⚠️ Nightly auto-updates

`unattended-upgrades` installs updates from **all** configured apt origins
nightly. It never reboots by itself: when an update needs one,
`/var/run/reboot-required` appears and the reboot waits for you. Kernel security
fixes take effect only after that reboot, so check for the file and reboot when
nothing is running overnight.
