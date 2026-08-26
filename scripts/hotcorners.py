#!/usr/bin/env python3
"""Safe backend for the Omarchy Hot Corners plugin.

Install/remove the Hyprland Lua hot-corners driver, expose the current
configuration to the settings panel, and apply changes with rollback.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN_ID = "io.github.sahzudin.hotcorners"
VERSION = 1
HOOK_START = "-- omarchy-hotcorners:start"
HOOK_END = "-- omarchy-hotcorners:end"
MENU_START = "  // omarchy-hotcorners:start"
MENU_END = "  // omarchy-hotcorners:end"

CORNER_ORDER = ("top-left", "top-right", "bottom-left", "bottom-right")

DEFAULT_CONFIG: dict[str, Any] = {
    "version": VERSION,
    "corners": {
        "top-left": "apps-menu",
        "top-right": "launcher",
        "bottom-left": "show-desktop",
        "bottom-right": "next-workspace",
    },
    "custom": {},
    "options": {"dwell": 250, "corner": 10, "edge": 4},
}

ACTIONS: list[dict[str, str]] = [
    {"id": "none", "label": "Disabled", "description": "Do nothing in this corner"},
    {"id": "apps-menu", "label": "Apps menu", "description": "Open the Apps menu (Launchpad-like)"},
    {"id": "launcher", "label": "Launcher (Omarchy menu)", "description": "Open the Omarchy menu and launcher"},
    {"id": "show-desktop", "label": "Show desktop", "description": "Minimize every window to reveal the desktop"},
    {"id": "next-workspace", "label": "Next workspace", "description": "Switch to the next workspace"},
    {"id": "prev-workspace", "label": "Previous workspace", "description": "Switch to the previous workspace"},
    {"id": "fullscreen", "label": "Toggle fullscreen", "description": "Toggle the active window fullscreen"},
    {"id": "close-window", "label": "Close window", "description": "Close the active window"},
    {"id": "custom", "label": "Custom command", "description": "Run a shell command"},
]

ACTION_IDS = {action["id"] for action in ACTIONS}


def home_path() -> Path:
    return Path(os.environ.get("OMARCHY_HOTCORNERS_HOME", Path.home())).expanduser()


def omarchy_path() -> Path:
    return Path(os.environ.get("OMARCHY_HOTCORNERS_OMARCHY_PATH", "/usr/share/omarchy"))


def plugin_path() -> Path:
    return Path(__file__).resolve().parent.parent


def paths() -> dict[str, Path]:
    home = home_path()
    return {
        "hyprland": home / ".config/hypr/hyprland.lua",
        "driver": home / ".config/hypr/hotcorners.lua",
        "config_lua": home / ".config/hypr/hotcorners-config.lua",
        "mousetrap_dir": home / ".config/hypr/mousetrap",
        "data": home / ".config/omarchy-hotcorners/config.json",
        "lock": home / ".local/state/omarchy-hotcorners/lock",
        "backups": home / ".local/state/omarchy-hotcorners/backups",
        "menu": home / ".config/omarchy/extensions/omarchy-menu.jsonc",
        "shell": home / ".config/omarchy/shell.json",
        "shell_defaults": omarchy_path() / "config/omarchy/shell.json",
        "vendor_mousetrap": plugin_path() / "vendor/mousetrap",
        "driver_template": plugin_path() / "scripts/driver.lua",
    }


def emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0 if payload.get("ok", False) else 1


@contextlib.contextmanager
def locked():
    lock_path = paths()["lock"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    backup_dir = paths()["backups"]
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    target = backup_dir / f"{path.name}.{stamp}.bak"
    shutil.copy2(path, target)
    return target


def atomic_write(path: Path, content: str, *, make_backup: bool = True) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    saved = backup(path) if make_backup else None
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
    return saved


def restore_file(path: Path, content: str | None) -> None:
    if content is None:
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
    else:
        atomic_write(path, content, make_backup=False)


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def load_store() -> dict[str, Any]:
    path = paths()["data"]
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read {path}: {error}") from error
    if not isinstance(value, dict):
        raise RuntimeError(f"Invalid hot corners data in {path}")
    merged: dict[str, Any] = json.loads(json.dumps(DEFAULT_CONFIG))
    for key in ("corners", "custom", "options"):
        if isinstance(value.get(key), dict):
            merged[key] = {**merged[key], **value[key]}
    return merged


def save_store(store: dict[str, Any]) -> None:
    content = json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write(paths()["data"], content)


def lua_string(value: str) -> str:
    return json.dumps(value)


def render_config_lua(store: dict[str, Any]) -> str:
    corners = store.get("corners", {})
    custom = store.get("custom", {}) or {}
    options = store.get("options", {}) or {}
    lines = [
        "-- Generated by the Omarchy Hot Corners plugin. Do not edit by hand.",
        "return {",
        "  corners = {",
    ]
    for corner in CORNER_ORDER:
        lines.append(f"    [{lua_string(corner)}] = {lua_string(corners.get(corner, 'none'))},")
    lines.append("  },")
    lines.append("  custom = {")
    for corner in CORNER_ORDER:
        lines.append(f"    [{lua_string(corner)}] = {lua_string(str(custom.get(corner, '')))},")
    lines.append("  },")
    lines.append("  options = {")
    for key, default in (("dwell", 250), ("corner", 10), ("edge", 4)):
        try:
            value = max(0, min(int(options.get(key, default)), 10000))
        except (TypeError, ValueError):
            value = default
        lines.append(f"    {key} = {value},")
    lines.append("  },")
    lines.append("}")
    return "\n".join(lines) + "\n"


def validate_lua(path: Path) -> None:
    result = subprocess.run(["luac", "-p", str(path)], capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Generated Lua failed validation")


def write_config_lua(store: dict[str, Any]) -> None:
    path = paths()["config_lua"]
    previous = read_text(path)
    atomic_write(path, render_config_lua(store))
    try:
        validate_lua(path)
    except Exception:
        restore_file(path, previous)
        raise


def reload_hyprland() -> None:
    if os.environ.get("OMARCHY_HOTCORNERS_SKIP_RELOAD") == "1":
        return
    reload_result = subprocess.run(
        ["hyprctl", "reload"], capture_output=True, text=True, timeout=20
    )
    if reload_result.returncode:
        raise RuntimeError(reload_result.stderr.strip() or reload_result.stdout.strip() or "hyprctl reload failed")
    errors = subprocess.run(
        ["hyprctl", "configerrors"], capture_output=True, text=True, timeout=20
    )
    output = (errors.stdout + errors.stderr).strip()
    if errors.returncode or (output and output.lower() not in {"no errors", "ok"}):
        raise RuntimeError(output or "Hyprland reported configuration errors")


def refresh_shell() -> None:
    if os.environ.get("OMARCHY_HOTCORNERS_SKIP_RELOAD") == "1":
        return
    subprocess.run(
        ["omarchy-shell", "shell", "reloadConfig"],
        capture_output=True,
        text=True,
        timeout=10,
    )


def load_shell_config() -> dict[str, Any]:
    path = paths()["shell"]
    source = path if path.exists() else paths()["shell_defaults"]
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read shell configuration: {error}") from error
    if not isinstance(value, dict):
        value = {}
    value["version"] = 1
    if not isinstance(value.get("plugins"), list):
        value["plugins"] = []
    return value


def entry_id(entry: Any) -> str:
    return str(entry.get("id", "")) if isinstance(entry, dict) else str(entry)


def register_shell() -> None:
    config = load_shell_config()
    if not any(entry_id(entry) == PLUGIN_ID for entry in config["plugins"]):
        config["plugins"].append({"id": PLUGIN_ID})
        atomic_write(paths()["shell"], json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    refresh_shell()


def unregister_shell() -> None:
    config = load_shell_config()
    config["plugins"] = [entry for entry in config["plugins"] if entry_id(entry) != PLUGIN_ID]
    atomic_write(paths()["shell"], json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    refresh_shell()


def ensure_hook(content: str) -> str:
    if HOOK_START in content and HOOK_END in content:
        return content
    content = re.sub(r'^[ \t]*require\("hypr\.hotcorners"\).*\n?', "", content, flags=re.M)
    block = f"\n{HOOK_START}\nrequire(\"hypr.hotcorners\")\n{HOOK_END}\n"
    return content.rstrip() + "\n" + block


def remove_marked(content: str, start: str, end: str) -> str:
    pattern = re.compile(rf"\n?{re.escape(start)}.*?{re.escape(end)}\n?", re.S)
    return pattern.sub("\n", content).rstrip() + "\n"


def strip_jsonc(content: str) -> str:
    out: list[str] = []
    index = 0
    in_string = False
    while index < len(content):
        character = content[index]
        if in_string:
            out.append(character)
            if character == "\\" and index + 1 < len(content):
                out.append(content[index + 1])
                index += 2
                continue
            if character == '"':
                in_string = False
            index += 1
        elif character == '"':
            in_string = True
            out.append(character)
            index += 1
        elif content.startswith("//", index):
            index = content.find("\n", index)
            if index < 0:
                break
        elif content.startswith("/*", index):
            finish = content.find("*/", index + 2)
            index = len(content) if finish < 0 else finish + 2
        else:
            out.append(character)
            index += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


def add_menu_entry() -> None:
    path = paths()["menu"]
    content = read_text(path) or "{\n}\n"
    if MENU_START in content:
        return
    try:
        parsed = json.loads(strip_jsonc(content))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Could not update invalid JSONC in {path}: {error}") from error
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Menu configuration in {path} is not an object")
    entries: list[tuple[str, dict[str, str]]] = []
    if "setup" not in parsed:
        entries.append(("setup", {"icon": "", "label": "Setup"}))
    if "setup.mouse" not in parsed:
        entries.append(("setup.mouse", {"icon": "", "label": "Mouse"}))
    entries.append(("setup.mouse.hotcorners", {
        "icon": "◲",
        "label": "Hot Corners",
        "description": "Choose an action for each screen corner",
        "action": f"omarchy-shell shell summon {PLUGIN_ID} '{{}}'",
    }))
    brace = content.find("{")
    if brace < 0:
        raise RuntimeError(f"Menu configuration in {path} has no root object")
    body = [MENU_START]
    for key, value in entries:
        body.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},")
    body.append(MENU_END)
    insertion = "\n".join(body) + "\n"
    atomic_write(path, content[: brace + 1] + "\n" + insertion + content[brace + 1:])


def remove_menu_entry() -> None:
    path = paths()["menu"]
    content = read_text(path)
    if content and MENU_START in content:
        atomic_write(path, remove_marked(content, MENU_START, MENU_END))


def installed() -> bool:
    content = read_text(paths()["hyprland"])
    return bool(content and HOOK_START in content and paths()["driver"].exists())


def apply_store(store: dict[str, Any]) -> None:
    previous = read_text(paths()["data"])
    save_store(store)
    try:
        write_config_lua(store)
        reload_hyprland()
    except Exception:
        restore_file(paths()["data"], previous)
        with contextlib.suppress(Exception):
            reload_hyprland()
        raise


def cmd_list(_: argparse.Namespace) -> int:
    store = load_store()
    return emit({
        "ok": True,
        "installed": installed(),
        "cornerOrder": list(CORNER_ORDER),
        "corners": store.get("corners", {}),
        "custom": store.get("custom", {}),
        "options": store.get("options", {}),
        "actions": ACTIONS,
        "driverPath": str(paths()["driver"]),
    })


def cmd_apply(args: argparse.Namespace) -> int:
    try:
        payload = json.loads(args.config)
    except json.JSONDecodeError as error:
        return emit({"ok": False, "error": f"Invalid settings payload: {error}"})
    if not isinstance(payload, dict):
        return emit({"ok": False, "error": "Settings payload must be an object."})

    with locked():
        store = load_store()
        corners = payload.get("corners")
        if not isinstance(corners, dict):
            return emit({"ok": False, "error": "Missing 'corners' in payload."})
        normalized: dict[str, str] = {}
        for corner in CORNER_ORDER:
            action = corners.get(corner)
            if action is None:
                normalized[corner] = store.get("corners", {}).get(corner, "none")
                continue
            if action not in ACTION_IDS:
                return emit({"ok": False, "error": f"Unknown action for {corner}: {action}"})
            normalized[corner] = action
        store["corners"] = normalized

        custom = payload.get("custom")
        if isinstance(custom, dict):
            existing_custom = store.get("custom", {})
            store["custom"] = {
                corner: str(custom.get(corner, existing_custom.get(corner, "")))
                for corner in CORNER_ORDER
            }

        options = payload.get("options")
        if isinstance(options, dict):
            current = store.setdefault("options", {})
            for key in ("dwell", "corner", "edge"):
                try:
                    current[key] = max(0, min(int(options.get(key, current.get(key, 0))), 10000))
                except (TypeError, ValueError):
                    pass
            store["options"] = current

        try:
            apply_store(store)
        except Exception as error:
            return emit({"ok": False, "error": f"Could not apply settings; changes were rolled back: {error}"})
    return emit({"ok": True})


def cmd_reset(_: argparse.Namespace) -> int:
    with locked():
        store = json.loads(json.dumps(DEFAULT_CONFIG))
        try:
            apply_store(store)
        except Exception as error:
            return emit({"ok": False, "error": f"Could not restore defaults; changes were rolled back: {error}"})
    return emit({"ok": True})


def cmd_install(args: argparse.Namespace) -> int:
    del args
    with locked():
        hyprland = paths()["hyprland"]
        if not hyprland.exists():
            return emit({"ok": False, "error": f"Missing {hyprland}; run 'omarchy refresh hyprland' first."})

        previous_driver = read_text(paths()["driver"])
        previous_config = read_text(paths()["config_lua"])
        previous_hyprland = read_text(hyprland)

        try:
            vendor = paths()["vendor_mousetrap"]
            if not vendor.exists():
                raise RuntimeError(f"Missing vendored mousetrap module at {vendor}")
            shutil.copytree(vendor, paths()["mousetrap_dir"], dirs_exist_ok=True)

            template = read_text(paths()["driver_template"])
            if not template:
                raise RuntimeError(f"Missing driver template at {paths()['driver_template']}")
            atomic_write(paths()["driver"], template, make_backup=False)

            write_config_lua(load_store())
            atomic_write(hyprland, ensure_hook(previous_hyprland or ""))
            reload_hyprland()
        except Exception as error:
            restore_file(paths()["driver"], previous_driver)
            restore_file(paths()["config_lua"], previous_config)
            restore_file(hyprland, previous_hyprland)
            with contextlib.suppress(Exception):
                reload_hyprland()
            return emit({"ok": False, "error": f"Installation failed and was rolled back: {error}"})

        try:
            add_menu_entry()
            register_shell()
        except Exception as error:
            return emit({"ok": False, "error": f"Hot corners support installed, but shell integration failed: {error}"})
    return emit({"ok": True})


def cmd_uninstall(args: argparse.Namespace) -> int:
    with locked():
        hyprland = paths()["hyprland"]
        content = read_text(hyprland)
        if content and HOOK_START in content:
            previous = content
            atomic_write(hyprland, remove_marked(content, HOOK_START, HOOK_END))
            try:
                reload_hyprland()
            except Exception as error:
                restore_file(hyprland, previous)
                with contextlib.suppress(Exception):
                    reload_hyprland()
                return emit({"ok": False, "error": f"Uninstall failed and was rolled back: {error}"})

        remove_menu_entry()
        unregister_shell()

        if args.purge:
            for path in (paths()["driver"], paths()["config_lua"], paths()["data"]):
                if path.exists():
                    backup(path)
                    path.unlink()
            if paths()["mousetrap_dir"].exists():
                backup_dir = paths()["backups"]
                backup_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
                shutil.copytree(paths()["mousetrap_dir"], backup_dir / f"mousetrap.{stamp}.bak")
                shutil.rmtree(paths()["mousetrap_dir"])
    return emit({"ok": True, "purged": args.purge})


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("list").set_defaults(handler=cmd_list)
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("config")
    apply_parser.set_defaults(handler=cmd_apply)
    commands.add_parser("reset").set_defaults(handler=cmd_reset)
    commands.add_parser("install").set_defaults(handler=cmd_install)
    uninstall_parser = commands.add_parser("uninstall")
    uninstall_parser.add_argument("--purge", action="store_true")
    uninstall_parser.set_defaults(handler=cmd_uninstall)
    return root


def main() -> int:
    args = parser().parse_args()
    try:
        return args.handler(args)
    except Exception as error:
        return emit({"ok": False, "error": str(error)})


if __name__ == "__main__":
    sys.exit(main())