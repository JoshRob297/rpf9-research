# Análisis del Contenedor RPF9 (GTA VI Xbox Series X|S)

## 1. Inventario de Muestras y Límites de Alcance

- `README.md` y el encargo mencionan 22 archivos `.rpf`, pero `/home/sistver/proyectos/rpf9-research/samples/` y `samples/MANIFEST.md` contienen en realidad **12** archivos RPF divididos en **47** ventanas binarias (`head`, `q1`, `q3`, `tail`; `appdata0` tiene 3 ventanas) (`raw/cabeceras.txt`, líneas 4–5, 73–84).
- En esas 47 ventanas se detectaron **31** cabeceras RPF9 válidas (**30** únicas; `script.head.bin @0xc4000` y `script.tail.bin @0x9bcd0` se solapan y corresponden al mismo contenedor anidado) (`raw/cabeceras.txt`, líneas 41–70).
- **Tamaños reales exactos** reconstruidos mediante solapamiento de ventanas (`raw/cabeceras.txt`, líneas 73–84):
  - `appdata0.rpf`: **8,880** bytes (`0x22b0`, archivo completo en `appdata0.head.bin`; `q1` inicia en `2220` y `q3` en `6660`).
  - `common.rpf`: **6,642,192** bytes (`0x655a10`, solapamiento `head->tail` en `rel=2447888` + `4194304`).
  - `script.rpf`: **4,358,960** bytes (`0x428330`, solapamiento `head->tail` en `rel=164656` + `4194304`).
  - Los 9 archivos restantes (`anim`, `audio`, `data`, `levels`, `movies`, `navmeshes`, `packs`, `shaders`, `textures`): cota inferior estimada **> 16 MiB** porque `head` (4 MiB), `q1` (2 MiB), `q3` (2 MiB) y `tail` (4 MiB) no se solapan (`raw/cabeceras.txt`, líneas 73–84).

## 2. Disposición Física del Contenedor

Todo contenedor RPF9 sigue un layout físico de 5 regiones (`raw/cabeceras.txt`, líneas 73–84; `raw/toc.txt`, secciones 1 y 5):

1. **`[0x00 .. 0x40)` (64 bytes)**: Cabecera en claro (16 enteros `uint32` little-endian).
2. **`[0x40 .. w04)` (`w04 - 64` bytes)**: Región cifrada de TOC inicial (alineada a 16 bytes; entropía Shannon `7.6043` a `7.9983` bits/byte; `raw/toc.txt`, sección 1). Dividida internamente por `w08` (`64 < w08 < w04`).
3. **`[w04 .. primer_payload)`**: Relleno de ceros hasta alineación de `0x1000` (4,096 bytes) en 10 de los 12 archivos externos y en todos los RPF9 anidados observados; en `appdata0` (`w04=0x360`) y `common` (`w04=0x9580`), un payload pequeño inicia inmediatamente en `w04` (`raw/cabeceras.txt`, líneas 74, 76).
4. **Payloads**: Mezcla de contenidos sin cifrar (flujos zlib `78 da`, video Bink 2 `KB2n`, shaders `SGD5`, recursos `LRSC`/`0DRP`/`CHKS`/`LGID`, contenedores `RPF9` anidados) y payloads cifrados/de alta entropía (`raw/firmas.txt`, secciones 2–3).
5. **`[EOF - w0c .. EOF)` (`w0c` bytes)**: Tráiler cifrado al final exacto de los archivos externos (precedido por `4` a `3,886` bytes en cero en 10 de 12 archivos; `0` ceros previos en `appdata0` y `script`; `raw/toc.txt`, sección 5) y después del último payload dentro de RPF9 anidados (ej. `anim.head.bin` `@0x62e0..0x6320` para `w0c=64`).

## 3. Estructura de la Cabecera (`0x00 .. 0x3F`, 64 bytes LE)

