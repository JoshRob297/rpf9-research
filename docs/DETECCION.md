# Detección del plugin `opencode-antigravity-auth` frente al CLI `agy` 1.5.14

Análisis diferencial de la petición real del plugin (OpenCode) contra la del CLI
oficial, con evidencia de archivo:línea y de cadenas extraídas del binario.

**Fecha:** 2026-11-23. **Alcance:** solo lectura; no se ejecutó `agy.bin`, no se
hizo tráfico de red y no se ejecutó ningún comando git de escritura.

---

## 0. Resumen ejecutivo

1. **El plugin ya no manda el User-Agent genérico.** La copia de producción
   (2.9.11) usa `antigravity/cli/<versión> (...)`, igual que el CLI. Pero el par
   `(versión, cl)` es imposible: la versión se actualiza en runtime y el `cl`
   está congelado en `962369648`, mientras que el build 1.5.14 tiene
   `cl=1027820220`. El par se puede comprobar con una regex en el servidor.
2. **Hay evidencia directa de que Google inspecciona el contenido de OpenCode.**
   El backend responde `429` solo si el literal `tools.opencode.session_move`
   aparece en `systemInstruction`; ningún otro `tools.opencode.*` lo dispara. El
   plugin lo neutraliza insertando un espacio. Es la única regla de detección
   *medida* y específica de OpenCode que tenemos.
3. **El body del plugin no tiene los campos/formatos que el CLI sí manda.**
   Falta `request.labels` (9 claves) y los identificadores no siguen el formato
   del CLI: el plugin manda `requestId: "agent-<uuid>"` y un `sessionId`
   compuesto `-<uuid>:<model>:<project>:<conversation>`.
4. **El CLI manda telemetría y el plugin no.** El binario contiene el cliente
   Clearcut de Play Log y el endpoint `https://play.googleapis.com/log`; la ayuda
   del flag `--disable_telemetry` implica que está activa por defecto. En el
   plugin no hay una sola referencia a Clearcut/Play Log.
5. **El header `anthropic-beta` no coincide en valor.** El plugin manda
   `interleaved-thinking-2025-05-14`; el CLI construye
   `thinking-binding-controls-2026-08-01`.
6. **La hipótesis del `deviceId` aleatorio no aplica a 2.9.11.** El plugin genera
   `deviceId` y `sessionToken`, pero nunca los envía: `buildFingerprintHeaders`
   no tiene llamadas. La hipótesis de "plataforma darwin/win32 desde Linux"
   tampoco aplica al `sgen` actual; solo sobrevive en el `Client-Metadata` de
   `loadCodeAssist`, que dice `MACOS` en Linux.
7. **No se puede atribuir estáticamente la suspensión a un vector.** Lo que sigue
   es un inventario de diferencias observables, un ranking razonado y experimentos
   para confirmar cada una. Ninguna recomendación promete evasión.

---

## 1. Método, fuentes y convenciones

### 1.1 Fuentes

| Fuente | Versión / identidad | Uso |
| --- | --- | --- |
| `agy.bin (copia local)` | 273 879 752 bytes; md5 `485ac1f779f3e0b8d5acc84868c49cdb`; sha256 `7b004d26…c941fa2d`; ELF x86-64 Go, build 1.5.14 | cadenas, pclntab, desensamblado, CL |
| `árbol fuente del plugin 2.9.11` | 2.9.11 | lógica del plugin |
| `paquete instalado 2.9.11` | 2.9.11 (`dist/`) | copia que corre en producción |
| `docs/AGY-CONTRACT.md` del repo del plugin | medición de `agy` 1.5.11 (MITM y replays) | única captura real de headers/body del CLI |

### 1.2 Convención de referencias

- `P:src/...:línea` — fuente del plugin.
- `D:dist/...:línea` — copia de producción compilada.
- `B:0x...` — offset de fichero del binario. En `.rodata` coincide con la
  dirección virtual, así que se puede leer directo.
- `M:docs/AGY-CONTRACT.md:línea` — medición previa de 1.5.11.
- `RAW:raw/deteccion/...` — transcripción reproducible.

### 1.3 Qué es medición y qué es inferencia

- **Medido en 1.5.11** (AGY-CONTRACT): el User-Agent completo, el body de una
  petición `200`, la ausencia de cabeceras `x-goog-*`/`x-sherlog-*` en
  `:streamGenerateContent`, el `Transfer-Encoding: chunked`, y la regla del
  literal de OpenCode.
- **Extraído del binario 1.5.14** (este trabajo): el `cl` del build, las piezas
  del User-Agent, `setHeaders`, `anthropic-beta`, la telemetría, los endpoints y
  las claves del body.
- **Inferido**: el orden exacto de los parámetros del UA en 1.5.14 (se toma de la
  captura de 1.5.11; las piezas y el formato son los mismos), el uso que Google
  da a cada diferencia y el peso de cada vector.

### 1.4 Reproducción

```bash
cd orca/workspaces/rpf9-research/task-t-re-detect
python3 tools/agy_build_facts.py          # CL, UA, setHeaders, telemetría
python3 tools/plugin_audit.py             # archivo:línea del plugin
./tools/build_evidence.sh                 # vuelca raw/deteccion/
python3 tools/go_symbols.py --grep userAgent
python3 tools/go_xrefs.py --target 0x64468d7
python3 tools/agy_strings.py find "aidev_client" --radius 300
```

El binario se verifica por md5 antes de usar direcciones fijas. Si cambia, los
scripts fallan en vez de dar una respuesta silenciosamente equivocada.

---

## 2. La petición real del plugin (producción 2.9.11)

### 2.1 Endpoint y método

En producción, el plugin intercepta la petición de OpenCode al proveedor
`google` (`@ai-sdk/google`, `P:README.md:472-474`) y la reescribe:

```
POST https://daily-cloudcode-pa.googleapis.com/v1internal:streamGenerateContent?alt=sse
Authorization: Bearer <access_token>
```

- El host del primer intento es `ANTIGRAVITY_ENDPOINT_FALLBACKS[0]`, es decir
  `https://daily-cloudcode-pa.googleapis.com` (`P:src/constants.ts:37,47-51`;
  `P:src/plugin.ts:2014`; `P:src/v2/adapter.ts:839`).
- El orden de fallback es daily directo → prod → sandbox
  (`P:src/constants.ts:47-51`). El `ANTIGRAVITY_ENDPOINT` por defecto sigue siendo el
  sandbox (`P:src/constants.ts:65`), pero los dos caminos de producción pasan el
  host diario como `endpointOverride`.
- La URL se construye en `P:src/plugin/request.ts:975`:
  `` `${baseEndpoint}/v1internal:${rawAction}${streaming ? "?alt=sse" : ""}` ``.

### 2.2 Cabeceras

El plugin parte de las cabeceras que le entrega OpenCode/AI SDK y las modifica:

