# Recuperacion de Nombres en Payloads RPF9 (`tools/name_recover.py`)

## 1. Proposito y Alternativas Evaluadas

Dado que la TOC de cabecera (`[0x40..w04)`) y el trailer al final (`[EOF - w0c .. EOF)`) de RPF9 estan cifrados y no se dispone de la clave (`docs/RPF9.es.md` §5, H3/H7/H13), no es posible leer los nombres originales desde el directorio del contenedor. `tools/name_recover.py` recupera rutas e identificadores directamente desde los flujos sin cifrar del payload registrando su procedencia exacta.

Se evaluaron tres alternativas reales:

1. **Alternativa A — Escaneo unico `78 da` + regex generico**: Reutiliza el escaner `78 da` de `rpf9.py` con una sola expresion regular sobre todos los flujos inflados. *Descartada*: omite las `869` entradas de shaders `DXBC` dentro de `SGD5` (comprimidas con deflate crudo `wbits=-15`), mezcla etiquetas estructurales (`LSCH`, `LENM`, `0DRPz`) o ruido binario con identificadores reales y no distingue procedencia por fuente.
2. **Alternativa B — Extractor tipado multifuente (Elegida)**: Combina inflado de flujos zlib `78 da` (`xml`, `xml_chunk`, `PSIN`, `0DRP`, `rsc50`, `raw`) con parseo de simbolos `SGD5` + deflate crudo `DXBC` (`tools/name_recover.py`), aplicando extractores ordenados por fuente (`xml` -> `psin`/`0drp` -> `sgd5` -> `rsc50`/`raw_stream`), separando `full_paths` de `identifiers`, deduplicando candidatos y marcando todo flujo sin cadenas legibles como `status="unnamed"` (sin nombre). *Elegida*: maximiza la recuperacion real en tiempo lineal $O(n)$ sin inventar nombres.
3. **Alternativa C — Decodificador binario profundo (`RSC8`/`rsc50`/`AWC`/`LSNS`)**: Intenta decodificar paginas de recursos binarios y revertir hashes Jenkins/JOAAT. *Descartada*: `LSNS` dentro de `PSIN` es opaco/alta entropia, `AWC`/`rsc50` almacenan hashes sin diccionario en claro y `METHODOLOGY.md` prohibe asumir estructuras no verificadas.

## 2. Fuentes de Nombre (en orden de prioridad)

1. **XML inflados y fragmentos de continuacion (`xml`, `xml_chunk`)**:
   - Extrae rutas con prefijo (`$(var)/...`, `scheme:/...`) o extensiones objetivo (`ytd`, `ydr`, `yft`, `ybn`, `ymap`, `ytyp`, `ycd`, `awc`, `rpf`, `xml`, `meta`, `rel`, `dat`, mas `.bk2`/`.ityp`/`.clip`) en `full_paths`.
   - Extrae etiquetas de identidad (`<id>`, `<deviceName>`, `<dlcName>`, `<packFile>`, `<scriptName>`, `<audioBank>`, `<datFile>`, `<videoFileName>`, `<modelName>`, `<ModelName>`, `<filename>`, `<loadPath>`, `<exportPath>`, `<Name>`, `<name>`) y atributos (`href`, `filename`, `loadPath`, etc.) en `identifiers`, filtrando valores genericos o numericos.
   - Detecta fragmentos de continuacion de XML de 64 KiB (`xml_chunk`, `929` flujos) validando etiquetas de cierre XML (`</Tag>`).
2. **Contenedores `PSIN` y `0DRP` (`psin`, `0drp`)**:
   - Extrae cadenas terminadas en `\x00` limpias y rutas `scheme:/...`, excluyendo marcas del contenedor (`PSIN`, `LSCH`, `LENM`, `LSNS`, `LGID`, `LRSC`, `CHKS`, `0DRPz`) y dialogos/artefactos binarios.
3. **Tabla de simbolos `SGD5` (`sgd5`)**:
   - Localiza `[VDHGMCP]S_*_Wrapped\0` seguido de la cabecera de 17 bytes (`<u8 kind><u32 stored><u32 id><u32 stored2><u32 raw_size>`) y el flujo deflate crudo (`wbits=-15`) hacia `DXBC` (`shaders.head.bin @0x10e3e..`, `shaders.q1.bin @0x9100..`). Las entradas cortadas al borde de ventana se registran como `sgd5_shader_truncated` con `inflated_bytes=null`.
