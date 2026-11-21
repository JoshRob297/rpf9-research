---
id: T-RPF9-2
run: R-20261121-131054-8939
role: heavy
status: done
verdict: null
refused: false
---

## Que hice

- **Objetivo A (`raw/cabeceras2.txt`)**: Extendida la tabla de cabeceras a los **22** RPF9 y **78** ficheros `.bin` en `/home/sistver/proyectos/rpf9-research/samples/` (sin subcarpeta `pack/`), validando **77** cabeceras RPF9 (**76** `archive_id` unicos). Verificada la regla exacta de `[w08..w04)`: `ceil(9*w24/16)*16` (`54/54` cuando `w20_hi==1` y `w2c_b0==1`, `w24<=194`) y `ceil(10*w24/16)*16` (`15/15` cuando `w20_hi==1` y `w2c_b0==2`, `w24>=265`). Confirmado `w24` contra conteo de payloads en los 4 archivos completos y 2 anidados acotados (`4==4` en `story000_bvh4.full.bin`, `2==2` en `appdata0.head.bin`, `4==4` en `core_licenses_data.full.bin` + `2==2` en su RPF9 `@0x1000`, `6==6` en `core_restofworld001.full.bin` + `22==22` grupos en su RPF9 `@0x1000`).
- **Objetivo B (`raw/payload.txt`, `tools/rpf9.py --payload`, `tests/test_rpf9.py`)**: Escaneados e inflados **16,213** flujos zlib `78 da` validos (477 XML, 4,066 `PSIN`, 872 `0DRP`, 4,357 `rsc50`, 6,441 otros/microcodigo shader); parseada la cabecera `SGD5` en `shaders.head.bin @0x9000` (`sub_count=33`, `first_section_bytes=2112`, 31 tablas secuenciales de 8 B con 2,419 registros y 737 simbolos `[VDHGMCP]S_*_Wrapped`); enumerados los **55** `RPF9` anidados (**54** unicos) con tamano exacto reconstruido en **29** de ellos; detectado `EDUP` (`core_restofworld001 @0xc14a0`). Extendido `tools/rpf9.py` con `--payload` para listar entradas legibles y reportar explicitamente TOC, traileres y regiones no legibles.
- **Objetivo C (`raw/toc-chico.txt`)**: Probadas 6 hipotesis estructurales (`H-C1`..`H-C6`) en archivos completos chicos (`w24=1..6`). Refutadas rutas ASCII en claro (`H-C1`), tamanos/offsets `u16`/`u32` en claro (`H-C2`) y reutilizacion de flujo en `[0x60..w04)` (`H-C6`); confirmada la regla de paso 9/10 B en `[w08..w04)` (`H-C3`), las colisiones exactas de bloque 0 del trailer por `(w24, w20_hi)` y de 32 B (`blk0+blk1`) por `(w24, w20_hi, w0c)` (`appdata0` vs `script @0x1000`, `core_licenses_data` vs `story000_bvh4`) con divergencia en `blk2` (`H-C4`), y capacidad de `w0c` para `32 B + rutas XML` (`H-C5`).
- **Documentacion (`docs/RPF9.md`, `docs/RPF9.es.md`)**: Actualizadas las especificaciones bilingues con los 22 archivos, 77 cabeceras, hallazgos de payload e hipotesis `H1`..`H13` citando `raw/cabeceras2.txt`, `raw/payload.txt` y `raw/toc-chico.txt`.

## Evidencia

- `python3 -m unittest -v tests/test_rpf9.py` -> `Ran 10 tests in 0.746s` / `OK` (10/10 pass).
- `python3 tools/rpf9.py /home/sistver/proyectos/rpf9-research/samples/story000_bvh4.full.bin --payload` -> 4 streams XML inflados (`story000_environment_bvh`, `story000_terrain_bvh`, `CDataFileMgr__ContentDef`, `SSetupData`), 2 regiones no legibles explicitadas (`head_toc` `0x40..0x340`, `archive_trailer` `0x1570..0x1600`).
- `python3 tools/rpf9.py /home/sistver/proyectos/rpf9-research/samples/shaders.head.bin --payload` -> `SGD5 @0x9000..0x400000 sub_count=33 sec0=2112B tables=31 recs=2419 syms=737` y regiones no legibles explicitadas.
- Transcripciones en `raw/cabeceras2.txt`, `raw/payload.txt`, `raw/toc-chico.txt`.
- Worktree `JoshRob297/task-t-rpf9-2` avanzado por fast-forward (`git merge --ff-only origin/main`) desde `eac3f6c` hasta `9b113cb` (`origin/main`) antes de iniciar ediciones, sin tocar la rama base `main` ni hacer commit/push.

## Requisitos cubiertos

- [x] Objetivo A: tabla extendida a 22 archivos, validacion de campos y `w24` en completos -> `raw/cabeceras2.txt`
- [x] Objetivo B: inflado zlib `78 da`, parseo `SGD5`, enumeracion de `RPF9` anidados -> `raw/payload.txt`, `tools/rpf9.py --payload`, `tests/test_rpf9.py`
- [x] Objetivo C: hipotesis en completos/chicos (`w24` 1..6) con prediccion, prueba y veredicto -> `raw/toc-chico.txt`
- [x] Documentacion actualizada en `docs/RPF9.md` y `docs/RPF9.es.md` sin push ni PR

## Pendientes y riesgos

- Sin la clave AES de RPF9 (ausente del entorno), la disposicion interna de registros dentro de `[0x60..w04)` y el formato exacto de cadenas en `[EOF-w0c+32..EOF)` permanecen `indeterminada`s.
- El prompt menciona `samples/.../pack/`, pero las 78 muestras binarias estan ubicadas directamente en `/home/sistver/proyectos/rpf9-research/samples/` (no dentro de `pack/` ni del worktree, que solo contiene `samples/MANIFEST.md`).
- Para `26/55` contenedores `RPF9` anidados, su tamano exacto queda sin cota superior porque la ventana `.head`/`.q3`/`.tail` de 2–4 MiB los trunca antes de su trailer `w0c`.

## Archivos modificados

- `raw/cabeceras2.txt`
- `raw/payload.txt`
- `raw/toc-chico.txt`
- `tools/rpf9.py`
- `tests/test_rpf9.py`
- `docs/RPF9.md`
- `docs/RPF9.es.md`
- `result.md`
