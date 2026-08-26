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
~/.config/hypr/hotcorners/               Everything the plugin installs
  init.lua                               Hyprland driver (managed)
  config.lua                             Generated config (managed)
  mousetrap/                             Vendored mousetrap module
~/.config/omarchy-hotcorners/config.json User settings (managed)
~/.local/share/omarchy-hotcorners/       Uninstaller copy (see below)
```

The plugin owns that one directory outright and installs nothing else into
`~/.config/hypr/`. If `~/.config/hypr/hotcorners/` already exists and was not
created by this plugin, installation refuses rather than merging into it.
A single line is added to `~/.config/hypr/hyprland.lua`, between markers:

```lua
-- omarchy-hotcorners:start
require("hypr.hotcorners.init")
-- omarchy-hotcorners:end
```

## Install with Omarchy

Add the public repository with Omarchy's plugin manager, then finish the setup
once:

```bash
omarchy plugin add https://github.com/sahzudin/omarchy-hot-corners.git --enable --yes
~/.config/omarchy/plugins/io.github.sahzudin.hotcorners/install.sh
```

The second line is needed because `omarchy plugin add` only clones, validates,
and enables a plugin — it never runs plugin code, so on its own it cannot
install the Hyprland driver. (If you would rather not run a script, opening the
panel once does the same work: `omarchy-shell shell summon
io.github.sahzudin.hotcorners '{}'`.)

### Updating

```bash
omarchy plugin update io.github.sahzudin.hotcorners --yes
```

`omarchy plugin update` only fast-forwards the checkout. The driver running
inside Hyprland is a separate copy, so the plugin reconciles it itself: opening
the settings panel checks whether the installed runtime still matches the
checkout and reinstalls it if not. That check is a no-op when nothing changed,
so there is no cost to it. To apply an update without opening the panel, run
`install.sh` again — it is idempotent.

### Removing

```bash
./uninstall.sh   # or: ~/.config/omarchy/plugins/io.github.sahzudin.hotcorners/uninstall.sh
```

Use `uninstall.sh` rather than `omarchy plugin remove`. `plugin remove` deletes
the checkout without running any plugin code, which would leave the Hyprland
driver, the hook, the menu entry, and your settings behind.

If you do remove the plugin that way, it recovers on the next Hyprland reload
or login: the driver notices its plugin directory is gone, stays inert instead
of binding corners, and removes the hook, the menu entry, the shell
registration, and its own directory. That is what the copy of the uninstaller
in `~/.local/share/omarchy-hotcorners/` is for — it has to live outside the
checkout to survive the checkout being deleted. It deletes itself last.

## Manual install

```bash
./install.sh
```

The script copies the plugin into `~/.config/omarchy/plugins/` (keeping its
`.git`, so `omarchy plugin update` still works), installs the Hyprland driver,
adds a `Setup > Mouse > Hot Corners` entry to the Omarchy menu, and reloads
Hyprland + the shell. Running it from an already-installed copy is safe: it
skips the copy and just brings the runtime up to date.

Then open the menu (**Super+Space**) → **Setup > Mouse > Hot Corners** and pick
an action for each corner. Changes apply immediately when you click **Save**.

## Uninstall

```bash
./uninstall.sh
```

This removes the menu entry, the Hyprland hook, `~/.config/hypr/hotcorners/`,
your settings, and the uninstaller copy. Everything it deletes is backed up
first under `~/.local/state/omarchy-hotcorners/backups/`.

## License

The plugin's own code is MIT-licensed (see [LICENSE](LICENSE)). It ships a
vendored copy of [`mousetrap`](vendor/mousetrap/), which is GPL-3.0; the
license text and the pinned upstream commit are recorded in
[vendor/mousetrap/PROVENANCE.md](vendor/mousetrap/PROVENANCE.md). The package
as distributed is therefore `MIT AND GPL-3.0-only`, which is what
`manifest.json` declares.

The plugin runs unsandboxed inside the Omarchy shell and Hyprland.