| Cabecera | Valor / acción | Evidencia |
| --- | --- | --- |
| `Authorization` | `Bearer <access_token>` | `P:src/plugin/request.ts:945` |
| `User-Agent` | `antigravity/cli/<versión> (aidev_client; os_type=linux; arch=amd64; cl=962369648; auth_method=consumer)` | `P:src/constants.ts:99-101`; `P:src/plugin/request.ts:1815-1816` |
| `Accept` | `text/event-stream` si es streaming | `P:src/plugin/request.ts:1790` |
| `anthropic-beta` | `interleaved-thinking-2025-05-14` en modelos Claude con thinking | `P:src/plugin/request.ts:1796-1804` |
| `Content-Type` | No lo fija el plugin; lo hereda del AI SDK | `P:src/plugin/request.ts:927` |
| `x-api-key` | Se borra | `P:src/plugin/request.ts:946` |
| `x-goog-api-key` | Se borra (lo inyecta OpenCode con una API key inválida) | `P:src/plugin/request.ts:950` |
| `x-goog-user-project` | Se borra (provoca 403 de licencia) | `P:src/plugin/request.ts:954` |

Consecuencia importante: el plugin **no enumera** las cabeceras que añade
OpenCode. Solo borra tres. Cualquier otra cabecera del AI SDK/OpenCode que no
esté en esa lista viaja tal cual. Esto es un vector residual, no una certeza:
no se puede saber desde las rutas nombradas qué manda exactamente el proveedor
`@ai-sdk/google` en esta versión de OpenCode.

En `loadCodeAssist` (descubrimiento de proyecto) el plugin usa otras cabeceras:

| Cabecera | Valor | Evidencia |
| --- | --- | --- |
| `User-Agent` | `antigravity` (sin versión) | `P:src/plugin/project.ts:131` |
| `X-Goog-Api-Client` | `google-cloud-sdk vscode_cloudshelleditor/0.1` | `P:src/plugin/project.ts:132` |
| `Client-Metadata` | `{"ideType":"ANTIGRAVITY","platform":"MACOS","pluginType":"GEMINI"}` en Linux | `P:src/plugin/project.ts:133`, `P:src/constants.ts:115-121` |

`Client-Metadata` dice `MACOS` en cualquier host que no sea `win32`
(`P:src/constants.ts:119`); en Linux es una incoherencia explícita.

### 2.3 User-Agent exacto

El constructor es `getAntigravityCliUserAgent()`:

```ts
`antigravity/cli/${getAntigravityCliVersion()} (aidev_client; os_type=linux; arch=amd64; cl=962369648; auth_method=consumer)`
```

- `P:src/constants.ts:99-101`; copia de producción idéntica en
  `D:dist/src/constants.js:86`.
- La versión es dinámica: fallback `1.5.8` (`P:src/constants.ts:93`), y al
  arrancar se consulta el auto-updater del CLI
  (`P:src/plugin/version.ts:31`). Si el fetch funciona, la versión pasa a la que
  publique el updater (probablemente 1.5.14); el `cl` no cambia nunca.
- `os_type=linux` y `arch=amd64` están **hardcodeados**, no se derivan de
  `process.platform`/`process.arch`.

Valores posibles en producción:

```
antigravity/cli/1.5.8 (aidev_client; os_type=linux; arch=amd64; cl=962369648; auth_method=consumer)
antigravity/cli/1.5.14 (aidev_client; os_type=linux; arch=amd64; cl=962369648; auth_method=consumer)
```

El primero es el fallback si el updater no responde; el segundo es el caso en que
la versión se actualiza pero el `cl` no. Ninguno puede coincidir con el CLI real
(§3.2).

### 2.4 Body: forma y campos

La ruta normal (body no envuelto) construye:

```json
{
  "project": "<managedProjectId | rising-fact-p41fc | <adj>-<noun>-<5hex>>",
  "model": "<modelo con tier, p.ej. gemini-4-argon-medium>",
  "request": {
    "contents": [ ... ],
    "systemInstruction": {
      "role": "user",
      "parts": [{ "text": "You are Antigravity, ...\n\n<system de OpenCode>" }]
    },
    "tools": [ ... ],
    "safetySettings": [ ... ],
    "generationConfig": { ... },
    "sessionId": "-<uuid>:<model>:<project>:<conversation>"
  },
  "requestType": "agent",
  "userAgent": "antigravity",
  "requestId": "agent-<uuid>"
}
```

Evidencia:

- `wrappedBody` y los tres campos de identidad: `P:src/plugin/request.ts:1765-1774`.
- `request.sessionId`: `P:src/plugin/request.ts:1776-1779`.
- `sessionId` compuesto: `P:src/plugin/request.ts:87` y `P:src/plugin/request.ts:93-108`
  (`-${uuid}` + `:model:project:conversation`).
- `safetySettings` inyectados si no vienen y el modelo no es Claude:
  `P:src/plugin/request.ts:1707-1708`.
- `project` resuelto por `ensureProjectContext` (`P:src/plugin/project.ts:236-308`),
  con fallback `rising-fact-p41fc` (`P:src/constants.ts:70`) y, si no hay nada,
  un id sintético `adj-noun-xxxxx` (`P:src/plugin/request.ts:831-838`).
- Prefijo del system instruction: `P:src/constants.ts:264` y
  `P:src/plugin/request.ts:1718-1744`.
- El `model` del request se borra y se mueve al nivel superior:
  `P:src/plugin/request.ts:1702-1704` (`if ("model" in requestPayload)`).

### 2.5 Qué campos son de OpenCode y qué son del contrato Antigravity

| Campo / capa | Origen | Qué hace el plugin |
| --- | --- | --- |
| `contents` | OpenCode / AI SDK | sanea tool pairing, thinking blocks, poda respuestas históricas |
| `tools` | OpenCode / AI SDK | endurece descripciones para Claude, corrige esquemas, placeholders |
| `systemInstruction` (texto) | OpenCode + plugin | antepone `ANTIGRAVITY_SYSTEM_INSTRUCTION`; el catálogo `# Code Mode` y la pista del worktree son de OpenCode |
| `generationConfig` | OpenCode / AI SDK + plugin | el plugin fuerza `thinkingLevel`/`thinkingBudget`, `maxOutputTokens`, etc. |
| `safetySettings` | plugin | no aparece en el body medido del CLI 1.5.11 |
| `project` | Antigravity (`loadCodeAssist`) o fallback del plugin | el CLI usa su propio proyecto |
| `model` | plugin (`model-resolver`) | id con tier, igual que el CLI |
| `requestType`, `userAgent` | contrato Antigravity | el plugin los fija a `agent` / `antigravity` para imitar |
| `requestId`, `sessionId` | plugin | formatos sintéticos propios |
| `labels` | CLI | el plugin no los manda |
| `x-api-key`, `x-goog-api-key`, `x-goog-user-project` | OpenCode / AI SDK | el plugin los borra |

