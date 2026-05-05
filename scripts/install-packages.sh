#!/usr/bin/env bash
# Install OS packages from packages/common.txt + the per-OS list.
# Idempotent — re-run any time.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$(uname -s)" in
  Darwin) os=darwin ;;
  Linux) os=linux ;;
  *)
    echo "error: unsupported OS '$(uname -s)'" >&2
    exit 1
    ;;
esac

# Individual install failures accumulate here so one bad formula or apt
# entry doesn't abort `chezmoi apply`. Summary printed on exit; script
# always exits 0 if it reaches the end.
declare -a failed=()
filtered_brewfile=""
bundle_log=""

cleanup() {
  [[ -n "$filtered_brewfile" ]] && rm -f "$filtered_brewfile"
  [[ -n "$bundle_log" ]] && rm -f "$bundle_log"
  if [[ ${#failed[@]} -gt 0 ]]; then
    printf '\033[1;33mfailed to install:\033[0m %s\n' "${failed[*]}" >&2
  fi
}
trap cleanup EXIT

# Resolve "Could not symlink bin/X" errors by running the exact `brew link
# --overwrite <formula>` recovery command brew prints. Happens when a previous
# install left a stale symlink or another tool (npm, manual install) claimed
# the link target before brew did. Returns 0 if any links were rewritten.
relink_from_log() {
  local log="$1" cmd applied=0
  command -v brew >/dev/null 2>&1 || return 1
  while IFS= read -r cmd; do
    [[ -z "$cmd" ]] && continue
    echo "==> $cmd" >&2
    # shellcheck disable=SC2086
    if $cmd; then applied=1; fi
  done < <(grep -oE 'brew link --overwrite [a-zA-Z0-9_@.+-]+' "$log" | sort -u)
  ((applied))
}

read_list() {
  local arr_name="$1" path="$2" line
  eval "$arr_name=()"
  [[ -f "$path" ]] || return 0
  while IFS= read -r line; do
    line="${line%%#*}"
    line="${line#"${line%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    if [[ -n "$line" ]]; then eval "$arr_name+=(\"\$line\")"; fi
  done <"$path"
}

declare -a common
read_list common "$SRC/packages/common.txt"

if [[ "$os" == "darwin" ]]; then
  if ! xcode-select -p &>/dev/null; then
    xcode-select --install
    echo "Waiting for Xcode CLI tools installation..."
    until xcode-select -p &>/dev/null; do
      sleep 5
    done
  fi

  if ! command -v brew >/dev/null 2>&1; then
    echo "error: Homebrew not installed. Install from https://brew.sh first." >&2
    exit 1
  fi

  # Run a noisy command quietly: capture combined output, only echo it if the
  # command fails (after any relink retry). Keeps `chezmoi apply` output to
  # one progress line per phase unless something actually breaks.
  run_quiet() {
    local label="$1" log status
    shift
    log="$(mktemp -t install-pkg.XXXXXX)"
    "$@" >"$log" 2>&1
    status=$?
    if ((status != 0)) && relink_from_log "$log"; then
      "$@" >"$log" 2>&1
      status=$?
    fi
    if ((status != 0)); then
      printf '\033[1;31m%s failed (exit %d):\033[0m\n' "$label" "$status" >&2
      cat "$log" >&2
    fi
    rm -f "$log"
    return "$status"
  }

  if [[ ${#common[@]} -gt 0 ]]; then
    echo "==> brew install (common.txt: ${#common[@]} packages)"
    if ! run_quiet "brew install (bulk)" brew install "${common[@]}"; then
      echo "==> retrying per-package..." >&2
      for pkg in "${common[@]}"; do
        run_quiet "brew install $pkg" brew install "$pkg" || failed+=("$pkg")
      done
    fi
  fi

  # Reconcile Brewfile casks with apps already installed by hand, .pkg, or
  # the App Store. The resolver tries `brew install --cask --adopt` for each
  # collision; anything it can't adopt is printed on stdout so we can drop it
  # from the Brewfile we feed to `brew bundle` (which would otherwise abort).
  echo "==> resolving cask conflicts"
  mapfile -t skip_casks < <("$SRC/scripts/macos/resolve-cask-conflicts.sh" "$SRC/Brewfile")

  # `brew bundle` exits non-zero when any entry fails. Capture output so we
  # can self-heal "Could not symlink" errors via `brew link --overwrite` and
  # try once more before giving up. Record the residual failure rather than
  # aborting so chezmoi apply continues.
  bundle_log="$(mktemp -t brew-bundle.XXXXXX)"
  if ((${#skip_casks[@]} > 0)); then
    filtered_brewfile="$(mktemp -t Brewfile.XXXXXX)"
    awk -v skips="$(
      IFS='|'
      echo "${skip_casks[*]}"
    )" '
      BEGIN { n = split(skips, arr, "|"); for (i = 1; i <= n; i++) skip[arr[i]] = 1 }
      /^[[:space:]]*cask "/ {
        match($0, /"[^"]+"/)
        name = substr($0, RSTART + 1, RLENGTH - 2)
        if (skip[name]) next
      }
      { print }
    ' "$SRC/Brewfile" >"$filtered_brewfile"
    echo "==> brew bundle (Brewfile, skipping ${#skip_casks[@]} conflicting cask(s): ${skip_casks[*]})"
    bundle_target="$filtered_brewfile"
  else
    echo "==> brew bundle (Brewfile)"
    bundle_target="$SRC/Brewfile"
  fi

  # `|| bundle_status=$?` keeps `set -e` from killing the script on a brew
  # bundle failure — recovery (relink, vsix fallback) and `brew bundle check`
  # below are responsible for distinguishing recoverable failures from real
  # ones.
  bundle_status=0
  brew bundle --file="$bundle_target" >"$bundle_log" 2>&1 || bundle_status=$?
  if ((bundle_status != 0)) && relink_from_log "$bundle_log"; then
    echo "==> retrying after relink" >&2
    bundle_status=0
    brew bundle --file="$bundle_target" >"$bundle_log" 2>&1 || bundle_status=$?
  fi

  # If brew bundle reported VSCode signature failures, recover via .vsix
  # silently. The "brew bundle check" pass below decides whether anything was
  # left unresolved.
  if [[ -x "$SRC/scripts/macos/install-vscode-vsix-fallback.sh" ]] \
    && grep -qE 'Failed Installing Extensions' "$bundle_log"; then
    echo "==> retrying signature-rejected VSCode extensions via .vsix"
    "$SRC/scripts/macos/install-vscode-vsix-fallback.sh" "$bundle_log" >/dev/null 2>&1 \
      || failed+=("vsix-fallback")
  fi

  # Re-check the bundle authoritatively. If everything resolved (including via
  # vsix fallback), brew bundle check passes and we stay quiet. Anything still
  # missing is a real failure we should surface.
  if ! brew bundle check --file="$bundle_target" --no-upgrade >/dev/null 2>&1; then
    printf '\033[1;31mbrew bundle: residual failures after recovery:\033[0m\n' >&2
    brew bundle check --file="$bundle_target" --no-upgrade --verbose >&2 || true
    failed+=("brew-bundle-entries")
  fi

  exit 0
fi

# Linux / Debian.
if ! command -v apt-get >/dev/null 2>&1; then
  echo "error: only apt-based Linux is supported by this script." >&2
  exit 1
fi

declare -A alias_map=()
if [[ -f "$SRC/packages/apt-aliases.txt" ]]; then
  while IFS='=' read -r key val; do
    key="${key%%#*}"
    key="${key#"${key%%[![:space:]]*}"}"
    key="${key%"${key##*[![:space:]]}"}"
    val="${val#"${val%%[![:space:]]*}"}"
    val="${val%"${val##*[![:space:]]}"}"
    if [[ -n "$key" && -n "$val" ]]; then alias_map["$key"]="$val"; fi
  done <"$SRC/packages/apt-aliases.txt"
fi

candidates=()
for pkg in "${common[@]:-}"; do
  candidates+=("${alias_map[$pkg]:-$pkg}")
done
read_list apt_only "$SRC/packages/apt.txt"
candidates+=("${apt_only[@]:-}")

# Filter out packages with no install candidate on this distro. Capture
# the policy output rather than `| grep -q`: under `pipefail`, grep's
# early exit sends SIGPIPE to apt-cache and the whole pipeline returns
# 141, which spuriously marks packages as skipped.
sudo apt-get update -y
available=()
skipped=()
for pkg in "${candidates[@]}"; do
  [[ -z "$pkg" ]] && continue
  candidate=$(apt-cache policy "$pkg" 2>/dev/null | awk '/^  Candidate:/ {print $2; exit}')
  if [[ -n "$candidate" && "$candidate" != "(none)" ]]; then
    available+=("$pkg")
  else
    skipped+=("$pkg")
  fi
done

if [[ ${#available[@]} -gt 0 ]]; then
  echo "==> apt-get install (${#available[@]} packages)"
  if ! sudo apt-get install -y --no-install-recommends "${available[@]}"; then
    echo "==> apt-get install: bulk failed, retrying per-package..." >&2
    for pkg in "${available[@]}"; do
      sudo apt-get install -y --no-install-recommends "$pkg" || failed+=("$pkg")
    done
  fi
fi

# Fallback installers for tools Debian doesn't ship (or ships too stale).
# Each handler installs the tool to ~/.local/bin (no sudo) and is idempotent.
install -d "$HOME/.local/bin"

fallback_ruff() {
  command -v ruff >/dev/null 2>&1 && return 0
  curl -LsSf https://astral.sh/ruff/install.sh | env UV_INSTALL_DIR="$HOME/.local/bin" sh
}

fallback_watchexec() {
  command -v watchexec >/dev/null 2>&1 && return 0
  local ver=2.5.1 arch
  case "$(uname -m)" in
    x86_64) arch=x86_64-unknown-linux-gnu ;;
    aarch64 | arm64) arch=aarch64-unknown-linux-gnu ;;
    *)
      echo "watchexec: unsupported arch $(uname -m)" >&2
      return 0
      ;;
  esac
  local tarball="watchexec-${ver}-${arch}.tar.xz"
  curl -fsSL "https://github.com/watchexec/watchexec/releases/download/v${ver}/${tarball}" \
    | tar -xJ -C "$HOME/.local/bin" --strip-components=1 "watchexec-${ver}-${arch}/watchexec"
}

fallback_tldr() {
  command -v tldr >/dev/null 2>&1 && return 0
  # tealdeer is the rust tldr client; ships static linux binaries.
  local ver=1.8.1 arch
  case "$(uname -m)" in
    x86_64) arch=x86_64-musl ;;
    aarch64 | arm64) arch=aarch64-musl ;;
    *)
      echo "tldr: unsupported arch $(uname -m)" >&2
      return 0
      ;;
  esac
  curl -fsSL -o "$HOME/.local/bin/tldr" \
    "https://github.com/tealdeer-rs/tealdeer/releases/download/v${ver}/tealdeer-linux-${arch}"
  chmod +x "$HOME/.local/bin/tldr"
}

declare -a still_skipped=()
for pkg in "${skipped[@]:-}"; do
  case "$pkg" in
    ruff) fallback_ruff || failed+=("ruff") ;;
    watchexec) fallback_watchexec || failed+=("watchexec") ;;
    tldr) fallback_tldr || failed+=("tldr") ;;
    *) still_skipped+=("$pkg") ;;
  esac
done

if [[ ${#still_skipped[@]} -gt 0 ]]; then
  printf '\033[1;33mskipped (not in apt):\033[0m %s\n' "${still_skipped[*]}" >&2
fi