4. **Respaldo `rsc50` y `raw` (`rsc50`, `raw_stream`)**:
   - Captura referencias internas limpias cuando existen (ej. `pack:/...clip`, `audio:/config/waveslots2.xml`, `AMB_STREAM_*`, `AGC_Scan_*`); en caso contrario marca `status="unnamed"`.

## 3. Cobertura Medida (`raw/nombres.txt`)

Ejecucion sobre los **78** archivos de muestra en `/home/sistver/proyectos/rpf9-research/samples` (`raw/nombres.txt` §1–§2):

- **Flujos totales**: `17,082` (`16,213` zlib `78 da` + `869` entradas `SGD5`)
- **Flujos con nombre**: `1,509` (**8.83%**)
- **Flujos sin nombre (`unnamed`)**: `15,573` (**91.17%**)
- **Unicos deduplicados**: `13,402` rutas completas (`full_paths`), `14,282` identificadores (`identifiers`)
- **Menciones de extensiones objetivo**: `.rpf` (`7,592`), `.xml` (`221`), `.meta` (`142`), `.dat` (`15`); `.ytd`/`.ydr`/`.yft`/`.ybn`/`.ymap`/`.ytyp`/`.ycd`/`.awc` registraron `0` menciones en claro dentro de los XML muestreados (ademas de `.bk2` e `.ityp`).

| `stream_type` | Total | Con nombre | Sin nombre | Cobertura |
|---|---:|---:|---:|---:|
| `sgd5_shader_dxbc` | 867 | 867 | 0 | **100.00%** |
| `sgd5_shader_truncated` | 2 | 2 | 0 | **100.00%** |
| `xml` | 477 | 181 | 296 | **37.95%** |
| `xml_chunk` | 929 | 179 | 750 | **19.27%** |
| `rsc50` | 4,357 | 197 | 4,160 | **4.52%** |
| `raw` | 5,512 | 69 | 5,443 | **1.25%** |
| `0DRP` | 872 | 8 | 864 | **0.92%** |
| `PSIN` | 4,066 | 6 | 4,060 | **0.15%** |

Por archivo/paquete (`raw/nombres.txt` §2): los paquetes XML chicos completos (`core_licenses_data`, `core_restofworld001`, `story000_bvh4`) alcanzan **100.00%**; `shaders` llega a **83.24%** (`869/1,044`); `core_restofworld` **46.97%**; `story000_restofworld` **46.73%**; `common` **18.16%**; mientras `script` (`0/2,977`) y `story000_script` (`0/673`) quedan en **0.00%**.

## 4. Ejemplos Reales y Validacion Obligatoria en Payload (`raw/nombres.txt` §1, §3)

- **XML (`xml`)**: `common.head.bin @0xb000` (`comp=2568`, `inf=65536`) -> `full_paths=['$(common)/movies/ArcadeGames/BFYB_IDLE_SCREEN_BINK.bk2', ...]`, `identifiers=['core_binks']`.
- **Continuacion XML (`xml_chunk`)**: `common.head.bin @0xba10` (`comp=397`, `inf=8732`) -> `full_paths=['$(common)/movies/TV/SPRT/BSKT/R_GM_WIN_11.bk2', ...]`.
- **PSIN (`psin`)**: `data.head.bin @0x13000` (`comp=1138`, `inf=2568`) -> `identifiers=['TEMP_0653AU_AAAA', 'TEMP_0653_TEMP_1']`; `navmeshes.tail.bin @0x3cdb50` -> `identifiers=['ambrosiaraceway_dirtracerfinalemission', ...]`.
- **0DRP (`0drp`)**: `story000.head.bin @0xc5010` (`comp=7812`, `inf=131072`) -> `full_paths=['cutscene_exclusive/AIR_TRAIN_INT_PHONE.bk2']`; `story000.head.bin @0x212010` -> `identifiers=['CSC_DRT_FINALAU', ...]`.
- **SGD5 (`sgd5`)**: `shaders.head.bin @0x10e3e` (`comp=2321`, `inf=2640`) -> `identifiers=['VS_AlphaTransmissionFullScreenTri_4f16bf6c_Wrapped']`.
- **Sin nombre (`unnamed`)**: `anim.head.bin @0x6000` (`PSIN`), `anim.head.bin @0x14010` (`0DRP`), `common.head.bin @0x15770` (`xml`), `anim.q1.bin @0x91d6c` (`rsc50`).

