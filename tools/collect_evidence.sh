#!/usr/bin/env bash
# Regenerate the raw evidence used by docs/DETECCION.md (T-RE-DETECT).
#
# Usage:
#   tools/collect_evidence.sh [AGY_BIN] [PLUGIN_SRC] [PROD_DIST]
#
# Defaults match the paths named in the task brief. The script is read-only: it
# never executes agy, never touches the network, and never writes outside raw/.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGY="${1:-/home/sistver/re/agy.bin}"
SRC="${2:-/home/sistver/proyectos/opencode-antigravity-auth}"
PROD="${3:-/home/sistver/.local/share/opencode-antigravity-auth/package/dist}"
OUT="$ROOT/raw"
mkdir -p "$OUT"

AGY_RAW="$OUT/deteccion-agy.txt"
PLUGIN_RAW="$OUT/deteccion-plugin.txt"

{
  echo "# Evidencia agy.bin (T-RE-DETECT)"
  echo "# generado: $(date -Is)"
  echo "# comando: tools/collect_evidence.sh $AGY"
  echo
  echo "## identidad del binario"
  stat -c 'path=%n size=%s mtime=%y' "$AGY"
  sha256sum "$AGY"
  file "$AGY"
  readelf -h "$AGY" | sed -n '1,12p'
  echo
  echo "## go buildinfo"
  readelf -x .go.buildinfo "$AGY" | sed -n '1,12p'
  echo
  echo "## UA: literales y candidatos numericos"
  python3 "$ROOT/tools/agy_extract.py" "$AGY" --ua
  echo
  echo "## funcion que construye la UA"
  python3 "$ROOT/tools/agy_extract.py" "$AGY" --function 'codeassistclient.userAgent'
  echo
  echo "## literales exactos"
  for needle in 'antigravity/cli/' 'aidev_client' 'os_type=%s' 'arch=%s' 'cl=%d' 'auth_method=%s' '%s/%s/%s (%s)' '1027820220' '1.5.14'; do
    echo "-- $needle"
    grep -aob -- "$needle" "$AGY" | head -6 || true
  done
  echo
  echo "## disasm: construccion de la UA (partes y cl)"
  objdump -d --start-address=0x95de900 --stop-address=0x95dec20 -M intel "$AGY" 2>/dev/null \
    | grep -E '^ 95de(9|a|b)' | sed -n '1,160p'
  echo
  echo "## cl: global 0xd82b440 -> relocacion -> string"
  readelf -r "$AGY" 2>/dev/null | grep -E '00000d82b44|00000d82b55' || true
  echo "-- bytes del global (vaddr 0xd82b440, file offset 0xd22b440)"
  xxd -s 0xd22b440 -l 32 "$AGY"
  echo "-- string apuntado (0x6ff2a90)"
  xxd -s 0x6ff2a90 -l 32 "$AGY"
  echo
  echo "## URLs de API/telemetria (needles exactos)"
  for needle in 'https://daily-cloudcode-pa.googleapis.com' \
                'https://daily-cloudcode-pa.sandbox.googleapis.com' \
                'https://cloudcode-pa.googleapis.com' \
                'https://autopush-cloudcode-pa.sandbox.googleapis.com' \
                'https://play.googleapis.com/logtrajectory' \
                'clearcut_proxy' 'logtrajectory' 'RecordAsyncTelemetry' \
                'BAICODE_TELEMETRY_ENDPOINT_URL' 'RecordCodeAssistMetrics' \
                'https://antigravity-cli-auto-updater-974169037036.us-central1.run.app'; do
    echo "-- $needle"
    grep -aob -- "$needle" "$AGY" | head -6 || true
  done
  echo
  echo "## cabeceras deterministas del CLI"
  python3 "$ROOT/tools/agy_extract.py" "$AGY" --function 'CodeAssistClient).setHeaders'
  for needle in 'X-Goog-Request-Reason' 'thinking-binding-controls-2026-08-01' \
                'interleaved-thinking-2025-05-14' 'application/json'; do
    echo "-- $needle"
    grep -aob -- "$needle" "$AGY" | head -4 || true
  done
  echo "-- refs LEA dentro de setHeaders (0x95df360..0x95df800)"
  objdump -d --start-address=0x95df360 --stop-address=0x95df800 -M intel "$AGY" 2>/dev/null \
    | grep -E 'lea .*# (64b054d|65a3739|64e7682|65448cc)' | head -10 || true
  echo "-- ref a anthropic-beta en el conversor Anthropic"
  objdump -d --start-address=0x95e1fd0 --stop-address=0x95e2020 -M intel "$AGY" 2>/dev/null \
    | grep -E '# 665cdbf|lea' | head -6 || true
  echo
  echo "## cabeceras propietarias / identificadores"
  for needle in 'X-Goog-Api-Client' 'client-metadata' 'Client-Metadata' 'x-goog-api-client' \
                'X-Client-Device-Id' 'X-Goog-QuotaUser' 'deviceId' 'device_id' 'sessionToken' \
                'machineId' 'installation_id' 'x-antigravity-csrf-token'; do
    echo "-- $needle"
    grep -aob -- "$needle" "$AGY" | head -8 || true
  done
  echo
  echo "## flujo de peticion: endpoints y modelo"
  for needle in 'daily-cloudcode-pa.googleapis.com' 'cloudcode-pa.googleapis.com' \
                'v1internal:streamGenerateContent' 'v1internal:loadCodeAssist' \
                'logtrajectory' 'RecordAsyncTelemetry'; do
    echo "-- $needle"
    grep -aob -- "$needle" "$AGY" | head -6 || true
  done
} > "$AGY_RAW"

