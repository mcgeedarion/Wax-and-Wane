import os
import plistlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from render_launchagent import render

ROOT = Path(__file__).resolve().parent.parent


class LaunchAgentTests(unittest.TestCase):
    def test_cli_renders_real_template_and_both_log_paths(self):
        with tempfile.TemporaryDirectory(prefix="wax space & ") as directory:
            root = Path(directory)
            output = root / "agent.plist"
            values = {
                "WAX_BINARY": str(root / "bin/wax-and-wane"),
                "WAX_CONFIG": str(root / "config/settings.json"),
                "WAX_LOG_DIR": str(root / "Library/Logs"),
                "WAX_TEMPLATE": str(ROOT / "com.user.waxandwane.plist"),
                "WAX_OUTPUT": str(output),
            }
            subprocess.run([sys.executable, str(ROOT / "packaging/render_launchagent.py")],
                           env={**os.environ, **values}, check=True)
            with output.open("rb") as source:
                result = plistlib.load(source)
            self.assertEqual(result["ProgramArguments"], [values["WAX_BINARY"], "run", "--config", values["WAX_CONFIG"]])
            self.assertEqual(result["StandardOutPath"], str(root / "Library/Logs/wax-and-wane.out.log"))
            self.assertEqual(result["StandardErrorPath"], str(root / "Library/Logs/wax-and-wane.err.log"))
            self.assertNotIn("__WAX_AND_WANE_", output.read_text())
            self.assertTrue(Path(result["StandardOutPath"]).is_absolute())
            self.assertTrue(Path(result["StandardErrorPath"]).is_absolute())
            self.assertEqual(result["ThrottleInterval"], 30)
            self.assertEqual(result["KeepAlive"], {"SuccessfulExit": False})

    def test_nested_values_preserve_non_strings(self):
        self.assertEqual(render({"a": ["__WAX_AND_WANE_LOG_DIR__/out", True, 30]},
                                {"__WAX_AND_WANE_LOG_DIR__": "/tmp/logs"}),
                         {"a": ["/tmp/logs/out", True, 30]})

    def test_unknown_placeholder_is_rejected(self):
        with self.assertRaises(KeyError):
            render("__WAX_AND_WANE_UNKNOWN__/out", {})

    def test_relative_paths_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "agent.plist"
            values = {"WAX_BINARY": "relative/binary", "WAX_CONFIG": "/tmp/config",
                      "WAX_LOG_DIR": "/tmp/logs", "WAX_TEMPLATE": str(ROOT / "com.user.waxandwane.plist"),
                      "WAX_OUTPUT": str(output)}
            result = subprocess.run([sys.executable, str(ROOT / "packaging/render_launchagent.py")],
                                    env={**os.environ, **values}, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
