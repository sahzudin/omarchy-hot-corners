import contextlib
import importlib.util
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


BACKEND = Path(__file__).resolve().parents[1] / "scripts/hotcorners.py"
SPEC = importlib.util.spec_from_file_location("hotcorners", BACKEND)
assert SPEC and SPEC.loader
hotcorners = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hotcorners)


class SafeReadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.environment = mock.patch.dict(
            os.environ,
            {
                "OMARCHY_HOTCORNERS_HOME": str(self.root),
                "OMARCHY_HOTCORNERS_OMARCHY_PATH": str(self.root / "omarchy"),
                "OMARCHY_HOTCORNERS_SKIP_RELOAD": "1",
            },
        )
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temporary.cleanup()

    def test_reads_regular_file(self):
        path = self.root / "config.json"
        path.write_text('{"ok": true}', encoding="utf-8")
        self.assertEqual(hotcorners.read_text(path), '{"ok": true}')

    def test_missing_file_is_optional(self):
        self.assertIsNone(hotcorners.read_text(self.root / "missing"))

    def test_refuses_symlink(self):
        target = self.root / "target"
        target.write_text("secret", encoding="utf-8")
        link = self.root / "config.json"
        link.symlink_to(target)
        with self.assertRaises(OSError):
            hotcorners.read_text(link)

    def test_refuses_fifo_without_blocking(self):
        fifo = self.root / "config.json"
        os.mkfifo(fifo)
        started = time.monotonic()
        with self.assertRaises(OSError):
            hotcorners.read_text(fifo)
        self.assertLess(time.monotonic() - started, 1.0)

    def test_refuses_oversized_file(self):
        path = self.root / "config.json"
        with path.open("wb") as handle:
            handle.truncate(hotcorners.MAX_READ_BYTES + 1)
        with self.assertRaisesRegex(OSError, "exceeds"):
            hotcorners.read_text(path)

    def test_refuses_file_that_grows_past_custom_limit(self):
        path = self.root / "config.json"
        path.write_bytes(b"12345")
        with self.assertRaisesRegex(OSError, "exceeds"):
            hotcorners.read_bytes(path, max_bytes=4)

    def test_settings_loader_refuses_fifo_without_blocking(self):
        path = hotcorners.paths()["data"]
        path.parent.mkdir(parents=True)
        os.mkfifo(path)
        started = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, "non-regular"):
            hotcorners.load_store()
        self.assertLess(time.monotonic() - started, 1.0)

    def test_lock_refuses_fifo_without_blocking(self):
        path = hotcorners.paths()["lock"]
        path.parent.mkdir(parents=True)
        os.mkfifo(path)
        started = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, "non-regular"):
            with hotcorners.locked():
                self.fail("FIFO must never be locked")
        self.assertLess(time.monotonic() - started, 1.0)

    def test_sync_and_list_complete_with_regular_bounded_inputs(self):
        paths = hotcorners.paths()
        paths["hyprland"].parent.mkdir(parents=True)
        paths["hyprland"].write_text("return {}\n", encoding="utf-8")
        paths["menu"].parent.mkdir(parents=True)
        paths["menu"].write_text("{}\n", encoding="utf-8")
        paths["shell_defaults"].parent.mkdir(parents=True)
        paths["shell_defaults"].write_text('{"plugins": []}\n', encoding="utf-8")
        paths["plugin"].parent.mkdir(parents=True)
        paths["plugin"].symlink_to(hotcorners.source_path(), target_is_directory=True)

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = hotcorners.cmd_sync(SimpleNamespace(force=False))
        self.assertEqual(result, 0, output.getvalue())
        self.assertTrue(json.loads(output.getvalue())["changed"])

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = hotcorners.cmd_list(SimpleNamespace())
        payload = json.loads(output.getvalue())
        self.assertEqual(result, 0, payload)
        self.assertTrue(payload["installed"])
        self.assertFalse(payload["needsSync"])


if __name__ == "__main__":
    unittest.main()
