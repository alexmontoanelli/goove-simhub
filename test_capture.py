import unittest

import capture


class TestDefaultRegion(unittest.TestCase):
    def test_center_50_percent(self):
        mon = {"left": 0, "top": 0, "width": 1920, "height": 1080}
        left, top, w, h = capture.default_region(mon)
        self.assertEqual((w, h), (960, 540))
        self.assertEqual((left, top), (480, 270))

    def test_respects_monitor_offset(self):
        mon = {"left": 100, "top": 200, "width": 800, "height": 600}
        left, top, w, h = capture.default_region(mon)
        self.assertEqual((w, h), (400, 300))
        self.assertEqual((left, top), (300, 350))


class TestSubsample(unittest.TestCase):
    def _solid_bgra(self, width, height, rgb):
        r, g, b = rgb
        px = bytes([b, g, r, 255])
        return px * (width * height)

    def test_solid_color_returns_that_color(self):
        bgra = self._solid_bgra(64, 64, (10, 20, 30))
        pixels = capture.subsample(bgra, 64, 64, grid=8)
        self.assertEqual(len(pixels), 64)  # 8x8
        self.assertTrue(all(p == (10, 20, 30) for p in pixels))

    def test_bgra_to_rgb_order(self):
        # 1x1 imagem: B=1, G=2, R=3
        bgra = bytes([1, 2, 3, 255])
        pixels = capture.subsample(bgra, 1, 1, grid=1)
        self.assertEqual(pixels, [(3, 2, 1)])


class TestScreenSampler(unittest.TestCase):
    def test_sample_uses_grab_and_subsamples(self):
        s = capture.ScreenSampler(region=(0, 0, 4, 4))
        # injeta um grab fake: imagem 4x4 verde (R=0,G=255,B=0)
        bgra = bytes([0, 255, 0, 255]) * 16

        def fake_grab(region):
            self.assertEqual(region, (0, 0, 4, 4))
            return (bgra, 4, 4)

        s._grab = fake_grab
        pixels = s.sample()
        self.assertTrue(pixels)
        self.assertTrue(all(p == (0, 255, 0) for p in pixels))

    def test_set_region(self):
        s = capture.ScreenSampler()
        s.set_region((1, 2, 3, 4))
        self.assertEqual(s.region, (1, 2, 3, 4))


if __name__ == "__main__":
    unittest.main()
