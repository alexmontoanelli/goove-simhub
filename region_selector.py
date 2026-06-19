"""Overlay de seleção de região da tela (monitor principal)."""

import tkinter as tk


def rect_from_drag(x0, y0, x1, y1):
    """Normaliza dois cantos arrastados em (left, top, width, height)."""
    left, right = sorted((int(x0), int(x1)))
    top, bottom = sorted((int(y0), int(y1)))
    return (left, top, right - left, bottom - top)


def select_region(parent=None):
    """Abre overlay translúcido; retorna (left, top, width, height) ou None."""
    top = tk.Toplevel(parent) if parent else tk.Tk()
    top.attributes("-fullscreen", True)
    top.attributes("-alpha", 0.3)
    top.configure(bg="black", cursor="cross")
    top.attributes("-topmost", True)

    canvas = tk.Canvas(top, highlightthickness=0, bg="gray20")
    canvas.pack(fill="both", expand=True)

    state = {"x0": 0, "y0": 0, "rect": None, "result": None}

    def on_press(e):
        state["x0"], state["y0"] = e.x_root, e.y_root
        state["rect"] = canvas.create_rectangle(
            e.x, e.y, e.x, e.y, outline="white", width=2
        )

    def on_drag(e):
        if state["rect"] is not None:
            x0 = state["x0"] - top.winfo_rootx()
            y0 = state["y0"] - top.winfo_rooty()
            canvas.coords(state["rect"], x0, y0, e.x, e.y)

    def on_release(e):
        state["result"] = rect_from_drag(state["x0"], state["y0"], e.x_root, e.y_root)
        top.destroy()

    def on_cancel(_e):
        state["result"] = None
        top.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    top.bind("<Escape>", on_cancel)
    top.focus_force()
    top.wait_window()
    res = state["result"]
    if res and res[2] > 0 and res[3] > 0:
        return res
    return None
