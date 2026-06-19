"""Captura de uma região da tela e subamostragem para lista de pixels RGB."""

GRID = 32  # 32x32 = 1024 amostras, custo constante


def default_region(monitor):
    """50% central do monitor (dict do mss: left/top/width/height)."""
    w = monitor["width"] // 2
    h = monitor["height"] // 2
    left = monitor["left"] + (monitor["width"] - w) // 2
    top = monitor["top"] + (monitor["height"] - h) // 2
    return (left, top, w, h)


def subsample(bgra, width, height, grid=GRID):
    """Amostra grid×grid pontos do buffer BGRA (4 bytes/pixel) -> lista RGB."""
    if width <= 0 or height <= 0:
        return []
    cols = min(grid, width)
    rows = min(grid, height)
    pixels = []
    for gy in range(rows):
        y = (gy * height) // rows
        row_off = y * width * 4
        for gx in range(cols):
            x = (gx * width) // cols
            i = row_off + x * 4
            b, g, r = bgra[i], bgra[i + 1], bgra[i + 2]
            pixels.append((r, g, b))
    return pixels


class ScreenSampler:
    def __init__(self, region=None):
        self.region = region
        self._mss = None

    def _ensure_mss(self):
        if self._mss is None:
            import mss  # lazy: só quando captura de verdade

            self._mss = mss.mss()
        return self._mss

    def primary_monitor(self):
        sct = self._ensure_mss()
        # monitors[0] = virtual total; [1] = monitor principal
        mons = sct.monitors
        return mons[1] if len(mons) > 1 else mons[0]

    def set_region(self, region):
        self.region = region

    def _grab(self, region):
        sct = self._ensure_mss()
        left, top, width, height = region
        shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
        return (bytes(shot.bgra), shot.width, shot.height)

    def sample(self):
        region = self.region
        if region is None:
            region = default_region(self.primary_monitor())
            self.region = region
        bgra, width, height = self._grab(region)
        return subsample(bgra, width, height)
