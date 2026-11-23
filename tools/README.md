# tools — extracción y auditoría

Los scripts de la tabla son Python 3 (sin dependencias) y leen el binario y la
fuente sin ejecutar `agy.bin`. El binario se valida por md5 en
`agy_build_facts.py`. El worktree puede contener otros extractores en paralelo
(`agy_extract.py`, `plugin_surface.py`, `collect_evidence.sh`); esta tabla
describe la ruta que usa `build_evidence.sh`.

| Script | Qué hace |
| --- | --- |
| `agy_strings.py` | `find` / `window` / `strings` sobre el ELF; busca bytes y vuelca ventanas de contexto con offsets |
| `go_symbols.py` | parsea el `pclntab` de Go y lista funciones por regex (el binario está stripped) |
| `go_xrefs.py` | busca referencias `lea disp32(%rip)` a una dirección de `.rodata` dentro de `.text` |
| `agy_build_facts.py` | hechos del build 1.5.14: CL (cadena de relocación), literales del UA, `setHeaders`, telemetría, endpoints |
| `plugin_audit.py` | auditoría `archivo:línea` de la fuente del plugin; comprueba ausencia de telemetría y que `buildFingerprintHeaders` no se usa |
| `build_evidence.sh` | ejecuta todo lo anterior y vuelca las transcripciones en `raw/deteccion/` |

## Ejemplos

```bash
python3 tools/agy_build_facts.py
python3 tools/plugin_audit.py
python3 tools/go_symbols.py --grep "codeassistclient.userAgent"
python3 tools/go_xrefs.py --target 0x64468d7
python3 tools/agy_strings.py find "https://play.googleapis.com/log" --radius 300
python3 tools/agy_strings.py window --offset 0x6630453 --radius 400
```

## Notas de implementación

- `go_symbols.py` usa `TEXT_BASE = 0x72bf080` porque este PIE trae `textStart=0`
  en la cabecera del pclntab; el valor se verificó contra prólogos de funciones
  (`cmp 0x10(%r14),%rsp; jbe; push %rbp`).
- `go_xrefs.py` solo detecta `lea` con prefijo REX (`0x48..0x4f`) y ModRM
  RIP-relativo; no detecta cargas indirectas ni tablas de strings.
- `agy_build_facts.py` tiene direcciones fijas de este build. Si el md5 no es
  `485ac1f779f3e0b8d5acc84868c49cdb`, aborta con código 2.
- Los offsets de `.rodata` coinciden con la dirección virtual; los de `.data`
  (p. ej. el global del CL) se mapean con los `PT_LOAD` del ELF.
