"""Parser do protocolo Adalight (stream serial de LEDs RGB)."""

MAGIC = b"Ada"


class AdalightParser:
    def __init__(self):
        self._buf = bytearray()

    def feed(self, data):
        self._buf.extend(data)
        frames = []
        while True:
            frame = self._try_extract()
            if frame is None:
                break
            if frame:  # frame válido (lista não-vazia)
                frames.append(frame)
        return frames

    def _try_extract(self):
        buf = self._buf
        idx = buf.find(MAGIC)
        if idx == -1:
            # mantém só o final que pode ser começo de "Ada"
            if len(buf) > 2:
                del buf[:-2]
            return None
        if idx > 0:
            del buf[:idx]  # descarta lixo antes do header
        if len(buf) < 6:
            return None  # header incompleto
        hi, lo, chk = buf[3], buf[4], buf[5]
        if (hi ^ lo ^ 0x55) != chk:
            del buf[:3]  # checksum ruim: pula este "Ada" e ressincroniza
            return []
        count = (hi << 8) + lo
        n_leds = count + 1
        total = 6 + n_leds * 3
        if len(buf) < total:
            return None  # corpo incompleto: espera mais bytes
        body = buf[6:total]
        del buf[:total]
        return [(body[i], body[i + 1], body[i + 2]) for i in range(0, len(body), 3)]