| Offset | Tipo | Rango / Valores Observados | Rol y Certeza | Fuente (`raw/cabeceras.txt`) |
|---|---|---|---|---|
| `0x00` | `u32` | `0x52504639` (`39 46 50 52`) | **Confirmada**: Magia `"RPF9"` en little-endian (31/31 cabeceras) | líneas 11–22, 41–70 |
| `0x04` | `u32` | `608` .. `219,840` (múlt. de 16) | **Confirmada**: Offset final (`w04`) de la TOC cifrada `[0x40..w04)`; los bytes no nulos terminan en `w04 - 1` | líneas 26–37, 73–84 |
| `0x08` | `u32` | `576` .. `187,600` (múlt. de 16) | **Plausible**: Límite interno dentro de la TOC (`w08 <= w04`). La diferencia `w04 - w08` va de `16` a `32,240` y escala con `w24` (~9–18 B/entrada; `ceil(10*w24/16)*16` exacto en 10/30 cabeceras únicas) | líneas 26–70 |
| `0x0c` | `u32` | `48` .. `119,520` (múlt. de 16) | **Ubicación confirmada / Rol plausible**: Longitud exacta (`w0c`) del tráiler cifrado en `[EOF - w0c .. EOF)`; escala ~9.5–105.9 B/`w24` (candidato a tabla cifrada de nombres/metadatos) | líneas 26–70, `raw/toc.txt` §5 |
| `0x10..0x17` | `u64` | Valor de 64 bits distinto por archivo | **Indeterminada**: Identificador / salt / hash único por archivo (30/30 únicos); no altera el texto cifrado de `0x40..0x5f` | líneas 41–70 |
| `0x18` | `u32` | `0x00047a00` (`293,376`) | **Constante confirmada**: Idéntico en las 31 cabeceras | líneas 26–37, 41–70 |
| `0x1c` | `u32` | `0x00000150` (`336`) | **Constante confirmada**: Idéntico en las 31 cabeceras | líneas 26–37, 41–70 |
| `0x20` | `u32` | `0x00010003`..`0x00020006` | **Indeterminada**: `u16` bajo `3..7`, `u16` alto `1..2`; candidato a banderas/profundidad/versión | líneas 26–70 |
| `0x24` | `u32` | `1` .. `3,224` | **Plausible**: Número de entradas/nodos (`w24`); gobierna `w04 - w08` y coincide cuando colisiona el primer bloque del tráiler (`w24=2` en `appdata0` y `script`) | líneas 26–70, `raw/toc.txt` §5 |
| `0x28` | `u32` | 5 valores discretos (`0xd98004d5`, `0xda72573e`, `0xc0a92754`, `0xd5c19f6b`, `0x5a5b4c6f`) | **Indeterminada**: Etiqueta de compilación/clave candidata; no altera `0x40..0x5f` | líneas 26–70 |
| `0x2c` | `u32` | `0x00090f01` (`w24<=194`) o `0x00090f02` (`w24>=265`) | **Plausible**: Subversión o bandera de página cuyo byte bajo cambia `1 -> 2` entre `w24=194` y `w24=265` | líneas 41–70 |
| `0x30` | `u32` | `0x00000010` (`16`) | **Constante confirmada**: Unidad de alineación/bloque de 16 bytes en las 31 cabeceras | líneas 26–70 |
| `0x34..0x3c` | `3xu32` | `0, 0, 0` | **Cero confirmado**: Relleno reservado en las 31 cabeceras | líneas 26–70 |

**Coherencia con tamaño real**: En los 3 archivos cuyo tamaño total exacto se reconstruyó (`appdata0` = `8,880`, `common` = `6,642,192`, `script` = `4,358,960`), se cumple `w04 + w0c <= real_size`, y **ninguno** de los 16 campos `u32` almacena el tamaño total del archivo (`size_in_hdr=False`, `raw/cabeceras.txt`, líneas 73–84).

## 4. Criptografía, Entropía y Firmas

