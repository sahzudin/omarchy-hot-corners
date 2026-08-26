#!/usr/bin/env bash
set -euo pipefail

id="io.github.sahzudin.hotcorners"
target="$HOME/.config/omarchy/plugins/$id"

if [[ ! -d "$target" ]]; then
  echo "Hot Corners is not installed." >&2
  exit 1
fi

python3 "$target/scripts/hotcorners.py" uninstall --purge
rm -rf "$target"
omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true

echo "Removed Hot Corners."