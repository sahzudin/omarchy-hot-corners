#!/usr/bin/env bash
set -euo pipefail

id="io.github.sahzudin.hotcorners"
target="$HOME/.config/omarchy/plugins/$id"
backend="$HOME/.local/share/omarchy-hotcorners/scripts/hotcorners.py"

if [[ ${1:-} == "--help" || ${1:-} == "-h" ]]; then
  echo "Usage: $0"
  echo "Removes the Hot Corners plugin, its Hyprland driver, and its settings."
  exit 0
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0" >&2
  exit 2
fi

# Prefer the checkout, but fall back to the copy of the backend kept outside
# it, so this still works after 'omarchy plugin remove' deleted the plugin.
if [[ -f "$target/scripts/hotcorners.py" ]]; then
  script="$target/scripts/hotcorners.py"
elif [[ -f $backend ]]; then
  script="$backend"
else
  echo "Hot Corners is not installed." >&2
  exit 1
fi

if ! result=$(python3 "$script" uninstall --purge); then
  echo "$result" >&2
  exit 1
fi

rm -rf "$target"
omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true
omarchy-shell -q omarchy.menu refresh >/dev/null 2>&1 || true

echo "Removed Hot Corners."
