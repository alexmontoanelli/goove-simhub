# Build do EXE (Windows)

Pré-requisitos: Python 3 no Windows (o instalador oficial já inclui tkinter).

```bat
pip install pyserial pyinstaller
cd adalight-bridge
pyinstaller --onefile --windowed --name adalight-bridge main.py
```

Saída: `dist\adalight-bridge.exe`. Distribua só esse arquivo — a config é
criada em `Documentos\Adalight Govee Bridge\config.ini` na 1ª execução.
