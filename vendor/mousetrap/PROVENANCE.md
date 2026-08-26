# Vendoring notes: mousetrap

`mousetrap` is a third-party Hyprland Lua addon that provides the corner and
edge detection this plugin builds on. It is vendored rather than fetched at
install time so that installing Hot Corners needs no network access and the
exact code that runs is the code that was reviewed.

- **Upstream:** <https://github.com/naregderlevonean/mousetrap>
- **Vendored commit:** `a17adea14fdea96c5b3c48f9364198df82ec550c` (2026-08-05)
- **Vendored version:** 0.12.3 (`M._VERSION` in `init.lua`)
- **License:** GPL-3.0-only — see [COPYING](COPYING)

## License status

Upstream declares GPL-3.0 in its README ("This project is licensed under the
GPL-3.0 License", reproduced in [UPSTREAM.md](UPSTREAM.md)) but ships no
license text file of its own. [COPYING](COPYING) is therefore a verbatim copy
of the GNU General Public License version 3 as published by the Free Software
Foundation, included here so the terms travel with the code.

The vendored files are unmodified. `mousetrap` resolves its own module path
from the `require` name, so it needed no patching to live at
`hypr.hotcorners.mousetrap`.

## Verifying provenance

Every vendored file is byte-identical to the pinned commit. `git hash-object`
reproduces the upstream blob ids:

```bash
cd vendor/mousetrap
for f in *.lua; do printf '%s %s\n' "$(git hash-object "$f")" "$f"; done
```

| File | Upstream blob |
|------|---------------|
| `binding.lua` | `dbd510495b7bcc39c687fc5670283ec118e75b93` |
| `bindings.lua` | `88b551f9c1147ef3e6f5b1880c74ba666dac583d` |
| `config.lua` | `b984e95810f41439303c805e803a2c97a6f5be94` |
| `context.lua` | `12f4a8f2781fdec179286476d07486a0959629d2` |
| `core.lua` | `7745bba4af95de03f5ff67b5966517c683fc8043` |
| `errors.lua` | `f3b166c81d492eae947c79db3313aecf04be19eb` |
| `events.lua` | `8676f4428dcce75cf24da7bb58dca98883581014` |
| `geometry.lua` | `8994a58ea23d3ffacd118ef63e51c9ba806e70a4` |
| `init.lua` | `678c655c7e9b64ffc0d4768c556aa5ad684cf78c` |
| `logger.lua` | `56c23bb82c01574ababe6cb786a56b74e5bf0dca` |
| `state.lua` | `fcf54fb9a5d3e999b4d4342721b9b9aa9351eaf4` |
| `trigger.lua` | `ffda729d11aace7ce2f63daece74110ec5097585` |
| `validator.lua` | `762155b88b89418d5edd742d6e7a63a2e4b37cb6` |

Compare against upstream with:

```bash
curl -s "https://api.github.com/repos/naregderlevonean/mousetrap/git/trees/a17adea14fdea96c5b3c48f9364198df82ec550c" \
  | jq -r '.tree[] | select(.type == "blob") | "\(.sha) \(.path)"'
```

Only the library sources are vendored; upstream's `tests/` and `Cheese.png`
are not shipped.

## Re-vendoring

1. Copy the `*.lua` files from the new upstream commit into this directory.
2. Update the pinned commit, version, and blob table above.
3. Refresh [UPSTREAM.md](UPSTREAM.md) from upstream's README.
4. Run `./install.sh`; the runtime fingerprint changes, so the driver and the
   vendored copy under `~/.config/hypr/hotcorners/` are both refreshed.
