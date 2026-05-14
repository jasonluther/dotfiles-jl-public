#!/usr/bin/env bash
# Bootstrap a fresh machine with dotfiles-jl-public.
#
# macOS (curl is preinstalled):
#   bash -c "$(curl -fsSL https://raw.githubusercontent.com/jasonluther/dotfiles-jl-public/main/install.sh)"
#
# Linux (apt-based; wget is preinstalled on minimal Debian, curl often isn't):
#   bash -c "$(wget -qO- https://raw.githubusercontent.com/jasonluther/dotfiles-jl-public/main/install.sh)"
#
# The bash -c "$(...)" form fully downloads the body before bash starts
# parsing — a dropped connection cannot run a truncated script.
#
# On Linux the script also runs apt prep, sshd hardening, GitHub-key sync,
# and tailscale install before applying chezmoi (see scripts/linux/).
# Optional positional args on Linux are forwarded to scripts/linux/setup.sh
# as module names.

set -euo pipefail

# REPO defaults to the canonical upstream but can be overridden so a forker
# can run their own install.sh without editing this file:
#
#   REPO=alice/dotfiles-jl-public bash -c "$(curl -fsSL https://raw.githubusercontent.com/alice/dotfiles-jl-public/main/install.sh)"
#
# After bootstrap, .chezmoi.toml.tmpl derives the operator's git identity
# from the cloned repo's `git log -1`, and scripts/linux/ssh-keys.sh derives
# the GitHub username from the source's `origin` remote — so forks need no
# additional editing for either to work.
REPO="${REPO:-jasonluther/dotfiles-jl-public}"
EXPECTED_URL="https://github.com/$REPO"
CHEZMOI_SRC="$HOME/.local/share/chezmoi"
BIN_DIR="$HOME/.local/bin"

is_linux=0
is_darwin=0
case "$(uname -s)" in
  Linux*) is_linux=1 ;;
  Darwin*) is_darwin=1 ;;
esac

if ((is_linux)); then
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "error: only apt-based Linux distros are supported" >&2
    exit 1
  fi
  # Minimal prereqs for the chezmoi-installer fetch and for .chezmoi.toml.tmpl
  # to derive identity via `git log` of the cloned source at init time. The
  # full prereq set (gh, claude, …) is installed later by scripts/linux/base.sh.
  echo "==> apt prep (curl, ca-certificates, git)..."
  sudo apt-get update -y
  sudo apt-get install -y --no-install-recommends curl ca-certificates git
fi

if ((is_darwin)); then
  # Homebrew is a hard prereq for scripts/install-packages.sh (the
  # before_ script chezmoi apply runs). The official installer also
  # installs the Xcode CLI tools as a side effect, which gives us git
  # for chezmoi init's identity derivation.
  brew_bin=""
  for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [[ -x "$candidate" ]] && brew_bin="$candidate" && break
  done
  if [[ -z "$brew_bin" ]] && ! command -v brew >/dev/null 2>&1; then
    # NONINTERACTIVE=1 below tells brew's installer not to prompt — but it
    # still needs sudo for /opt/homebrew chown. Prime the sudo timestamp
    # here so the installer's silent `sudo` calls succeed.
    echo "==> Homebrew install needs sudo. Enter your password if prompted."
    if ! sudo -v; then
      echo "error: sudo access is required to install Homebrew." >&2
      echo "       The user '$(id -un)' must be an Administrator on this Mac." >&2
      exit 1
    fi
    echo "==> Installing Homebrew..."
    NONINTERACTIVE=1 /bin/bash -c \
      "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    for candidate in /opt/homebrew/bin/brew /usr/local/bin/brew; do
      [[ -x "$candidate" ]] && brew_bin="$candidate" && break
    done
  fi
  [[ -n "$brew_bin" ]] && eval "$("$brew_bin" shellenv)"
  unset brew_bin candidate
fi

# Install chezmoi if missing. Use ~/.local/bin so we don't need sudo.
if ! command -v chezmoi >/dev/null 2>&1 && [[ ! -x "$BIN_DIR/chezmoi" ]]; then
  echo "==> Installing chezmoi to $BIN_DIR..."
  install -d -m 0755 "$BIN_DIR"
  sh -c "$(curl -fsLS get.chezmoi.io)" -- -b "$BIN_DIR"
fi
export PATH="$BIN_DIR:$PATH"

# Clone/update the chezmoi source. Bootstrap modules need it on disk before
# chezmoi apply runs.
if [[ ! -d "$CHEZMOI_SRC/.git" ]]; then
  echo "==> chezmoi init $REPO..."
  chezmoi init "$REPO"
else
  current_url="$(git -C "$CHEZMOI_SRC" remote get-url origin 2>/dev/null || true)"
  # Treat https/ssh and trailing-`.git`/no-`.git` as equivalent — `chezmoi
  # init` writes the no-suffix https form, but `git clone` and most users
  # write the `.git` suffix; both point at the same repo.
  normalized="${current_url%.git}"
  if [[ "$normalized" != "$EXPECTED_URL" && "$normalized" != "git@github.com:$REPO" ]]; then
    # `chezmoi init` skips cloning when the source dir already exists, so
    # `--force` alone won't swap remotes. Refuse to wipe a dirty tree;
    # otherwise move it aside and re-clone.
    dirty=0
    git -C "$CHEZMOI_SRC" diff --quiet HEAD 2>/dev/null || dirty=1
    [[ -z "$(git -C "$CHEZMOI_SRC" status --porcelain 2>/dev/null)" ]] || dirty=1
    if ((dirty)); then
      echo "error: chezmoi source at $CHEZMOI_SRC points at '$current_url' (expected '$EXPECTED_URL') and has uncommitted changes." >&2
      echo "       Resolve manually, then re-run." >&2
      exit 1
    fi
    backup="$CHEZMOI_SRC.bak.$(date +%Y%m%d%H%M%S)"
    echo "==> chezmoi source remote is '$current_url', expected '$EXPECTED_URL' — moving to $backup and re-initializing..."
    mv "$CHEZMOI_SRC" "$backup"
    chezmoi init "$REPO"
  else
    echo "==> chezmoi update (pull only, no apply yet)..."
    chezmoi update --apply=false
  fi
fi

if ((is_linux)); then
  echo "==> Running Linux bootstrap modules..."
  bash "$CHEZMOI_SRC/scripts/linux/setup.sh" "$@"
fi

echo "==> chezmoi apply..."
chezmoi apply

echo
echo "✓ Dotfiles installed."
cat <<'EOF'

Open a new terminal — or run `exec zsh -l` in this one — so the new
PATH (Homebrew, ~/.local/bin, etc.) is picked up. Newly installed
tools like gh, gcloud, claude, code, etc. won't be found in this
shell until that's done.
EOF
if ((is_linux)); then
  cat <<'EOF'

Next steps on Linux:

  sudo tailscale up --ssh
EOF
fi
