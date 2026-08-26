# Hot Corners

macOS-style hot corners for Omarchy, configured from a settings panel.

Move your cursor into a screen corner and hold it there briefly to trigger an
action. Each of the four corners can run a different action, chosen from a
panel that opens from the Omarchy menu.

## What it does

| Corner    | Default action       |
|-----------|----------------------|
| Top-left  | Apps menu            |
| Top-right | Launcher (Omarchy menu) |
| Bottom-left | Show desktop       |
| Bottom-right | Next workspace     |

Available actions per corner:

- **Disabled**
- **Apps menu** — the Launchpad-like app menu
- **Launcher (Omarchy menu)** — the main Omarchy menu / launcher
- **Show desktop** — stashes every window on the active workspace into a
  hidden `special:desktop` workspace; triggering the corner again restores
  them (windows return to the workspace they came from)
- **Next / Previous workspace**
- **Toggle fullscreen**
- **Close window**
- **Custom command** — run any shell command

Also configurable: the **hold time** (dwell, in milliseconds) before a corner
fires, the **corner size** and **edge size** trigger zones (logical pixels).

## Architecture

The corners themselves are implemented as a native Hyprland Lua addon
([`mousetrap`](https://github.com/naregderlevonean/mousetrap)), which runs
inside Hyprland's built-in Lua runtime — no external daemon, and it survives
Hyprland updates because it is pure Lua. The settings panel writes a small
Lua config file and reloads Hyprland to apply changes.

```
~/.config/hypr/hotcorners.lua          Hyprland driver (managed)
~/.config/hypr/hotcorners-config.lua   Generated config (managed)
~/.config/hypr/mousetrap/              Vendored mousetrap module
~/.config/omarchy-hotcorners/config.json  User settings (managed)
```

## Install with Omarchy

For a git-managed installation, add the public repository with Omarchy's plugin
manager:

```bash
omarchy plugin add https://github.com/sahzudin/omarchy-hot-corners.git --enable --yes
```

To update or remove it later:

```bash
omarchy plugin update io.github.sahzudin.hotcorners --yes
omarchy plugin remove io.github.sahzudin.hotcorners --yes
```

## Manual install

```bash
./install.sh
```

The script copies the plugin into `~/.config/omarchy/plugins/`, installs the
Hyprland driver, adds a `Setup > Mouse > Hot Corners` entry to the Omarchy
menu, and reloads Hyprland + the shell.

Then open the menu (**Super+Space**) → **Setup > Mouse > Hot Corners** and pick
an action for each corner. Changes apply immediately when you click **Save**.

The plugin runs unsandboxed inside the Omarchy shell and Hyprland. Its only
vendored dependency is the pure-Lua [`mousetrap`](vendor/mousetrap/) module,
which is GPL-3.0; the plugin's own code is MIT-licensed.

## Uninstall

```bash
./uninstall.sh
```

This removes the menu entry, the Hyprland driver, the generated config, the
mousetrap module, and your settings (backed up first).

## Manual notes

- `omarchy refresh hyprland` resets your Hyprland Lua configs and will remove
  the `require("hypr.hotcorners")` line. Re-run `./install.sh` to restore it.
- You can re-run an action by hand for debugging:

  ```bash
  hyprctl eval '_G.omarchy_hotcorners.actions.show_desktop()'
  ```

## Development

- `scripts/hotcorners.py` — backend: `list`, `apply <json>`, `reset`,
  `install`, `uninstall [--purge]`. Set `OMARCHY_HOTCORNERS_SKIP_RELOAD=1` to
  skip `hyprctl reload` / shell reload, and `OMARCHY_HOTCORNERS_HOME=/tmp/…`
  to test against a scratch HOME.
- `scripts/driver.lua` — the Hyprland Lua driver (copied to
  `~/.config/hypr/hotcorners.lua` on install).
- `vendor/mousetrap/` — vendored copy of mousetrap (see `UPSTREAM.md`).
- `HotcornersContent.qml` / `Panel.qml` — the settings panel.

## License

MIT. The vendored `mousetrap` module is GPL-3.0 (see `vendor/mousetrap/UPSTREAM.md`).
