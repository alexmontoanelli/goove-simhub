"""Config em .ini no Documents do usuário."""

import configparser
import pathlib

DEFAULTS = {
    "govee": {"ip": "auto"},
    "serial": {"port": "COM11", "baud": 115200},
    "render": {
        "reduce": "average",
        "rate_hz": 12,
        "black_off": True,
        "black_frames": 5,
        "brightness": 100,
    },
    "startup": {
        "start_with_windows": False,
        "minimize_to_tray": False,
        "start_minimized": False,
        "autostart_bridge": False,
    },
}


def config_path():
    return pathlib.Path.home() / "Documents" / "Adalight Govee Bridge" / "config.ini"


def _typed(section, key, raw):
    default = DEFAULTS[section][key]
    if isinstance(default, bool):
        return str(raw).strip().lower() in ("1", "true", "yes", "on")
    if isinstance(default, int):
        return int(raw)
    return raw


def load(path=None):
    path = pathlib.Path(path) if path else config_path()
    parser = configparser.ConfigParser()
    if path.exists():
        parser.read(path, encoding="utf-8")
    cfg = {s: dict(vals) for s, vals in DEFAULTS.items()}
    for section in DEFAULTS:
        if parser.has_section(section):
            for key in DEFAULTS[section]:
                if parser.has_option(section, key):
                    cfg[section][key] = _typed(section, key, parser.get(section, key))
    return cfg


def save(cfg, path=None):
    path = pathlib.Path(path) if path else config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    parser = configparser.ConfigParser()
    for section, vals in cfg.items():
        parser[section] = {k: str(v) for k, v in vals.items()}
    with open(path, "w", encoding="utf-8") as f:
        parser.write(f)
