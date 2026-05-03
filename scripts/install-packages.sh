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

  if [[ ${#common[@]} -gt 0 ]]; then
    echo "==> brew install (common.txt: ${#common[@]} packages)"
    brew install "${common[@]}"
  fi

  echo "==> brew bundle (Brewfile)"
  brew bundle --file="$SRC/Brewfile"
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
  sudo apt-get install -y --no-install-recommends "${available[@]}"
fi
if [[ ${#skipped[@]} -gt 0 ]]; then
  printf '\033[1;33mskipped (not in apt):\033[0m %s\n' "${skipped[*]}" >&2
fi
