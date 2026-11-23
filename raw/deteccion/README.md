# raw/deteccion — transcripciones del análisis de detección

Generadas por `tools/build_evidence.sh` (salvo `plugin-git-history.txt`, que se
generó con `git show` de solo lectura). No se ejecutó `agy.bin`.

Convención de offsets: en `.rodata` la dirección virtual coincide con el offset
de fichero, así que `0x64e76e2` se puede leer con `dd`/`agy_strings.py window`
directamente. En `.data` no: `0xd82b440` (global del CL) está en el offset de
fichero `0xd22b440`; el script `tools/agy_build_facts.py` hace el mapeo con los
`PT_LOAD` del ELF.

| Archivo | Contenido |
| --- | --- |
| `agy-hash.txt` | tamaño, md5 y sha256 del binario |
| `agy-build-facts.txt` | hechos de build: CL, literales del UA, `setHeaders`, telemetría, endpoints |
| `agy-ua-context.txt` | ventanas de contexto de las cadenas del User-Agent |
| `agy-ua-xrefs.txt` | referencias `lea` a esas cadenas dentro de `.text` |
| `agy-functions.txt` | direcciones de `userAgent`, `setHeaders` y `anthropicConverter` |
| `agy-endpoints-body.txt` | hosts, formatos de id y claves de `labels` |
| `agy-telemetry.txt` | endpoint de Play Log, Clearcut y flags de telemetría |
| `plugin-audit.txt` | auditoría `archivo:línea` de la fuente del plugin |
| `plugin-no-telemetry.txt` | ausencia de Clearcut/Play Log en `src` y en el `dist` de producción |
| `plugin-production.txt` | UA, `requestId`, `anthropic-beta` y parche de contenido en la copia instalada |
| `plugin-git-history.txt` | commits `6c5d9ae` (introduce el `cl`) y `e9085a7` (sube versión sin tocarlo) |

El binario auditado es:

```
273879752 bytes
md5    485ac1f779f3e0b8d5acc84868c49cdb
sha256 7b004d26c3fdea25a7c9d456de4bfaccef4be1e4cc7fd6db628859c5c941fa2d
```
