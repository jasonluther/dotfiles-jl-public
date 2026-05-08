#!/usr/bin/env bash
# Install VSCode extensions that the default installer marketplace can't
# provide. Two scenarios:
#   - macOS `code`: marketplace says NotSigned (signature error).
#   - Linux `code-server`: extension isn't on Open VSX (most Microsoft and
#     some proprietary publishers).
# We download the .vsix directly from Microsoft's marketplace and install
# from the local file, which bypasses both the signature check and the
# Open-VSX-vs-MS-marketplace gap.
#
# Args:
#   $1 (optional): path to a brew bundle log; failed extensions are parsed
#                  from "Failed Installing Extensions: foo.bar baz.qux".
#                  When omitted, falls back to the hardcoded list of known
#                  problematic extensions.
#   -- <id> [<id>...]: explicit extension IDs to retry. Used by the
#                  vscode-extensions chezmoi onchange script when a
#                  marketplace install fails.
#
# Marketplace asset URL pattern (the same one VSCode itself uses):
#   https://<publisher>.gallery.vsassets.io/_apis/public/gallery/publisher/
#   <publisher>/extension/<name>/latest/assetbyname/
#   Microsoft.VisualStudio.Services.VSIXPackage

set -euo pipefail

# Extensions that have published unsigned releases recently. Add to this list
# if a marketplace install fails with `Signature verification failed`.
known_unsigned=(
  "stkb.rewrap"
)

declare -a wanted=()

if [[ "${1:-}" == "--" ]]; then
  shift
  wanted=("$@")
elif [[ -n "${1:-}" && -f "$1" ]]; then
  bundle_log="$1"
  # `Failed Installing Extensions: a.b c.d` -> one per line. Take the last
  # occurrence so a retry log overrides earlier output.
  while IFS= read -r ext; do
    [[ -n "$ext" ]] && wanted+=("$ext")
  done < <(awk '
    /Failed Installing Extensions:/ {
      sub(/.*Failed Installing Extensions:[[:space:]]*/, "")
      for (i = 1; i <= NF; i++) print $i
    }
  ' "$bundle_log" | sort -u)
fi

# Fall back to known-bad list if log parsing yielded nothing.
((${#wanted[@]} == 0)) && wanted=("${known_unsigned[@]}")

if command -v code >/dev/null 2>&1; then
  installer=code
elif command -v code-server >/dev/null 2>&1; then
  installer=code-server
else
  echo "vsix-fallback: neither 'code' nor 'code-server' on PATH; skipping." >&2
  exit 0
fi

declare -a failed=()
tmpdir="$(mktemp -d -t vsix.XXXXXX)"
trap 'rm -rf "$tmpdir"' EXIT

for ext in "${wanted[@]}"; do
  if "$installer" --list-extensions 2>/dev/null | grep -ixq "$ext"; then
    echo "vsix-fallback: $ext already installed, skipping."
    continue
  fi

  publisher="${ext%%.*}"
  name="${ext#*.}"
  if [[ -z "$publisher" || -z "$name" || "$publisher" == "$ext" ]]; then
    echo "vsix-fallback: '$ext' is not in publisher.name form, skipping." >&2
    failed+=("$ext")
    continue
  fi

  url="https://${publisher}.gallery.vsassets.io/_apis/public/gallery/publisher/${publisher}/extension/${name}/latest/assetbyname/Microsoft.VisualStudio.Services.VSIXPackage"
  vsix="$tmpdir/${ext}.vsix"
  echo "==> downloading $ext from marketplace"
  if ! curl -fsSL -o "$vsix" "$url"; then
    echo "vsix-fallback: download failed for $ext" >&2
    failed+=("$ext")
    continue
  fi

  echo "==> $installer --install-extension $vsix"
  if ! "$installer" --install-extension "$vsix" --force; then
    failed+=("$ext")
  fi
done

if ((${#failed[@]} > 0)); then
  printf '\033[1;33mvsix-fallback failed:\033[0m %s\n' "${failed[*]}" >&2
  exit 1
fi
