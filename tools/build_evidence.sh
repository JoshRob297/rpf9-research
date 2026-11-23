#!/usr/bin/env bash
# Regenera las transcripciones de evidencia en raw/deteccion/.
# Solo lee el binario, la fuente del plugin y la copia de produccion.
# No ejecuta el binario y no escribe en git.
set -euo pipefail

cd "$(dirname "$0")/.."
MYTOOLS="tools"
OUT="raw/deteccion"
BIN="${AGY_BIN:-/home/sistver/re/agy.bin}"
SRC="${PLUGIN_SRC:-/home/sistver/proyectos/opencode-antigravity-auth/src}"
DIST="${PLUGIN_DIST:-/home/sistver/.local/share/opencode-antigravity-auth/package/dist}"

mkdir -p "$OUT"

echo "[1/9] hashes y hechos del binario"
{
  md5sum "$BIN"
  sha256sum "$BIN"
  stat -c '%s bytes' "$BIN"
} > "$OUT/agy-hash.txt"
python3 "$MYTOOLS/agy_build_facts.py" --binary "$BIN" > "$OUT/agy-build-facts.txt"

echo "[2/9] auditoria del plugin"
python3 "$MYTOOLS/plugin_audit.py" --src "$SRC" > "$OUT/plugin-audit.txt"

echo "[3/9] contexto de las cadenas del User-Agent"
{
  for p in "antigravity" "os_type=%s" "arch=%s" "aidev_client" "cl=%d" "auth_method=%s" "%s/%s (%s)" "datacollection_opt_in=false"; do
    echo "######## $p"
    python3 "$MYTOOLS/agy_strings.py" --binary "$BIN" find "$p" --radius 220 --limit 2
  done
} > "$OUT/agy-ua-context.txt" 2>&1

echo "[4/9] xrefs del constructor del UA y de setHeaders"
{
  for t in 0x64cbbc3 0x64b052f 0x6466a71 0x64e76e2 0x64468d7 0x6518d7d 0x64b0543 0x6432ad2; do
    echo "######## target $t"
    python3 "$MYTOOLS/go_xrefs.py" --binary "$BIN" --target "$t"
  done
} > "$OUT/agy-ua-xrefs.txt" 2>&1

echo "[5/9] funciones Go relevantes"
python3 "$MYTOOLS/go_symbols.py" --binary "$BIN" --grep \
  "codeassistclient\.(userAgent|\(\*CodeAssistClient\)\.setHeaders)|anthropicConverter\.ToRequestPayload" \
  > "$OUT/agy-functions.txt"

echo "[6/9] endpoints, cabeceras y body del CLI"
{
  echo "## hosts cloudcode"
  LC_ALL=C grep -aoE 'https?://[a-zA-Z0-9.-]*(cloudcode|cloudaicompanion)[a-zA-Z0-9./:-]*' "$BIN" | sort -u
  echo
  echo "## formatos de id"
  for p in '%s/%s/%d/%s' 'agent-%s' 'requestId' 'sessionId'; do
    echo "-- $p"
    LC_ALL=C grep -abo -- "$p" "$BIN" | head -8
  done
  echo
  echo "## claves de labels en el binario"
  for p in root_cascade_id last_step_index used_non_gemini_model MODEL_PLACEHOLDER_M0; do
    LC_ALL=C grep -abo -- "$p" "$BIN" | head -3
  done
} > "$OUT/agy-endpoints-body.txt" 2>&1

echo "[7/9] telemetria del CLI"
{
  echo "## cadenas"
  for p in 'https://play.googleapis.com/log' '--disable_telemetry' 'datacollection_opt_in=false' 'antigravity_ide_installation_id' 'clearcut_go_client_telemetry' 'clearcut.Client'; do
    echo "-- $p"
    LC_ALL=C grep -abo -- "$p" "$BIN" | head -6
  done
  echo
  echo "## contexto del endpoint de Play Log"
  python3 "$MYTOOLS/agy_strings.py" --binary "$BIN" find 'https://play.googleapis.com/log' --radius 260 --limit 1
} > "$OUT/agy-telemetry.txt" 2>&1

echo "[8/9] ausencia de telemetria en el plugin (src y dist)"
{
  echo "## src"
  grep -rniE "clearcut|play\.googleapis|playlog|sendTelemetry" "$SRC" --include=*.ts | grep -v "\.test\.ts" || echo "(sin coincidencias)"
  echo
  echo "## dist de produccion"
  grep -rniE "clearcut|play\.googleapis|playlog" "$DIST" 2>/dev/null | head -5 || echo "(sin coincidencias)"
} > "$OUT/plugin-no-telemetry.txt" 2>&1

echo "[9/9] copia de produccion: UA, requestId y anthropic-beta"
{
  grep -n "cl=962369648" "$DIST/src/constants.js"
  grep -n "ANTIGRAVITY_CLI_VERSION_FALLBACK" "$DIST/src/constants.js"
  grep -n 'requestId = "agent-"' "$DIST/src/plugin/request.js"
  grep -n "interleaved-thinking" "$DIST/src/plugin/request.js"
  grep -n "neutralizeBlockedSystemInstructionLiterals" "$DIST/src/plugin/request-helpers.js" | head -3
} > "$OUT/plugin-production.txt" 2>&1

echo "OK: evidencia en $OUT"
ls -l "$OUT"
