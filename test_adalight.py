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


class TestConnectEffect(unittest.TestCase):
    def _run(self):
        calls = []
        engine.connect_effect(lambda cmd, data: calls.append((cmd, data)), sleep=lambda _s: None)
        return calls

    def test_turns_on_and_sets_green(self):
        calls = self._run()
        self.assertEqual(calls[0], ("turn", {"value": 1}))
        color = next(d["color"] for c, d in calls if c == "colorwc")
        self.assertEqual(color, {"r": 0, "g": 255, "b": 0})

    def test_pulses_brightness_twice(self):
        calls = self._run()
        levels = [d["value"] for c, d in calls if c == "brightness"]
        self.assertEqual(levels, [30, 100, 30, 100])


if __name__ == "__main__":
    unittest.main()