- **Cifrado de TOC**: Toda TOC externa (`[0x40..w04)`) presenta entropía Shannon `7.6043`–`7.9983` bits/byte (`raw/toc.txt`, §1).
- **Evidencia de modo (`raw/toc.txt`, §2–§3)**:
  - **0** repeticiones de bloques de 16 bytes dentro de ninguna TOC (`62,487` bloques analizados entre las 12 TOC externas y las 6 mayores TOC anidadas, incluyendo `13,736` bloques en `navmeshes @0x1000` y `12,200` en `packs @0x306000`).
  - **Primeros 32 bytes idénticos** (`5f08daabecbdd40258c3516807024c24fb9f756755ef4be458785bfed8aa6989`) en `[0x40..0x60)` en los 12 archivos externos y en RPF9 anidados, pese a diferir en `w04`, `w10..w17`, `w24` y `w28`.
  - **Refutación por XOR de cifrado de flujo / AES-CTR**: `C1 ^ C2` desde `0x60` da entropía `7.561`–`7.989` y `0.20%`–`0.39%` ceros (ruido uniforme, `raw/toc.txt`, §3).
  - En conjunto, la evidencia apunta a **cifrado por bloques encadenado (como AES-CBC con IV fijo)** sobre un prefijo plano idéntico de 32 bytes, y refuta ECB (que colisionaría en bloques repetidos/rellenados) y CTR con nonce fijo.
- **Cifrado del tráiler (`raw/toc.txt`, §5)**: `[EOF - w0c .. EOF)` tiene entropía `7.82`–`8.00` (tráileres completos), `0` duplicados intra-tráiler y colisión exacta de los primeros 16 bytes (`b7da7c1d963787c846fe15fd0e243364`) entre `appdata0` y `script` (ambos con `w24=2`).
- **Pruebas de claves RPF7 y candidatas (`raw/toc.txt`, §6)**:
  - Claves triviales y derivadas de cabecera AES-128/256 (ECB y CBC-IV0) fallan en `appdata0` (`266–313 / 800` ASCII imprimibles, entropía ~`7.74`).
  - Claves propietarias de RPF7: **no verificado** — las herramientas abiertas de RPF7 (`CodeWalker`, `RageLib`, `LibertyV`) no publican claves AES estáticas de GTA V en código fuente, sino que las extraen de `GTA5.exe` / `gta5keys.bin`, ausentes en este entorno.
- **Firmas (`raw/firmas.txt`, §1–§3)**:
  - Firmas solicitadas (`ISG1`, `OSG1`, `DXBC`, `RSC7`, `RDS5`, `DDS `, `RIFF`, `BINK`): **0 coincidencias exactas** en los 47 archivos.
  - Firmas reales observadas sin cifrar: `9FPR` (`RPF9` anidados, 19 ocurrencias anidadas), `KB2n` (video Bink 2 en `movies.head.bin @0x7000`, `@0x3b1000`, `movies.tail.bin @0x133610`, `@0x28a610`), `SGD5` (`shaders.head.bin @0x9000`), `LGID`/`LRSC`/`0DRP`/`CHKS` (recursos en `anim`, `data`, `levels`, `navmeshes`, `packs`) y miles de flujos zlib `78 da` válidos que descomprimen a `<?xml ... CDataFileMgr__ContentChangeSetGroups>`, `PSIN` y `0DRP`.

## 5. Tabla de Hipótesis

