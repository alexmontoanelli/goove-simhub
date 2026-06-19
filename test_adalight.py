import os
import tempfile
import unittest

import appconfig
import engine
import govee_lan_core as govee
import reduce as reducer
from adalight import AdalightParser


def frame_bytes(leds):
    n = len(leds) - 1
    hi, lo = (n >> 8) & 0xFF, n & 0xFF
    chk = hi ^ lo ^ 0x55
    out = bytearray(b"Ada")
    out += bytes([hi, lo, chk])
    for r, g, b in leds:
        out += bytes([r, g, b])
    return bytes(out)


class TestAdalightParser(unittest.TestCase):
    def test_single_valid_frame(self):
        p = AdalightParser()
        frames = p.feed(frame_bytes([(10, 20, 30), (40, 50, 60)]))
        self.assertEqual(frames, [[(10, 20, 30), (40, 50, 60)]])

    def test_bad_checksum_discarded(self):
        p = AdalightParser()
        raw = bytearray(frame_bytes([(1, 2, 3)]))
        raw[5] ^= 0xFF  # corrompe o checksum
        self.assertEqual(p.feed(bytes(raw)), [])

    def test_resync_after_garbage(self):
        p = AdalightParser()
        data = b"\x00\xffxx" + frame_bytes([(7, 8, 9)])
        self.assertEqual(p.feed(data), [[(7, 8, 9)]])

    def test_frame_split_across_feeds(self):
        p = AdalightParser()
        full = frame_bytes([(1, 1, 1), (2, 2, 2)])
        self.assertEqual(p.feed(full[:5]), [])
        self.assertEqual(p.feed(full[5:]), [[(1, 1, 1), (2, 2, 2)]])

    def test_two_frames_one_feed(self):
        p = AdalightParser()
        data = frame_bytes([(1, 1, 1)]) + frame_bytes([(2, 2, 2)])
        self.assertEqual(p.feed(data), [[(1, 1, 1)], [(2, 2, 2)]])


class TestReduce(unittest.TestCase):
    def test_average(self):
        self.assertEqual(reducer.average([(0, 0, 0), (100, 200, 50)]), (50, 100, 25))

    def test_average_empty_is_black(self):
        self.assertEqual(reducer.average([]), (0, 0, 0))

    def test_dominant_picks_most_common(self):
        leds = [(255, 0, 0), (255, 0, 0), (0, 0, 255)]
        self.assertEqual(reducer.dominant(leds), (255, 0, 0))

    def test_luminance_black_and_white(self):
        self.assertEqual(round(reducer.luminance((0, 0, 0))), 0)
        self.assertEqual(round(reducer.luminance((255, 255, 255))), 255)


class TestGoveeCore(unittest.TestCase):
    def test_build_message(self):
        self.assertEqual(
            govee.build_message("turn", {"value": 1}),
            {"msg": {"cmd": "turn", "data": {"value": 1}}},
        )


class TestAppConfig(unittest.TestCase):
    def test_defaults_when_missing(self):
        with tempfile.TemporaryDirectory() as d:
            p = appconfig.pathlib.Path(d) / "config.ini"
            cfg = appconfig.load(p)
            self.assertEqual(cfg["serial"]["baud"], 115200)
            self.assertEqual(cfg["render"]["reduce"], "average")
            self.assertTrue(cfg["render"]["black_off"])

    def test_save_then_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = appconfig.pathlib.Path(d) / "sub" / "config.ini"
            cfg = appconfig.load(p)
            cfg["govee"]["ip"] = "192.168.0.177"
            cfg["render"]["rate_hz"] = 20
            cfg["render"]["black_off"] = False
            cfg["render"]["brightness"] = 60
            appconfig.save(cfg, p)
            again = appconfig.load(p)
            self.assertEqual(again["govee"]["ip"], "192.168.0.177")
            self.assertEqual(again["render"]["rate_hz"], 20)
            self.assertFalse(again["render"]["black_off"])
            self.assertEqual(again["render"]["brightness"], 60)


