# Metodología

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

## Entregables

- `tools/rpf9.py` — cabecera + intento de TOC, con `--json`.
- `docs/RPF9.md` / `docs/RPF9.es.md` — layout, campos, hipótesis, límites.
- `raw/` — transcripciones.
- `result.md` — estado del encargo al cerrar.
