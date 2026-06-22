"""Entrypoint do EXE. Abre a GUI; modos de diagnóstico via CLI."""

import sys

import govee_lan_core as govee


def _cli():
    if "--discover" in sys.argv:
        for d in govee.lan_discover():
            print(d)
        return True
    if "--list-com" in sys.argv:
        try:
            from serial.tools import list_ports

            for p in list_ports.comports():
                print(p.device, "-", p.description)
        except Exception as e:
            print("pyserial ausente:", e)
        return True
    return False


def main():
    if _cli():
        return
    import tkinter as tk
    from tkinter import messagebox

    from gui import App

    root = tk.Tk()
    try:
        App(root)
        root.mainloop()
    except Exception as e:
        # Última linha de defesa: não fechar com tela de crash crua.
        try:
            messagebox.showerror("Adalight → Govee Bridge", f"Erro inesperado:\n{e}")
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
