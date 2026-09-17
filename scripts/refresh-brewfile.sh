#!/bin/bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
brewfile_tmp=$(mktemp)
trap 'rm -f "$brewfile_tmp"' EXIT

export HOMEBREW_NO_AUTO_UPDATE=1
brew bundle dump --file="$brewfile_tmp" --force --no-describe --no-restart \
  --no-mas --no-vscode --no-go --no-cargo --no-uv --no-npm

# This Mac's Rift receipt is omitted by bundle dump despite being installed.
if brew list --formula --full-name | grep -qx 'acsandmann/tap/rift'; then
  if ! grep -Eq '^brew "(acsandmann/tap/)?rift"' "$brewfile_tmp"; then
    printf '\nbrew "acsandmann/tap/rift"\n' >> "$brewfile_tmp"
  fi
fi

cp "$brewfile_tmp" "$repo_dir/packages/Brewfile"
printf 'Updated %s\n' "$repo_dir/packages/Brewfile"
