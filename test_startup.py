import sys
import tempfile
import unittest

import appconfig
import autostart


class TestStartupConfig(unittest.TestCase):
    def test_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = appconfig.load(appconfig.pathlib.Path(d) / "config.ini")
            su = cfg["startup"]
            self.assertEqual(su["start_with_windows"], False)
            self.assertEqual(su["minimize_to_tray"], False)
            self.assertEqual(su["start_minimized"], False)
            self.assertEqual(su["autostart_bridge"], False)

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = appconfig.pathlib.Path(d) / "config.ini"
            cfg = appconfig.load(p)
            cfg["startup"]["minimize_to_tray"] = True
            cfg["startup"]["autostart_bridge"] = True
            appconfig.save(cfg, p)
            again = appconfig.load(p)
            self.assertTrue(again["startup"]["minimize_to_tray"])
            self.assertTrue(again["startup"]["autostart_bridge"])
            self.assertFalse(again["startup"]["start_with_windows"])


class TestAutostart(unittest.TestCase):
    def test_supported_matches_platform(self):
        self.assertEqual(autostart.is_supported(), sys.platform == "win32")

    @unittest.skipIf(sys.platform == "win32", "no-op behavior is for non-Windows")
    def test_noop_off_windows(self):
        # Off Windows everything must be a safe no-op returning False.
        self.assertFalse(autostart.is_enabled())
        self.assertFalse(autostart.enable())
        self.assertFalse(autostart.disable())
        self.assertFalse(autostart.apply(True))
        self.assertFalse(autostart.apply(False))


if __name__ == "__main__":
    unittest.main()
