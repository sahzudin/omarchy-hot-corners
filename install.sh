#!/usr/bin/env bash
set -euo pipefail

plugin_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
id="io.github.sahzudin.hotcorners"
target="$HOME/.config/omarchy/plugins/$id"

if [[ ${1:-} == "--help" || ${1:-} == "-h" ]]; then
  echo "Usage: $0"
  echo "Installs the Hot Corners plugin (settings panel + Hyprland Lua driver)."
  echo
  echo "Safe to run from an existing install, including a checkout made by"
  echo "'omarchy plugin add'; in that case nothing is copied and the runtime"
  echo "is simply brought up to date."
  exit 0
elif [[ $# -gt 0 ]]; then
  echo "Usage: $0" >&2
  exit 2
fi

# Running from the installed location (an 'omarchy plugin add' checkout, or a
# second run of this script) means there is nothing to copy: the source and
# the destination are the same directory.
if [[ $plugin_dir == "$target" ]]; then
  echo "Already installed at $target; updating the runtime."
elif [[ -L $target ]]; then
  echo "$target is a symlink to $(readlink "$target"); leaving it alone." >&2
  echo "Run this script from that checkout instead." >&2
  exit 1
else
  # Stage beside the target and swap, so a failed copy cannot leave a
  # half-installed plugin behind. The .git directory is kept, because that is
  # what makes 'omarchy plugin update' able to fast-forward the plugin later.
  # Keep staging hidden: Omarchy watches this parent directory and treats
  # visible children as plugin candidates while they are being copied.
  staging="$(dirname "$target")/.${id}.install.$$"
  rm -rf "$staging"
  mkdir -p "$(dirname "$target")"
  cp -r "$plugin_dir" "$staging"
  rm -rf "$staging/scripts/__pycache__"
  rm -rf "$target"
  mv "$staging" "$target"
  echo "Installed into $target"
fi

omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true

if ! result=$(python3 "$target/scripts/hotcorners.py" sync); then
  echo "$result" >&2
  exit 1
fi

omarchy-shell -q shell rescanPlugins >/dev/null 2>&1 || true
omarchy-shell -q omarchy.menu refresh >/dev/null 2>&1 || true

echo "Installed Hot Corners. Open Setup > Mouse > Hot Corners to configure."