El catálogo `# Code Mode` de OpenCode es la parte que Google ya demostró que
inspecciona (§5.1): en el body real del plugin aparecía dos veces, y el backend
respondía 429 por el literal `tools.opencode.session_move`.

### 2.6 Lo que el plugin genera pero no envía

- `deviceId`: UUIDv4 aleatorio (`P:src/plugin/fingerprint.ts:84-86`).
- `sessionToken`: 16 bytes aleatorios en hex (`P:src/plugin/fingerprint.ts:88-90`).
- `buildFingerprintHeaders()`: definido en `P:src/plugin/fingerprint.ts:159-167`,
  **sin ninguna llamada** en `src/` (tests excluidos). El único uso del
  fingerprint es un log en `P:src/plugin.ts:1984`.

Por tanto, en 2.9.11 el `deviceId` y el `sessionToken` **no están en la petición
HTTP**. Cualquier hipótesis que los ponga en el wire es falsa para esta versión.

### 2.7 Peticiones adicionales

- Warmup de thinking para Claude: `P:src/plugin/request.ts:1840-1855`
  (`"Warmup request for thinking signature."`), invocado desde
  `P:src/plugin.ts:1921`. Es una petición `sgen` extra; no hay evidencia de que el
  CLI haga este warmup (no se midió su flujo para ello).
- Reintentos/fallback por host: `P:src/plugin.ts:2007-2014`.
- Consultas de cuota/modelos con el UA del CLI:
  `P:src/plugin/quota.ts:182-215`, `P:src/plugin/search.ts:295-296`.
- Fetch de versión al auto-updater del CLI: `P:src/plugin/version.ts:31`.

---

## 3. La petición del CLI `agy` 1.5.14

### 3.1 Endpoint y método

El CLI usa el host diario (`https://daily-cloudcode-pa.googleapis.com`,
`B:0x6681b6d`) y el path `/v1internal:streamGenerateContent?alt=sse`
(`B:0x65bb152` para `/v1internal:`, `B:0x65a3580` para
`streamGenerateContent`). El método es POST y el body va con
`Transfer-Encoding: chunked` (medido en 1.5.11, `M:docs/AGY-CONTRACT.md:15-18`).

`CodeAssistClient.setHeaders` (`B:0x95df3e0`) fija:

| Cabecera | Valor | Evidencia |
| --- | --- | --- |
| `User-Agent` | UA del CLI | `B:0x95df449` → `0x64b054d` |
| `Content-Type` | `application/json`, solo si el método es POST | `B:0x95df656` → `0x64e7682`, `0x65448cc` |
| `X-Goog-Request-Reason` | Condicional: solo si el request lleva un `reason` no vacío | `B:0x95df579` → `0x65a3739` |

No hay una cabecera `X-Goog-Api-Client` ni `Client-Metadata` en el binario. La
única `client-metadata` en minúsculas es la URL de metadatos OAuth
`https://antigravity.google/oauth/client-metadata.json` (`B:0x66c6488`), no una
cabecera. La única `x-goog-api-client` en minúsculas está en descriptores de
protobuf y en el SDK `genai`, no en `setHeaders`.

`Authorization` no se ve en `setHeaders`; debe añadirla otra capa (transporte o
interceptor de autenticación, no localizada en este análisis). El plugin también
la añade.

Otras cabeceras propietarias que existen en el binario pero **no** están en
`setHeaders` (pertenecen a otras rutas: proxy, aicode, remote control, sherlog):

| Cadena | Offset | Ruta probable |
| --- | --- | --- |
| `x-cloudaicompanion-trace-id` | `B:0x6603e38` | trazas de `streamGenerateContent` |
| `X-Aicode-Request-Id` | `B:0x657f4f8` | Business AI Code / AICode |
| `X-Jetski-Via-Remote-Control` | `B:0x6604003` | remote control |
| `goog-originating-service-id` | `B:0x6603f2b` | rutas internas |
| `x-goog-sherlog-Link` | `B:0x657f499` | sherlog / proxy de depuración |
| `X-Goog-User-Project` | `B:0x657f486` | proyecto de usuario (AICode) |

Que una cadena exista en el binario no significa que se mande en `sgen`: la
medición de 1.5.11 (`M:docs/AGY-CONTRACT.md:30-32`) no vio `x-goog-*` ni
`x-sherlog-*` en esa ruta.

Para modelos Claude, `anthropicConverter.ToRequestPayload` (`B:0x95e1e80`)
construye un mapa con:

```
anthropic-beta: thinking-binding-controls-2026-08-01
```

Evidencia: clave en `B:0x6518da7` (14 bytes), valor de 36 bytes en
`B:0x665cdbf`, referencia `lea` en `B:0x95e1fd1`.

### 3.2 User-Agent exacto del build 1.5.14

La cadena se compone en `codeassistclient.userAgent` (`B:0x95de840-0x95df3e0`)
con estas piezas:

| Pieza | Offset | Uso |
| --- | --- | --- |
| `antigravity` | `B:0x64cbbc3` | nombre del producto |
| `os_type=%s` | `B:0x64b052f` | sistema operativo real |
| `arch=%s` | `B:0x6466a71` | arquitectura real |
| `aidev_client` | `B:0x64e76e2` | tipo de cliente |
| `cl=%d` | `B:0x64468d7` | changelist del build |
| `auth_method=%s` | `B:0x6518d7d` | método de autenticación |
| `; ` | `B:0x6432ad2` | separador de parámetros |
| `%s/%s (%s)` | `B:0x64b0543` | formato final |

Las referencias `lea` caen todas dentro de `userAgent`:

```
0x95de92d -> os_type=%s
0x95de97b -> arch=%s
0x95dea28 -> aidev_client
0x95deabc -> cl=%d
0x95debae -> auth_method=%s
0x95df35c -> %s/%s (%s)
```

El `cl` se obtiene así:

1. El global `0xd82b440` es un string header `{ptr, len}`; el puntero se rellena
   por una relocación `R_X86_64_RELATIVE` con addend `0x6ff2a90` y longitud 10.
2. En `0x6ff2a90` está la cadena `1027820220`.
3. El código hace `strconv.Atoi` (`0x95dea6d`) y formatea `cl=%d`
   (`0x95deabc`). Si el `Atoi` falla o el valor es ≤ 0, usa `3`.

Comprobación directa:

```text
$ readelf -rW agy.bin | grep d82b440
000000000d82b440  0000000000000008 R_X86_64_RELATIVE  6ff2a90
$ # 10 bytes en 0x6ff2a90:
1027820220
```

La primera entrada del changelog embebido es `## 1.5.14` (la cadena `1.5.14` está en
`B:0x6f3991e`), consistente con la versión del encargo. El UA reconstruido para este build es:

