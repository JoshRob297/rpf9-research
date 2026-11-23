# RESOLVER — de una ruta del manifiesto a los bytes del asset

Herramienta: `tools/resolve_path.py` (Python 3, solo biblioteca estándar).
Fixture de trabajo: `(fixture local)`.

## 1. Alcance

El resolutor convierte una ruta del índice (`paths-*.tsv`) en los bytes del asset
que viven dentro de un contenedor RPF9. No parsea la TOC cifrada de RPF9 ni
descifra nombres: se apoya en el recorte de índice ya extraído
(`streams-*.tsv` + `paths-*.tsv`), que le dice exactamente qué offset leer,
cuántos bytes comprimidos leer y cuántos bytes debe medir el resultado.

La cadena es:

```
ruta -> fila(s) en paths-*.tsv -> (rpf, abs_offset) -> fila en streams-*.tsv
     -> seek(abs_offset) en <rpf>.rpf, read(compressed)
     -> zlib si empieza en 0x78, si no bytes crudos
     -> comprobar len(resultado) == inflated
```

## 2. Fixture verificado

`ls -la (fixture local)/{rpf,index}` (bytes reales):

| Archivo | Bytes |
|---|---:|
| `rpf/data.rpf` | 481.544.304 |
| `rpf/script.rpf` | 4.358.960 |
| `rpf/core_restofworld001.rpf` | 791.984 |
| `index/streams-data.tsv` | 1.488.140 |
| `index/paths-data.tsv` | 281.839 |
| `index/streams-script.tsv` | 53.770 |
| `index/streams-core_restofworld001.tsv` | 2.092 |
| `index/paths-core_restofworld001.tsv` | 3.746 |

Los tres contenedores empiezan con `39 46 50 52` (`RPF9` little-endian); se
comprobó leyendo los primeros 4 bytes de cada uno. `data.rpf` es el contenedor
grande (459 MiB); los otros dos son de control.

## 3. Formato del índice

### 3.1 `streams-*.tsv`

Cabecera: `rpf`, `abs_offset`, `offset_hex`, `compressed`, `inflated`, `type`,
`status`, `n_paths`, `n_ids`. Una fila por **stream único**.

| Columna | Uso en el resolutor |
|---|---|
| `rpf` | Nombre del contenedor sin extensión; el archivo es `<rpf>.rpf`. |
| `abs_offset` | Offset absoluto del stream dentro del contenedor. |
| `offset_hex` | El mismo offset en hexadecimal; se valida que coincida con `abs_offset`. |
| `compressed` | Bytes exactos a leer desde `abs_offset`. |
| `inflated` | Bytes que debe medir el resultado tras zlib o como dato crudo. |
| `type` | Tipo de stream; solo informativo (`raw`, `PSIN`, `rsc50`, `0DRP`, `xml` observados). |
| `status` | `named`/`unnamed`; informativo, no afecta a la resolución. |
| `n_paths`, `n_ids` | Conteos del índice; informativos. |

Medidas del recorte: **29.599 streams únicos** (28.509 de `data`, 1.057 de
`script`, 33 de `core_restofworld001`), **0 claves `(rpf, abs_offset)`
duplicadas**, **0 streams que terminen más allá del final del contenedor**
(el final máximo es `481.520.114 <= 481.544.304`).

### 3.2 `paths-*.tsv`

Cabecera: `ruta`, `rpf`, `abs_offset`. Una fila por **mención**, no por ruta
única: la misma ruta puede aparecer varias veces, incluso apuntando a streams
distintos.

Medidas del recorte: **4.704 menciones** (4.639 de `data`, 65 de
`core_restofworld001`) que corresponden a **2.295 rutas únicas** (2.273 de
`data`, 22 de `core_restofworld001`). Las 4.704 menciones tienen fila de stream
(0 huérfanas). La ruta con más menciones del recorte tiene 87; en `data`, 1.671
de las 2.273 rutas tienen una sola mención.

## 4. Algoritmo y errores

