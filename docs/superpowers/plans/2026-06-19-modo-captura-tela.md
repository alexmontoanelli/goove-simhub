# Modo Standalone (captura de tela) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adicionar um modo standalone que captura uma região da tela como fonte de cor (alternativa à serial Adalight), com seletor visual de área.

**Architecture:** A `Engine` já separa fonte de cor (thread leitora → `self._color`) de envio (thread sender → Govee). Tornamos a fonte plugável: `_reader_serial` (atual) ou `_reader_screen` (nova, via `mss`). O sender, `reduce.py`, `black_off`, brilho e resolução de IP não mudam. Um novo `capture.py` faz a captura+subamostragem; um `region_selector.py` faz o overlay de seleção; a GUI ganha um toggle de fonte.

**Tech Stack:** Python 3, tkinter, `mss` (captura), `unittest` (testes), stdlib UDP (Govee).

## Global Constraints

- **Sem numpy.** Subamostragem em Python puro.
- **`mss` importado de forma preguiçosa** (dentro de funções/métodos), nunca no topo do módulo — os testes das funções puras devem rodar sem `mss` instalado.
- **Apenas monitor principal.** Sem multi-monitor.
- **Subamostragem fixa 32×32 = 1024 pixels**, custo constante.
- **1 cor única** enviada à Govee (sem zonas).
- Testes seguem o padrão existente: `unittest`, arquivo `test_adalight.py`, rodados com `.venv/bin/python -m unittest -v`.
- Config em `.ini` via `appconfig.py`; sentinela `-1` = "não definido".

---

### Task 1: Config — seções `[mode]` e `[capture]`

**Files:**
- Modify: `appconfig.py` (DEFAULTS)
- Test: `test_adalight.py` (nova TestCase)

**Interfaces:**
- Consumes: `appconfig.load`, `appconfig.save` (já existem).
- Produces: `cfg["mode"]["source"]` (`"serial"|"screen"`); `cfg["capture"]` com `left/top/width/height` (int, `-1` = indefinido).

- [ ] **Step 1: Write the failing test**

Adicione ao final de `test_adalight.py`:

```python
class TestModeCaptureConfig(unittest.TestCase):
    def test_defaults_have_mode_and_capture(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.ini")
            cfg = appconfig.load(path)  # arquivo inexistente => defaults
            self.assertEqual(cfg["mode"]["source"], "serial")
            self.assertEqual(cfg["capture"]["left"], -1)
            self.assertEqual(cfg["capture"]["top"], -1)
            self.assertEqual(cfg["capture"]["width"], -1)
            self.assertEqual(cfg["capture"]["height"], -1)

    def test_roundtrip_screen_source(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "config.ini")
            cfg = appconfig.load(path)
            cfg["mode"]["source"] = "screen"
            cfg["capture"]["left"] = 100
            cfg["capture"]["width"] = 640
            appconfig.save(cfg, path)
            cfg2 = appconfig.load(path)
            self.assertEqual(cfg2["mode"]["source"], "screen")
            self.assertEqual(cfg2["capture"]["left"], 100)
            self.assertEqual(cfg2["capture"]["width"], 640)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_adalight.TestModeCaptureConfig -v`
Expected: FAIL com `KeyError: 'mode'`.

- [ ] **Step 3: Write minimal implementation**

Em `appconfig.py`, adicione ao dict `DEFAULTS` (após a seção `render`):

```python
    "mode": {"source": "serial"},
    "capture": {"left": -1, "top": -1, "width": -1, "height": -1},
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_adalight.TestModeCaptureConfig -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add appconfig.py test_adalight.py
git commit -m "feat: config para modo de fonte e regiao de captura"
```

---

### Task 2: `capture.py` — subamostragem e região padrão (funções puras)

**Files:**
- Create: `capture.py`
- Test: `test_capture.py`

**Interfaces:**
- Produces:
  - `default_region(monitor) -> (left, top, width, height)` — 50% central. `monitor` é um dict no formato do `mss` (`{"left","top","width","height"}`).
  - `subsample(bgra, width, height, grid=32) -> list[(r,g,b)]` — amostra `grid×grid` pontos do buffer BGRA (4 bytes/pixel, ordem B,G,R,A) e devolve RGB.

- [ ] **Step 1: Write the failing test**

Crie `test_capture.py`:

```python
import unittest

import capture


class TestDefaultRegion(unittest.TestCase):
    def test_center_50_percent(self):
        mon = {"left": 0, "top": 0, "width": 1920, "height": 1080}
        left, top, w, h = capture.default_region(mon)
        self.assertEqual((w, h), (960, 540))
        self.assertEqual((left, top), (480, 270))

    def test_respects_monitor_offset(self):
        mon = {"left": 100, "top": 200, "width": 800, "height": 600}
        left, top, w, h = capture.default_region(mon)
        self.assertEqual((w, h), (400, 300))
        self.assertEqual((left, top), (300, 350))


class TestSubsample(unittest.TestCase):
    def _solid_bgra(self, width, height, rgb):
        r, g, b = rgb
        px = bytes([b, g, r, 255])
        return px * (width * height)

    def test_solid_color_returns_that_color(self):
        bgra = self._solid_bgra(64, 64, (10, 20, 30))
        pixels = capture.subsample(bgra, 64, 64, grid=8)
        self.assertEqual(len(pixels), 64)  # 8x8
        self.assertTrue(all(p == (10, 20, 30) for p in pixels))

    def test_bgra_to_rgb_order(self):
        # 1x1 imagem: B=1, G=2, R=3
        bgra = bytes([1, 2, 3, 255])
        pixels = capture.subsample(bgra, 1, 1, grid=1)
        self.assertEqual(pixels, [(3, 2, 1)])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_capture -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'capture'`.

- [ ] **Step 3: Write minimal implementation**

Crie `capture.py` (note: `mss` NÃO é importado no topo):

```python
"""Captura de uma região da tela e subamostragem para lista de pixels RGB."""

GRID = 32  # 32x32 = 1024 amostras, custo constante


def default_region(monitor):
    """50% central do monitor (dict do mss: left/top/width/height)."""
    w = monitor["width"] // 2
    h = monitor["height"] // 2
    left = monitor["left"] + (monitor["width"] - w) // 2
    top = monitor["top"] + (monitor["height"] - h) // 2
    return (left, top, w, h)


def subsample(bgra, width, height, grid=GRID):
    """Amostra grid×grid pontos do buffer BGRA (4 bytes/pixel) -> lista RGB."""
    if width <= 0 or height <= 0:
        return []
    cols = min(grid, width)
    rows = min(grid, height)
    pixels = []
    for gy in range(rows):
        y = (gy * height) // rows
        row_off = y * width * 4
        for gx in range(cols):
            x = (gx * width) // cols
            i = row_off + x * 4
            b, g, r = bgra[i], bgra[i + 1], bgra[i + 2]
            pixels.append((r, g, b))
    return pixels
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_capture -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add capture.py test_capture.py
git commit -m "feat: capture.py com default_region e subsample (BGRA->RGB)"
```

---

### Task 3: `capture.py` — `ScreenSampler` (integração com mss)

**Files:**
- Modify: `capture.py`
- Test: `test_capture.py` (com mss fake injetado)

**Interfaces:**
- Consumes: `subsample` (Task 2).
- Produces:
  - `ScreenSampler(region=None)` — mantém 1 instância de `mss.mss()` (criada na 1ª captura, lazy).
  - `.set_region((left, top, width, height))`
  - `.sample() -> list[(r,g,b)]` — captura a região atual e devolve pixels RGB. Se `region` for `None`, usa `default_region` do monitor principal.
  - `primary_monitor() -> dict` — geometria do monitor principal via mss.

O `ScreenSampler` recebe a captura por um atributo injetável `_grab(region) -> (bgra_bytes, width, height)` para permitir teste sem `mss`.

- [ ] **Step 1: Write the failing test**

Adicione a `test_capture.py`:

```python
class TestScreenSampler(unittest.TestCase):
    def test_sample_uses_grab_and_subsamples(self):
        s = capture.ScreenSampler(region=(0, 0, 4, 4))
        # injeta um grab fake: imagem 4x4 verde (R=0,G=255,B=0)
        bgra = bytes([0, 255, 0, 255]) * 16

        def fake_grab(region):
            self.assertEqual(region, (0, 0, 4, 4))
            return (bgra, 4, 4)

        s._grab = fake_grab
        pixels = s.sample()
        self.assertTrue(pixels)
        self.assertTrue(all(p == (0, 255, 0) for p in pixels))

    def test_set_region(self):
        s = capture.ScreenSampler()
        s.set_region((1, 2, 3, 4))
        self.assertEqual(s.region, (1, 2, 3, 4))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_capture.TestScreenSampler -v`
Expected: FAIL com `AttributeError: module 'capture' has no attribute 'ScreenSampler'`.

- [ ] **Step 3: Write minimal implementation**

Adicione a `capture.py`:

```python
class ScreenSampler:
    def __init__(self, region=None):
        self.region = region
        self._mss = None

    def _ensure_mss(self):
        if self._mss is None:
            import mss  # lazy: só quando captura de verdade

            self._mss = mss.mss()
        return self._mss

    def primary_monitor(self):
        sct = self._ensure_mss()
        # monitors[0] = virtual total; [1] = monitor principal
        mons = sct.monitors
        return mons[1] if len(mons) > 1 else mons[0]

    def set_region(self, region):
        self.region = region

    def _grab(self, region):
        sct = self._ensure_mss()
        left, top, width, height = region
        shot = sct.grab({"left": left, "top": top, "width": width, "height": height})
        return (bytes(shot.bgra), shot.width, shot.height)

    def sample(self):
        region = self.region
        if region is None:
            region = default_region(self.primary_monitor())
            self.region = region
        bgra, width, height = self._grab(region)
        return subsample(bgra, width, height)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_capture -v`
Expected: PASS (todas as classes de `test_capture`).

- [ ] **Step 5: Commit**

```bash
git add capture.py test_capture.py
git commit -m "feat: ScreenSampler com mss lazy e grab injetavel"
```

---

### Task 4: `engine.py` — fonte plugável (`_reader_screen`)

**Files:**
- Modify: `engine.py` (`start`, novo `_reader_screen`, helper de região)
- Test: `test_adalight.py` (nova TestCase com sampler fake)

**Interfaces:**
- Consumes: `cfg["mode"]["source"]`, `cfg["capture"]`, `capture.ScreenSampler`, `capture.default_region`, `reducer.average/dominant`.
- Produces: `Engine` que, no modo screen, alimenta `self._color` a partir do sampler. `Engine._resolve_region(sampler) -> (l,t,w,h)`.

- [ ] **Step 1: Write the failing test**

Adicione a `test_adalight.py`:

```python
class TestEngineScreenSource(unittest.TestCase):
    def _cfg(self):
        with tempfile.TemporaryDirectory() as d:
            return appconfig.load(os.path.join(d, "config.ini"))

    def test_resolve_region_uses_config_when_set(self):
        cfg = self._cfg()
        cfg["capture"].update({"left": 5, "top": 6, "width": 7, "height": 8})
        eng = engine.Engine(cfg)

        class FakeSampler:
            def primary_monitor(self):
                raise AssertionError("não deveria consultar o monitor")

        self.assertEqual(eng._resolve_region(FakeSampler()), (5, 6, 7, 8))

    def test_resolve_region_falls_back_to_default(self):
        cfg = self._cfg()  # capture = -1 (indefinido)
        eng = engine.Engine(cfg)

        class FakeSampler:
            def primary_monitor(self):
                return {"left": 0, "top": 0, "width": 1000, "height": 1000}

        self.assertEqual(eng._resolve_region(FakeSampler()), (250, 250, 500, 500))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_adalight.TestEngineScreenSource -v`
Expected: FAIL com `AttributeError: 'Engine' object has no attribute '_resolve_region'`.

- [ ] **Step 3: Write minimal implementation**

Em `engine.py`, adicione `import capture` no topo (junto dos outros imports) e os métodos/lógica abaixo.

Helper de região (método novo em `Engine`):

```python
    def _resolve_region(self, sampler):
        c = self.cfg["capture"]
        vals = (int(c["left"]), int(c["top"]), int(c["width"]), int(c["height"]))
        if vals[2] > 0 and vals[3] > 0:
            return vals
        return capture.default_region(sampler.primary_monitor())
```

Substitua o corpo de `start()` para escolher a fonte. A versão atual abre serial e inicia 2 threads; troque a parte da serial/reader por:

```python
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
```

Adicione `self._sampler = None` no `__init__` (junto de `self._serial = None`).

Novo método leitor de tela:

```python
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
```

- [ ] **Step 4: Run all tests**

Run: `.venv/bin/python -m unittest -v`
Expected: PASS em tudo (Adalight, config, capture, engine).

- [ ] **Step 5: Commit**

```bash
git add engine.py test_adalight.py
git commit -m "feat: engine com fonte plugavel (modo Tela via ScreenSampler)"
```

---

### Task 5: `region_selector.py` — cálculo de retângulo + overlay

**Files:**
- Create: `region_selector.py`
- Test: `test_capture.py` (cálculo puro do retângulo)

**Interfaces:**
- Produces:
  - `rect_from_drag(x0, y0, x1, y1) -> (left, top, width, height)` — normaliza dois cantos (pura, testável).
  - `select_region(parent=None) -> (left, top, width, height) | None` — overlay tkinter translúcido em tela cheia; arrasta retângulo; `Esc` cancela.

- [ ] **Step 1: Write the failing test**

Adicione a `test_capture.py`:

```python
import region_selector


class TestRectFromDrag(unittest.TestCase):
    def test_topleft_to_bottomright(self):
        self.assertEqual(region_selector.rect_from_drag(10, 20, 110, 220), (10, 20, 100, 200))

    def test_reversed_drag_normalizes(self):
        self.assertEqual(region_selector.rect_from_drag(110, 220, 10, 20), (10, 20, 100, 200))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest test_capture.TestRectFromDrag -v`