class TestDecideAction(unittest.TestCase):
    def test_color_when_bright(self):
        action, bc = engine.decide_action((200, 0, 0), 60.0, True, 10.0, 0, 5)
        self.assertEqual(action, "color")
        self.assertEqual(bc, 0)

    def test_counts_black_frames_then_off(self):
        bc = 0
        for _ in range(4):  # abaixo do limiar, mas ainda não atingiu black_frames=5
            action, bc = engine.decide_action((0, 0, 0), 0.0, True, 10.0, bc, 5)
            self.assertEqual(action, "skip")
        action, bc = engine.decide_action((0, 0, 0), 0.0, True, 10.0, bc, 5)
        self.assertEqual(action, "off")  # 5º frame preto -> desliga

    def test_off_only_once(self):
        action, bc = engine.decide_action((0, 0, 0), 0.0, True, 10.0, 10, 5)
        self.assertEqual(action, "skip")  # já passou do gatilho, não repete off

    def test_black_off_disabled_always_color(self):
        action, bc = engine.decide_action((0, 0, 0), 0.0, False, 10.0, 0, 5)
        self.assertEqual(action, "color")


class TestLogFormatting(unittest.TestCase):
    def test_format_log_color_sent(self):
        line = engine.format_log((120, 30, 30), 58.0, "color", "ok->192.168.0.42")
        self.assertIn("cor=(120, 30, 30)", line)
        self.assertIn("lum=58", line)
        self.assertIn("acao=color", line)
        self.assertIn("ok->192.168.0.42", line)

    def test_format_log_skip(self):
        line = engine.format_log((0, 0, 0), 2.0, "skip", "skip")
        self.assertIn("acao=skip", line)


class TestShouldLog(unittest.TestCase):
    def test_logs_when_key_changes(self):
        self.assertTrue(engine.should_log("b", "a", now=10.0, last_time=10.0))

    def test_logs_on_heartbeat_after_one_second(self):
        self.assertTrue(engine.should_log("a", "a", now=11.0, last_time=10.0))

    def test_skips_same_key_within_one_second(self):
        self.assertFalse(engine.should_log("a", "a", now=10.5, last_time=10.0))


class TestEngineScreenSource(unittest.TestCase):
    def _cfg(self):
        with tempfile.TemporaryDirectory() as d:
            return appconfig.load(os.path.join(d, "config.ini"))

    def test_resolve_region_uses_config_when_set(self):
        cfg = self._cfg()
        cfg["capture"].update({"left": 5, "top": 6, "width": 7, "height": 8})
        eng = engine.Engine(cfg)

        class FakeSampler:
            def primary_monitor(self):
                raise AssertionError("não deveria consultar o monitor")

        self.assertEqual(eng._resolve_region(FakeSampler()), (5, 6, 7, 8))

    def test_resolve_region_falls_back_to_default(self):
        cfg = self._cfg()  # capture = -1 (indefinido)
        eng = engine.Engine(cfg)

        class FakeSampler:
            def primary_monitor(self):
                return {"left": 0, "top": 0, "width": 1000, "height": 1000}

        self.assertEqual(eng._resolve_region(FakeSampler()), (250, 250, 500, 500))


class TestModeCaptureConfig(unittest.TestCase):
    def test_defaults_have_mode_and_capture(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.ini")
            cfg = appconfig.load(path)  # arquivo inexistente => defaults
            self.assertEqual(cfg["mode"]["source"], "serial")
            self.assertEqual(cfg["capture"]["left"], -1)
            self.assertEqual(cfg["capture"]["top"], -1)
            self.assertEqual(cfg["capture"]["width"], -1)
            self.assertEqual(cfg["capture"]["height"], -1)

    def test_roundtrip_screen_source(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.ini")
            cfg = appconfig.load(path)
            cfg["mode"]["source"] = "screen"
            cfg["capture"]["left"] = 100
            cfg["capture"]["width"] = 640
            appconfig.save(cfg, path)
            cfg2 = appconfig.load(path)
            self.assertEqual(cfg2["mode"]["source"], "screen")
            self.assertEqual(cfg2["capture"]["left"], 100)
            self.assertEqual(cfg2["capture"]["width"], 640)


if __name__ == "__main__":
    unittest.main()
