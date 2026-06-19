"""Janela de descoberta contínua de dispositivos Govee na LAN."""

import threading
import tkinter as tk
from tkinter import ttk

import govee_lan_core as govee


def merge_devices(existing, new):
    """Une listas de dispositivos, dedup por IP, preservando a ordem/1ª vista."""
    seen = {d["ip"] for d in existing if d.get("ip")}
    merged = list(existing)
    for d in new:
        ip = d.get("ip")
        if ip and ip not in seen:
            seen.add(ip)
            merged.append(d)
    return merged


def _label(dev):
    parts = [dev.get("ip", "?")]
    if dev.get("sku"):
        parts.append(dev["sku"])
    if dev.get("device"):
        parts.append(dev["device"])
    return " — ".join(parts)


def select_device(parent=None, discover_fn=None):
    """Abre a janela; busca em loop e retorna o IP escolhido ou None."""
    discover_fn = discover_fn or (lambda: govee.lan_discover(timeout=3.0))
    win = tk.Toplevel(parent) if parent else tk.Tk()
    win.title("Descobrir dispositivos Govee")
    win.geometry("360x240")

    frm = ttk.Frame(win, padding=10)
    frm.pack(fill="both", expand=True)

    status = ttk.Label(frm, text="Buscando…")
    status.pack(anchor="w")

    listbox = tk.Listbox(frm, height=8)
    listbox.pack(fill="both", expand=True, pady=6)

    state = {"devices": [], "result": None}
    stop = threading.Event()

    def refresh(devices):
        if stop.is_set():
            return
        state["devices"] = devices
        listbox.delete(0, tk.END)
        for d in devices:
            listbox.insert(tk.END, _label(d))
        status.config(text=f"{len(devices)} encontrado(s)" if devices else "Buscando…")

    def worker():
        while not stop.is_set():
            try:
                found = discover_fn()
            except Exception:
                found = []
            merged = merge_devices(state["devices"], found)
            win.after(0, lambda m=merged: refresh(m))

    def choose():
        sel = listbox.curselection()
        if not sel:
            return
        state["result"] = state["devices"][sel[0]]["ip"]
        close()

    def close():
        stop.set()
        win.destroy()

    listbox.bind("<Double-Button-1>", lambda _e: choose())
    btns = ttk.Frame(frm)
    btns.pack(fill="x")
    ttk.Button(btns, text="Selecionar", command=choose).pack(side="left")
    ttk.Button(btns, text="Fechar", command=close).pack(side="right")
    win.protocol("WM_DELETE_WINDOW", close)

    threading.Thread(target=worker, daemon=True).start()
    win.focus_force()
    win.wait_window()
    return state["result"]
