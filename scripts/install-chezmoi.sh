#!/usr/bin/env bash
# Install a pinned chezmoi release into a directory, checking the download's
# SHA-256 before unpacking it (instead of piping get.chezmoi.io into a shell).
#
# Usage: scripts/install-chezmoi.sh <bin-dir>
#
# install.sh fetches this file from the same repo and ref it came from, so a
# fresh machine and CI install the same checked binary. To upgrade, set
# VERSION and copy the four lines from that release's
# chezmoi_<version>_checksums.txt.

set -euo pipefail

VERSION=2.74.1
checksum_for() {
  case "$1" in
    darwin_amd64) echo b2229c6ff9eb7d1f10d098aac94241da652dd7df989c7ef35df6777dbe00d397 ;;
    darwin_arm64) echo fbc7b86c7b36eb0448e2a99a616b6d32f022d1f3895076ad44f4c5d65a77fe60 ;;
    linux_amd64) echo ae01c66b1a6dbf563667c63fbbd9986b3cfa3c98dd266ddee732f63e8af2e9d1 ;;
    linux_arm64) echo 8c62619c4303770342e7c7e75d168b6cc6efee4ad5e4b994980de7cf794d68e2 ;;
    *) return 1 ;;
  esac
}

bin_dir="${1:?usage: install-chezmoi.sh <bin-dir>}"

case "$(uname -s)" in
  Darwin) os=darwin ;;
  Linux) os=linux ;;
  *)
    echo "error: unsupported OS $(uname -s)" >&2
    exit 1
    ;;
esac
case "$(uname -m)" in
  x86_64 | amd64) arch=amd64 ;;
  arm64 | aarch64) arch=arm64 ;;
  *)
    echo "error: unsupported CPU $(uname -m)" >&2
    exit 1
    ;;
esac
platform="${os}_${arch}"
expected="$(checksum_for "$platform")"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
tarball="chezmoi_${VERSION}_${platform}.tar.gz"
curl -fsSL -o "$tmp/$tarball" \
  "https://github.com/twpayne/chezmoi/releases/download/v${VERSION}/${tarball}"

if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "$tmp/$tarball" | cut -d' ' -f1)"
else
  actual="$(shasum -a 256 "$tmp/$tarball" | cut -d' ' -f1)"
fi
if [[ "$actual" != "$expected" ]]; then
  echo "error: $tarball checksum mismatch (expected $expected, got $actual)" >&2
  exit 1
fi

tar -xzf "$tmp/$tarball" -C "$tmp" chezmoi
install -d -m 0755 "$bin_dir"
install -m 0755 "$tmp/chezmoi" "$bin_dir/chezmoi"
echo "chezmoi $VERSION installed to $bin_dir"