Expected: FAIL com `ModuleNotFoundError: No module named 'region_selector'`.

- [ ] **Step 3: Write minimal implementation**

Crie `region_selector.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest test_capture.TestRectFromDrag -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add region_selector.py test_capture.py
git commit -m "feat: seletor de regiao da tela (overlay + rect_from_drag)"
```

---

### Task 6: `gui.py` — toggle de fonte e botão "Selecionar área"

**Files:**
- Modify: `gui.py`

**Interfaces:**
- Consumes: `cfg["mode"]["source"]`, `cfg["capture"]`, `region_selector.select_region`.
- Produces: GUI com seletor de fonte; persiste `source` e `capture` em `_collect`.

Nota: este passo é majoritariamente UI; o teste é manual (smoke). Mantemos as mudanças pequenas e verificáveis abrindo a janela.

- [ ] **Step 1: Adicionar o seletor de fonte e o botão**

Em `gui.py`, dentro de `App.__init__`, após o bloco "Serial" (linha do botão "Atualizar"), insira um seletor de fonte ANTES dos campos serial — ou no topo do `frm`. Adicione:

```python
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
```

(Use uma `row` livre; ajuste os números de linha conforme o layout — o importante é existir o combobox `source`, o botão `area_btn`, e o status continuar na última linha.)

- [ ] **Step 2: Adicionar os métodos de apoio**

Adicione ao `App`:

```python
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
```

E chame `self._apply_source()` no fim do `__init__` para refletir o estado inicial.

- [ ] **Step 3: Persistir no `_collect`**

Em `App._collect`, adicione:

```python
        self.cfg["mode"]["source"] = self.source.get()
```

(O `cfg["capture"]` já é atualizado em `_select_area`; `appconfig.save` persiste ambos.)

- [ ] **Step 4: Smoke test manual**

Run: `.venv/bin/python -c "import tkinter as tk; from gui import App; r=tk.Tk(); App(r); r.update(); print('GUI ok'); r.destroy()"`
Expected: imprime `GUI ok` sem exceção.

- [ ] **Step 5: Commit**

```bash
git add gui.py
git commit -m "feat: GUI com toggle de fonte e selecao de area"
```

---

### Task 7: Dependências e build

**Files:**
- Modify: `requirements.txt`, `build.md`

**Interfaces:** nenhuma de código.

- [ ] **Step 1: Adicionar `mss` ao requirements**

`requirements.txt` passa a conter:

```
pyserial
mss
```

- [ ] **Step 2: Instalar e rodar a suíte completa**

Run: `.venv/bin/python -m pip install mss && .venv/bin/python -m unittest -v`
Expected: PASS em toda a suíte, agora com `mss` disponível.

- [ ] **Step 3: Atualizar o build**

Em `build.md`, garanta que o comando PyInstaller colete `mss` (ex.: adicionar `--hidden-import mss` / `--collect-all mss` ao comando de build documentado). Ajuste o texto para mencionar o novo modo Tela (standalone) e que não exige COM.

- [ ] **Step 4: Verificar captura real (manual, opcional)**

Run: `.venv/bin/python -c "import capture; s=capture.ScreenSampler(); print(len(s.sample()), 'amostras')"`
Expected: imprime `1024 amostras` (em ambiente com display).

- [ ] **Step 5: Commit**

```bash
git add requirements.txt build.md
git commit -m "build: adiciona mss e documenta modo Tela"
```

---

## Self-Review

**Spec coverage:**
- Toggle Serial/Tela → Task 4 (engine) + Task 6 (GUI). ✓
- mss / captura → Task 3, Task 7. ✓
- Monitor principal + região padrão 50% central → Task 2 (`default_region`), Task 4 (`_resolve_region`). ✓
- Subamostragem 32×32 → Task 2 (`subsample`, `GRID=32`). ✓
- Seletor de área (overlay, Esc cancela, salva no config) → Task 5 + Task 6. ✓
- Config `[mode]`/`[capture]` com sentinela -1 → Task 1. ✓
- Tratamento de erros (mss ausente, captura falha, região inválida) → Task 4 (ImportError, except no reader), Task 2/5 (região inválida → vazio/None → default). ✓
- Sem numpy / mss lazy → Global Constraints, respeitado em capture.py. ✓
- Build/deps → Task 7. ✓

**Placeholder scan:** sem TBD/TODO; todo passo de código mostra o código.

**Type consistency:** `default_region(monitor)` recebe dict, retorna 4-tupla; usada igual em Task 4. `subsample(bgra, width, height, grid)` consistente entre Task 2/3. `ScreenSampler.sample()/set_region()/primary_monitor()` usados igual em Task 4. `rect_from_drag`/`select_region` consistentes entre Task 5/6.
