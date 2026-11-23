#!/usr/bin/env python3
"""Extract the observable client surface of the opencode-antigravity-auth plugin.

Works against either the TypeScript source (`src/constants.ts`,
`src/plugin/request.ts`) or the installed build
(`.../package/dist/src/constants.js`, `.../dist/src/plugin/request.js`).

Usage
-----
    python3 tools/plugin_surface.py \
        /home/sistver/.local/share/opencode-antigravity-auth/package/dist/src/constants.js \
        /home/sistver/.local/share/opencode-antigravity-auth/package/dist/src/plugin/request.js

    python3 tools/plugin_surface.py --json ...
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ENDPOINT_RE = re.compile(r"export const (ANTIGRAVITY_ENDPOINT_[A-Z_]+)\s*=\s*[\"']([^\"']+)[\"']")
FALLBACK_RE = re.compile(r"export const (ANTIGRAVITY_(?:CLI_)?VERSION_FALLBACK)\s*=\s*[\"']([^\"']+)[\"']")
CLI_UA_RE = re.compile(r"antigravity/cli/\$\{getAntigravityCliVersion\(\)\}\s*\(([^`]+)\)")
PLATFORM_CHOICES_RE = re.compile(r"PLATFORM_CHOICES\s*=\s*\[([^\]]+)\]")
PLATFORM_EXPR_RE = re.compile(r'platform\"\s*:\s*\"\$\{process\.platform[^}]+\}\"')
DELETE_RE = re.compile(r"headers\.delete\(\s*[\"']([^\"']+)[\"']\s*\)")
SET_RE = re.compile(r"headers\.set\(\s*[\"']([^\"']+)[\"']\s*,\s*([^)]+)\)")


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def parse_constants(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    facts: dict = {"path": str(path), "line_count": text.count("\n") + 1}

    fallbacks = {}
    for match in FALLBACK_RE.finditer(text):
        fallbacks[match.group(1)] = {"value": match.group(2), "line": _line_of(text, match.start())}
    facts["fallbacks"] = fallbacks
    facts["cli_version_fallback"] = fallbacks.get("ANTIGRAVITY_CLI_VERSION_FALLBACK", {}).get("value")

    endpoints = {}
    for match in ENDPOINT_RE.finditer(text):
        endpoints[match.group(1)] = {"url": match.group(2), "line": _line_of(text, match.start())}
    facts["endpoints"] = endpoints

    ua = {}
    match = CLI_UA_RE.search(text)
    if match:
        ua["template"] = match.group(0)
        ua["line"] = _line_of(text, match.start())
        for key, pattern in {
            "os_type": r"os_type=([a-z0-9]+)",
            "arch": r"arch=([a-z0-9]+)",
            "cl": r"cl=(\d+)",
            "auth_method": r"auth_method=([a-z0-9]+)",
        }.items():
            inner = re.search(pattern, match.group(1))
            if inner:
                ua[key] = inner.group(1)
    facts["cli_ua"] = ua

    choices = PLATFORM_CHOICES_RE.search(text)
    facts["platform_choices"] = (
        [item.strip().strip("\"'") for item in choices.group(1).split(",")] if choices else []
    )

    platform = PLATFORM_EXPR_RE.search(text)
    facts["client_metadata_platform_expr"] = {
        "expr": platform.group(0) if platform else None,
        "line": _line_of(text, platform.start()) if platform else None,
    }
    return facts


def parse_request(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    facts: dict = {"path": str(path), "line_count": text.count("\n") + 1}

    deleted = []
    for match in DELETE_RE.finditer(text):
        deleted.append({"header": match.group(1), "line": _line_of(text, match.start())})
    facts["deleted_headers"] = [item["header"] for item in deleted]
    facts["deleted_header_lines"] = deleted

    set_headers = {}
    for match in SET_RE.finditer(text):
        value = match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        set_headers.setdefault(match.group(1), value)
    facts["set_headers"] = set_headers

    url = next((line.strip() for line in text.splitlines() if "v1internal:" in line and "${" in line), None)
    facts["transformed_url"] = url

    body_fields = {}
    for key in ("requestType", "userAgent", "requestId"):
        match = re.search(rf"wrappedBody\.{key}\s*=\s*([^;]+);", text)
        if match:
            value = match.group(1).strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            body_fields[key] = value
    facts["body_fields"] = body_fields
    facts["session_id_line"] = next(
        (line.strip() for line in text.splitlines() if ".sessionId = signatureSessionKey" in line), None
    )
    return facts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    result = {}
    for path in args.files:
        if not path.is_file():
            raise FileNotFoundError(path)
        if "constants" in path.name:
            result[str(path)] = parse_constants(path)
        elif "request" in path.name:
            result[str(path)] = parse_request(path)
        else:
            result[str(path)] = {"error": "unknown file kind (expected constants* or request*)"}

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0

    for path, facts in result.items():
        print(f"=== {path} ===")
        if "cli_version_fallback" in facts:
            print(f"CLI version fallback: {facts['cli_version_fallback']}")
            ua = facts.get("cli_ua", {})
            print(f"CLI UA: {ua.get('template')}")
            print(f"  cl={ua.get('cl')} os_type={ua.get('os_type')} arch={ua.get('arch')} auth_method={ua.get('auth_method')}")
            print(f"  platform choices: {facts.get('platform_choices')}")
            print(f"  Client-Metadata expr: {facts.get('client_metadata_platform_expr', {}).get('expr')}")
            for name, endpoint in facts.get("endpoints", {}).items():
                print(f"  {name}: {endpoint['url']} (line {endpoint['line']})")
        if "deleted_headers" in facts:
            print(f"Deleted headers: {facts['deleted_headers']}")
            print(f"Set headers: {sorted(facts['set_headers'])}")
            print(f"Transformed URL: {facts['transformed_url']}")
            print(f"Body fields: {facts['body_fields']}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
