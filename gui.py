"""Tkinter window: configure, control and show the bridge status."""

import tkinter as tk
from tkinter import messagebox, ttk

import appconfig
import autostart
import discovery_dialog
import govee_lan_core as govee
import tray
from engine import Engine

try:
    from serial.tools import list_ports
except Exception:  # pyserial missing in dev
    list_ports = None


class App:
    def __init__(self, root):
        self.root = root
        root.title("Adalight → Govee Bridge")
        self.cfg = appconfig.load()
        self.engine = None
        self._test_job = None  # color-cycle job (None = stopped)
        self._tray = None  # tray icon while minimized

        frm = ttk.Frame(root, padding=12)
        frm.grid(sticky="nsew")

        # Serial
        ttk.Label(frm, text="COM port:").grid(row=0, column=0, sticky="w")
        self.com = ttk.Combobox(frm, values=self._ports(), width=18)
        self.com.set(self.cfg["serial"]["port"])
        self.com.grid(row=0, column=1, sticky="w")
        ttk.Button(frm, text="Refresh", command=self._refresh_ports).grid(row=0, column=2)

        ttk.Label(frm, text="Baud:").grid(row=1, column=0, sticky="w")
        self.baud = ttk.Entry(frm, width=20)
        self.baud.insert(0, str(self.cfg["serial"]["baud"]))
        self.baud.grid(row=1, column=1, sticky="w")

        # Govee
        ttk.Label(frm, text="Govee IP:").grid(row=2, column=0, sticky="w")
        self.ip = ttk.Entry(frm, width=20)
        self.ip.insert(0, self.cfg["govee"]["ip"])
        self.ip.grid(row=2, column=1, sticky="w")
        self.discover_btn = ttk.Button(frm, text="Discover", command=self._discover)
        self.discover_btn.grid(row=2, column=2)
        self.test_btn = ttk.Button(frm, text="Test color", command=self._test_color)
        self.test_btn.grid(row=2, column=3)

        # Render
        ttk.Label(frm, text="Reduce:").grid(row=3, column=0, sticky="w")
        self.reduce = ttk.Combobox(frm, values=["average", "dominant"], width=18)
        self.reduce.set(self.cfg["render"]["reduce"])
        self.reduce.grid(row=3, column=1, sticky="w")

        ttk.Label(frm, text="Rate (Hz):").grid(row=4, column=0, sticky="w")
        self.rate = ttk.Spinbox(frm, from_=1, to=30, width=18)
        self.rate.set(self.cfg["render"]["rate_hz"])
        self.rate.grid(row=4, column=1, sticky="w")

        ttk.Label(frm, text="Brightness:").grid(row=5, column=0, sticky="w")
        self.brightness = tk.IntVar(value=self.cfg["render"].get("brightness", 100))
        ttk.Scale(
            frm, from_=0, to=100, orient="horizontal", variable=self.brightness,
            command=self._on_brightness,
        ).grid(row=5, column=1, sticky="we")

        self.black = tk.BooleanVar(value=self.cfg["render"]["black_off"])
        ttk.Checkbutton(frm, text="Turn off on black", variable=self.black).grid(
            row=6, column=1, sticky="w"
        )

        # Controls
        ttk.Button(frm, text="Save", command=self._save).grid(row=7, column=0, pady=8)
        self.toggle = ttk.Button(frm, text="Start", command=self._toggle)
        self.toggle.grid(row=7, column=1, pady=8, sticky="w")
        ttk.Button(frm, text="Turn on", command=self._turn_on).grid(row=7, column=2, pady=8)
        ttk.Button(frm, text="Turn off", command=self._turn_off).grid(row=7, column=3, pady=8)

        self.status = ttk.Label(frm, text="stopped")
        self.status.grid(row=8, column=0, columnspan=4, sticky="w")

        # Startup options
        su = self.cfg["startup"]
        self.start_with_windows = tk.BooleanVar(value=bool(su["start_with_windows"]))
        self.minimize_to_tray = tk.BooleanVar(value=bool(su["minimize_to_tray"]))
        self.start_minimized = tk.BooleanVar(value=bool(su["start_minimized"]))
        self.autostart_bridge = tk.BooleanVar(value=bool(su["autostart_bridge"]))

        opts = ttk.LabelFrame(frm, text="Startup", padding=8)
        opts.grid(row=9, column=0, columnspan=4, sticky="we", pady=(8, 0))
        ttk.Checkbutton(
            opts, text="Start with Windows", variable=self.start_with_windows
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            opts, text="Minimize to tray", variable=self.minimize_to_tray
        ).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(
            opts, text="Start minimized", variable=self.start_minimized
        ).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(
            opts, text="Auto-start bridge", variable=self.autostart_bridge
        ).grid(row=1, column=1, sticky="w")

        root.protocol("WM_DELETE_WINDOW", self._on_close)
        root.bind("<Unmap>", self._on_unmap)

        # Apply launch behavior once the window is up
        if self.autostart_bridge.get():
            root.after(500, self._toggle)
        if self.start_minimized.get():
            root.after(200, self._minimize_to_tray)

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
            self.status.config(text=f"selected: {ip}")

    def _on_brightness(self, _value):
        if self.engine:
            self.engine.set_brightness(self.brightness.get())

    def _resolve_ip(self):
        ip = self.ip.get().strip()
        if ip and ip != "auto":
            return ip
        devs = govee.lan_discover()
        return devs[0]["ip"] if devs else None

    # palette walked by the color test
    _TEST_COLORS = [
        (255, 0, 0), (0, 255, 0), (0, 0, 255),
        (255, 255, 0), (0, 255, 255), (255, 0, 255), (255, 255, 255),
    ]

    def _test_color(self):
        # toggle: if already cycling, stop; otherwise start the color cycle
        if self._test_job is not None:
            self.root.after_cancel(self._test_job)
            self._test_job = None
            self.test_btn.config(text="Test color")
            self.status.config(text="test stopped")
            return
        ip = self._resolve_ip()
        if not ip:
            messagebox.showwarning("Test color", "Govee not found. Set the IP.")
            return
        self._test_ip = ip
        self._test_idx = 0
        try:
            govee.send_command(ip, "turn", {"value": 1})
            govee.send_command(ip, "brightness", {"value": int(self.brightness.get())})
        except Exception as e:
            messagebox.showerror("Test color", str(e))
            return
        self.test_btn.config(text="Stop test")
        self._cycle_color()

    def _cycle_color(self):
        r, g, b = self._TEST_COLORS[self._test_idx % len(self._TEST_COLORS)]
        try:
            govee.send_command(
                self._test_ip, "colorwc",
                {"color": {"r": r, "g": g, "b": b}, "colorTemInKelvin": 0},
            )
            self.status.config(text=f"test: ({r},{g},{b})")
        except Exception as e:
            self.status.config(text=f"test error: {e}")
        self._test_idx += 1
        self._test_job = self.root.after(800, self._cycle_color)

    def _turn_on(self):
        # turn on alone may light a near-black color (looks off); so light up
        # with brightness + visible white.
        ip = self._resolve_ip()
        if not ip:
            messagebox.showwarning("Turn on", "Govee not found. Set the IP.")
            return
        try:
            govee.send_command(ip, "turn", {"value": 1})
            govee.send_command(ip, "brightness", {"value": int(self.brightness.get())})
            govee.send_command(
                ip, "colorwc", {"color": {"r": 255, "g": 255, "b": 255}, "colorTemInKelvin": 0}
            )
            self.status.config(text=f"on (white) -> {ip}")
        except Exception as e:
            messagebox.showerror("Turn on", str(e))

    def _turn_off(self):
        ip = self._resolve_ip()
        if not ip:
            messagebox.showwarning("Turn off", "Govee not found. Set the IP.")
            return
        try:
            govee.send_command(ip, "turn", {"value": 0})
            self.status.config(text=f"off -> {ip}")
        except Exception as e:
            messagebox.showerror("Turn off", str(e))

    def _collect(self):
        self.cfg["serial"]["port"] = self.com.get()
        self.cfg["serial"]["baud"] = int(self.baud.get())
        self.cfg["govee"]["ip"] = self.ip.get().strip()
        self.cfg["render"]["reduce"] = self.reduce.get()
        self.cfg["render"]["rate_hz"] = int(self.rate.get())
        self.cfg["render"]["black_off"] = bool(self.black.get())
        self.cfg["render"]["brightness"] = int(self.brightness.get())
        self.cfg["startup"]["start_with_windows"] = bool(self.start_with_windows.get())
        self.cfg["startup"]["minimize_to_tray"] = bool(self.minimize_to_tray.get())
        self.cfg["startup"]["start_minimized"] = bool(self.start_minimized.get())
        self.cfg["startup"]["autostart_bridge"] = bool(self.autostart_bridge.get())

    def _save(self):
        self._collect()
        appconfig.save(self.cfg)
        autostart.apply(self.start_with_windows.get())  # no-op off Windows
        messagebox.showinfo("Config", f"Saved to\n{appconfig.config_path()}")

    def _set_status(self, s):
        text = s.get("state", "")
        if s.get("color"):
            text += f"  color={s['color']}"
        if s.get("msg"):
            text += f"  {s['msg']}"
        self.root.after(0, lambda: self.status.config(text=text))

    def _toggle(self):
        if self.engine:
            self.engine.stop()
            self.engine = None
            self.toggle.config(text="Start")
            return
        self._collect()
        appconfig.save(self.cfg)
        self.engine = Engine(self.cfg, on_status=self._set_status)
        if self.engine.start():
            self.toggle.config(text="Stop")
        else:
            self.engine = None

    # --- system tray ---

    def _on_unmap(self, _event):
        if self.minimize_to_tray.get() and self.root.state() == "iconic":
            self._minimize_to_tray()

    def _minimize_to_tray(self):
        if self._tray is None:
            self._tray = tray.make_icon(
                on_show=lambda: self.root.after(0, self._show_window),
                on_turn_on=lambda: self.root.after(0, self._turn_on),
                on_turn_off=lambda: self.root.after(0, self._turn_off),
                on_quit=lambda: self.root.after(0, self._tray_quit),
            )
            tray.run_in_thread(self._tray)
        self.root.withdraw()

    def _show_window(self):
        self.root.deiconify()
        if self._tray is not None:
            self._tray.stop()
            self._tray = None

    def _tray_quit(self):
        if self._tray is not None:
            self._tray.stop()
            self._tray = None
        self._on_close()

    def _on_close(self):
        if self._test_job is not None:
            self.root.after_cancel(self._test_job)
            self._test_job = None
        if self._tray is not None:
            self._tray.stop()
            self._tray = None
        # known IP without triggering discovery (which would block closing)
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
