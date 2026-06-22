"""System tray icon (requires pystray + Pillow). Runs in its own thread."""

import threading


def _build_image():
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (64, 64), (20, 20, 20))
    d = ImageDraw.Draw(img)
    d.ellipse((12, 12, 52, 52), fill=(0, 180, 70))
    return img


def make_icon(on_show, on_turn_on, on_turn_off, on_quit):
    """Create (but do not run) the tray icon with its menu."""
    import pystray

    menu = pystray.Menu(
        pystray.MenuItem("Show", lambda icon, item: on_show(), default=True),
        pystray.MenuItem("Turn on", lambda icon, item: on_turn_on()),
        pystray.MenuItem("Turn off", lambda icon, item: on_turn_off()),
        pystray.MenuItem("Quit", lambda icon, item: on_quit()),
    )
    return pystray.Icon("adalight-govee", _build_image(), "Adalight → Govee", menu)


def run_in_thread(icon):
    """Start the icon loop in a daemon thread and return the thread."""
    t = threading.Thread(target=icon.run, daemon=True)
    t.start()
    return t
