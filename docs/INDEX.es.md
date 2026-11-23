# Cobertura del escaneo completo

[English](INDEX.md) · **Español**

El paquete son 208.5 GiB. Los **22 contenedores `.rpf`** suman 150.2 GiB; los otros 57.9 GiB son 57
archivos `.ttpf` que se midieron y se descartaron: cabecera `RDS5`, entropía de 7.97 bits por byte y
cero rutas recuperables. No es una omisión, es un resultado: sin llave no hay nada que extraer ahí.

De esos 150.2 GiB, el primer barrido leyó **123.0 GiB (81.9%)** en 68 tramos de 2.2 GB. Una pasada de
huecos leyó 13 de los 15 tramos que faltaban, y una pasada de cierre leyó los dos últimos: `core_bvh4`
(7.7 GiB, cortado en ocho piezas porque el archivo completo agotaba la memoria del contenedor) y un
tramo de `story000`. Los contenedores quedan **cubiertos por completo**.

- 92 tramos de 2.2 GB o menos, en tres rondas
- 2,235,084 streams recorridos
- **215,028 streams con nombre (9.62%)**
- **168,660 rutas únicas** y **511,526 identificadores únicos**
- 611,264 menciones de ruta en total

El porcentaje bajó de 11.89% a 9.62% porque los últimos 27.2 GiB eran densos en streams y pobres en
nombres: solo `core_bvh4` tiene 565,591 streams y nombra 12. Los conteos subieron; el porcentaje
siguió a los datos, no al revés.

## Cobertura por tipo de stream

| tipo | streams | con nombre | cobertura |
|---|---:|---:|---:|
| `sgd5_shader_dxbc` | 25,043 | 25,043 | **100.00%** |
| `xml` | 349 | 208 | 59.60% |
| `xml_chunk` | 510 | 115 | 22.55% |
| `rsc50` | 872,918 | 154,782 | 17.73% |
| `PSIN` | 18,590 | 1,129 | 6.07% |
| `raw` | 1,032,855 | 30,826 | 2.98% |
| `0DRP` | 284,819 | 2,925 | 1.03% |

Los shaders salen completos porque su cabecera guarda el nombre del programa en claro. Los `0DRP`
siguen cerrados: 285 mil contenedores y 2,925 nombres, contra 227 mil y 624 cuando solo había
corrido el primer barrido.

## Por contenedor

| archivo | streams | con nombre | rutas (menciones) | identificadores |
|---|---:|---:|---:|---:|
| `levels` | 1,086,499 | 62,743 | 6,692 | 447,622 |
| `core_bvh4` | 565,591 | 12 | 3,827 | 4 |
| `packs` | 144,364 | 16,634 | 166 | 917,698 |
| `story000` | 141,161 | 39,664 | 217,907 | 311,264 |
| `anim` | 130,509 | 64,785 | 367,190 | 3,547 |
| `navmeshes` | 90,304 | 96 | 95 | 231 |
| `shaders` | 29,248 | 25,050 | 7 | 25,043 |
| `data` | 28,509 | 4,700 | 4,639 | 84,675 |
| `shared_minigame000` | 5,074 | 163 | 158 | 3,195 |
| `textures` | 2,749 | 41 | 4 | 1,875 |
| `story000_script` | 2,632 | 0 | 0 | 0 |
| `shared_minigame000_bvh4` | 2,560 | 5 | 12 | 4 |
| `core_restofworld` | 2,371 | 386 | 56 | 6,166 |
| `script` | 1,057 | 0 | 0 | 0 |
| `common` | 954 | 226 | 8,261 | 8,399 |
| `audio` | 838 | 68 | 17 | 9,010 |
| `story000_restofworld` | 624 | 415 | 2,102 | 2,768 |
| `core_restofworld001` | 33 | 33 | 65 | 47 |
| `story000_bvh4` | 4 | 4 | 63 | 3 |
| `core_licenses_data` | 3 | 3 | 3 | 2 |
| `movies.rpf` | 0 | 0 | 0 | 0 |

## Dos resultados negativos, medidos sobre el archivo completo

`movies.rpf` no produjo un solo stream en sus **8.8 GiB enteros**, con las dos mitades leídas: todo lo
que contiene es Bink 2, sin streams zlib ni XML de montaje. El primer barrido solo había llegado al
52% del archivo, así que este resultado era parcial; la pasada de cierre lo completó.

`script.rpf` y `story000_script` sí tienen streams, pero ninguno con nombre. Los dos se leyeron
completos.

