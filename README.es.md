# rpf9-research

[English](README.md) · **Español**

Ingeniería inversa del contenedor **RPF9** usado por GTA VI (Xbox Series X|S), a partir de
un paquete de 209 GiB del que se tienen 22 archivos `.rpf` y 57 `.ttpf`.

## Qué sabemos antes de empezar

- La magia es `39 46 50 52` en los primeros cuatro bytes: `RPF9` leído como entero
  little-endian. GTA V usa `RPF7` (`37 46 50 52`).
- Los primeros bytes después de la magia no son texto ni una tabla legible: la región
  posterior parece cifrada (entropía alta, sin nombres en claro en los primeros 2 MB).
- En GTA V la tabla de contenidos de un RPF7 va cifrada con AES y las herramientas públicas
  (OpenIV, CodeWalker) conocen esa clave. Para RPF9 no hay herramienta pública.

## Objetivo

Determinar, con evidencia reproducible, **la estructura de la cabecera y de la tabla de
contenidos** de RPF9, y hasta dónde se puede llegar sin la clave. El resultado esperado es
un documento (`docs/RPF9.md`) más un prototipo (`tools/rpf9.py`) que:

1. lea la cabecera y explique cada campo con su medición,
2. diga si la TOC está cifrada y con qué evidencia (no por suposición),
3. liste entradas si logra descifrarla, o explique exactamente qué falta.

## Reglas del repositorio

- **Cada número que aparezca en la documentación debe tener su transcripción en `raw/`.**
  No se afirma nada que no esté medido.
- Lo que no se pueda determinar se escribe como **no determinado**, con la prueba que se
  intentó y falló.
- `raw/` guarda la salida de los comandos tal cual se produjo. Es evidencia y no se traduce.
- Los binarios de muestra **no se versionan** (ver `.gitignore`); solo su manifiesto con
  hashes.
- Documentación en pares: `docs/RPF9.md` (inglés) y `docs/RPF9.es.md` (español); igual con
  `docs/NAMES.md`, `docs/INDEX.md`, `docs/NESTED.md`, `docs/PSIN.md` y `docs/COMPARATIVA.md`.

Ver `METHODOLOGY.md`.

## Fusionar índices de orígenes distintos

`tools/merge_index.py` sigue aceptando la forma histórica, sin cambios:

```sh
tools/merge_index.py <dir_tramos> <dir_salida> --skip packs_1.json,packs_2.json,packs_3.json
```

La forma multifuente exige que cada origen declare su tipo; el fusionador no lo adivina:

```sh
tools/merge_index.py <dir_salida> \
    --source name_recover=<dir_o_json> \
    --source paths=<nombres.txt|nombres.json> \
    --source inventory-tsv=<inventario.tsv> \
    --source inventory-csv=<inventario.csv> \
    --source hashes=<paths.sha256>
```

| tipo | entrada | aporta |
|---|---|---|
| `name_recover` | JSON de `tools/name_recover.py` | streams, rutas, identificadores y offsets |
| `paths` | una ruta por línea, o `{"paths": [...]}` | rutas sin offset ni tamaño |
| `inventory-tsv` / `inventory-csv` | `archivo, offset, ruta` (`offset` decimal o `0x...`) | rutas con archivo y offset absoluto |
| `hashes` | lista de `sha256` con sal como `raw/paths.sha256` | solo compara cobertura; nunca fusiona |

Los conflictos se resuelven en este orden, que también se escribe en `report.json`:

1. Una ruta recuperada literalmente del payload (XML de montaje) gana sobre cualquier versión
   derivada de un patrón cuando discrepan en el offset.
2. La misma ruta, contenedor, offset y tamaño se fusionan en una entrada sin marca.
3. La misma ruta y contenedor con offset distinto, o el mismo offset con tamaño distinto,
   quedan como `conflict` con todas las versiones y el motivo. No se elige una.
4. Dos rutas distintas con el mismo hash quedan como `collision`.
5. Una entrada sin ruta pero con identificador queda como `orphan`.

Una discrepancia resuelta por la regla 1 igual se escribe en `conflict` con
`resolution: literal`; solo las entradas `unresolved` conservan más de una versión en
`index.tsv`.

`streams.tsv`, `paths.tsv` e `ids.tsv` conservan su significado anterior: el log de menciones
de las fuentes `name_recover`, para que los conteos de `docs/INDEX.md` sigan reproduciéndose.
`index.tsv` es el índice normalizado de rutas (una fila por versión, `estado=conflict` cuando
no se resolvió) y `report.json` guarda las listas `conflict`, `collision`, `orphan` y
`unrecognized` más los conteos por fuente. `--skip` sigue descartando archivos por nombre.

## Proyectos relacionados y qué responde este dato

Este repositorio mide un solo paquete retail. Estos proyectos consumen el mismo formato, y cada
uno necesita una parte distinta de lo que aquí se publica.

| proyecto | qué hace | qué le responde este repo |
|---|---|---|
| [ItsNotRexed/Leonida](https://github.com/ItsNotRexed/Leonida) | recompilación nativa a PC del build de Xbox | cobertura por archivo y por tipo (`docs/INDEX.md`), y 155k hashes con sal para comparar contra su propio recorrido |
| [penwin2000/open-vfs](https://github.com/penwin2000/open-vfs) | filesystem virtual para los contenedores | 22 fixtures de cabecera en cinco formatos (`raw/cabeceras/`) y la fórmula de la región de tabla, medida en 22 de 22 |
| [ivall/xcl](https://github.com/ivall/xcl) | capa de compatibilidad, shaders RDNA2 a DXIL | 25,043 streams `sgd5_shader_dxbc`, el 100% con nombre, frente a las cifras 24,064 y 26,503 publicadas en otros lados |
| [R0Y00/Xbox2Windows](https://github.com/R0Y00/Xbox2Windows) | investigación de recompilación estática | dónde viven los streams con textura por archivo, en conteos y sin nombres |
| [omonkeyz/xbox-emulator](https://github.com/omonkeyz/xbox-emulator) | notas de progreso para correr los builds | el mapa del contenedor, para que las notas apunten a offsets y no a nombres de archivo |

La regla es la misma para todos: hechos medidos y geometría, nunca el manifiesto de contenido.

`docs/COMPARATIVA.es.md` pone nuestras mediciones de PSIN, contenedores anidados y geometría de la
tabla al lado de tres implementaciones públicas de RPF9 (`rpf9-extract`, `PercyStar`, `rpf9`), leídas
y nunca ejecutadas, con una etiqueta `[verified]`/`[hypothesis]` en cada afirmación.

## Licencia

GPL-3.0-or-later.

El motivo es práctico: el trabajo de referencia más cercano, `ItsNotRexed/Leonida`, es
GPL-3.0 y publica hechos de formato medidos sobre este mismo paquete. Se pueden tomar los
hechos con atribución, pero si en algún momento se reutiliza código, esta licencia es la
única que lo permite sin conflicto. Los proyectos con GPL-2.0-only (`xcl`,
`americas-recomp`) y los de licencia no comercial (`PercyStar`) quedan como referencia de
lectura, nunca como fuente de código.

Ver también `docs/` para el estado medido del formato.
