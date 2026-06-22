# Build do EXE (Windows)

Pré-requisitos: Python 3 no Windows (o instalador oficial já inclui tkinter).

```bat
pip install pyserial pystray Pillow pyinstaller
cd adalight-bridge
pyinstaller --onefile --windowed --name adalight-bridge ^
  --collect-all pystray --collect-all PIL main.py
```

Saída: `dist\adalight-bridge.exe`. Distribua só esse arquivo — a config é
criada em `Documentos\Adalight Govee Bridge\config.ini` na 1ª execução.

Lê o stream de LEDs do Adalight numa porta COM (uso clássico com
Prismatik/Lightpack) e envia a cor para a Govee via API LAN. Suporta bandeja
(minimizar para a bandeja) e iniciar com o Windows (somente Windows).
