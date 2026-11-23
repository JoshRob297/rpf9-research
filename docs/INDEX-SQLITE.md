# Índice consolidado RPF9 con SQLite

`tools/index_full_sqlite.py` combina los archivos `{rpf}__{base}.json` de un
directorio y escribe `streams.tsv`, `paths.tsv`, `ids.tsv` y `summary.json`.
`base` se interpreta como entero decimal y cada offset de stream es relativo a
esa rebanada:

```text
abs_offset = base + stream.offset
```

## Uso

```bash
python3 tools/index_full_sqlite.py /ruta/a/rebanadas /ruta/a/salida
```

El comando requiere únicamente Python 3 y su biblioteca estándar. Por omisión
el archivo SQLite temporal es `<salida>/index.sqlite3` y se elimina tras
exportar correctamente. `--keep-db` lo conserva para inspección; `--db RUTA`
selecciona otra ubicación y `--quiet` desactiva el progreso por archivo.

## Reglas y esquema

Se procesan las rebanadas en orden ascendente por nombre de RPF y luego por
`base`. Se omiten `packs_1.json`, `packs_2.json`, `packs_3.json` y todas las
rebanadas cuyo RPF sea `packs_1`, `packs_2` o `packs_3`. Un stream es nombrado
si tiene al menos un elemento no vacío en `full_paths` o `identifiers`;
`status` no determina si está nombrado.

La base contiene tres tablas `WITHOUT ROWID`:

| Tabla | Clave primaria | Efecto |
|---|---|---|
| `streams` | `(rpf, abs_offset)` | `INSERT OR IGNORE` conserva la primera aparición y su metadato. |
| `paths` | `(ruta, rpf, abs_offset)` | Elimina menciones repetidas de la misma terna. |
| `ids` | `(identificador, rpf, abs_offset)` | Elimina menciones repetidas de la misma terna. |

Las menciones de rutas e identificadores se ingieren desde cada stream válido;
si hay offsets repetidos, las salidas de menciones conservan las ternas
distintas aunque la fila de `streams.tsv` sea la de la primera aparición.
`n_paths` y `n_ids` reflejan los elementos no vacíos de esa primera fila.
`offset_hex` se genera a partir del offset absoluto.

Los TSV tienen las cabeceras especificadas por el formato y se exportan con
`ORDER BY` sobre la clave primaria correspondiente. Los campos de texto escapan
barra invertida, tabulador y saltos de línea como `\\`, `\t`, `\n` y `\r`, de
modo que cada registro sigue ocupando una sola línea TSV.

`summary.json` informa los streams únicos, los nombrados, `cobertura_pct`,
`paths_unicos`, `path_mentions`, `ids_unicos`, `id_mentions`, el número de filas
de menciones deduplicadas y los agregados `por_contenedor` y `por_tipo`.
`path_mentions` e `id_mentions` cuentan menciones de entrada antes de deduplicar
ternas; `paths_unicos` e `ids_unicos` cuentan cadenas distintas.

## Memoria, disco y costo

No se carga el corpus entero en memoria. Se carga una rebanada JSON por vez y
las inserciones se envían en lotes (`--batch-size`, por defecto 10 000); SQLite
mantiene las tablas y sus índices en disco. El caché de páginas de SQLite está
limitado a 64 MiB y `temp_store=FILE` permite que operaciones temporales usen
disco. La memoria de Python es proporcional al JSON de la rebanada actual, los
lotes de inserción y el resumen pequeño por tipo/contenedor, no al total de
streams del corpus.

El costo dominante es escribir y mantener las tres claves primarias de SQLite,
y después leerlas ordenadas para exportar. No hay listas globales de streams,
rutas o IDs ni una ordenación externa: `ORDER BY` recorre los B-trees que ya
imponen el orden de salida. El tamaño temporal depende de la cantidad y longitud
de streams y menciones únicas; reservar espacio de disco para la base más los
cuatro archivos generados. El tiempo de ejecución depende principalmente del
disco y del número de menciones, además de los 2.24 millones de streams
estimados para el corpus completo.

La carga usa `journal_mode=OFF` y `synchronous=OFF` para acelerar la generación
de un artefacto reproducible. Una interrupción puede dejar una base temporal
incompleta; no debe considerarse salida válida. En una ejecución exitosa, los
TSV y el resumen se exportan antes de borrar esa base.

## Pruebas

```bash
python3 -m unittest -v tests/test_index_sqlite.py
```

Las pruebas sintéticas verifican deduplicación, orden, offsets, exclusiones y
esquema de las salidas. Si está disponible `/home/sistver/idx-fixtures`, se
ejecutan además la comparación contra un oráculo en memoria y la comprobación
de totales exactos del fixture.
