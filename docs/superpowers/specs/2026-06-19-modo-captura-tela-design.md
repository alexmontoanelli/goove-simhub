# Modo Standalone: captura de tela como fonte de cor

**Data:** 2026-06-19
**Status:** Aprovado, pronto para planejamento

## Problema

O bridge hoje depende de uma fonte serial (Adalight): um software externo
(ex: Prismatik) envia o stream de LEDs pela COM, o `engine` reduz a uma cor e
envia para a Govee. Isso exige uma porta COM e um produtor Adalight rodando.

Queremos um modo **standalone** que não dependa da COM: capturar uma região da
tela diretamente, reduzir à cor dominante/média e enviar para a Govee. O usuário
escolhe qual área da tela é capturada através de um seletor visual.

## Decisões tomadas

- **Toggle de fonte:** o modo serial e o modo tela coexistem. A GUI tem um
  seletor `Serial` ou `Tela (standalone)`.
- **Biblioteca de captura:** `mss` (rápida, ~ms por frame, multi-monitor).
- **Monitores:** apenas o monitor principal.
- **Região padrão:** 50% central do monitor principal (funciona antes de o
  usuário selecionar qualquer coisa).
- **Subamostragem:** grade fixa de 32×32 (1024 pixels), custo constante
  independente do tamanho da região.
- **Sem numpy:** mantém o conjunto de dependências mínimo.

## Arquitetura

A `Engine` já separa **fonte de cor** (thread leitora que alimenta
`self._color`) de **envio** (thread sender que manda para a Govee). A mudança
torna a fonte plugável; o sender, o `reduce.py`, o `black_off`, o brilho e a
resolução de IP da Govee permanecem idênticos.

### Fluxo

```
[ fonte ] --(self._color, sob lock)--> [ sender ] --> Govee (LAN UDP)

fonte = _reader_serial  (serial -> AdalightParser -> reduce)
      | _reader_screen  (mss -> subamostra 32x32 -> reduce)
```

### Componentes

**`capture.py`** (novo)
- `default_region()` → `(left, top, width, height)` do 50% central do monitor
  principal. Usa `mss` para descobrir a geometria do monitor principal.
- `ScreenSampler(region)`: classe que mantém **uma instância `mss.mss()`**
  (a lib recomenda 1 por thread). Método `sample() -> list[(r,g,b)]` captura
  a região, subamostra uma grade fixa de 32×32 pontos (1024 pixels) lendo
  direto do buffer BGRA do `mss` (converte BGRA→RGB) e devolve a lista de
  pixels. Custo constante mesmo para regiões grandes. `set_region(region)`
  atualiza a área sem recriar a instância.
- Não depende de tkinter; isolado e testável.

**`region_selector.py`** (novo)
- `select_region(parent=None) -> (left, top, width, height) | None`
- Abre um overlay tkinter translúcido em tela cheia no monitor principal.
- O usuário arrasta um retângulo com o mouse; ao soltar, retorna a geometria.
- `Esc` cancela e retorna `None`.
- Isolado da GUI principal (recebe/retorna apenas tuplas).

**`engine.py`** (alterado)
- `start()` escolhe a thread leitora conforme `cfg["mode"]["source"]`:
  - `"serial"` → `_reader_serial` (lógica atual, abre serial).
  - `"screen"` → `_reader_screen` (não abre serial; usa `capture` + `reduce`).
- `_reader_screen`: a cada ciclo, `sample(region)` → `reduce_fn(pixels)` →
  grava `self._color` sob lock. Respeita o mesmo `reduce` (`average`/`dominant`).
- O sender (`_sender`) não muda. `black_off`, brilho e envio `colorwc`/`turn`
  continuam iguais.
- No modo screen, `start()` não exige porta COM; apenas resolve o IP da Govee.

**`gui.py`** (alterado)
- Seletor de fonte no topo: `Serial` / `Tela (standalone)`.
- No modo Tela: campos COM/Baud desabilitados; botão **"Selecionar área"**
  habilitado (chama `region_selector.select_region`, salva a região no config).
- No modo Serial: comportamento atual (campos COM/Baud habilitados).
- Reaproveita Redução, Taxa (Hz), Brilho, Desligar no preto, Descobrir,
  Testar cor.

**`appconfig.py`** (alterado) — novas seções/chaves nos `DEFAULTS`:

```ini
[mode]
source = serial        # "serial" | "screen"

[capture]
left = -1              # -1 (ou ausente) => usa default_region() em runtime
top = -1
width = -1
height = -1
```

Sem região salva (valores -1), o engine usa `capture.default_region()`.

## Dados / config

- `[mode].source`: string, `serial` ou `screen`.
- `[capture]`: inteiros `left/top/width/height`. Sentinela `-1` significa
  "não definido → use o 50% central".

## Tratamento de erros

- `mss` ausente no modo screen → `Engine.start()` retorna erro de status
  claro ("instale mss" / "captura indisponível"), como o erro de Govee ausente.
- Falha de captura em runtime (`_reader_screen`) → emite status de erro e
  encerra a thread, igual ao tratamento da serial caindo.
- Seletor cancelado (`Esc`) → mantém a região anterior do config.
- Região inválida/zerada → cai no `default_region()`.

## Testes

- `capture.py`: `default_region()` retorna 50% central dado um monitor
  conhecido (monitor mock/injetado). `sample()` reduz um buffer BGRA sintético
  conhecido à grade esperada e às cores corretas (BGRA→RGB).
- `decide_action`/sender: já coberto por `test_adalight.py`; sem mudança.
- `engine`: seleção da thread leitora conforme `source` (sem abrir hardware
  real — injeta uma fonte fake/monkeypatch de `sample`).
- `region_selector.py`: lógica de cálculo do retângulo (drag → geometria) em
  função pura testável; o overlay tkinter em si não é testado automaticamente.

## Build / deps

- `requirements.txt` ganha `mss`.
- `build.md` / spec do PyInstaller: incluir `mss` nos imports coletados.

## Fora de escopo (YAGNI)

- Multi-monitor no seletor.
- Captura por janela/aplicativo específico.
- Múltiplas zonas/segmentação espacial (continua 1 cor única).
- numpy / aceleração GPU.