```
antigravity/cli/1.5.14 (aidev_client; os_type=linux; arch=amd64; cl=1027820220; auth_method=consumer)
```

Notas:

- `os_type` y `arch` son los del runtime; este binario es Linux/amd64.
- `auth_method=consumer` es el modo OAuth de consumidor. Otros modos
  (enterprise/ADC) pueden cambiar ese valor.
- El orden de los parámetros se toma de la captura de 1.5.11 (`M:docs/AGY-CONTRACT.md:27`); el
  binario 1.5.14 contiene las mismas piezas y el mismo formato. El desensamblado
  muestra el orden de las llamadas a `Sprintf` (`os_type`, `arch`, `aidev_client`,
  `cl`, `auth_method`), que no es el orden final del string; el orden final es el
  de la captura. Lo que importa aquí son las piezas y el `cl`.

### 3.3 Body del CLI

La captura de 1.5.11 (`M:docs/AGY-CONTRACT.md:44-69`) muestra:

```json
{
  "project": "aicode-consumers",
  "requestId": "agent/513023f7-.../1795031044589/b55ec3f4-.../1",
  "request": {
    "contents": [ ... ],
    "systemInstruction": { "role": "user", "parts": [{ "text": "..." }] },
    "tools": [ ... ],
    "labels": {
      "cascade_id": "...",
      "root_cascade_id": "...",
      "trajectory_id": "...",
      "request_id": "...-0",
      "last_step_index": "0",
      "model_enum": "MODEL_PLACEHOLDER_M418",
      "used_claude": "false",
      "used_claude_conservative": "false",
      "used_non_gemini_model": "false"
    },
    "generationConfig": { ... },
    "sessionId": "..."
  },
  "model": "gemini-4-argon-medium",
  "userAgent": "antigravity",
  "requestType": "agent"
}
```

Las claves de `labels`, `MODEL_PLACEHOLDER_*`, `requestType` y los formatos de id
siguen presentes en el binario 1.5.14:

- `root_cascade_id` `B:0x652fd79`; `last_step_index` `B:0x652fd6a`;
  `used_non_gemini_model` `B:0x65a4f2d`;
  `MODEL_PLACEHOLDER_M0` `B:0x6592248`.
- Formato de id con barras `%s/%s/%d/%s` en `B:0x64cd2f7`, junto al literal
  `agent`, consistente con `agent/<uuid>/<ms>/<uuid>`.

No se re-midió el body de 1.5.14; se usa la captura de 1.5.11 como medición y el
binario 1.5.14 como evidencia de que las claves siguen ahí.

### 3.4 Telemetría

El binario contiene una pila completa de telemetría de Play/Clearcut:

| Evidencia | Offset |
| --- | --- |
| `https://play.googleapis.com/log` | `B:0x6630453` |
| `--disable_telemetry` (flag y ayuda) | `B:0x657f3ee`, `B:0x6660363` |
| `datacollection_opt_in=false` | `B:0x6603ebf` |
| `antigravity_ide_installation_id` | `B:0x6630491` |
| protos `clearcut_go_client_telemetry` | `B:0x280a268` y siguientes |
| `clearcut.Client` | `B:0xc2cc1c9`, `B:0xc422af3`, `B:0xc4dba9c` |

La cadena de ayuda de la UI dice que el ajuste de animación/telemetría queda
"overridden by `--disable_telemetry`", lo que implica que la telemetría está
activa por defecto y que el flag la desactiva. El `datacollection_opt_in=false` aparece además como
parámetro opcional del User-Agent (`B:0x95dec76`: solo si el flag booleano es
verdadero).

No se puede demostrar estáticamente que esa telemetría se una a la cuenta OAuth
ni que Google la use para detectar al plugin. Lo que sí está demostrado es que el
CLI tiene el canal y el plugin no.

**Identificadores de instalación/dispositivo.** El body de `sgen` no lleva un
`deviceId`. Los modelos de telemetría sí llevan `installation_id` como string
(`ProductEvent`, `B:0x6ead220`; `AntigravityExtension`, `B:0x67fd20b`), y la clave
de settings `antigravity_ide_installation_id` (`B:0x6630491`) es donde se
persiste. El binario no muestra un formato impuesto para ese valor (no hay regex
ni literal UUID asociado en las inmediaciones), así que **el formato exacto no se
pudo determinar**; es un string opaco, no necesariamente un UUIDv4 como el
`deviceId` del plugin.

No se localizó una ruta de latido separada de `/log`; los eventos de telemetría
van a `https://play.googleapis.com/log`.

### 3.5 Pila TLS/HTTP

- El binario es Go 1.28 con `boringcrypto` (`go buildinfo`:
  `go1.28-20261102-RC01 cl/1012564305 +298f53e483 X:fieldtrack,boringcrypto`).
- El cliente HTTP es `net/http` (Go; HTTP/2 por defecto en HTTPS, con soporte
  ALPN HTTP/1.1 visible en el binario: `tls_handshake`, `x509_hostname`,
  `ALPN_PROTOCOL_HTTP1_1`).
- El plugin corre dentro de OpenCode, que usa Bun como runtime (el plugin se
  carga como módulo de OpenCode; `P:README.md:472-474` configura
  `@ai-sdk/google`). Bun usa su propia pila TLS/HTTP, no la de Go.

La diferencia de pila es segura; el valor exacto de JA3/JA4, ALPN, `SETTINGS` de
HTTP/2, orden de cabeceras y `Accept-Encoding` **no se puede determinar
estáticamente**. Hay que capturarlo (§5.5).

---

## 4. Tabla diferencial campo por campo

Leyenda de estado: **IGUAL** (mismo valor en el wire), **DISTINTO** (ambos lo
mandan, no coincide), **AUSENTE** (el CLI lo manda, el plugin no), **SOBRANTE**
(el plugin lo manda, el CLI no), **CONDICIONAL** (depende de ruta/config),
**N/D** (no determinable estáticamente).

