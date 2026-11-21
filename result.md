---
id: T-RPF9-1
run: R-20261121-124631-31fa
role: heavy
status: partial
verdict: null
refused: false
---

## Que hice

- **Fase 1 (`raw/cabeceras.txt`)**: Parseadas las 12 cabeceras `.head.bin` externas y 19 cabeceras RPF9 anidadas (31 cabeceras RPF9 validas, 30 unicas) en `samples/` (`/home/sistver/proyectos/rpf9-research/samples/`). Tabulados los 16 campos `uint32` LE (`0x00..0x3c`), reconstruido el tamaño real exacto de 3 archivos por solapamiento (`appdata0` = 8,880 B, `common` = 6,642,192 B, `script` = 4,358,960 B) y verificada coherencia de `w04` (fin de TOC) y `w0c` (longitud del trailer al final del archivo).
- **Fase 2 (`raw/toc.txt`, `raw/firmas.txt`)**: Medida entropia Shannon por bloques de 4 KB en los primeros 4 MB de las 12 muestras; localizada region cifrada de TOC en `[0x40..w04)` y trailer cifrado en `[EOF - w0c .. EOF)`. Evaluados modos AES (0 duplicados intra-TOC en 62,487 bloques de 16 B -> refuta ECB; `C1 ^ C2` desde `0x60` con entropia ~7.99 -> refuta CTR/stream nonce fijo; prefijo identico de 32 B `5f08daab...` en `0x40..0x5f` en los 30 RPF9 unicos -> compatible con cifrado encadenado IV fijo). Escaneadas las 47 ventanas por firmas solicitadas (0 hits) y reales (`9FPR`, `KB2n`, `SGD5`, `LGID`/`LRSC`/`0DRP`/`CHKS`, >3,000 flujos zlib `78 da`). Probadas claves triviales/derivadas de cabecera (todas fallan) y documentado estado de claves RPF7.
- **Fase 3 (`tools/rpf9.py`, `tests/test_rpf9.py`)**: Implementado prototipo CLI con `--json` y `--scan-nested` que explica cada campo de 32 bits, detecta cifrado de TOC sin inventar entradas y corre pruebas sobre muestras reales de distinto tamaño (`appdata0` 8,880 B, `levels` 4,194,304 B, `script` 4,194,304 B) y casos sinteticos.
- **Documentacion (`docs/RPF9.md`, `docs/RPF9.es.md`)**: Especificacion bilingue con tabla de 10 hipotesis (confirmadas, refutadas, indeterminadas) y trazabilidad linea/seccion a `raw/`.

## Evidencia

- `python3 -m unittest -v tests/test_rpf9.py` -> `Ran 6 tests in 0.064s` / `OK` (6/6 pass).
- `python3 tools/rpf9.py /home/sistver/proyectos/rpf9-research/samples/levels.head.bin --json --scan-nested` -> salida JSON valida con `toc_encrypted: true`, `entry_listing_status: "blocked_encrypted_toc_no_key"`, `entries: []`, 2 RPF9 anidados en `0x1c000` y `0x4d000`.
- `raw/cabeceras.txt`, `raw/toc.txt`, `raw/firmas.txt`: transcripciones reproducibles con comando y salida cruda.
- `pytest`: **no verificado** (`No module named pytest` en `/usr/bin/python3`); verificado con `unittest` equivalente.
- Claves propietarias RPF7 (`gtav_aes_key.dat` / `gta5keys.bin`): **no verificado** (ausentes del entorno y no incluidas en repositorios abiertos como CodeWalker/RageLib/LibertyV).

## Requisitos cubiertos

- [x] Fase 1: parseo de cabeceras disponibles (12 externas + 19 anidadas), campos 32-bit, coherencia con tamaño real -> `raw/cabeceras.txt`
- [x] Fase 2: entropia 4 KB, ECB/CBC/CTR, firmas conocidas y reales, prueba de claves candidatas y cola -> `raw/toc.txt`, `raw/firmas.txt`
- [x] Fase 3: `tools/rpf9.py` con `--json` y sin inventar entradas + `tests/test_rpf9.py`
- [x] Documentacion: `docs/RPF9.md` y `docs/RPF9.es.md` con tabla de hipotesis y citas a `raw/`

## Pendientes y riesgos

- Discrepancia de inventario: el brief/README citan 22 `.rpf`, pero `samples/MANIFEST.md` y `samples/` solo contienen 12 RPF (47 archivos `.bin`).
- `pytest` no esta instalado en el sistema; aunque `tests/test_rpf9.py` es compatible con `pytest`, solo pudo ejecutarse con `python3 -m unittest`.
- Sin la clave AES de RPF9 (ni binario de GTA V para claves RPF7), la estructura interna de registros dentro de `[0x40..w04)` y `[EOF - w0c .. EOF)` permanece `indeterminada`.
- En el worktree, el harness reemplazo `samples/` por symlink y `samples.manifest/` (dejados sin tocar en git).

## Archivos modificados

- `raw/cabeceras.txt`
- `raw/toc.txt`
- `raw/firmas.txt`
- `tools/rpf9.py`
- `tests/test_rpf9.py`
- `docs/RPF9.md`
- `docs/RPF9.es.md`
- `result.md`
