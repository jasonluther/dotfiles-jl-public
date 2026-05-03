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

REPO="jasonluther/dotfiles-jl-public"
EXPECTED_URL="https://github.com/$REPO"
CHEZMOI_SRC="$HOME/.local/share/chezmoi"
BIN_DIR="$HOME/.local/bin"

is_linux=0
case "$(uname -s)" in
  Linux*) is_linux=1 ;;
esac

if ((is_linux)); then
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "error: only apt-based Linux distros are supported" >&2
    exit 1
  fi
  # Minimal prereq for the chezmoi-installer fetch below. The full
  # prereq set (git, gh, claude, …) is installed by scripts/linux/base.sh
  # after chezmoi init clones the source. chezmoi uses its built-in git
  # for the initial clone, so system git isn't needed yet.
  echo "==> apt prep (curl, ca-certificates)..."
  sudo apt-get update -y
  sudo apt-get install -y --no-install-recommends curl ca-certificates
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
  if [[ "$current_url" != "$EXPECTED_URL" && "$current_url" != "git@github.com:$REPO.git" ]]; then
    # `chezmoi init` skips cloning when the source dir already exists, so
    # `--force` alone won't swap remotes. Refuse to wipe a dirty tree;
    # otherwise move it aside and re-clone.
    if ! git -C "$CHEZMOI_SRC" diff --quiet HEAD 2>/dev/null ||
      [[ -n "$(git -C "$CHEZMOI_SRC" status --porcelain 2>/dev/null)" ]]; then
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
if ((is_linux)); then
  cat <<'EOF'

Next steps on Linux:

  sudo tailscale up --ssh

If a private overlay applies to this machine, layer it now:

  git clone git@github.com:jasonluther/dotfiles-jl.git ~/.local/share/chezmoi-private
  ~/.local/share/chezmoi-private/private_dot_local/bin/executable_dotfiles-bootstrap
EOF
fi
