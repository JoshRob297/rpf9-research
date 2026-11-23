#!/usr/bin/env python3
"""Audita la peticion real del plugin opencode-antigravity-auth sobre su fuente.

Imprime `archivo:linea: texto` para cada hecho que se cita en docs/DETECCION.md,
y comprueba que no existe codigo de telemetria (Clearcut / Play Log) ni uso de
los fingerprints generados. Sale con codigo 1 si falta un patron esperado, de
modo que sirve como test de la evidencia.

Uso:
    plugin_audit.py [--src RUTA]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_SRC = Path("/home/sistver/proyectos/opencode-antigravity-auth/src")

# (fichero, regex, descripcion)
CHECKS: list[tuple[str, str, str]] = [
    ("constants.ts", r"ANTIGRAVITY_ENDPOINT_DAILY\s*=", "host sandbox"),
    ("constants.ts", r"ANTIGRAVITY_ENDPOINT_DAILY_DIRECT\s*=", "host daily directo"),
    ("constants.ts", r"ANTIGRAVITY_ENDPOINT_FALLBACKS\s*=", "orden de fallback"),
    ("constants.ts", r"ANTIGRAVITY_ENDPOINT\s*=", "endpoint por defecto"),
    ("constants.ts", r'ANTIGRAVITY_DEFAULT_PROJECT_ID\s*=\s*"', "project id hardcodeado"),
    ("constants.ts", r'ANTIGRAVITY_CLI_VERSION_FALLBACK\s*=\s*"', "version CLI de fallback"),
    ("constants.ts", r"cl=962369648", "cl congelado en el UA"),
    ("constants.ts", r"getAntigravityCliUserAgent", "constructor del UA CLI"),
    ("constants.ts", r"Client-Metadata", "header Client-Metadata"),
    ("plugin/request.ts", r"const PLUGIN_SESSION_ID", "session id del plugin"),
    ("plugin/request.ts", r'headers\.delete\("x-api-key"\)', "borra x-api-key"),
    ("plugin/request.ts", r'headers\.delete\("x-goog-api-key"\)', "borra x-goog-api-key"),
    ("plugin/request.ts", r'headers\.delete\("x-goog-user-project"\)', "borra x-goog-user-project"),
    ("plugin/request.ts", r"const transformedUrl", "construccion de URL"),
    ("plugin/request.ts", r"wrappedBody\.requestType", "requestType del body"),
    ("plugin/request.ts", r"wrappedBody\.userAgent", "userAgent del body"),
    ("plugin/request.ts", r'wrappedBody\.requestId\s*=\s*"agent-"', "requestId del plugin"),
    ("plugin/request.ts", r"sessionId = signatureSessionKey", "sessionId = clave compuesta"),
    ("plugin/request.ts", r'headers\.set\("Accept"', "Accept SSE"),
    ("plugin/request.ts", r'headers\.set\("User-Agent"', "UA final"),
    ("plugin/request.ts", r"buildSafetySettings", "safetySettings inyectados"),
    ("plugin/request.ts", r"generateSyntheticProjectId", "project sintetico"),
    ("plugin/project.ts", r'"User-Agent": "antigravity"', "UA del loadCodeAssist"),
    ("plugin/project.ts", r'"X-Goog-Api-Client"', "X-Goog-Api-Client del loadCodeAssist"),
    ("plugin/project.ts", r'"Client-Metadata"', "Client-Metadata del loadCodeAssist"),
    ("plugin/fingerprint.ts", r"crypto\.randomUUID\(\)", "deviceId aleatorio"),
    ("plugin/fingerprint.ts", r"crypto\.randomBytes\(16\)", "sessionToken aleatorio"),
    ("plugin/version.ts", r"CLI_VERSION_URL", "updater de version del CLI"),
    ("plugin.ts", r"ANTIGRAVITY_ENDPOINT_FALLBACKS\[i\]", "bucle de fallback"),
    ("v2/adapter.ts", r"ANTIGRAVITY_ENDPOINT_FALLBACKS\[0\]", "host del adaptador v2"),
]

# Patrones que deben estar presentes.
EXPECTED = [f"{f}:{rx}" for f, rx, _ in CHECKS]

# Codigo de telemetria que, si aparece, seria un hallazgo (no debe aparecer).
TELEMETRY_RX = re.compile(r"clearcut|play\.googleapis|playlog|sendTelemetry", re.IGNORECASE)


def iter_ts(root: Path):
    for path in sorted(root.rglob("*.ts")):
        if path.name.endswith((".test.ts", ".d.ts")):
            continue
        yield path


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--src", type=Path, default=DEFAULT_SRC)
    args = p.parse_args()

    src = args.src.resolve()
    print(f"# plugin_audit: {src}")
    missing: list[str] = []

    for rel, rx, desc in CHECKS:
        path = src / rel
        pattern = re.compile(rx)
        found = False
        if path.exists():
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if pattern.search(line):
                    print(f"{rel}:{i}: {line.strip()}  # {desc}")
                    found = True
                    break
        if not found:
            missing.append(f"{rel}:{rx} ({desc})")
            print(f"MISSING {rel}: {rx} ({desc})")

    print("\n## ausencia de telemetria en el plugin")
    hits = []
    for path in iter_ts(src):
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if TELEMETRY_RX.search(line):
                hits.append(f"{path.relative_to(src)}:{i}: {line.strip()}")
    if hits:
        print("\n".join(hits))
    else:
        print("(sin coincidencias de clearcut/play.googleapis/playlog/sendTelemetry en src, tests excluidos)")

    print("\n## buildFingerprintHeaders: definido y no usado")
    callers = []
    for path in iter_ts(src):
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if "buildFingerprintHeaders" in line:
                print(f"{path.relative_to(src)}:{i}: {line.strip()}")
                if not path.name == "fingerprint.ts":
                    callers.append(path)
    if not callers:
        print("(una sola definicion, cero llamadas fuera de fingerprint.ts)")

    if missing:
        print("\nFALTAN PATRONES:", file=sys.stderr)
        for m in missing:
            print(" -", m, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
