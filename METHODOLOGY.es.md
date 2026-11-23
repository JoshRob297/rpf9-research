# Metodología

[English](METHODOLOGY.md) · **Español**

## Regla de la evidencia

Toda afirmación numérica o estructural necesita:

1. el comando o script que la produjo,
2. su salida cruda en `raw/<tema>.txt`,
3. la referencia en el documento (`docs/RPF9.md`) con el archivo donde está la prueba.

Si un experimento falla, se guarda igual: `raw/` conserva los intentos, no solo los aciertos.

## Prohibido

- Deducir un formato "porque en GTA V era así" sin medirlo en RPF9.
- Rellenar campos con ceros porque el tamaño "cuadra".
- Presentar como hecho algo que dependa de una clave que no tenemos.
- Tocar los binarios de `samples/`: son de solo lectura, y su sha256 está en el manifiesto.

## Hipótesis y falsación

Cada hipótesis vive como una fila con: qué predice, cómo se prueba y resultado
(`confirmada`, `refutada`, `indeterminada`). Una hipótesis refutada vale tanto como una
confirmada y se documenta igual.

## Comparación con RPF7

El formato de GTA V es referencia de contraste, no plantilla. Se puede usar la herramienta
pública para *verificar nuestro método* contra un RPF7 conocido, pero ningún campo de RPF9
se hereda sin medición en las muestras.

## Fusionador multifuente

`tools/merge_index.py` es la única herramienta que cruza fuentes. Cada fuente declara su tipo
en la línea de comandos; lo que no encaja con ese tipo se escribe en `unrecognized` y la
corrida continúa. El orden de conflictos está fijado en el código y se copia tal cual en
`report.json`:

1. una ruta recuperada literalmente del payload (XML de montaje) gana sobre cualquier patrón;
2. mismo contenedor, ruta, offset y tamaño se fusionan sin marca;
3. misma ruta con offset o tamaño distinto queda como `conflict`; se conservan las versiones;
4. dos rutas distintas con el mismo hash quedan como `collision`;
5. sin ruta pero con identificador queda como `orphan`.

Las fuentes `hashes` son solo de referencia: comparan el SHA-256 con sal de las rutas
fusionadas y nunca agregan una entrada. La invocación histórica de dos posicionales y
`--skip` no cambian.

### Decisiones de diseño

- `streams.tsv`, `paths.tsv` e `ids.tsv` quedaron como logs de menciones en vez de
  redefinirse. Los conteos publicados se reproducen byte a byte; la vista normalizada va a
  `index.tsv`.
- El contenedor (`rpf`) es parte de la identidad porque los offsets son absolutos dentro de
  un contenedor. La misma ruta en otro contenedor es otra ubicación, no un conflicto.
- La regla (a) resuelve solo discrepancias de offset. Una discrepancia de tamaño en el mismo
  offset sigue siendo conflicto: la procedencia dice de dónde vino el nombre, no cuál tamaño
  es correcto.
- Las colisiones de hash se detectan re-hasheando las rutas fusionadas con la sal publicada;
  se reportan, nunca se usan para fusionar dos nombres.

## Entregables

- `tools/rpf9.py` — cabecera + intento de TOC, con `--json`.
- `tools/name_recover.py` — recuperación de nombres desde el payload, con procedencia.
- `tools/merge_index.py` — fusiona los JSON de tramos y fuentes heterogéneas; escribe
  `index.tsv` y `report.json` junto a los logs de menciones históricos.
- `docs/RPF9.md` / `docs/RPF9.es.md` — layout, campos, hipótesis, límites.
- `docs/INDEX.md` / `docs/INDEX.es.md` — cobertura del escaneo completo.
- `raw/` — transcripciones.
- `result.md` — estado del encargo al cerrar.
