#!/usr/bin/env bash
set -euo pipefail

if ! command -v file >/dev/null 2>&1; then
  echo "'file' utility not available; skipping binary verification."
  exit 0
fi

binary_files=$(git ls-files -z | xargs -0 -r file --mime | awk -F: '$2 ~ /charset=binary/ {print $1}')
if [[ -n "${binary_files}" ]]; then
  echo "Binary files detected in repository:"
  echo "${binary_files}"
  exit 1
fi

echo "No binaries detected."
