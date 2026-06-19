# Adalight → Govee H6046 Bridge

Standalone **Windows** app that lets **SimHub** drive a **Govee H6046** light in
real time. SimHub sends an **Adalight** stream (serial LED protocol) over a
virtual COM port; this app reads the stream, reduces the LED array to a single
color and sends it to the Govee over its **local LAN API** (UDP) — no cloud.

Configured through a GUI; the `.exe` is built automatically by GitHub Actions.

```
SimHub ──Adalight serial──► COM10 ┐ com0com (virtual pair)
                                  │
adalight-bridge.exe (GUI) ◄─read─ COM11 ┘
   ├─ reader thread: parse Adalight frames → keep "latest color"
   └─ sender loop (~rate_hz): latest color → colorwc → UDP → H6046
```

## Why the Govee H6046 isn't supported by SimHub/Razer natively

The H6046 is a consumer smart light, not a PC RGB device. It only exposes itself
through Govee's own channels: the Govee Home mobile app, Govee's cloud API,
Bluetooth (BLE), and an undocumented local **LAN API**. It does **not** present
itself to the PC as any of the device classes that SimHub and Razer integrate
with.

- **SimHub** drives RGB through a fixed set of integrations: Arduino/FastLED,
  **Adalight** (serial), Philips Hue Entertainment, WLED, and similar. It has no
  Govee driver, and the Govee LAN API implements none of those protocols.
- **Razer Chroma** only controls Chroma-certified hardware (or apps via the
  Chroma SDK). The H6046 is not a Chroma device. Govee's *desktop* app offers a
  one-way "Chroma sync" for some products, but that is Govee's app reacting to
  Chroma broadcasts — it is not a device SimHub can target, and it is not built
  for low-latency telemetry.
- The only real-time, PC-reachable interface the H6046 has is its **LAN API**,
  which no sim-racing/RGB software speaks, and which is limited to a single color
  per device at roughly 10 Hz.

This bridge closes that gap: it speaks a protocol SimHub *does* output
(**Adalight**) and translates it into the Govee LAN API.

## Why this design

- SimHub speaks Adalight natively (serial output); it has no Govee support.
- The Govee LAN API accepts **one color per device** (`colorwc`) at ~10 Hz, so
  the per-LED Adalight data is **reduced to a single color** (average or
  dominant). Per-bar/per-segment color is not possible over LAN (a limit of the
  Govee protocol, not of this app).

## Components

| File | Responsibility |
|---|---|
| `adalight.py` | Adalight protocol parser (resync, split frames) |
| `reduce.py` | reduce the LED array to one color (`average`/`dominant`) + luminance |
| `govee_lan_core.py` | Govee LAN over UDP (discover, send, status) |
| `appconfig.py` | `.ini` config under `Documents/Adalight Govee Bridge/` |
| `engine.py` | two threads (serial reader + throttled sender), brightness, black→off |
| `gui.py` | tkinter window (config, Discover, Brightness, Test color, Start/Stop) |
| `main.py` | EXE entrypoint (+ `--discover` / `--list-com`) |

## Usage (Windows)

1. **Virtual COM port:** install [com0com](https://com0com.sourceforge.net/) and
   create a pair, e.g. `COM10` ↔ `COM11`.
2. **SimHub:** Settings → Arduino/RGB LEDs → **Adalight**, port `COM10`, baud
   `115200`; set the LED count and map your effects.
3. **This app:** run `adalight-bridge.exe`, select `COM11`, click **Discover**
   (or type the Govee IP), adjust brightness/reduction/rate and click **Start**.
   **Test color** sends a color straight to the Govee, without SimHub.

> Turn off Govee cloud/app and Alexa/Google control while using this (avoids
> conflicts/flicker). Pinning the Govee's IP in your router is recommended.

## Getting the EXE

- **CI:** every push (or "Run workflow") runs the *Build Windows EXE* workflow
  and publishes `adalight-bridge.exe` as an **artifact**.
- **Local (Windows):** see [`build.md`](build.md)
  (`pyinstaller --onefile --windowed`).

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python3 -m unittest test_adalight -v
```

The pure modules (`adalight`, `reduce`, `appconfig`, `govee_lan_core`) and the
`engine.decide_action` rule are tested and run on any OS. The GUI uses `tkinter`
(stdlib; on macOS via Homebrew you may need `brew install python-tk@3.13`). The
only external dependency is `pyserial`.

## Diagnostics

```bat
adalight-bridge.exe --discover    REM list Govee devices on the network
adalight-bridge.exe --list-com    REM list COM ports
```
