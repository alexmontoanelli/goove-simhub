"""Janela tkinter: configura, controla e mostra status do bridge."""

import tkinter as tk
from tkinter import colorchooser, messagebox, ttk

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
        ttk.Button(frm, text="Testar cor", command=self._test_color).grid(row=7, column=2, pady=8)

        self.status = ttk.Label(frm, text="parado")
        self.status.grid(row=8, column=0, columnspan=3, sticky="w")

        # Fonte (modo)
        ttk.Label(frm, text="Fonte:").grid(row=9, column=0, sticky="w")
        self.source = ttk.Combobox(
            frm, values=["serial", "screen"], width=18, state="readonly"
        )
        self.source.set(self.cfg["mode"]["source"])
        self.source.grid(row=9, column=1, sticky="w")
        self.source.bind("<<ComboboxSelected>>", lambda _e: self._apply_source())
        self.area_btn = ttk.Button(frm, text="Selecionar área", command=self._select_area)
        self.area_btn.grid(row=9, column=2)
        self._apply_source()

        root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_source(self):
        screen = self.source.get() == "screen"
        self.com.config(state="disabled" if screen else "normal")
        self.baud.config(state="disabled" if screen else "normal")
        self.area_btn.config(state="normal" if screen else "disabled")

    def _select_area(self):
        import region_selector

        region = region_selector.select_region(self.root)
        if region:
            left, top, w, h = region
            self.cfg["capture"].update({"left": left, "top": top, "width": w, "height": h})
            self.status.config(text=f"área: {left},{top} {w}x{h}")

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

    def _test_color(self):
        rgb = colorchooser.askcolor(title="Testar cor na Govee")[0]
        if not rgb:
            return
        ip = self._resolve_ip()
        if not ip:
            messagebox.showwarning("Testar cor", "Govee não encontrada. Defina o IP.")
            return
        r, g, b = (int(c) for c in rgb)
        try:
            govee.send_command(ip, "turn", {"value": 1})
            govee.send_command(ip, "brightness", {"value": int(self.brightness.get())})
            govee.send_command(
                ip, "colorwc", {"color": {"r": r, "g": g, "b": b}, "colorTemInKelvin": 0}
            )
            self.status.config(text=f"teste enviado: ({r},{g},{b}) -> {ip}")
        except Exception as e:
            messagebox.showerror("Testar cor", str(e))

    def _collect(self):
        self.cfg["serial"]["port"] = self.com.get()
        self.cfg["serial"]["baud"] = int(self.baud.get())
        self.cfg["govee"]["ip"] = self.ip.get().strip()
        self.cfg["render"]["reduce"] = self.reduce.get()
        self.cfg["render"]["rate_hz"] = int(self.rate.get())
        self.cfg["render"]["black_off"] = bool(self.black.get())
        self.cfg["render"]["brightness"] = int(self.brightness.get())
        self.cfg["mode"]["source"] = self.source.get()

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
        if self.engine:
            self.engine.stop()
        self.root.destroy()