| ID | Hipótesis | Qué predice | Cómo se probó y evidencia | Resultado |
|---|---|---|---|---|
| H1 | RPF9 abre con cabecera en claro de 64 bytes y `w04` marca el fin de la TOC | Los datos no nulos de TOC van de `0x40` a `w04 - 1`, seguidos de ceros hasta `0x1000` | Medido en los 12 `.head.bin`; 10/12 tienen relleno `00` desde `w04`, y `appdata0`/`common` empaquetan payload #0 en `w04` (`raw/cabeceras.txt` §4) | **confirmada** |
| H2 | Un campo de cabecera guarda el tamaño total del archivo | Alguno de los 16 `u32` iguala `8,880` (`appdata0`), `6,642,192` (`common`) o `4,358,960` (`script`) | Reconstrucción exacta vía solapamiento y comparación contra los 16 `u32` (`raw/cabeceras.txt` §4, `size_in_hdr=False`) | **refutada** |
| H3 | La tabla de nombres vive en claro al final del archivo (`tail`) | Últimos 4 KB de `.tail.bin` / `appdata0` con baja entropía y rutas ASCII legibles | Entropía medida de `7.42`–`7.96` en últimos 4 KB (`raw/toc.txt` §5) y 0 rutas en claro; en su lugar apareció un tráiler cifrado de `w0c` bytes en `[EOF - w0c .. EOF)` | **refutada** (en claro al final) |
| H4 | `w0c` es la longitud del tráiler cifrado al final del archivo (candidato a tabla de nombres/metadatos) | `[EOF - w0c .. EOF)` va precedido de ceros y escala con `w24` | Medidos `4`–`3,886` ceros previos a `EOF - w0c` en 10/12 archivos externos, límite exacto en RPF9 anidados y colisión `b7da7c1d...` cuando `w24=2` (`raw/toc.txt` §5) | **confirmada** (ubicación/tamaño); **indeterminada** (rol semántico sin clave) |
| H5 | La TOC `[0x40..w04)` usa AES-ECB | Bloques de 16 bytes repetidos en TOC grandes por relleno o campos iguales | Revisados `62,487` bloques de 16 bytes en 12 TOC externas + 6 anidadas mayores: `0` duplicados intra-TOC (`raw/toc.txt` §2) | **refutada** |
| H6 | La TOC `[0x40..w04)` usa cifrado de flujo / AES-CTR con nonce fijo | El XOR de dos TOC (`0x60..`) muestra baja entropía y muchos ceros | `C1 ^ C2` en 4 pares da entropía `7.561`–`7.989` y `0.20%`–`0.39%` ceros (`raw/toc.txt` §3) | **refutada** |
| H7 | La TOC `[0x40..w04)` usa cifrado de bloques encadenado (ej. AES-CBC IV fijo) sobre prefijo plano de 32 bytes | Primeros 32 bytes (`0x40..0x5f`) idénticos entre archivos y divergencia desde `0x60` con `0` duplicados internos | Las 12 cabeceras externas y las anidadas comparten `5f08daab...` en `+0x40..+0x5f`, divergen en `+0x60` y tienen `0` duplicados intra-TOC (`raw/toc.txt` §2–§3) | **confirmada** (huella conductual); algoritmo/clave exactos **indeterminada** sin clave |
| H8 | `w24` es el conteo de entradas/nodos y `w08` separa una subtabla `[w08..w04)` indexada por entrada | `w04 - w08` escala linealmente con `w24` | Medido `w04 - w08 = ceil(10*w24/16)*16` en 10/30 cabeceras y ~9–18 B/`w24` en las 30 (`raw/cabeceras.txt` §3); estructura exacta inverificable sin clave | **indeterminada** (correlación fuerte, no verificable sin clave) |
| H9 | Los payloads internos del RPF9 van cifrados uniformemente | No hay cabeceras estándar ni flujos zlib legibles en payloads | Hallados `KB2n`, `SGD5`, `9FPR` anidados, `LRSC`/`0DRP` y >3,000 flujos zlib `78 da` que descomprimen a XML/`PSIN` (`raw/firmas.txt` §2–§3) | **refutada** (numerosos payloads van sin cifrar / solo zlib) |
| H10 | Las claves públicas de RPF7 descifran la TOC de RPF9 | Aplicar claves públicas AES de RPF7 produce campos legibles | No existen claves estáticas de GTA V en repositorios abiertos de RPF7 (`CodeWalker`/`RageLib`/`LibertyV`); claves triviales/de cabecera fallan (`raw/toc.txt` §6) | **indeterminada** (`no verificado` para clave propietaria RPF7) |