{
  echo "# Evidencia plugin (T-RE-DETECT)"
  echo "# generado: $(date -Is)"
  echo "# comando: tools/collect_evidence.sh $AGY $SRC $PROD"
  echo
  echo "## superficie de produccion (dist instalado)"
  python3 "$ROOT/tools/plugin_surface.py" \
    "$PROD/src/constants.js" "$PROD/src/plugin/request.js"
  echo
  echo "## superficie del fuente (HEAD)"
  python3 "$ROOT/tools/plugin_surface.py" \
    "$SRC/src/constants.ts" "$SRC/src/plugin/request.ts"
  echo
  echo "## citas de codigo (fuente)"
  for file in src/constants.ts src/plugin/request.ts src/plugin/project.ts \
              src/plugin/fingerprint.ts src/plugin/version.ts src/plugin/accounts.ts \
              src/plugin/quota.ts src/plugin.ts; do
    echo "--- $file"
    grep -nE 'getAntigravityCliUserAgent|ANTIGRAVITY_CLI_VERSION_FALLBACK|cl=962369648|ANTIGRAVITY_ENDPOINT_FALLBACKS|headers\.delete|headers\.set\("User-Agent"|headers\.set\("Accept"|wrappedBody\.(requestType|userAgent|requestId)|sessionId = signatureSessionKey|generateDeviceId|generateSessionToken|PLATFORM_CHOICES|platform:|X-Goog-Api-Client|Client-Metadata|generateFingerprint\(\)|CLI_VERSION_URL' \
      "$SRC/$file" | head -40 || true
  done
  echo
  echo "## changelog: cabeceras retiradas y plataforma"
  grep -nE 'X-Goog-QuotaUser|Extra Outgoing Headers|Fingerprint Headers Simplified|Linux Fingerprints|do not bump the changelist' \
    "$SRC/CHANGELOG.md" "$SRC/docs/ANTIGRAVITY_API_SPEC.md" | head -20 || true
  echo
  echo "## captura medida previa (agy 1.5.11)"
  grep -nE 'antigravity/cli/1\.5\.11|aicode-consumers|cl=1024248524|User-Agent real|logtrajectory' \
    "$SRC/docs/AGY-CONTRACT.md" | head -20 || true
} > "$PLUGIN_RAW"

echo "wrote $AGY_RAW"
echo "wrote $PLUGIN_RAW"