## Lo que había en el hueco

El primer barrido dejó 27.2 GiB en 15 tramos sin cortar. Leerlos, en dos rondas, añadió **745,407
streams**, de los cuales **37,941 tienen nombre**, más **13,446 rutas** y **311,342 identificadores**
que no estaban en el primer índice.

| archivo | lo que faltaba | lo que devolvió |
|---|---|---|
| `core_bvh4` | 7.73 GiB | 565,591 streams, 12 con nombre |
| `story000` | 6.44 GiB | 82,333 streams, 32,702 con nombre |
| `levels.rpf` | 4.30 GiB | 66,407 streams, 515 con nombre |
| `audio.rpf` | 4.30 GiB | 0 streams |
| `movies.rpf` | 3.93 GiB | 0 streams |
| `data.rpf` | 0.45 GiB | 28,509 streams, 4,700 con nombre |
| `shared_minigame000_bvh4` | 0.06 GiB | 2,560 streams, 5 con nombre |
| `appdata0`, `story000_bvh4`, `core_licenses_data` | < 1 MiB | 7 streams |

`data.rpf` no lo había recorrido nadie, y `core_bvh4` resultó lo contrario de lo que su tamaño sugiere:
un cuarto de los streams del paquete y una docena de nombres.

## Lo que estos números no dicen

Un stream con nombre **no** es una entrada de la tabla de contenidos. La TOC sigue cifrada y no se
decodificó: los nombres salen de los XML de montaje que viajan en claro dentro del payload. Por eso
la cobertura es del 11.89% y no del 100%: no hay método conocido para cerrar la brecha sin llave.

Tampoco hay correspondencia uno a uno entre nombre y bloque: varios streams pueden declarar la
misma ruta, y `paths.tsv` conserva todas las menciones con su offset absoluto para que eso se
pueda auditar.

## Qué forma tienen los nombres

No son rutas de sistema de archivos clásicas. Conviven tres formas:

```
pack:/get_out_walk_90.clip                       clips de animación
Tequesta/Perschars/Peds/Player/bk_lucia_...      modelos de personaje por zona
platform:/levels/americas/gameshapes/...          mallas de nivel
doorinfo/uidoors_TR_ABI_Airbase_Islands.pso.meta  metadatos de puertas
```

En `raw/muestra-rutas.txt` hay 20 ejemplos con su archivo y offset de origen.

## Verificar sin publicar los nombres

El índice completo no se publica: 168,660 rutas reconstruyen el manifiesto de contenido del
juego. Lo que sí se publica permite que cualquiera compare su extracción contra la nuestra.

```
raw/paths.sha256        155,214 hashes, ordenados   (primer barrido)
raw/ids.sha256          200,184 hashes, ordenados   (primer barrido)
raw/paths.v2.sha256     168,660 hashes, ordenados   (índice completo)
raw/ids.v2.sha256       511,526 hashes, ordenados   (índice completo)
raw/muestra-rutas-v2.txt  200 rutas con archivo y offset
raw/index.schema.json  columnas y conteos
```

El hash es `sha256("rpf9-research/2026-11" + "\t" + nombre)`. La sal es pública a propósito:
deja que dos partes comparen cobertura sin que ninguna revele un nombre.

Para comparar: corre `tools/name_recover.py` sobre los mismos tramos de tu propio paquete, toma
tus nombres únicos, aplica la misma sal, ordena y compara contra el archivo. Los hashes que
falten son streams que tu recorrido no alcanzó; los que sobren, nombres que no recuperamos.
Conteos, no contenidos.

## Reproducir

```
tools/name_recover.py <tramo.bin> --out <salida>.json     # un tramo de 2.2 GB
tools/merge_index.py <dir_tramos> <dir_salida> \
    --skip packs_1.json,packs_2.json,packs_3.json         # fusiona sumando las bases
```

Correr ambos sobre el mismo paquete reproduce los conteos de este documento: 92 tramos (68 en el
primer barrido, 13 en la pasada de huecos y 11 en la de cierre), 2,235,084 streams, 215,028 con
nombre y 168,660 rutas únicas.

## Relación con la geometría de la TOC

El paso de 9 o 10 bytes por entrada que documenta `docs/RPF9.md` —y el relleno de la región a
múltiplo de 16— es una medición distinta: describe el acomodo de la tabla, no la cobertura de
nombres. Aquí solo se reporta cuántos streams llevan nombre y de dónde salen.
