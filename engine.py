"""Engine: lê Adalight da serial e envia cor para a Govee (2 threads)."""

import threading
import time

import serial  # pyserial

import capture
import govee_lan_core as govee
import reduce as reducer
from adalight import AdalightParser


def decide_action(color, lum, black_off, threshold, black_count, black_frames):
    """Decide o que enviar. Retorna (action, new_black_count).

    action: "color" envia colorwc; "off" desliga; "skip" não faz nada.
    """
    if not black_off or lum >= threshold:
        return ("color", 0)
    new_count = black_count + 1
    if new_count == black_frames:
        return ("off", new_count)
    return ("skip", new_count)


def format_log(color, lum, action, result):
    """Monta uma linha de log crua para um ciclo do sender."""
    return f"cor={color} lum={lum:.0f} acao={action} {result}"


def should_log(key, last_key, now, last_time, heartbeat=1.0):
    """Loga se a chave (cor+ação) mudou ou passou ``heartbeat`` segundos."""
    return key != last_key or (now - last_time) >= heartbeat


class Engine:
    def __init__(self, cfg, on_status=None, on_log=None):
        self.cfg = cfg
        self.on_status = on_status or (lambda s: None)
        self.on_log = on_log or (lambda line: None)
        self._last_log_key = None
        self._last_log_time = 0.0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._color = (0, 0, 0)
        self._threads = []
        self._serial = None
        self._sampler = None
        self._ip = None
        self._black_count = 0
        self._is_on = None
        self._brightness = int(cfg["render"].get("brightness", 100))
        self._last_brightness = None

    def set_brightness(self, value):
        """Ajuste de brilho ao vivo (0-100), aplicado no próximo envio."""
        self._brightness = max(0, min(100, int(value)))

    def _resolve_ip(self):
        ip = self.cfg["govee"]["ip"]
        if ip and ip != "auto":
            return ip
        devs = govee.lan_discover()
        return devs[0]["ip"] if devs else None

    def _resolve_region(self, sampler):
        c = self.cfg["capture"]
        vals = (int(c["left"]), int(c["top"]), int(c["width"]), int(c["height"]))
        if vals[2] > 0 and vals[3] > 0:
            return vals
        return capture.default_region(sampler.primary_monitor())

    def start(self):
        self._ip = self._resolve_ip()
        if not self._ip:
            self.on_status({"state": "error", "msg": "Govee não encontrada (defina o IP)"})
            return False

        source = self.cfg["mode"]["source"]
        if source == "screen":
            try:
                self._sampler = capture.ScreenSampler()
                self._sampler.set_region(self._resolve_region(self._sampler))
            except ImportError:
                self.on_status({"state": "error", "msg": "Instale 'mss' para o modo Tela"})
                return False
            reader = self._reader_screen
        else:
            self._serial = serial.Serial(
                self.cfg["serial"]["port"], int(self.cfg["serial"]["baud"]), timeout=0.1
            )
            reader = self._reader

        self._stop.clear()
        self._threads = [
            threading.Thread(target=reader, daemon=True),
            threading.Thread(target=self._sender, daemon=True),
        ]
        for t in self._threads:
            t.start()
        self.on_status({"state": "running", "ip": self._ip})
        return True

    def stop(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=1.0)
        if self._serial:
            self._serial.close()
            self._serial = None
        self.on_status({"state": "stopped"})

    def _reader(self):
        parser = AdalightParser()
        reduce_fn = (
            reducer.dominant if self.cfg["render"]["reduce"] == "dominant" else reducer.average
        )
        while not self._stop.is_set():
            try:
                data = self._serial.read(4096)
            except Exception as e:  # serial caiu
                self.on_status({"state": "error", "msg": str(e)})
                break
            if not data:
                continue
            for frame in parser.feed(data):
                color = reduce_fn(frame)
                with self._lock:
                    self._color = color

    def _reader_screen(self):
        reduce_fn = (
            reducer.dominant if self.cfg["render"]["reduce"] == "dominant" else reducer.average
        )
        interval = 1.0 / float(self.cfg["render"]["rate_hz"])
        while not self._stop.is_set():
            try:
                pixels = self._sampler.sample()
            except Exception as e:
                self.on_status({"state": "error", "msg": str(e)})
                break
            if pixels:
                color = reduce_fn(pixels)
                with self._lock:
                    self._color = color
            time.sleep(interval)

    def _sender(self):
        interval = 1.0 / float(self.cfg["render"]["rate_hz"])
        black_off = bool(self.cfg["render"]["black_off"])
        black_frames = int(self.cfg["render"]["black_frames"])
        threshold = 8.0
        while not self._stop.is_set():
            with self._lock:
                color = self._color
            lum = reducer.luminance(color)
            action, self._black_count = decide_action(
                color, lum, black_off, threshold, self._black_count, black_frames
            )
            try:
                if action == "off":
                    result = f"off->{self._ip}"
                    if self._is_on is not False:
                        govee.send_command(self._ip, "turn", {"value": 0})
                        self._is_on = False
                        self._last_brightness = None  # reaplica o brilho ao reacender
                elif action == "color":
                    if self._is_on is not True:
                        govee.send_command(self._ip, "turn", {"value": 1})
                        self._is_on = True
                    if self._brightness != self._last_brightness:
                        govee.send_command(self._ip, "brightness", {"value": self._brightness})
                        self._last_brightness = self._brightness
                    govee.send_command(
                        self._ip,
                        "colorwc",
                        {
                            "color": {"r": color[0], "g": color[1], "b": color[2]},
                            "colorTemInKelvin": 0,
                        },
                    )
                    result = f"ok->{self._ip}"
                else:  # skip (preto, ainda contando)
                    result = "skip (preto)"
                self.on_status({"state": "running", "color": color})
            except Exception as e:
                result = f"erro: {e}"
                self.on_status({"state": "error", "msg": str(e)})
            self._maybe_log(color, lum, action, result)
            time.sleep(interval)

    def _maybe_log(self, color, lum, action, result):
        key = (color, action, result)
        now = time.monotonic()
        if should_log(key, self._last_log_key, now, self._last_log_time):
            self._last_log_key = key
            self._last_log_time = now
            self.on_log(format_log(color, lum, action, result))