1. `load_streams()` lee todos los `streams-*.tsv` del directorio de índice y arma
   un diccionario `(rpf, abs_offset) -> Stream`; valida columnas, enteros,
   `offset_hex` y claves duplicadas (`tools/resolve_path.py:176-224`).
2. `load_mentions()` lee todos los `paths-*.tsv` en orden de nombre de archivo
   (`tools/resolve_path.py:227-250`) y `group_mentions()` agrupa por ruta
   conservando el orden de filas (`tools/resolve_path.py:252-262`).
3. Búsqueda de ruta **exacta**; por defecto se resuelve **la primera mención** y
   `--all` recorre todas (`tools/resolve_path.py:269-286`).
4. `resolve_mention()` busca la fila de stream, abre `<rpf_dir>/<rpf>.rpf`, hace
   `seek(abs_offset)` y `read(compressed)`: nunca lee el contenedor entero
   (`tools/resolve_path.py:289-357`).
5. Detección de compresión: si el slice empieza con `0x78` se descomprime con
   `zlib.decompress`; si no, se trata como dato crudo (`tools/resolve_path.py:326-339`).
6. Comprobación de tamaño: `len(resultado) == inflated`; si no, error
   (`tools/resolve_path.py:342-352`).

Errores con `reason` estable:

| `reason` | Cuándo |
|---|---|
| `path_not_found` | La ruta no está en `paths-*.tsv` (o no tiene menciones para el `--rpf` pedido). |
| `stream_missing` | Hay mención pero no hay fila `(rpf, abs_offset)` en `streams-*.tsv`. |
| `container_missing` | No existe `<rpf>.rpf` en `--rpf-dir`. |
| `container_read_error` | Error de E/S al abrir o leer el contenedor. |
| `short_read` | El contenedor termina antes de `compressed` bytes. |
| `zlib_error` | El slice empieza en `0x78` pero zlib falla. |
| `size_mismatch` | El resultado no mide `inflated`. |
| `index_error` | Índice ausente, cabecera incorrecta, entero inválido, duplicado, etc. |
| `stdout_is_tty` | Se intentó escribir binario a una terminal sin `--out`. |
| `write_error` | No se pudo escribir el archivo de `--out`. |

Todos los errores se informan por `stderr` con código de salida 1; los errores
de uso de argparse salen con 2.

## 5. Modos de uso

```
# bytes a stdout (redirigir; se niega a escribir binario en una TTY)
python3 tools/resolve_path.py 'activity_launcher_menu/controls/info_label_banner' > /tmp/asset.bin

# bytes a un archivo
python3 tools/resolve_path.py 'activity_launcher_menu/controls/info_label_banner' \
    --out /tmp/asset.bin

# metadatos de la primera mención
python3 tools/resolve_path.py 'activity_launcher_menu/controls/info_label_banner' --info

# todas las menciones
python3 tools/resolve_path.py 'activity_launcher_menu/controls/info_label_banner' --all

# verificación aleatoria acotada a data.rpf
python3 tools/resolve_path.py --verify 200 --rpf data

# verificación de todo el recorte (2.295 rutas, 4.704 menciones)
python3 tools/resolve_path.py --verify 2295
```

`--verify N` toma `N` rutas únicas al azar (sin reemplazo) del índice, resuelve
**todas** las menciones de cada ruta elegida y cuenta por separado menciones y
rutas. Una ruta pasa solo si pasan todas sus menciones. La muestra es
reproducible con `--seed` (por defecto 0) porque se ordena la lista de rutas
antes de muestrear (`tools/resolve_path.py:400-401`). Si `N` supera las rutas
disponibles, se recorta y se informa `requested N, capped`.

Los valores por defecto de `--index-dir` y `--rpf-dir` apuntan al fixture
`(fixture local)`. Para otro recorte hay que pasar ambos
flags; no se deduce un directorio a partir del otro.

Ejemplo real de `--info`:

```
path: activity_launcher_menu/controls/info_label_banner
mentions: 3
mention: 1/3 (first of 3; use --all to list every mention)
rpf: data
offset: 298999808 (0x11d26000)
type: raw
compressed: 852
inflated: 4353
decompressed: yes
size_check: ok (4353 == 4353)
```

