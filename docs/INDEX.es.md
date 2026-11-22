# Cobertura del escaneo completo

El barrido cubrió los **22 contenedores `.rpf`** del paquete: 150.2 GiB de los 208.5 GiB totales.
Lo que queda fuera son 57 archivos `.ttpf` (57.9 GiB) que se midieron y se descartaron: cabecera
`RDS5`, entropía de 7.97 bits por byte y cero rutas recuperables. No es una omisión, es un
resultado: sin llave no hay nada que extraer ahí.

- 71 tramos de 2.2 GB, procesados de uno en uno
- 1,489,677 streams recorridos
- **177,087 streams con nombre (11.89%)**
- **155,214 rutas únicas** y **200,184 identificadores únicos**
- 526,581 menciones de ruta en total

## Cobertura por tipo de stream

| tipo | streams | con nombre | cobertura |
|---|---:|---:|---:|
| `sgd5_shader_dxbc` | 25,043 | 25,043 | **100.00%** |
| `xml` | 332 | 191 | 57.53% |
| `rsc50` | 531,370 | 123,889 | 23.32% |
| `xml_chunk` | 504 | 109 | 21.63% |
| `raw` | 690,003 | 26,766 | 3.88% |
| `PSIN` | 15,380 | 465 | 3.02% |
| `0DRP` | 227,045 | 624 | 0.27% |

Los shaders salen completos porque su cabecera guarda el nombre del programa en claro. Los
`0DRP` siguen cerrados: 227 mil contenedores y 624 nombres.

## Por contenedor

| archivo | streams | con nombre | rutas (menciones) | identificadores |
|---|---:|---:|---:|---:|
| `anim.rpf` | 130,509 | 64,785 | 367,190 | 3,547 |
| `levels.rpf` | 1,020,092 | 62,228 | 6,448 | 447,167 |
| `shaders.rpf` | 29,248 | 25,050 | 7 | 25,043 |
| `packs.rpf` | 144,364 | 16,634 | 166 | 917,698 |
| `story000.rpf` | 58,828 | 6,962 | 142,012 | 3,208 |
| `story000_restofworld` | 624 | 415 | 2,102 | 2,768 |
| `core_restofworld` | 2,371 | 386 | 56 | 6,166 |
| `common.rpf` | 954 | 226 | 8,261 | 8,399 |
| `shared_minigame000` | 5,074 | 163 | 158 | 3,195 |
| `navmeshes.rpf` | 90,304 | 96 | 95 | 231 |
| `audio.rpf` | 838 | 68 | 17 | 9,010 |
| `textures.rpf` | 2,749 | 41 | 4 | 1,875 |
| `core_restofworld001` | 33 | 33 | 65 | 47 |
| `movies.rpf` | 0 | 0 | 0 | 0 |
| `script.rpf` | 1,057 | 0 | 0 | 0 |
| `story000_script` | 2,632 | 0 | 0 | 0 |

## Dos resultados negativos, medidos

`movies.rpf` no produjo un solo stream: todo su contenido es Bink 2, sin streams zlib ni XML de
montaje. `script.rpf` y `story000_script` sí tienen streams, pero ninguno con nombre.

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

El índice completo no se publica: 155,214 rutas reconstruyen el manifiesto de contenido del
juego. Lo que sí se publica permite que cualquiera compare su extracción contra la nuestra.

```
raw/paths.sha256       155,214 hashes, ordenados
raw/ids.sha256         200,184 hashes, ordenados
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
tools/name_recover.py <tramo.bin> --out <salida>.json    # un tramo de 2.2 GB
python3 merge_index.py                                   # fusiona sumando las bases
```

El índice fusionado (`streams.tsv`, `paths.tsv`, `ids.tsv`) **no se publica**: es un inventario de
contenido. Lo que se publica es la cobertura, el método y la muestra.

## Relación con la geometría de la TOC

El paso de 9 o 10 bytes por entrada que documenta `docs/RPF9.md` —y el relleno de la región a
múltiplo de 16— es una medición distinta: describe el acomodo de la tabla, no la cobertura de
nombres. Aquí solo se reporta cuántos streams llevan nombre y de dónde salen.