| # | Campo | Plugin 2.9.11 | CLI 1.5.14 | Estado | Evidencia |
| --- | --- | --- | --- | --- | --- |
| 1 | Host de `:streamGenerateContent` | `daily-cloudcode-pa.googleapis.com` (primer intento) | `daily-cloudcode-pa.googleapis.com` | **IGUAL** | `P:src/constants.ts:37,47-51`; `P:src/plugin.ts:2014`; `B:0x6681b6d`; `M:docs/AGY-CONTRACT.md:76-78` |
| 2 | Orden de fallback de host | daily → prod → sandbox | Sin bucle equivalente medido; el binario tiene preprod/autopush/sandbox | **DISTINTO** (patrón) | `P:src/constants.ts:47-51`; `B:0x6603eda,0x66d79ea,0x66c174a` |
| 3 | Método y path | `POST /v1internal:streamGenerateContent?alt=sse` | igual | **IGUAL** | `P:src/plugin/request.ts:975`; `B:0x65bb152,0x65a3580`; `M:docs/AGY-CONTRACT.md:76-78` |
| 4 | Framing del body | Fetch de Bun/OpenCode (N/D) | `Transfer-Encoding: chunked` (medido) | **N/D** | `M:docs/AGY-CONTRACT.md:15-18`; `B` buildinfo |
| 5 | Versión HTTP / TLS | Bun (BoringSSL) | Go + BoringCrypto, HTTP/2 | **DISTINTO** (pila); JA3 N/D | `B` `.go.buildinfo`; `P:README.md:472-474` |
| 6 | UA: producto y formato | `antigravity/cli/<v> (aidev_client; ...)` | igual | **IGUAL** | `P:src/constants.ts:99-101`; `B:0x64cbbc3,0x64b0543`; `M:docs/AGY-CONTRACT.md:27` |
| 7 | UA: versión | Dinámica: 1.5.8 de fallback, updater en runtime | 1.5.14 | **DISTINTO** (probable) | `P:src/constants.ts:93`; `P:src/plugin/version.ts:31`; `B:0x6f3991e` |
| 8 | UA: `cl` | `962369648` (congelado) | `1027820220` (build) | **DISTINTO** (seguro) | `P:src/constants.ts:100`; §3.2; `RAW:agy-build-facts.txt` |
| 9 | UA: `os_type`/`arch` | Hardcodeado `linux/amd64` | Runtime `linux/amd64` en este build | **IGUAL** aquí; **CONDICIONAL** en macOS/Windows | `P:src/constants.ts:100`; §3.2 |
| 10 | UA: `auth_method` / `datacollection_opt_in` | `consumer`; nunca el opt-in | `consumer`; añade `datacollection_opt_in=false` si el flag booleano del builder está activo (probablemente telemetría desactivada) | **IGUAL** base; **AUSENTE** condicional | `P:src/constants.ts:100`; `B:0x6603ebf,0x95dec76` |
| 11 | `Authorization` / `Content-Type` | Bearer; `application/json` heredado del SDK | Bearer; `application/json` (solo POST) | **IGUAL** (probable) | `P:src/plugin/request.ts:945,927`; `B:0x95df656` |
| 12 | `Accept` | `text/event-stream` en streaming | Sin evidencia en `setHeaders` | **SOBRANTE** (probable) / **N/D** | `P:src/plugin/request.ts:1790`; `B:0x95df3e0` |
| 13 | `anthropic-beta` | `interleaved-thinking-2025-05-14` | `thinking-binding-controls-2026-08-01` | **DISTINTO** | `P:src/plugin/request.ts:1797-1804`; `B:0x6518da7,0x665cdbf,0x95e1fd1` |
| 14 | `X-Goog-Request-Reason` | Nunca | Condicional (solo si hay `reason`) | **AUSENTE** condicional | `B:0x95df579`; `RAW:plugin-audit.txt` |
| 15 | `X-Goog-Api-Client` / `Client-Metadata` en `loadCodeAssist` | Sí, con `platform=MACOS` en Linux | Sin cabecera en el binario | **SOBRANTE** (probable) | `P:src/plugin/project.ts:131-133`; `P:src/constants.ts:119`; `B` búsqueda |
| 16 | `x-api-key` / `x-goog-api-key` / `x-goog-user-project` | Se borran | No se mandan | **IGUAL** (neto), con riesgo residual | `P:src/plugin/request.ts:946-954` |
| 17 | Otras cabeceras del AI SDK/OpenCode | No se enumeran; solo se borran tres | No aplica | **N/D** | `P:src/plugin/request.ts:927`; §2.2 |
| 18 | `body.project` | Managed project, `rising-fact-p41fc` o `adj-noun-xxxxx` | `aicode-consumers` (medido 1.5.11) | **DISTINTO** (probable) | `P:src/plugin/request.ts:1714,831-838`; `P:src/constants.ts:70`; `M:docs/AGY-CONTRACT.md:46` |
| 19 | `body.requestId` | `agent-<uuid>` | `agent/<uuid>/<ms>/<uuid>/1` | **DISTINTO** | `P:src/plugin/request.ts:1774`; `M:docs/AGY-CONTRACT.md:47`; `B:0x64cd2f7` |
| 20 | `body.request.labels` | Ausente | 9 claves | **AUSENTE** | `P:src/plugin/request.ts:1765-1782` (sin `labels`); `M:docs/AGY-CONTRACT.md:52-58`; `B:0x652fd6a,0x652fd79,0x65a4f2d` |
| 21 | `body.request.sessionId` | `-<uuid>:<model>:<project>:<conversation>` | Identificador opaco (capturado) | **DISTINTO** (probable) | `P:src/plugin/request.ts:87,93-108,1778-1779`; `M:docs/AGY-CONTRACT.md:63` |
| 22 | `body.requestType` / `userAgent` | `agent` / `antigravity` | `agent` / `antigravity` | **IGUAL** | `P:src/plugin/request.ts:1772-1773`; `M:docs/AGY-CONTRACT.md:66-67` |
| 23 | `body.request.safetySettings` | Se inyectan si no vienen (no-Claude) | No aparecen en el body medido | **SOBRANTE** | `P:src/plugin/request.ts:1707-1708`; `M:docs/AGY-CONTRACT.md:59-62` |
| 24 | `body.request.systemInstruction` | Prefijo propio + catálogo `# Code Mode` de OpenCode | Prompt propio del CLI | **DISTINTO** | `P:src/constants.ts:264`; `M:docs/AGY-CONTRACT.md:114-119`; `P:src/plugin/request-helpers.ts:1669-1690` |
| 25 | `body.model` | ID con tier | ID con tier | **IGUAL** | `P:src/plugin/transform/model-resolver.ts:231`; `M:docs/AGY-CONTRACT.md:65`; `B` modelos |
| 26 | `deviceId` / `sessionToken` | Se generan y persisten; **no se envían** | No hay device id en la petición API | **IGUAL** (ambos ausentes); hipótesis refutada | `P:src/plugin/fingerprint.ts:84-90,159-167`; `RAW:plugin-audit.txt` |
| 27 | Telemetría Play Log/Clearcut | Ninguna | `play.googleapis.com/log` + Clearcut, activa por defecto | **AUSENTE** | `B:0x6630453,0x280a268`; `RAW:plugin-no-telemetry.txt` |
| 28 | Peticiones extra | Warmup, fallback, quota, updater | Flujo propio del CLI; telemetría | **DISTINTO** (patrón) | `P:src/plugin/request.ts:1840-1855`; `P:src/plugin.ts:1921`; `P:src/plugin/version.ts:31` |

---

## 5. Ranking de vectores de detección

Criterios, en este orden:

1. **Evidencia directa** de que Google inspecciona esa capa (no solo que la
   diferencia exista).