Ejemplo real de `--all`:

```
path: activity_launcher_menu/controls/info_label_banner
mentions: 3
[1/3] rpf=data offset=298999808 (0x11d26000) type=raw compressed=852 inflated=4353 decompressed=yes check=ok
[2/3] rpf=data offset=299003904 (0x11d27000) type=raw compressed=1142 inflated=4424 decompressed=yes check=ok
[3/3] rpf=data offset=299012096 (0x11d29000) type=raw compressed=2999 inflated=15961 decompressed=yes check=ok
summary: 3 mentions, 3 passed, 0 failed
```

Los offsets `abs_offset` son absolutos dentro del contenedor; no son relativos
al payload ni al inicio de la TOC.

## 6. Decisiones

1. **Resolvedor guiado por índice, no por TOC.** La TOC de RPF9 está cifrada y
   no hay clave; el índice ya contiene las longitudes necesarias. El resolutor
   no depende de AES ni de parsear la cabecera, y por eso puede entregar bytes
   hoy, a cambio de confiar en el recorte del índice.
2. **Una mención por defecto, `--all` para todas.** Una ruta puede estar
   mencionada en varios streams (duplicados/overrides del paquete). El modo por
   defecto elige la primera fila en el orden de `paths-*.tsv` (archivos
   ordenados y filas en orden) para que la salida sea determinista; `--all`
   muestra y valida todas. `--info` avisa cuántas hay.
3. **Detección zlib por prefijo `0x78`.** Es la regla pedida. `0x78` es el byte
   CMF habitual de zlib/deflate con ventana de 32 KiB. El fallback a datos
   crudos existe para streams almacenados sin comprimir. Riesgo teórico: un
   stream crudo que empiece casualmente en `0x78` se intentaría inflar; en este
   recorte no ocurre (las 4.704 menciones son zlib válido) y el fallback está
   cubierto por un test sintético.
4. **Verificar todas las menciones de una ruta muestreada.** Muestrear
   menciones sobre-representaría rutas con muchas apariciones; muestrear rutas
   y comprobar todas sus menciones cubre el índice sin sesgo de multiplicidad.
5. **Muestra reproducible.** `random.Random(seed).sample` sobre una lista
   ordenada de rutas; `seed=0` por defecto. Misma versión de Python y mismo seed
   producen la misma salida (comprobado con `diff`).
6. **Lectura por `seek`.** Cada mención abre el contenedor, hace `seek` y lee
   solo `compressed` bytes. No hay `mmap`, no se carga el `.rpf` en memoria y no
   se cachean contenidos. La memoria retenida es el índice (29.599 filas) más el
   buffer del stream que se está resolviendo.
7. **Ruta exacta, sin normalizar.** `$(root)/...` y `$(target)/...` son parte
   literal de la ruta; hay que entrecomillarlas en la shell (`'$(root)/...'`)
   para que bash no intente ejecutar `root` como sustitución de comando.
8. **Validación estricta del índice.** Columnas requeridas, enteros no
   negativos, `offset_hex == abs_offset`, sin claves de stream duplicadas y sin
   líneas con columnas de más. Un índice inconsistente falla con
   `index_error` en vez de adivinar.
9. **Cero dependencias externas.** Solo `argparse`, `csv`, `random`, `re`,
   `sys`, `zlib`, `dataclasses` y `pathlib` (`tools/resolve_path.py:15-22`).

## 7. Verificación reproducible

### 7.1 Suite de tests

```
$ python3 -m unittest discover -s tests -v
...
Ran 44 tests in 4.752s

OK
```

29 tests son de `tests/test_resolve_path.py`: 20 sintéticos (incluido el caso
crudo sin `0x78`, errores de tamaño, stream faltante, contenedor faltante, zlib
inválido, lectura corta y CLI) y 9 sobre el fixture real. La suite completa del
repo sigue pasando (15 tests previos + 29 nuevos).

### 7.2 `--verify 200` sobre `data.rpf`

