---
id: T-RPF9-3
run: R-20261121-145315-61c2
role: heavy
status: done
verdict: null
refused: false
---

## Que hice

- **Extractor multifuente (`tools/name_recover.py`)**: Implementado pipeline que escanea archivos `.bin`/`.rpf`, infla flujos zlib `78 da` (`xml`, `xml_chunk`, `PSIN`, `0DRP`, `rsc50`, `raw`) y entradas de shaders `SGD5` (`[VDHGMCP]S_*_Wrapped\0` + cabecera de 17 B + deflate crudo `wbits=-15` hacia `DXBC`), extrae rutas completas e identificadores con procedencia ordenada (`xml` -> `psin`/`0drp` -> `sgd5` -> `rsc50`/`raw_stream`), deduplica y separa `full_paths` de `identifiers`, y marca todo flujo sin cadenas legibles como `status="unnamed"` (sin inventar nombres).
- **Medicion y transcripcion (`raw/nombres.txt`)**: Ejecutado sobre los 78 archivos de muestra en `/home/sistver/proyectos/rpf9-research/samples` (`17,082` flujos: `1,509` con nombre = `8.83%`; `15,573` sin nombre = `91.17%`; `13,402` rutas unicas y `14,282` identificadores unicos). Verificada la presencia exacta byte a byte dentro de los payloads inflados para 6 nombres de las distintas fuentes (`--validate`).
- **Documentacion bilingue (`docs/NAMES.md`, `docs/NAMES.es.md`)**: Documentadas las 3 alternativas de diseno con trade-offs, cobertura medida por tipo de flujo y archivo, ejemplos reales con citas a `raw/nombres.txt`, limitaciones y comparacion contra el enfoque por offset de `ItsNotRexed/Leonida` (`docs/rpf.md`, `tools/rpf9_carve.py`, `tools/shader_carve.py`).
- **Pruebas (`tests/test_name_recover.py`)**: Anadidas 5 pruebas (4 sobre muestras reales + 1 sintetica con separacion `full_paths`/`identifiers`, filtrado de ruido binario/dialogos, `SGD5` `DXBC` y flujos `unnamed`).
- **Sincronizacion de worktree**: Restaurado `result.md` borrado al inicio y avanzado `JoshRob297/task-t-rpf9-3` por fast-forward (`git merge --ff-only origin/main`) desde `3d9384c` hasta `72d1969` para disponer de `docs/RPF9.md` y `raw/payload.txt` de T-RPF9-2 sin tocar `main` ni hacer commit/push.

## Evidencia

- **E1 (Ejecucion real en 78 muestras + validacion en payload)**: `python3 tools/name_recover.py /home/sistver/proyectos/rpf9-research/samples --validate --out /tmp/opencode/index.json` -> `Total streams: 17082 | named: 1509 (8.83%) | unnamed (sin nombre): 15573`; `Payload validation (checked=6, all_verified=True)` (`raw/nombres.txt`, lineas 4–34).
- **E1 (Suite de pruebas con `unittest`)**: `python3 -m unittest discover -s tests -v` -> `Ran 15 tests in 3.056s` / `OK` (`tests/test_name_recover.py` 5/5 pass + `tests/test_rpf9.py` 10/10 pass).
- **E1 (Cobertura por fuente medida)**: `sgd5_shader_dxbc` `867/867` (`100.00%`), `sgd5_shader_truncated` `2/2` (`100.00%`), `xml` `181/477` (`37.95%`), `xml_chunk` `179/929` (`19.27%`), `rsc50` `197/4357` (`4.52%`), `raw` `69/5512` (`1.25%`), `0DRP` `8/872` (`0.92%`), `PSIN` `6/4066` (`0.15%`) (`raw/nombres.txt`, lineas 10–18).
- **No verificado (`pytest`)**: `python3 -m pytest --version` -> `No module named pytest`; ejecutadas exactamente las mismas pruebas compatibles con `pytest` mediante `python3 -m unittest`.

## Requisitos cubiertos

- [x] `tools/name_recover.py` infla flujos de muestra o RPF completo y genera `index.json` (`file`, `offset`, `compressed_bytes`, `inflated_bytes`, `stream_type`, `candidates`, procedencia, deduplicacion y separacion `full_paths` / `identifiers`) — evidencia: `tools/name_recover.py:242-371`
- [x] Fuentes ordenadas (XML con extensiones objetivo e identificadores -> PSIN/0DRP -> tabla SGD5) y flujos sin nombre marcados `unnamed` sin inventar datos — evidencia: `tools/name_recover.py:113-295`, `raw/nombres.txt:10-20`
- [x] Validacion obligatoria (>=3 nombres comprobados dentro del payload inflado + % de cobertura medido) — evidencia: `raw/nombres.txt:23-30` (6/6 verificados, 8.83% global)
- [x] Documentacion bilingue `docs/NAMES.md` y `docs/NAMES.es.md` con cobertura, ejemplos reales, limitaciones y comparacion contra Leonida — evidencia: `docs/NAMES.md:1-101`, `docs/NAMES.es.md:1-101`
- [x] Transcripciones en `raw/nombres.txt` y pruebas en `tests/test_name_recover.py` — evidencia: `raw/nombres.txt:1-108`, `tests/test_name_recover.py:1-169`

## Pendientes y riesgos

- `pytest` no esta instalado en `/usr/bin/python3`; las pruebas se verificaron con `unittest` (`15/15 OK`).
- Sin la clave AES de RPF9, `15,573` de `17,082` flujos (`91.17%`) carecen de cadenas en claro (`LSNS` opaco en `PSIN`, paginas `0DRP`/`rsc50`, tuning XML) y permanecen como `unnamed`.
- Existen `2` entradas `SGD5` truncadas al borde de las ventanas `.bin` de 2–4 MiB (`shaders.head.bin @0x3ff36c`, `shaders.q1.bin @0x1facd3`).

## Archivos modificados

- `tools/name_recover.py` (nuevo)
- `raw/nombres.txt` (nuevo)
- `docs/NAMES.md` (nuevo)
- `docs/NAMES.es.md` (nuevo)
- `tests/test_name_recover.py` (nuevo)
- `result.md` (actualizado para T-RPF9-3)
