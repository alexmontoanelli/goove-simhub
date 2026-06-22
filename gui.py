"""Janela tkinter: configura, controla e mostra status do bridge."""

import tkinter as tk
from tkinter import messagebox, ttk

import appconfig
import discovery_dialog
import govee_lan_core as govee
from engine import Engine

try:
    from serial.tools import list_ports
except Exception:  # pyserial ausente em dev
    list_ports = None


class App:
    def __init__(self, root):
        self.root = root
        root.title("Adalight → Govee Bridge")
        self.cfg = appconfig.load()
        self.engine = None
        self._test_job = None  # job do ciclo de cores (None = parado)

        frm = ttk.Frame(root, padding=12)
        frm.grid(sticky="nsew")

        # Serial
        ttk.Label(frm, text="Porta COM:").grid(row=0, column=0, sticky="w")
        self.com = ttk.Combobox(frm, values=self._ports(), width=18)
        self.com.set(self.cfg["serial"]["port"])
        self.com.grid(row=0, column=1, sticky="w")
        ttk.Button(frm, text="Atualizar", command=self._refresh_ports).grid(row=0, column=2)

        ttk.Label(frm, text="Baud:").grid(row=1, column=0, sticky="w")
        self.baud = ttk.Entry(frm, width=20)
        self.baud.insert(0, str(self.cfg["serial"]["baud"]))
        self.baud.grid(row=1, column=1, sticky="w")

        # Govee
        ttk.Label(frm, text="Govee IP:").grid(row=2, column=0, sticky="w")
        self.ip = ttk.Entry(frm, width=20)
        self.ip.insert(0, self.cfg["govee"]["ip"])
        self.ip.grid(row=2, column=1, sticky="w")
        self.discover_btn = ttk.Button(frm, text="Descobrir", command=self._discover)
        self.discover_btn.grid(row=2, column=2)

        # Render
        ttk.Label(frm, text="Redução:").grid(row=3, column=0, sticky="w")
        self.reduce = ttk.Combobox(frm, values=["average", "dominant"], width=18)
        self.reduce.set(self.cfg["render"]["reduce"])
        self.reduce.grid(row=3, column=1, sticky="w")

        ttk.Label(frm, text="Taxa (Hz):").grid(row=4, column=0, sticky="w")
        self.rate = ttk.Spinbox(frm, from_=1, to=30, width=18)
        self.rate.set(self.cfg["render"]["rate_hz"])
        self.rate.grid(row=4, column=1, sticky="w")

        ttk.Label(frm, text="Brilho:").grid(row=5, column=0, sticky="w")
        self.brightness = tk.IntVar(value=self.cfg["render"].get("brightness", 100))
        ttk.Scale(
            frm, from_=0, to=100, orient="horizontal", variable=self.brightness,
            command=self._on_brightness,
        ).grid(row=5, column=1, sticky="we")

        self.black = tk.BooleanVar(value=self.cfg["render"]["black_off"])
        ttk.Checkbutton(frm, text="Desligar no preto", variable=self.black).grid(
            row=6, column=1, sticky="w"
        )

        # Controle
        ttk.Button(frm, text="Salvar", command=self._save).grid(row=7, column=0, pady=8)
        self.toggle = ttk.Button(frm, text="Iniciar", command=self._toggle)
        self.toggle.grid(row=7, column=1, pady=8, sticky="w")
        self.test_btn = ttk.Button(frm, text="Testar cor", command=self._test_color)
        self.test_btn.grid(row=7, column=2, pady=8)
        ttk.Button(frm, text="Ligar", command=self._turn_on).grid(row=7, column=3, pady=8)
        ttk.Button(frm, text="Desligar", command=self._turn_off).grid(row=7, column=4, pady=8)

        self.status = ttk.Label(frm, text="parado")
        self.status.grid(row=8, column=0, columnspan=3, sticky="w")

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _ports(self):
        if not list_ports:
            return []
        return [p.device for p in list_ports.comports()]

    def _refresh_ports(self):
        self.com["values"] = self._ports()

    def _discover(self):
        ip = discovery_dialog.select_device(self.root)
        if ip:
            self.ip.delete(0, tk.END)
            self.ip.insert(0, ip)
            self.status.config(text=f"selecionado: {ip}")

    def _on_brightness(self, _value):
        if self.engine:
            self.engine.set_brightness(self.brightness.get())

    def _resolve_ip(self):
        ip = self.ip.get().strip()
        if ip and ip != "auto":
            return ip
        devs = govee.lan_discover()
        return devs[0]["ip"] if devs else None

    # paleta percorrida pelo teste de cores
    _TEST_COLORS = [
        (255, 0, 0), (0, 255, 0), (0, 0, 255),
        (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 255, 255),
    ]

    def _test_color(self):
        # toggle: se já está ciclando, para; senão começa o ciclo de cores
        if self._test_job is not None:
            self.root.after_cancel(self._test_job)
            self._test_job = None
            self.test_btn.config(text="Testar cor")
            self.status.config(text="teste parado")
            return
        ip = self._resolve_ip()
        if not ip:
            messagebox.showwarning("Testar cor", "Govee não encontrada. Defina o IP.")
            return
        self._test_ip = ip
        self._test_idx = 0
        try:
            govee.send_command(ip, "turn", {"value": 1})
            govee.send_command(ip, "brightness", {"value": int(self.brightness.get())})
        except Exception as e:
            messagebox.showerror("Testar cor", str(e))
            return
        self.test_btn.config(text="Parar teste")
        self._cycle_color()

    def _cycle_color(self):
        r, g, b = self._TEST_COLORS[self._test_idx % len(self._TEST_COLORS)]
        try:
            govee.send_command(
                self._test_ip, "colorwc",
                {"color": {"r": r, "g": g, "b": b}, "colorTemInKelvin": 0},
            )
            self.status.config(text=f"teste: ({r},{g},{b})")
        except Exception as e:
            self.status.config(text=f"erro teste: {e}")
        self._test_idx += 1
        self._test_job = self.root.after(800, self._cycle_color)

    def _turn_on(self):
        # turn on sozinho pode acender numa cor quase preta (parece apagada);
        # então acende com brilho + branco visível.
        ip = self._resolve_ip()
        if not ip:
            messagebox.showwarning("Ligar", "Govee não encontrada. Defina o IP.")
            return
        try:
            govee.send_command(ip, "turn", {"value": 1})
            govee.send_command(ip, "brightness", {"value": int(self.brightness.get())})
            govee.send_command(
                ip, "colorwc", {"color": {"r": 255, "g": 255, "b": 255}, "colorTemInKelvin": 0}
            )
            self.status.config(text=f"ligado (branco) -> {ip}")
        except Exception as e:
            messagebox.showerror("Ligar", str(e))

    def _turn_off(self):
        ip = self._resolve_ip()
        if not ip:
            messagebox.showwarning("Desligar", "Govee não encontrada. Defina o IP.")
            return
        try:
            govee.send_command(ip, "turn", {"value": 0})
            self.status.config(text=f"desligado -> {ip}")
        except Exception as e:
            messagebox.showerror("Desligar", str(e))

    def _collect(self):
        self.cfg["serial"]["port"] = self.com.get()
        self.cfg["serial"]["baud"] = int(self.baud.get())
        self.cfg["govee"]["ip"] = self.ip.get().strip()
        self.cfg["render"]["reduce"] = self.reduce.get()
        self.cfg["render"]["rate_hz"] = int(self.rate.get())
        self.cfg["render"]["black_off"] = bool(self.black.get())
        self.cfg["render"]["brightness"] = int(self.brightness.get())

    def _save(self):
        self._collect()
        appconfig.save(self.cfg)
        messagebox.showinfo("Config", f"Salvo em\n{appconfig.config_path()}")

    def _set_status(self, s):
        text = s.get("state", "")
        if s.get("color"):
            text += f"  cor={s['color']}"
        if s.get("msg"):
            text += f"  {s['msg']}"
        self.root.after(0, lambda: self.status.config(text=text))

    def _toggle(self):
        if self.engine:
            self.engine.stop()
            self.engine = None
            self.toggle.config(text="Iniciar")
            return
        self._collect()
        appconfig.save(self.cfg)
        self.engine = Engine(self.cfg, on_status=self._set_status)
        if self.engine.start():
            self.toggle.config(text="Parar")
        else:
            self.engine = None

    def _on_close(self):
        if self._test_job is not None:
            self.root.after_cancel(self._test_job)
            self._test_job = None
        # IP conhecido sem disparar discovery (que travaria o fechamento)
        ip = self.engine._ip if self.engine else None
        if self.engine:
            self.engine.stop()
            self.engine = None
        if not ip:
            val = self.ip.get().strip()
            if val and val != "auto":
                ip = val
        if ip:
            try:
                govee.send_command(ip, "turn", {"value": 0})
            except Exception:
                pass
        self.root.destroy()