Comando y salida real:

```
$ time python3 tools/resolve_path.py --verify 200 --rpf data
verify: sampled 200 of 2273 paths (seed=0; rpf=data)
mentions: 410 resolved, 410 passed, 0 failed
paths: 200 passed, 0 failed
failure reasons: none
verify: PASS

real	0m0.620s
```

200 rutas = 410 menciones (hay rutas con más de una mención). Todas las
comprobaciones de tamaño pasaron.

### 7.3 Todo el recorte

```
$ time python3 tools/resolve_path.py --verify 2295
verify: sampled 2295 of 2295 paths (seed=0)
mentions: 4704 resolved, 4704 passed, 0 failed
paths: 2295 passed, 0 failed
failure reasons: none
verify: PASS

real	0m3.825s
```

### 7.4 Memoria

Con un wrapper que mide `ru_maxrss` del proceso hijo:

```
verify: sampled 200 of 2273 paths (seed=0; rpf=data)
mentions: 410 resolved, 410 passed, 0 failed
paths: 200 passed, 0 failed
failure reasons: none
verify: PASS

exit 0
peak RSS (KiB): 78660
```

78.660 KiB de RSS máximo para verificar 200 rutas contra un contenedor de
481.544.304 B. El RSS incluye intérprete, índice y el mayor stream inflado
(`14.876.672` B es el `inflated` máximo del recorte); no incluye páginas en la
page cache del sistema. Es consistente con no cargar el contenedor entero.

### 7.5 Determinismo

```
$ python3 tools/resolve_path.py --verify 200 --rpf data > /tmp/v1.txt
$ python3 tools/resolve_path.py --verify 200 --rpf data > /tmp/v2.txt
$ diff -u /tmp/v1.txt /tmp/v2.txt && echo IDENTICAL
IDENTICAL
```

## 8. Límites y riesgos

- **Cobertura del recorte.** `paths-*.tsv` solo cubre `data` y
  `core_restofworld001`. `streams-script.tsv` existe, pero no hay
  `paths-script.tsv`: las rutas de `script.rpf` no son resolubles con este
  fixture. No se inventó un `paths-script.tsv`.
- **Se confía en el índice.** El resolutor comprueba coherencia interna
  (stream existe, tamaño cuadra), pero no puede saber si el recorte está
  desactualizado respecto del `.rpf` ni si el stream corresponde semánticamente
  a la ruta. Un índice viejo produce `size_mismatch`/`zlib_error`, no una
  respuesta silenciosamente incorrecta.
- **Solo zlib y crudo.** No se soportan deflate crudo (`-15`), LZ4 ni otros
  codecs; el brief define zlib-si-`0x78` y crudo-en-otro-caso.
- **Heurística de compresión.** Un dato crudo que empiece en `0x78` daría
  `zlib_error` en lugar de devolverse tal cual. En el recorte real no hay casos;
  el caso crudo está probado sintéticamente.
- **Sin verificación criptográfica.** No hay hash ni firma en el índice; pasar
  la comprobación de tamaño no demuestra autenticidad, solo coherencia.
- **Sin caché de archivos.** Cada mención abre y cierra el contenedor. Para 200
  rutas tarda 0,6 s y para las 2.295 rutas 3,8 s; aceptable para este uso, pero
  un barrido mucho mayor pediría reutilizar descriptores.
- **Salida binaria en TTY.** El modo por defecto se niega a volcar binario a una
  terminal; hay que redirigir o usar `--out`. Es una protección deliberada, no
  un fallo.
- **Rutas con `$`.** Sin entrecomillar, la shell expande `$(root)`/`$(target)`.
  La herramienta no normaliza esas rutas; el usuario debe pasar la cadena
  literal entre comillas simples.

## 9. Archivos

- `tools/resolve_path.py` — implementación y CLI.
- `tests/test_resolve_path.py` — 29 tests (fixture real + sintético).
- `docs/RESOLVER.md` — este documento.
- `result.md` — cierre del encargo con la salida real de `--verify 200`.
