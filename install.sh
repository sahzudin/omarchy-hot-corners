#!/usr/bin/env bash
set -euo pipefail

plugin_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
id="io.github.sahzudin.hotcorners"
target="$HOME/.config/omarchy/plugins/$id"

if [[ ${1:-} == "--help" || ${1:-} == "-h" ]]; then
  echo "Usage: $0"
  echo "Installs the Hot Corners plugin (settings panel + Hyprland Lua driver)."
  exit 0
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0" >&2
  exit 2
fi

rm -rf "$target"
mkdir -p "$(dirname "$target")"
cp -r "$plugin_dir" "$target"
rm -rf "$target/.git"

omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true
python3 "$target/scripts/hotcorners.py" install
omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true
omarchy-shell -q omarchy.menu refresh >/dev/null 2>&1 || true

echo "Installed Hot Corners. Open Setup > Mouse > Hot Corners to configure."