2. **Facilidad** de comprobarlo en el servidor (regex, campo obligatorio, cruce de datos).
3. **Determinismo** de la diferencia (¿el plugin puede coincidir por azar?).
4. **Dificultad** de imitarla sin ser el CLI.

La probabilidad es una estimación razonada, no una medición. Ningún vector está
demostrado como causa de la suspensión.

| # | Vector | Probabilidad | Diferencia | Evidencia de uso |
| --- | --- | --- | --- | --- |
| 1 | Contenido del `systemInstruction` (firma de OpenCode) | Muy alta | Segura | **Directa** (429 medido) |
| 2 | `cl`/versión del User-Agent | Alta | Segura | Inferida (regex trivial) |
| 3 | Estructura del body (`labels`, `requestId`, `sessionId`) | Alta | Segura | Inferida (validación de campos) |
| 4 | Ausencia de telemetría del CLI | Media-alta | Segura | Desconocida (requiere cruce) |
| 5 | Huella TLS/HTTP (JA3/JA4, ALPN, h2, orden) | Media-alta | Probable | Desconocida |
| 6 | Cabeceras residuales de OpenCode/AI SDK | Media | N/D | Desconocida |
| 7 | Patrón de peticiones (warmup, fallback, quota) | Media-baja | Segura | Desconocida |
| 8 | `project` sintético o de fallback | Baja-media | Probable | Desconocida |
| 9 | `os_type`/`Client-Metadata` incoherentes | Baja en sgen; media en `loadCodeAssist` | Segura en Linux | Inferida |
| 10 | `deviceId`/`sessionToken` aleatorios | **Nula** (no se envían) | — | — |

### 5.1 Contenido del `systemInstruction` — el vector con evidencia directa

**Qué se midió.** En `M:docs/AGY-CONTRACT.md:88-121` hay una matriz de replays sobre el body real del
plugin. El backend devuelve `429 RESOURCE_EXHAUSTED` si y solo si aparece el
literal `tools.opencode.session_move` dentro de `systemInstruction`. Otros 18
nombres `tools.opencode.*` no lo disparan; el mismo literal en `contents` no lo
dispara; el tamaño no influye; el prefijo de 26 caracteres no basta y el literal
completo sí. Eso no es cuota: es una regla de contenido.

**Por qué importa.** Es la única evidencia de que Google mira el texto que
inyecta OpenCode y tiene una firma específica del harness. El plugin ya lo
neutraliza (`P:src/plugin/request-helpers.ts:1669-1690`), y la copia de producción incluye
el parche (`D:dist/src/plugin/request-helpers.js:1344-1359`). Pero:

- El parche cambia **un** literal; el resto del catálogo `# Code Mode`, la pista
  del worktree y el prompt de OpenCode siguen viajando.
- La regla es una lista negra; Google puede añadir otra entrada o pasar a una
  clasificación más general en cualquier momento.
- El 429 es una respuesta visible; una detección de cuenta puede usar la misma
  señal en modo silencioso.

**Cómo se comprobaría.** Repetir la matriz de `M:docs/AGY-CONTRACT.md:88-121` con el body actual:
quitar/poner el catálogo, bisecar `systemInstruction`, probar variantes
(`tools.opencode. session_move`, mayúsculas, otros nombres) y anotar
status/body. Es el experimento de menor coste y mayor señal.

### 5.2 `cl` y versión del User-Agent

**Qué se midió.** El CLI 1.5.14 usa `cl=1027820220`; el plugin usa
`cl=962369648` y una versión dinámica. El `cl` se introdujo en `6c5d9ae` cuando
el fallback era 1.4.7 y nunca se actualizó; `e9085a7` subió el fallback a 1.5.8
sin tocarlo (`RAW:plugin-git-history.txt`). El par `(1.5.14, 962369648)` no
corresponde al build 1.5.14: el `cl` se congeló en la era 1.4.x y la versión
siguió subiendo.

**Por qué importa.** Es una comprobación de una línea en el servidor: si el
backend conoce el `cl` de cada versión, el par del plugin es imposible. Incluso
si no lo conoce, un `cl` viejo con una versión nueva es sospechoso. Es
especialmente probable porque el UA es lo primero que se mira para identificar
clientes.

**Cómo se comprobaría.** Con una cuenta de prueba, enviar el mismo body válido
con cuatro UA: (a) el del CLI exacto, (b) 1.5.14 + `962369648`, (c) 1.5.8 +
`962369648`, (d) 1.5.14 + `1027820220`. Comparar status y cuerpo. Si (b) y (c)
dan 200 y (a)/(d) también, el backend no valida el `cl`; si (b)/(c) dan 403/429
o un body de "versión no soportada", el vector es real.

### 5.3 Estructura del body: `labels`, `requestId`, `sessionId`

**Qué se midió.** El body del CLI 1.5.11 lleva `labels` con 9 claves, un
`requestId` `agent/<uuid>/<ms>/<uuid>/1` y un `sessionId` opaco. El plugin no
manda `labels`, usa `agent-<uuid>` y un `sessionId`
`-<uuid>:<model>:<project>:<conversation>`.

**Por qué importa.** El `requestId` se valida con una regex; `labels` puede ser
obligatorio para telemetría/facturación; el `sessionId` puede tener formato
esperado. Son diferencias deterministas y baratas de comprobar.

**Cómo se comprobaría.** Replay de variable única sobre un body válido: quitar
`labels`, cambiar el formato de `requestId`, cambiar el `sessionId`. Ver si el
status o el body cambian. Si `labels` es obligatorio, el intento de imitarlo
puede romper la facturación; hay que hacerlo con una cuenta de prueba.

### 5.4 Ausencia de telemetría

**Qué se midió.** El CLI tiene el cliente Clearcut de Play Log, el endpoint
`https://play.googleapis.com/log` y un flag `--disable_telemetry`; la ayuda del
flag implica que la telemetría está activa por defecto. El plugin no manda nada
a ese canal.

**Por qué importa.** Si Google cruza la telemetría con la cuenta OAuth o con
la instalación, una cuenta que hace llamadas API pero no produce telemetría es
anómala. Es un vector de "señal negativa": no requiere que el plugin mande algo
incorrecto, sino que **no** manda lo que el cliente oficial sí.

**Cómo se comprobaría.** Capturar el tráfico del CLI a `play.googleapis.com/log`
con y sin `--disable_telemetry`; ver qué identidad lleva el payload (installation
id, cuenta, sesión); después comparar una cuenta con telemetría y otra sin ella.
Es más caro y no concluyente si el cruce no existe.

### 5.5 Huella TLS/HTTP

**Qué se midió.** El CLI es Go + BoringCrypto; el plugin corre en Bun/OpenCode.
La pila es distinta. No se midió JA3/JA4 ni el orden de cabeceras de ninguno de
los dos en 1.5.14.