`--validate` reinfla los flujos desde disco y comprueba la presencia exacta byte a byte en el payload (`raw/nombres.txt` §1, 6/6 verificados):
- `[xml] common.head.bin @0xb000 -> 'core_binks'` (`verified=True`, `payload_off=141`)
- `[psin] data.head.bin @0x13000 -> 'TEMP_0653AU_AAAA'` (`verified=True`, `payload_off=464`)
- `[0drp] story000.head.bin @0xbe010 -> 'cutscene_exclusive/AIR_TAIL_INT'` (`verified=True`, `payload_off=169584`)
- `[sgd5] shaders.head.bin @0x10e3e -> 'VS_AlphaTransmissionFullScreenTri_4f16bf6c_Wrapped'` (`verified=True`, `DXBC` 2,640 B verificado)
- `[rsc50] anim.q1.bin @0x5cd6c -> 'pack:/biped_q5'` (`verified=True`, `payload_off=304952`)
- `[raw_stream] anim.q1.bin @0x53b5c -> 'pack:/biped_q5'` (`verified=True`, `payload_off=39992`)

## 5. Limitaciones

- **Techo por TOC/Trailer cifrados**: Sin la clave AES de RPF9, el `91.17%` (`15,573/17,082`) de flujos sin cadenas en claro (cuerpo `LSNS` opaco en `PSIN`, directorios numericos `0DRP`, geometria/texturas `rsc50`, XMLs numericos de tuning) no puede asociarse a su ruta original en la TOC.
- **Nombres referenciados vs nombre propio del flujo**: Los XML de manifiesto (`CDataFileMgr__ContentChangeSetDef`) listan rutas *referenciadas* (`$(target)/data/credits/credits.rpf`) y no la ruta propia del XML dentro de la TOC (`content.xml`), y los `xml_chunk` solo contienen los nombres presentes en su segmento de 64 KiB.
- **Truncamiento en ventanas de muestra**: `2` entradas `SGD5` (`shaders.head.bin @0x3ff36c`, `shaders.q1.bin @0x1facd3`) y los flujos partidos al borde de ventanas de 2–4 MiB quedan incompletos en los recortes `.bin`.
- **Activos no comprimidos con zlib**: Los videos `KB2n` y bancos de audio `AWC` crudos quedan fuera del indice de flujos inflados de `name_recover.py`.

## 6. Comparacion contra el Enfoque por Offset de Leonida

Segun la referencia publica `ItsNotRexed/Leonida` (`docs/rpf.md`, `tools/rpf9_carve.py`, `tools/shader_carve.py`, licencia GPL-3.0):

| Dimension | Leonida (`rpf9_carve.py` / `rpf9dump`) | `rpf9-research` (`tools/name_recover.py`) |
|---|---|---|
| **Estrategia de nombres** | Asigna rutas sinteticas por offset (`recovered/...`, `off`) a todo flujo zlib tallado (`docs/rpf.md`); `shader_carve.py` usa `<name>\0` previo al DXBC en deflate crudo. | Extrae rutas e identificadores reales del payload inflado con procedencia explicita (`xml`, `psin`, `0drp`, `sgd5`, `rsc50`, `raw_stream`); marca el 91.17% restante como `unnamed`. |
| **Cobertura para extraccion** | 100% de los flujos zlib tallados reciben nombre de archivo unico en disco. | 8.83% global (100% en shaders `SGD5` y paquetes XML chicos, 37.95% en `xml`, 0% en `script`). |
| **Fidelidad semantica** | Los nombres por offset ubican fisicamente el recurso pero no revelan identidad del juego (salvo shaders en `shader_carve.py`). | Cada nombre emitido esta verificado dentro del payload real; separa `full_paths` de `identifiers` y no inventa nombres sinteticos. |
| **Complementariedad** | Ideal para exportacion masiva sin TOC y deduplicacion fisica por offset. | Ideal para indexar referencias semanticas reales, verificar evidencia en payload y anotar flujos previamente ubicados por offset. |
