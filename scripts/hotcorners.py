#!/usr/bin/env python3
"""Safe backend for the Omarchy Hot Corners plugin.

Reconcile the Hyprland Lua hot-corners runtime with the plugin checkout,
expose the current configuration to the settings panel, and apply changes
with rollback.

No Omarchy plugin command (`omarchy plugin add|update|remove`) runs plugin
code, so the runtime cannot be installed as a one-shot side effect of adding
the plugin. Instead `sync` is idempotent and cheap when nothing changed: the
settings panel runs it every time it opens, which is what makes a plain
`omarchy plugin update` reach the running driver.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PLUGIN_ID = "io.github.sahzudin.hotcorners"
VERSION = 1

# Bumped whenever the installed runtime layout changes, so an existing install
# is refreshed even if the driver and vendored sources happen to hash the same.
RUNTIME_VERSION = 2

HOOK_START = "-- omarchy-hotcorners:start"
HOOK_END = "-- omarchy-hotcorners:end"
MENU_START = "  // omarchy-hotcorners:start"
MENU_END = "  // omarchy-hotcorners:end"

# Everything the plugin installs into Hyprland lives under a single directory
# it owns outright (`~/.config/hypr/hotcorners/`), so a purge never has to
# guess which files were ours.
REQUIRE_PATH = "hypr.hotcorners.init"
HOOK_BODY = f'require("{REQUIRE_PATH}")'
ANY_REQUIRE_RE = re.compile(r'^[ \t]*require\("hypr\.hotcorners(?:\.init)?"\).*\n?', re.M)

STAMP_NAME = ".install.json"

# Panel startup invokes `sync` automatically, so none of its reads may trust a
# predictable user-writable pathname.  Configuration and shipped source files
# are deliberately small; this ceiling prevents a replaced or growing file
# from consuming unbounded memory before it is parsed, fingerprinted, or
# rewritten.
MAX_READ_BYTES = 1024 * 1024

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

MENU_ENTRY = {
    "icon": "◲",
    "label": "Hot Corners",
    "description": "Choose an action for each screen corner",
    "action": f"omarchy-shell shell summon {PLUGIN_ID} '{{}}'",
}


def home_path() -> Path:
    return Path(os.environ.get("OMARCHY_HOTCORNERS_HOME", Path.home())).expanduser()


def omarchy_path() -> Path:
    return Path(os.environ.get("OMARCHY_HOTCORNERS_OMARCHY_PATH", "/usr/share/omarchy"))


def source_path() -> Path:
    """Directory this script was started from — a plugin checkout or the
    private runtime copy under ~/.local/share."""
    return Path(__file__).resolve().parent.parent


def paths() -> dict[str, Path]:
    home = home_path()
    runtime = home / ".config/hypr/hotcorners"
    backend = home / ".local/share/omarchy-hotcorners"
    source = source_path()
    return {
        "hyprland": home / ".config/hypr/hyprland.lua",
        "runtime": runtime,
        "driver": runtime / "init.lua",
        "config_lua": runtime / "config.lua",
        "mousetrap_dir": runtime / "mousetrap",
        "stamp": runtime / STAMP_NAME,
        # Pre-2.0 layout, migrated away from because these paths are generic
        # enough that another tool could legitimately own them.
        "legacy_driver": home / ".config/hypr/hotcorners.lua",
        "legacy_config": home / ".config/hypr/hotcorners-config.lua",
        "legacy_mousetrap": home / ".config/hypr/mousetrap",
        "data": home / ".config/omarchy-hotcorners/config.json",
        "lock": home / ".local/state/omarchy-hotcorners/lock",
        "backups": home / ".local/state/omarchy-hotcorners/backups",
        "menu": home / ".config/omarchy/extensions/omarchy-menu.jsonc",
        "shell": home / ".config/omarchy/shell.json",
        "shell_defaults": omarchy_path() / "config/omarchy/shell.json",
        # Where `omarchy plugin add` puts the checkout. The driver watches this
        # exact path so that removing the plugin cleans up after itself.
        "plugin": home / f".config/omarchy/plugins/{PLUGIN_ID}",
        # A self-contained copy of the backend, kept so uninstall still works
        # after the checkout is gone.
        "backend": backend,
        "backend_script": backend / "scripts/hotcorners.py",
        "source": source,
        "vendor_mousetrap": source / "vendor/mousetrap",
        "driver_template": source / "scripts/driver.lua",
    }


def emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0 if payload.get("ok", False) else 1


@contextlib.contextmanager
def locked():
    lock_path = paths()["lock"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW
    try:
        descriptor = os.open(lock_path, flags, 0o600)
    except OSError as error:
        raise RuntimeError(f"Could not open lock {lock_path} safely: {error}") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise RuntimeError(f"Refusing non-regular lock file {lock_path}")
        handle = os.fdopen(descriptor, "a+", encoding="utf-8")
        descriptor = -1
        with handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            yield
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_bytes(path: Path, *, max_bytes: int = MAX_READ_BYTES) -> bytes:
    """Read a small regular file without following its final symlink.

    O_NONBLOCK makes an attacker-planted FIFO or device fail closed instead of
    hanging the panel helper.  Validation happens on the opened descriptor,
    avoiding a check/use race, and the read loop enforces the limit even when a
    file grows after fstat().
    """
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise OSError(error.errno, f"Could not open {path} safely: {error.strerror}", path) from error
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError(f"Refusing to read non-regular file {path}")
        if metadata.st_size > max_bytes:
            raise OSError(f"Refusing to read {path}: exceeds {max_bytes} bytes")

        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        if len(content) > max_bytes:
            raise OSError(f"Refusing to read {path}: exceeds {max_bytes} bytes")
        return content
    finally:
        os.close(descriptor)


def backup(path: Path) -> Path | None:
    if not path.exists():
        return None
    content = read_bytes(path)
    backup_dir = paths()["backups"]
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    target = backup_dir / f"{path.name}.{stamp}.bak"
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=backup_dir)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)
    return target


def backup_tree(path: Path) -> Path | None:
    if not path.is_dir():
        return None
    backup_dir = paths()["backups"]
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    target = backup_dir / f"{path.name}.{stamp}.bak"
    shutil.copytree(path, target)
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
        return read_bytes(path).decode("utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return None


def load_store() -> dict[str, Any]:
    path = paths()["data"]
    try:
        content = read_text(path)
        if content is None:
            return json.loads(json.dumps(DEFAULT_CONFIG))
        value = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
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
        content = read_text(source)
        if content is None:
            raise FileNotFoundError(source)
        value = json.loads(content)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not read shell configuration: {error}") from error
    if not isinstance(value, dict):
        value = {}
    value["version"] = 1
    if not isinstance(value.get("plugins"), list):
        value["plugins"] = []
    return value


def entry_id(entry: Any) -> str:
    return str(entry.get("id", "")) if isinstance(entry, dict) else str(entry)


def shell_registered() -> bool:
    try:
        config = load_shell_config()
    except RuntimeError:
        return False
    return any(entry_id(entry) == PLUGIN_ID for entry in config["plugins"])


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


def hook_block() -> str:
    return f"{HOOK_START}\n{HOOK_BODY}\n{HOOK_END}"


def hook_current(content: str | None) -> bool:
    return bool(content) and hook_block() in content


def ensure_hook(content: str) -> str:
    """Return `content` with exactly one current hook block at the end.

    Rewriting rather than skipping keeps an install from an older layout
    (which required `hypr.hotcorners`) from being left pointing at a module
    that no longer exists.
    """
    if hook_current(content):
        return content
    stripped = remove_marked(content, HOOK_START, HOOK_END) if HOOK_START in content else content
    stripped = ANY_REQUIRE_RE.sub("", stripped)
    return stripped.rstrip() + "\n\n" + hook_block() + "\n"


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


def menu_block(content: str) -> str:
    """The menu entries this plugin owns, rendered for `content`.

    Parent sections are only claimed when they are missing, so removing the
    plugin never takes an existing `Setup` menu down with it.
    """
    try:
        parsed = json.loads(strip_jsonc(content))
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Could not update invalid JSONC in {paths()['menu']}: {error}") from error
    if not isinstance(parsed, dict):
        raise RuntimeError(f"Menu configuration in {paths()['menu']} is not an object")

    entries: list[tuple[str, dict[str, str]]] = []
    if "setup" not in parsed:
        entries.append(("setup", {"icon": "", "label": "Setup"}))
    if "setup.mouse" not in parsed:
        entries.append(("setup.mouse", {"icon": "", "label": "Mouse"}))
    entries.append(("setup.mouse.hotcorners", MENU_ENTRY))

    body = [MENU_START]
    for key, value in entries:
        body.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)},")
    body.append(MENU_END)
    return "\n".join(body) + "\n"


def menu_current() -> bool:
    content = read_text(paths()["menu"])
    if not content or MENU_START not in content:
        return False
    without = remove_marked(content, MENU_START, MENU_END)
    return menu_block(without) in content


def add_menu_entry() -> None:
    path = paths()["menu"]
    content = read_text(path) or "{\n}\n"
    if menu_current():
        return
    if MENU_START in content:
        content = remove_marked(content, MENU_START, MENU_END)
    insertion = menu_block(content)
    brace = content.find("{")
    if brace < 0:
        raise RuntimeError(f"Menu configuration in {path} has no root object")
    atomic_write(path, content[: brace + 1] + "\n" + insertion + content[brace + 1:])


def remove_menu_entry() -> None:
    path = paths()["menu"]
    content = read_text(path)
    if content and MENU_START in content:
        atomic_write(path, remove_marked(content, MENU_START, MENU_END))


# ----------------------------------------------------------------- runtime

def vendor_files() -> list[Path]:
    vendor = paths()["vendor_mousetrap"]
    if not vendor.is_dir():
        return []
    return sorted(path for path in vendor.iterdir() if path.is_file())


def fingerprint() -> str:
    """Identity of the runtime this checkout would install.

    Covers the driver template, every vendored Lua source, and the layout
    version, so `sync` can tell "already current" from "the checkout moved
    ahead" without reinstalling on every panel open.
    """
    digest = hashlib.sha256()
    digest.update(f"runtime={RUNTIME_VERSION}\n".encode())
    # The backend copies itself into ~/.local/share, so a change to this file
    # has to count as a change to the runtime.
    digest.update(b"backend\0")
    digest.update(read_bytes(Path(__file__).resolve()))
    template = paths()["driver_template"]
    digest.update(b"driver\0")
    digest.update(read_bytes(template) if template.is_file() else b"")
    for path in vendor_files():
        digest.update(f"vendor/{path.name}\0".encode())
        digest.update(read_bytes(path))
    return digest.hexdigest()


def read_stamp() -> dict[str, Any] | None:
    content = read_text(paths()["stamp"])
    if not content:
        return None
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def write_stamp(mark: str) -> None:
    payload = {
        "plugin": PLUGIN_ID,
        "runtimeVersion": RUNTIME_VERSION,
        "fingerprint": mark,
        "installedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": str(paths()["plugin"]),
    }
    atomic_write(paths()["stamp"], json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", make_backup=False)


def runtime_owned() -> bool:
    """True when the runtime directory is absent or was created by us.

    A directory that exists without our stamp belongs to someone else, and
    the plugin refuses to write into or delete it.
    """
    runtime = paths()["runtime"]
    if not runtime.exists():
        return True
    stamp = read_stamp()
    return bool(stamp and stamp.get("plugin") == PLUGIN_ID)


def render_driver() -> str:
    template = read_text(paths()["driver_template"])
    if not template:
        raise RuntimeError(f"Missing driver template at {paths()['driver_template']}")
    cleanup = " ".join([
        "python3",
        shlex.quote(str(paths()["backend_script"])),
        "uninstall", "--purge", "--orphan",
    ])
    return (template
            .replace('"@@PLUGIN_MANIFEST@@"', lua_string(str(paths()["plugin"] / "manifest.json")))
            .replace('"@@CLEANUP_COMMAND@@"', lua_string(cleanup)))


def install_backend_copy() -> None:
    """Mirror the pieces needed to uninstall into ~/.local/share.

    `omarchy plugin remove` deletes the checkout without running anything, so
    the cleanup path cannot live in the checkout.
    """
    backend = paths()["backend"]
    staging = backend.with_name(backend.name + ".new")
    shutil.rmtree(staging, ignore_errors=True)
    (staging / "scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy2(Path(__file__).resolve(), staging / "scripts/hotcorners.py")
    shutil.copy2(paths()["driver_template"], staging / "scripts/driver.lua")
    shutil.copytree(paths()["vendor_mousetrap"], staging / "vendor/mousetrap")
    shutil.rmtree(backend, ignore_errors=True)
    staging.replace(backend)


def legacy_mousetrap_is_ours() -> bool:
    """True when `~/.config/hypr/mousetrap/` holds only files we shipped.

    Anything else — an extra file, an edited one — means a user or another
    tool owns that directory, and migration leaves it alone.
    """
    legacy = paths()["legacy_mousetrap"]
    if not legacy.is_dir():
        return False
    shipped = {path.name: read_bytes(path) for path in vendor_files()}
    if not shipped:
        return False
    for path in legacy.rglob("*"):
        if path.is_dir():
            return False
        expected = shipped.get(path.name)
        if expected is None or read_bytes(path) != expected:
            return False
    return True


# Header text both pre-2.0 files carried when this plugin wrote them. Anything
# else at those paths belongs to someone else.
LEGACY_SIGNATURES = ("Omarchy Hot Corners plugin", PLUGIN_ID)


def legacy_file_is_ours(path: Path) -> bool:
    content = read_text(path)
    return content is not None and any(signature in content for signature in LEGACY_SIGNATURES)


def legacy_pending() -> bool:
    """True only for leftovers migration will actually clear.

    Checking mere existence would be wrong: a file we have refused to touch
    would then keep `sync` reporting work to do forever, and the panel
    reinstalls on every open.
    """
    if any(legacy_file_is_ours(paths()[key]) for key in ("legacy_driver", "legacy_config")):
        return True
    return legacy_mousetrap_is_ours()


def migrate_legacy() -> list[str]:
    """Retire the pre-2.0 layout, touching only files we can prove are ours."""
    notes: list[str] = []
    for key in ("legacy_driver", "legacy_config"):
        path = paths()[key]
        if not path.exists():
            continue
        if legacy_file_is_ours(path):
            backup(path)
            path.unlink()
            notes.append(f"removed {path}")
        else:
            notes.append(f"left {path} in place (not written by this plugin)")

    legacy = paths()["legacy_mousetrap"]
    if legacy.is_dir():
        if legacy_mousetrap_is_ours():
            backup_tree(legacy)
            shutil.rmtree(legacy)
            notes.append(f"removed {legacy}")
        else:
            notes.append(f"left {legacy} in place (it holds files this plugin did not install)")
    return notes


def pending(mark: str) -> list[str]:
    """Everything about the current install that does not match this checkout."""
    reasons: list[str] = []
    stamp = read_stamp()
    if not paths()["driver"].exists():
        reasons.append("driver missing")
    if not paths()["mousetrap_dir"].is_dir():
        reasons.append("mousetrap missing")
    if not paths()["config_lua"].exists():
        reasons.append("generated config missing")
    if stamp is None:
        reasons.append("not installed")
    elif stamp.get("fingerprint") != mark:
        reasons.append("plugin updated")
    if not hook_current(read_text(paths()["hyprland"])):
        reasons.append("hyprland hook missing")
    if read_text(paths()["backend_script"]) is None:
        reasons.append("uninstaller missing")
    if not menu_current():
        reasons.append("menu entry missing")
    if not shell_registered():
        reasons.append("shell registration missing")
    if legacy_pending():
        reasons.append("older layout present")
    return reasons


def installed() -> bool:
    return hook_current(read_text(paths()["hyprland"])) and paths()["driver"].exists()


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


# ---------------------------------------------------------------- commands

def cmd_list(_: argparse.Namespace) -> int:
    store = load_store()
    try:
        outstanding = pending(fingerprint())
    except OSError:
        outstanding = ["checkout unreadable"]
    return emit({
        "ok": True,
        "installed": installed(),
        "needsSync": bool(outstanding),
        "pending": outstanding,
        "cornerOrder": list(CORNER_ORDER),
        "corners": store.get("corners", {}),
        "custom": store.get("custom", {}),
        "options": store.get("options", {}),
        "actions": ACTIONS,
        "driverPath": str(paths()["driver"]),
    })


def cmd_sync(args: argparse.Namespace) -> int:
    """Bring the installed runtime in line with this checkout, idempotently."""
    with locked():
        source = paths()["source"]
        plugin = paths()["plugin"]
        canonical = plugin.resolve() if plugin.exists() else plugin
        if source != canonical:
            return emit({
                "ok": False,
                "error": (
                    f"Refusing to install from {source}. Hot Corners installs from "
                    f"{plugin}; run this checkout's ./install.sh instead."
                ),
            })

        mark = fingerprint()
        outstanding = pending(mark)
        if not outstanding and not args.force:
            return emit({"ok": True, "changed": False, "pending": []})

        if not runtime_owned():
            return emit({
                "ok": False,
                "error": (
                    f"{paths()['runtime']} already exists and was not created by this "
                    "plugin. Move it aside and try again."
                ),
            })

        hyprland = paths()["hyprland"]
        if not hyprland.exists():
            return emit({"ok": False, "error": f"Missing {hyprland}; run 'omarchy refresh hyprland' first."})

        vendor = paths()["vendor_mousetrap"]
        if not vendor.is_dir():
            return emit({"ok": False, "error": f"Missing vendored mousetrap module at {vendor}"})

        previous_driver = read_text(paths()["driver"])
        previous_config = read_text(paths()["config_lua"])
        previous_hyprland = read_text(hyprland)
        previous_stamp = read_text(paths()["stamp"])
        fresh_runtime = not paths()["runtime"].exists()

        notes: list[str] = []
        try:
            paths()["runtime"].mkdir(parents=True, exist_ok=True)
            shutil.copytree(vendor, paths()["mousetrap_dir"], dirs_exist_ok=True)
            atomic_write(paths()["driver"], render_driver(), make_backup=False)
            validate_lua(paths()["driver"])
            write_config_lua(load_store())
            install_backend_copy()
            write_stamp(mark)
            atomic_write(hyprland, ensure_hook(previous_hyprland or ""))
            notes = migrate_legacy()
            reload_hyprland()
        except Exception as error:
            restore_file(paths()["driver"], previous_driver)
            restore_file(paths()["config_lua"], previous_config)
            restore_file(hyprland, previous_hyprland)
            restore_file(paths()["stamp"], previous_stamp)
            if fresh_runtime:
                shutil.rmtree(paths()["runtime"], ignore_errors=True)
            with contextlib.suppress(Exception):
                reload_hyprland()
            return emit({"ok": False, "error": f"Installation failed and was rolled back: {error}"})

        try:
            add_menu_entry()
            register_shell()
        except Exception as error:
            return emit({
                "ok": False,
                "changed": True,
                "error": f"Hot corners are active, but shell integration failed: {error}",
            })
    return emit({"ok": True, "changed": True, "pending": outstanding, "notes": notes})


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


def cmd_uninstall(args: argparse.Namespace) -> int:
    """Remove the Hyprland hook, and with --purge the runtime it points at.

    `--orphan` is how the driver cleans up after `omarchy plugin remove`: it
    runs from inside a Hyprland reload, so it must not trigger another one.
    """
    if args.orphan:
        os.environ["OMARCHY_HOTCORNERS_SKIP_RELOAD"] = "1"

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
        with contextlib.suppress(Exception):
            unregister_shell()

        if args.purge:
            if paths()["runtime"].exists() and not runtime_owned():
                return emit({
                    "ok": False,
                    "error": f"Refusing to delete {paths()['runtime']}: it was not created by this plugin.",
                })
            if paths()["runtime"].is_dir():
                backup_tree(paths()["runtime"])
                shutil.rmtree(paths()["runtime"])
            for key in ("legacy_driver", "legacy_config", "data"):
                path = paths()[key]
                if path.exists():
                    backup(path)
                    path.unlink()
            if legacy_mousetrap_is_ours():
                backup_tree(paths()["legacy_mousetrap"])
                shutil.rmtree(paths()["legacy_mousetrap"])

            # Last, because it is the script running this. Deleting the copy
            # while executing from it is safe: the interpreter already read it.
            if paths()["backend"].is_dir():
                shutil.rmtree(paths()["backend"], ignore_errors=True)
    return emit({"ok": True, "purged": args.purge, "orphan": args.orphan})


def cmd_status(_: argparse.Namespace) -> int:
    try:
        mark = fingerprint()
        outstanding = pending(mark)
    except OSError as error:
        return emit({"ok": False, "error": str(error)})
    return emit({
        "ok": True,
        "installed": installed(),
        "needsSync": bool(outstanding),
        "pending": outstanding,
        "runtime": str(paths()["runtime"]),
        "source": str(paths()["source"]),
        "fingerprint": mark,
        "stamp": read_stamp(),
    })


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("list").set_defaults(handler=cmd_list)
    commands.add_parser("status").set_defaults(handler=cmd_status)
    apply_parser = commands.add_parser("apply")
    apply_parser.add_argument("config")
    apply_parser.set_defaults(handler=cmd_apply)
    commands.add_parser("reset").set_defaults(handler=cmd_reset)
    for name in ("sync", "install"):
        sync_parser = commands.add_parser(name)
        sync_parser.add_argument("--force", action="store_true")
        sync_parser.set_defaults(handler=cmd_sync)
    uninstall_parser = commands.add_parser("uninstall")
    uninstall_parser.add_argument("--purge", action="store_true")
    uninstall_parser.add_argument("--orphan", action="store_true")
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
