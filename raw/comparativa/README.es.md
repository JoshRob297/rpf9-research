# Evidencia de la comparación

[English](README.md) · **Español**

Transcripciones detrás de `docs/COMPARATIVA.md`. Se produjeron para la tarea `T-RPF9-COMPARA` y son
la única fuente de los números de esa página; aquí no se copió nada de una corrida de terceros.

## Archivos

```
psin_census.py     censo de chunks PSIN sobre las ventanas de muestra, en solo lectura
psin_census.txt    su salida: streams, formas, framing, layouts de cuerpo LSCH/LENM
nested_scan.py     escaneo de cabeceras anidadas, por pasos de 4 KiB vs byte a byte
nested_scan.txt    su salida para diez ventanas de muestra
```

Los dos scripts solo abren archivos para leer. Reciben rutas por línea de comandos y no escriben nada.

## Cómo se corrieron

```
python3 raw/comparativa/psin_census.py <directorio de muestras>   > raw/comparativa/psin_census.txt
python3 raw/comparativa/nested_scan.py <10 ventanas de muestra>   > raw/comparativa/nested_scan.txt
```

`psin_census.py` se apuntó al directorio de muestras del laboratorio, 78 ventanas `.bin` (19 `.head`
más 59 rebanadas `.q1`/`.q3`/`.tail`), 225,877,312 bytes en total. `nested_scan.py` recibió estos
diez archivos, en este orden:

```
core_restofworld.head.bin      core_restofworld001.full.bin   story000_bvh4.full.bin
core_licenses_data.full.bin    data.head.bin                  packs.head.bin
script.head.bin                common.head.bin                shaders.head.bin
textures.head.bin
```

## Qué son las muestras y qué no

Los binarios de muestra **no están en este repositorio** (`.gitignore`, `samples/*.bin`); solo su
manifiesto con hashes. Las dos transcripciones describen entonces una corrida sobre datos que quien
lea tiene que conseguir aparte, y los números solo son reproducibles sobre las mismas ventanas.

Cinco de las ventanas son archivos completos de unos pocos kilobytes; el resto son rebanadas de
4 MiB de archivos `.rpf` más grandes. Una rebanada puede cortar un contenedor, un miembro comprimido
o un stream `PSIN` por la mitad, y las transcripciones lo dicen donde importa: 107 streams `PSIN`
guardan un prefijo de 65,536 bytes cuyo último chunk declara un largo más allá del cuerpo inflado, y
quedan fuera de los conteos de layout en lugar de contarse como violaciones del formato.

`raw/` guarda la salida de los comandos tal cual se produjo. La cabecera de procedencia dentro de
cada `.txt` (comando, conjunto de muestras, qué hace el script, de dónde sale cada regla) se escribió
antes de la corrida y se conserva junto a la salida. Los scripts y los títulos de sección están en
inglés, igual que `raw/payload.txt` y `raw/cabeceras.txt`, para que las afirmaciones `ruta:línea` de
`docs/COMPARATIVA.md` se puedan comprobar contra ellas sin traducir.

## Qué sostiene cada transcripción

`psin_census.txt` sostiene, en `docs/COMPARATIVA.md`, la sección 1: el conteo de 4,066 streams, los
3,959 que terminan exactamente en el tamaño inflado (3,958 cadenas completas de siete chunks más la
variante PMAP), los 107 prefijos de 64 KiB, los cero chunks que declaran un largo menor que 8, las
ecuaciones exactas de cuerpo `LSCH` (3,983/3,983) y `LENM` (3,980/3,980), y el alcance 2,929/3,980 de
la lectura intercalada de `LENM`. La sección 3 imprime además los 23,829 sucesores; como el recorrido
avanza por ese largo, la fila del 100% es por construcción y los finales exactos son la evidencia
discriminante.

`nested_scan.txt` sostiene la sección 2: las diez ventanas, qué cabeceras encuentra cada escaneo y en
qué offset, la cabecera de `0xaa0` a la que solo llega el escaneo byte a byte, y el hecho de que las
seis ventanas de 4 MiB del censo no añaden ninguna cabecera desalineada.
