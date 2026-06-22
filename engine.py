"""Engine: lê Adalight da serial e envia cor para a Govee (2 threads)."""

import threading
import time

import serial  # pyserial

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


def connect_effect(send_fn, sleep=time.sleep):
    """Pulso verde de 'conectado': acende verde e pulsa o brilho 2x.

    ``send_fn(cmd, data)`` envia um comando à Govee; ``sleep`` é injetável p/ teste.
    """
    send_fn("turn", {"value": 1})
    sleep(0.25)
    send_fn("colorwc", {"color": {"r": 0, "g": 255, "b": 0}, "colorTemInKelvin": 0})
    sleep(0.3)
    # 2 pulsos de brilho; espaçados p/ a Govee não dropar comandos (rate-limit)
    for level in (30, 100, 30, 100):
        send_fn("brightness", {"value": level})
        sleep(0.3)


# Quanto a cor precisa mudar (por canal) p/ valer um reenvio à Govee, e de quanto
# em quanto tempo reenviamos a mesma cor (keepalive) p/ cobrir pacote UDP perdido.
COLOR_THRESHOLD = 6
COLOR_KEEPALIVE = 2.0


def color_changed(new, last, threshold):
    """True se ``new`` difere de ``last`` em mais que ``threshold`` em algum canal."""
    if last is None:
        return True
    return any(abs(n - l) > threshold for n, l in zip(new, last))


def should_send_color(new, last, now, last_send, threshold, keepalive):
    """Envia se a cor mudou além do limiar, ou se passou o keepalive."""
    return color_changed(new, last, threshold) or (now - last_send) >= keepalive


class Engine:
    def __init__(self, cfg, on_status=None):
        self.cfg = cfg
        self.on_status = on_status or (lambda s: None)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._color = (0, 0, 0)
        self._threads = []
        self._serial = None
        self._ip = None
        self._black_count = 0
        self._is_on = None
        self._brightness = int(cfg["render"].get("brightness", 100))
        self._last_brightness = None
        self._last_sent_color = None
        self._last_color_send = 0.0

    def set_brightness(self, value):
        """Ajuste de brilho ao vivo (0-100), aplicado no próximo envio."""
        self._brightness = max(0, min(100, int(value)))

    def _resolve_ip(self):
        ip = self.cfg["govee"]["ip"]
        if ip and ip != "auto":
            return ip
        devs = govee.lan_discover()
        return devs[0]["ip"] if devs else None

    def start(self):
        self._ip = self._resolve_ip()
        if not self._ip:
            self.on_status({"state": "error", "msg": "Govee not found (set the IP)"})
            return False
        self._serial = self._open_serial()

        self._connect_effect()

        self._stop.clear()
        self._threads = [
            threading.Thread(target=self._reader, daemon=True),
            threading.Thread(target=self._sender, daemon=True),
        ]
        for t in self._threads:
            t.start()
        self.on_status({"state": "running", "ip": self._ip})
        return True

    def _connect_effect(self):
        """Toca o pulso verde de conexão; cosmético, nunca impede iniciar."""
        try:
            connect_effect(lambda cmd, data: govee.send_command(self._ip, cmd, data))
        except Exception:
            pass

    def stop(self):
        self._stop.set()
        for t in self._threads:
            t.join(timeout=1.0)
        if self._serial:
            self._serial.close()
            self._serial = None
        self.on_status({"state": "stopped"})

    def _open_serial(self):
        return serial.Serial(
            self.cfg["serial"]["port"], int(self.cfg["serial"]["baud"]), timeout=0.1
        )

    def _reader(self):
        parser = AdalightParser()
        reduce_fn = (
            reducer.dominant if self.cfg["render"]["reduce"] == "dominant" else reducer.average
        )
        while not self._stop.is_set():
            try:
                data = self._serial.read(4096)
                if not data:
                    continue
                for frame in parser.feed(data):
                    color = reduce_fn(frame)
                    with self._lock:
                        self._color = color
            except Exception as e:  # serial caiu: tenta reconectar sem morrer
                self.on_status({"state": "error", "msg": f"serial: {e} — reconectando"})
                self._reconnect_serial()

    def _reconnect_serial(self):
        try:
            if self._serial:
                self._serial.close()
        except Exception:
            pass
        self._serial = None
        while not self._stop.is_set():
            try:
                self._serial = self._open_serial()
                self.on_status({"state": "running", "msg": "serial reconectada"})
                return
            except Exception:
                self._stop.wait(2.0)  # espera, mas acorda no stop

    def _sender(self):
        interval = 1.0 / float(self.cfg["render"]["rate_hz"])
        black_off = bool(self.cfg["render"]["black_off"])
        black_frames = int(self.cfg["render"]["black_frames"])
        threshold = 8.0
        while not self._stop.is_set():
            try:
                with self._lock:
                    color = self._color
                lum = reducer.luminance(color)
                action, self._black_count = decide_action(
                    color, lum, black_off, threshold, self._black_count, black_frames
                )
                if action == "off" and self._is_on is not False:
                    govee.send_command(self._ip, "turn", {"value": 0})
                    self._is_on = False
                    self._last_brightness = None  # reaplica o brilho ao reacender
                    self._last_sent_color = None  # força reenvio da cor ao reacender
                elif action == "color":
                    if self._is_on is not True:
                        govee.send_command(self._ip, "turn", {"value": 1})
                        self._is_on = True
                    if self._brightness != self._last_brightness:
                        govee.send_command(self._ip, "brightness", {"value": self._brightness})
                        self._last_brightness = self._brightness
                    now = time.monotonic()
                    if should_send_color(
                        color, self._last_sent_color, now, self._last_color_send,
                        COLOR_THRESHOLD, COLOR_KEEPALIVE,
                    ):
                        govee.send_command(
                            self._ip,
                            "colorwc",
                            {
                                "color": {"r": color[0], "g": color[1], "b": color[2]},
                                "colorTemInKelvin": 0,
                            },
                        )
                        self._last_sent_color = color
                        self._last_color_send = now
                self.on_status({"state": "running", "color": color})
            except Exception as e:  # nunca derruba a thread por erro pontual
                self.on_status({"state": "error", "msg": str(e)})
            time.sleep(interval)