**Por qué importa.** Es de los pocos vectores que el plugin no puede imitar
cambiando una cadena: exigiría otro cliente HTTP/TLS. Si Google usa JA3/JA4 o
`SETTINGS` de HTTP/2, es un discriminador fuerte y estable.

**Cómo se comprobaría.** Proxy MITM con logging de JA3/JA4 para ambos clientes;
comparar ClientHello (cifrados, extensiones, ALPN, GREASE), `SETTINGS` de h2,
orden de cabeceras, `Accept-Encoding`, `TE`, `:authority`. Es una comparación
directa, sin necesidad de cuenta.

### 5.6 Cabeceras residuales de OpenCode/AI SDK

**Qué se midió.** El plugin borra `x-api-key`, `x-goog-api-key` y
`x-goog-user-project`; el comentario de `P:src/plugin/request.ts:947-954` confirma que
OpenCode/AI SDK las inyecta. No hay una lista blanca: cualquier otra cabecera
del SDK viaja.

**Por qué importa.** Si `@ai-sdk/google` añade `x-goog-api-client`,
`x-stainless-*`, un `User-Agent` propio (el plugin lo pisa) o cabeceras de
tracing, el backend ve una mezcla de cliente Google/Node con UA de CLI Go.

**Cómo se comprobaría.** Capturar `prepared.init.headers` antes del `fetch`
(con debug del plugin o proxy) y compararlas con el `setHeaders` del CLI. Es la
prueba que falta para cerrar el inventario de cabeceras.

### 5.7 Patrón de peticiones

**Qué se midió.** El plugin hace un `sgen` extra de warmup para Claude
(`P:src/plugin/request.ts:1840-1855`), reintenta contra prod/sandbox
(`P:src/plugin.ts:2007-2014`) y consulta cuota/modelos. El CLI tiene su propio flujo y telemetría; no se midió su secuencia de warmup.

**Por qué importa.** Un analista de abuso no necesita mirar el body: el volumen,
el orden y los hosts de las peticiones ya dibujan un cliente distinto. El warmup
es especialmente visible: es un `sgen` con un prompt fijo
(`"Warmup request for thinking signature."`).

**Cómo se comprobaría.** Contar peticiones por turno en ambos clientes; buscar el
prompt de warmup; registrar la secuencia de hosts.

### 5.8 `project` sintético o de fallback

**Qué se midió.** El CLI usa `aicode-consumers` en la captura de 1.5.11. El
plugin usa el proyecto gestionado que devuelve `loadCodeAssist`; si falla, cae a
`rising-fact-p41fc` o a un id `adj-noun-xxxxx` (`useful-fuze-a1b2c`).

**Por qué importa.** `rising-fact-p41fc` es una constante conocida del plugin, y
`adj-noun-xxxxx` es un patrón generado que no parece un proyecto de Google Cloud.
Si alguna petición cae en esos fallbacks, es una firma directa.

**Cómo se comprobaría.** Capturar el campo `project` en el plugin y compararlo con
el que devuelve `loadCodeAssist` para la misma cuenta y con el del CLI. Probar
una cuenta sin proyecto gestionado para forzar el fallback.

### 5.9 `os_type`/`Client-Metadata` incoherentes

**Qué se midió.** El UA del plugin hardcodea `linux/amd64`, que en este host es
correcto; en macOS/Windows mentiría. El `Client-Metadata` de `loadCodeAssist`
dice `MACOS` en Linux.

**Por qué importa.** En `loadCodeAssist` la combinación UA `antigravity`
(sin versión), `X-Goog-Api-Client` de VS Code Cloud Shell y
`Client-Metadata: MACOS` es claramente de plugin. En `sgen`, el UA ya es de CLI;
la mentira de plataforma desapareció de esa ruta en 2.9.11.

**Cómo se comprobaría.** Capturar las cabeceras de `loadCodeAssist` del plugin y
del CLI; comparar `Client-Metadata` y `X-Goog-Api-Client`.

### 5.10 `deviceId`/`sessionToken` aleatorios — hipótesis refutada

**Qué se midió.** `fingerprint.ts` genera UUIDv4 y 16 bytes hex, y
`accounts.ts` los persiste. Pero `buildFingerprintHeaders` no se llama en
ninguna parte y el único uso es un log (`P:src/plugin.ts:1984`). En la petición HTTP
no hay `deviceId` ni `sessionToken`.

**Conclusión.** Para 2.9.11, la hipótesis "deviceId aleatorio y no estable" no
explica la detección. Si se detectó el plugin por identidad de dispositivo, no
fue por este campo. El CLI, por su parte, tiene un
`antigravity_ide_installation_id` en la telemetría; no aparece en el body medido
de la petición API.

---

## 6. Hipótesis refutadas o matizadas

| Hipótesis | Veredicto | Evidencia |
| --- | --- | --- |
| "El plugin manda un UA genérico `antigravity/<ver> darwin/arm64`" | **Falso en 2.9.11**: el `sgen` usa el UA del CLI | `P:src/plugin/request.ts:1815-1816`; `P:src/constants.ts:99-101`; `D:dist/src/plugin/request.js:1429` |
| "El plugin declara darwin/win32 desde Linux" | **Falso en el `sgen` actual**; el fingerprint viejo sorteaba `darwin`/`win32` (`P:src/plugin/fingerprint.ts:96-113`) pero ya no se usa en el wire. En `loadCodeAssist` el `Client-Metadata` dice `MACOS` en Linux | `P:src/plugin/fingerprint.ts:73,96-113`; `P:src/constants.ts:119` |
| "El plugin manda un deviceId aleatorio" | **Falso**: se genera y persiste, pero no se envía | `P:src/plugin/fingerprint.ts:159-167`; `P:src/plugin.ts:1984` |
| "El plugin manda `x-goog-api-client` en el `sgen`" | **Falso por código**: no lo fija. Podría llegar del AI SDK; no determinado | `P:src/plugin/request.ts:1815-1816`; §5.6 |
| "El plugin manda `Client-Metadata` en el `sgen`" | **Falso**: solo en `loadCodeAssist` | `P:src/plugin/project.ts:131-133` |
| "El body del plugin es el del CLI" | **Falso**: faltan `labels`, el formato de `requestId` y el `sessionId` difiere; sobran `safetySettings` | §4, filas 18-24 |
| "El CLI y el plugin mandan el mismo `anthropic-beta`" | **Falso**: mismo header, valor distinto | §3.1, §4 fila 13 |
| "Google no puede ver el contenido de OpenCode" | **Falso**: el 429 por `tools.opencode.session_move` es evidencia directa | `M:docs/AGY-CONTRACT.md:88-121` |

---

## 7. Recomendaciones ordenadas por coste

> **Aviso:** esto reduce diferencias observables; **no garantiza evasión**. Google
> puede cambiar las reglas, y la atribución de una suspensión no se puede hacer
> desde el binario. Úsese para investigación/defensa, no como receta de abuso.

