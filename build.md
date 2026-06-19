# Build do EXE (Windows)

Pré-requisitos: Python 3 no Windows (o instalador oficial já inclui tkinter).

```bat
pip install pyserial mss pyinstaller
cd adalight-bridge
pyinstaller --onefile --windowed --name adalight-bridge ^
  --collect-all mss main.py
```

Saída: `dist\adalight-bridge.exe`. Distribua só esse arquivo — a config é
criada em `Documentos\Adalight Govee Bridge\config.ini` na 1ª execução.

## Modos

- **Serial (Adalight):** lê o stream de LEDs de uma porta COM (uso clássico
  com Prismatik/Lightpack).
- **Tela (standalone):** captura uma região da tela como fonte de cor, sem
  precisar de COM nem de software Adalight. Use o botão **Selecionar área**
  para definir a região; `mss` (`--collect-all mss`) faz a captura.
