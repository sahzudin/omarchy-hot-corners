![](Cheese.png)

# mousetrap

A lightweight, native hot-corner and edge-action addon for **Hyprland 0.55+**, written entirely in Lua. It leverages Hyprland's built-in Lua runtime to provide programmable actions for screen edges and corners with minimal overhead.

## Features

- **Native Integration**: Runs as a first-class Lua module inside Hyprland.
- **Context-Aware**: Supports 8 interaction zones (4 corners and 4 edges).
- **Multi-Monitor & DPI Ready**: Automatically calculates logical coordinates based on monitor scale and rotation.
- **Low Latency**: Polls cursor movement every 16 ms by default.
- **Configurable Geometry**: Per-monitor edge and corner sizes.
- **Priority Resolution**: Multiple bindings per zone are resolved by priority.
- **Dwell Triggers**: Execute actions after holding the cursor inside a zone.
- **Flick & Velocity Detection**: Trigger actions from fast cursor movement.
- **Directional Gestures**: Trigger actions after moving in a specified direction.
- **Exit Triggers**: Execute actions when leaving the active edge/corner area completely.
- **Modifier Support**: Restrict bindings to specific keyboard modifiers.
- **Runtime Reloading**: Reload configuration without restarting.
- **Unit Tested**: Includes unit and integration tests.

## Installation

Place the files into your Hyprland Lua directory:

```text
.../mousetrap.lua
.../mousetrap/
    ├── init.lua
    ├── ...
```

Initialize the addon:

```lua
local mousetrap = require("...mousetrap.init").setup({
    motion = {
        timer = 16,
    },

    geometry = {
        default = { corner = 4, edge = 2 },

        ["eDP-1"] = {
            corner = 60,
            edge = 10,
        },
    },

})
```

## Examples

### Touch

```lua
mousetrap.bind("top-left", function()
    hl.exec_cmd("notify-send 'Touch'")
end)
```

### Dwell

```lua
mousetrap.bind("top-right", function()
    hl.exec_cmd("notify-send 'Delayed'")
end, {
    delay = 2000,
})
```

### Flick

```lua
mousetrap.bind("top", function()
    hl.exec_cmd("notify-send 'Flick'")
end, {
    flick = 50,
})
```

### Velocity

```lua
mousetrap.bind("right", function()
    hl.exec_cmd("notify-send 'Fast movement'")
end, {
    velocity = 80,
})
```

### Directional Gesture

```lua
mousetrap.bind("left", function()
    hl.exec_cmd("notify-send 'Dragged up'")
end, {
    direction = "up",
    distance = 120,
})
```

### Exit Trigger

```lua
mousetrap.bind("bottom", function()
    hl.exec_cmd("notify-send 'Exited bottom edge'")
end, {
    exit = true,
})
```

### Repeating Trigger

```lua
mousetrap.bind("top", function()
    hl.exec_cmd("brightnessctl set +2%")
end, {
    delay = 100,
    loop = true,
})
```

### Priority

```lua
mousetrap.bind("top-left", normal_action, {
    priority = 0,
})

-- Matching bindings are sorted by priority.
-- Modifier requirements are checked before selection.
mousetrap.bind("top-left", special_action, {
    priority = 100,
    modifiers = {
        ctrl = true,
    },
})
```

## Using Modifier Keys

To trigger bindings only while specific modifiers are held, update the modifier state using ordinary Hyprland key bindings.

```lua
hl.bind(
    "ALT_L",
    mousetrap.modifiers({
        alt = true,
    })
)

hl.bind(
    "ALT + ALT_L",
    mousetrap.modifiers({
        alt = false,
    }),
    {
        release = true,
    }
)
```

Using:

```lua
mousetrap.bind("top", function()
    hl.exec_cmd("notify-send 'Secret Menu'")
end, {
    delay = 200,
    modifiers = {
        alt = true,
    },
})
```

# API Reference

| Method                          | Description                                                   |
| :------------------------------ | :------------------------------------------------------------ |
| `setup(config)`                 | Initializes the addon.                                        |
| `reload(config)`                | Reloads the configuration.                                    |
| `validate(config)`              | Validates a configuration table.                              |
| `bind(zone, callback, opts)`    | Creates a binding and returns its ID.                         |
| `remove_binding(id)`            | Removes a binding by ID.                                      |
| `find_binding(id)`              | Returns a binding by ID.                                      |
| `unbind(zone[, callback])`      | Removes bindings from a zone.                                 |
| `modifiers(mods)`               | Creates a Hyprland bind callback that updates modifier state. |
| `state()`                       | Returns the current runtime state.                            |
| `errors()`                      | Returns captured errors.                                      |
| `logger()`                      | Returns the logger instance.                                  |
| `log_level(level)`              | Changes logger verbosity.                                     |
| `start()`, `stop()`, `toggle()` | Controls the runtime.                                         |
| `status()`                      | Returns whether the addon is running.                         |

## Configuration

### `geometry`

```lua
geometry = {

    default = {
        corner = 4,
        edge = 2,
    },

    ["eDP-1"] = {
        corner = 60,
        edge = 10,
    },

}
```

| Field    | Description                       |
| :------- | :-------------------------------- |
| `corner` | Corner size in logical pixels.    |
| `edge`   | Edge thickness in logical pixels. |

### `motion`

```lua
motion = {
    timer = 16,
}
```

| Field   | Description                       |
| :------ | :-------------------------------- |
| `timer` | Polling interval in milliseconds. |

## `bind()`

```lua
mousetrap.bind(zone, callback, options)
```

### Parameters

| Option              | Description                                                  |
| :------------------ | :----------------------------------------------------------- |
| `delay`             | Delay before triggering (ms).                                |
| `flick`             | Minimum instantaneous cursor movement.                       |
| `velocity`          | Minimum cursor velocity.                                     |
| `direction`         | Required movement direction (`left`, `right`, `up`, `down`). |
| `distance`          | Required accumulated movement for directional bindings.      |
| `loop`              | Automatically re-arm after every trigger.                    |
| `exit`              | Fire when leaving a zone into the neutral area.              |
| `priority`          | Higher priority bindings are evaluated first.                |
| `modifiers` / `mod` | Required keyboard modifiers.                                 |

## Runtime Control

```lua
mousetrap.start()
mousetrap.stop()
mousetrap.toggle()

print(mousetrap.status())
```

## Reloading Configuration

```lua
mousetrap.reload({
    geometry = {
        ["HDMI-A-1"] = {
            corner = 40,
        },
    },
})
```

## Configuration Validation

```lua
local ok, err = mousetrap.validate(config)

if not ok then
    print(err)
end
```

## Testing

Run the test suite:

```sh
lua tests/run.lua
```

Current coverage includes:

- binding creation
- geometry calculations
- modifier matching
- trigger logic
- runtime reload
- Hyprland API mocking

## Diagnostics

mousetrap keeps internal logs and errors:

```lua
local errors = mousetrap.errors()

print(errors.count)
print(errors.last)
```

Logging level:

```lua
mousetrap.log_level("debug")
```

## Removing Bindings

`bind()` returns an identifier that can later be used:

```lua
local id = mousetrap.bind("top", action)
mousetrap.remove_binding(id)
```

## License

This project is licensed under the GPL-3.0 License.