| Coste | Acción | Efecto esperado | Riesgo / límite |
| --- | --- | --- | --- |
| **0 — medir** | Capturar headers/body reales del plugin y del CLI (debug o MITM), y JA3/JA4 | Cierra las incógnitas de §5.5-5.6 antes de tocar nada | Requiere una cuenta y un proxy; no cambia el comportamiento |
| **Bajo** | Emparejar `versión` y `cl` del UA: fijar un build real y actualizar ambos a la vez | Elimina el par imposible (§5.2) | Sigue sin ser el CLI; el `cl` caduca con el tiempo |
| **Bajo** | Quitar `Client-Metadata` y `X-Goog-Api-Client` de `loadCodeAssist`, o igualarlos al CLI | Elimina cabeceras que el CLI no tiene y la incoherencia `MACOS` en Linux | Puede romper el descubrimiento de proyecto en algunas cuentas |
| **Bajo** | Alinear `anthropic-beta` al valor del CLI | Quita una diferencia de cabecera trivial | El valor puede cambiar entre builds; hay que mantenerlo |
| **Medio** | No mandar `safetySettings` si el CLI no los manda, o mandarlos solo cuando el modelo los requiera | Reduce campos sobrantes | Puede cambiar el filtrado de seguridad |
| **Medio** | Alinear `labels`, `requestId` y `sessionId` a los formatos del CLI | Reduce diferencias estructurales | `labels` puede ser obligatorio para facturación; los IDs pueden romper la caché de firmas |
| **Medio** | Evitar warmup y fallbacks a hosts que el CLI no usa; no generar `project` sintético | Reduce el patrón de peticiones | Menos tolerancia a fallos |
| **Alto** | Usar un cliente HTTP/TLS con la misma pila que el CLI (Go/BoringSSL), o un transporte que imite su ClientHello/h2 | Ataca el vector más difícil de imitar | Complejo, frágil, puede romper el streaming; no hay garantía |
| **Muy alto / no recomendado** | Usar el CLI oficial como único cliente | Es lo único indistinguible por definición | Implica renunciar a OpenCode; riesgo de ToS |

Prioridad práctica si el objetivo es **entender** y no evadir: primero §5.1
(contenido), luego §5.2 (UA), después §5.3 (body) y §5.5 (TLS). Son los que más
información dan por unidad de esfuerzo.

---

## 8. Límites de este análisis

1. **No se ejecutó `agy.bin`.** Todo es estático. No hay captura de 1.5.14; la
   captura de headers/body es de 1.5.11 (`docs/AGY-CONTRACT.md`).
2. **No se puede saber si Google usa un vector concreto.** El ranking es una
   estimación; la suspensión puede ser manual, multi-señal o por una regla que no
   está en el binario.
3. **El orden de los parámetros del UA en 1.5.14** se toma de la captura de
   1.5.11; las piezas y el formato son del binario 1.5.14. Si el orden cambiara,
   el `cl` y la versión seguirían siendo la diferencia principal.
4. **El `cl` es un dato de build.** `1027820220` es el de este binario; otro build
   de 1.5.14 con otro `cl` cambiaría el valor, no el argumento.
5. **El cruce telemetría↔cuenta no está demostrado.** La existencia del canal está
   probada; su uso para detección, no.
6. **La copia de producción es 2.9.11.** El repo tiene commits posteriores; se
   auditó la copia instalada y la fuente cuando coincidían. El parche de
   `tools.opencode.session_move` sí está en el `dist` instalado.
7. **No se puede demostrar una negativa absoluta** ("el CLI no manda X") solo por
   ausencia de una cadena: Go puede construir nombres de cabecera por
   concatenación. Por eso las afirmaciones de ausencia se apoyan además en la
   medición de 1.5.11 y en `setHeaders`, no solo en `grep`.

---

## Apéndice A — Offsets y funciones clave

| Dato | Offset / dirección |
| --- | --- |
| `codeassistclient.userAgent` | `0x95de840`–`0x95df3e0` |
| `(*CodeAssistClient).setHeaders` | `0x95df3e0`–`0x95df7c0` |
| `anthropicConverter.ToRequestPayload` | `0x95e1e80`–`0x95e2120` |
| `antigravity` | `0x64cbbc3` |
| `os_type=%s` | `0x64b052f` |
| `arch=%s` | `0x6466a71` |
| `aidev_client` | `0x64e76e2` |
| `cl=%d` | `0x64468d7` |
| `auth_method=%s` | `0x6518d7d` |
| `%s/%s (%s)` | `0x64b0543` |
| `datacollection_opt_in=false` | `0x6603ebf` |
| CL del build | global `0xd82b440` → RELA addend `0x6ff2a90` → `1027820220` |
| `anthropic-beta` (clave) | `0x6518da7` |
| valor de `anthropic-beta` | `0x665cdbf` (36 bytes) |
| `https://play.googleapis.com/log` | `0x6630453` |
| `--disable_telemetry` | `0x657f3ee`, `0x6660363` |
| `antigravity_ide_installation_id` | `0x6630491` |
| `root_cascade_id` | `0x652fd79` |
| `last_step_index` | `0x652fd6a` |
| `used_non_gemini_model` | `0x65a4f2d` |
| `MODEL_PLACEHOLDER_M0` | `0x6592248` |
| formato `%s/%s/%d/%s` | `0x64cd2f7` |

## Apéndice B — Glosario

- **`cl`**: changelist de Google del build. Cambia con cada build; el CLI lo
  formatea en el UA con `cl=%d`.
- **`sgen`**: `:streamGenerateContent`, la llamada de inferencia.
- **`loadCodeAssist`**: llamada de descubrimiento de proyecto/cuota.
- **JA3/JA4**: huellas del ClientHello TLS (cifrados, extensiones, orden). No se
  pueden calcular sin capturar el handshake.
- **Clearcut/Play Log**: infraestructura de telemetría de Google;
  `play.googleapis.com/log` es el endpoint que aparece en el binario.
- **`labels`**: metadatos de la cascada/trayectoria que el CLI añade al body.

## Apéndice C — Archivos de evidencia

- `raw/deteccion/agy-build-facts.txt` — CL, UA, `setHeaders`, telemetría.
- `raw/deteccion/agy-ua-xrefs.txt` — referencias `lea` dentro de `.text`.
- `raw/deteccion/agy-telemetry.txt` — endpoint y cliente Clearcut.
- `raw/deteccion/plugin-audit.txt` — `archivo:línea` del plugin.
- `raw/deteccion/plugin-no-telemetry.txt` — ausencia en `src` y `dist`.
- `raw/deteccion/plugin-production.txt` — UA/ids/parche en la copia instalada.
- `raw/deteccion/plugin-git-history.txt` — commits del `cl` y de la versión.
