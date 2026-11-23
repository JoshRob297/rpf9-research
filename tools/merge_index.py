#!/usr/bin/env python3
"""Fusiona indices de nombres de origenes distintos y reporta los conflictos.

La forma historica sigue funcionando sin cambios: recibe una carpeta de tramos
de ``tools/name_recover.py`` y una carpeta de salida, y suma la base que viene
en el nombre de cada archivo (``<rpf>__<offset>.json``)::

    python3 tools/merge_index.py <dir_tramos> <dir_salida> [--skip a.json,b.json]

La forma multifuente declara el tipo de cada origen; el fusionador no adivina::

    python3 tools/merge_index.py <dir_salida> \\
        --source name_recover=<dir_o_json> \\
        --source paths=<lista.txt|lista.json> \\
        --source inventory-tsv=<inventario.tsv> \\
        --source inventory-csv=<inventario.csv> \\
        --source hashes=<paths.sha256>

Tipos de fuente:

* ``name_recover``: JSON de ``tools/name_recover.py``. Aporta streams, rutas,
  identificadores y offsets relativos (o absolutos si la base es 0).
* ``paths``: diccionario plano, una ruta por linea o ``{"paths": [...]}``.
  Aporta rutas sin offset ni tamano.
* ``inventory-tsv`` / ``inventory-csv``: inventario de otra herramienta con
  columnas ``archivo, offset, ruta``. El offset puede ser decimal o ``0x...``.
* ``hashes``: listado de hashes con sal, formato ``raw/paths.sha256``. No trae
  rutas: solo sirve para comparar cobertura, nunca para fusionar.

Orden de resolucion, aplicado en este orden y publicado en ``report.json``:

a. Una ruta recuperada literalmente del payload (XML de montaje) gana sobre
   cualquier version derivada de un patron cuando las versiones discrepan en
   el offset.
b. Misma ruta, mismo contenedor, mismo offset y mismo tamano: se fusiona sin
   marcar nada.
c. Misma ruta y mismo contenedor con offset distinto, o mismo offset con
   tamano distinto: no se elige una version. La entrada queda como
   ``conflict`` con todas las versiones y el motivo.
d. Dos rutas distintas con el mismo hash: ``collision``, nunca se descarta en
   silencio.
e. Entrada sin ruta pero con identificador: ``orphan``.

Salidas:

* ``streams.tsv``, ``paths.tsv``, ``ids.tsv``: el log de menciones de las
  fuentes ``name_recover``. Se mantiene igual que antes para reproducir los
  conteos publicados en ``docs/INDEX.md``.
* ``index.tsv``: el indice normalizado de rutas, una fila por version. Las
  entradas en conflicto aparecen una vez por version y con ``estado=conflict``.
* ``summary.json``: los conteos historicos mas el resumen por fuente.
* ``report.json``: listas ``conflict``, ``collision``, ``orphan`` y
  ``unrecognized``, la prioridad aplicada y los conteos por fuente.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

SALT = "rpf9-research/2026-11"

SOURCE_TYPES = ("name_recover", "paths", "inventory-tsv", "inventory-csv", "hashes")

PRIORITY = [
    "a. a path recovered literally from the payload (mount XML) beats any pattern",
    "b. same path with identical container, offset and size merges without a mark",
    "c. same path with a different offset or size is a conflict with all versions",
    "d. two different paths with the same hash are a collision, never dropped",
    "e. an entry without a path but with an identifier is an orphan",
]

HEADER_FIRST = {"archivo", "archive", "rpf", "file", "fichero"}
HEADER_SECOND = {"offset", "off", "desplazamiento"}
HEADER_THIRD = {"ruta", "path", "nombre", "name"}

HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")
TRAMO_RE = re.compile(r"(.+?)__(\d+)\.json$")


def path_hash(name: str) -> str:
    """Hash publicado por el repo: sha256(sal + "\\t" + ruta)."""
    return hashlib.sha256((SALT + "\t" + name).encode("utf-8")).hexdigest()


@dataclass(slots=True)
class Mention:
    source_id: str
    source_type: str
    path: str | None = None
    identifier: str | None = None
    rpf: str | None = None
    offset: int | None = None
    compressed: int | None = None
    inflated: int | None = None
    provenance: str = "declared"  # literal | pattern | declared


@dataclass(slots=True)
class SourceResult:
    id: str
    type: str
    path: str
    status: str = "ok"
    reason: str = ""
    files: int = 0
    streams: int = 0
    path_mentions: int = 0
    id_mentions: int = 0
    literal_mentions: int = 0
    pattern_mentions: int = 0
    skipped: list[str] = field(default_factory=list)
    paths: set[str] = field(default_factory=set)
    ids: set[str] = field(default_factory=set)
    hashes: set[str] = field(default_factory=set)
    duplicate_hashes: int = 0
    mentions: list[Mention] = field(default_factory=list)
    stream_rows: list[tuple[Any, ...]] = field(default_factory=list)
    path_rows: list[tuple[Any, ...]] = field(default_factory=list)
    id_rows: list[tuple[Any, ...]] = field(default_factory=list)
    orphans: list[dict[str, Any]] = field(default_factory=list)
    ranges: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers de lectura
# ---------------------------------------------------------------------------


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _parse_offset(value: str) -> int:
    raw = value.strip().replace("_", "")
    if not raw:
        raise ValueError("offset vacio")
    if raw.lower().startswith("0x"):
        number = int(raw, 16)
    elif raw.isdigit():
        number = int(raw, 10)
    else:
        raise ValueError(f"offset no numerico: {value!r}")
    if number < 0:
        raise ValueError(f"offset negativo: {value!r}")
    return number


def _unrecognized(
    source_id: str,
    source_type: str,
    path: str,
    reason: str,
    line: int | None = None,
    file: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "source": source_id,
        "type": source_type,
        "path": path,
        "reason": reason,
    }
    if line is not None:
        item["line"] = line
    if file is not None:
        item["file"] = file
    return item


def _add_error(res: SourceResult, item: dict[str, Any]) -> None:
    res.errors.append(item)


def _provenance(kinds: set[str]) -> str:
    if "literal" in kinds:
        return "literal"
    if "pattern" in kinds:
        return "pattern"
    return "declared"


def _candidate_sources(stream: dict[str, Any]) -> dict[tuple[str, str], set[str]]:
    found: dict[tuple[str, str], set[str]] = defaultdict(set)
    candidates = stream.get("candidates")
    if not isinstance(candidates, list):
        return found
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        name = candidate.get("name")
        kind = candidate.get("kind")
        source = candidate.get("source")
        if (
            isinstance(name, str)
            and isinstance(source, str)
            and kind in ("full_path", "identifier")
        ):
            found[(kind, name)].add(source)
    return found


# ---------------------------------------------------------------------------
# Carga de fuentes
# ---------------------------------------------------------------------------


def load_name_recover(source_id: str, ruta: str, skip: set[str]) -> SourceResult:
    res = SourceResult(id=source_id, type="name_recover", path=ruta)

    if os.path.isdir(ruta):
        files = []
        for nombre in sorted(os.listdir(ruta)):
            if not nombre.endswith(".json"):
                continue
            if nombre in skip:
                res.skipped.append(nombre)
                continue
            files.append(os.path.join(ruta, nombre))
        if not files:
            res.status = "empty"
            res.reason = "sin archivos .json que fusionar"
            return res
    elif os.path.isfile(ruta):
        nombre = os.path.basename(ruta)
        if nombre in skip:
            res.skipped.append(nombre)
            res.status = "empty"
            res.reason = "archivo omitido por --skip"
            return res
        files = [ruta]
    else:
        res.status = "unrecognized"
        res.reason = f"no existe: {ruta}"
        _add_error(res, _unrecognized(source_id, "name_recover", ruta, res.reason))
        return res

    for fpath in files:
        nombre = os.path.basename(fpath)
        match = TRAMO_RE.match(nombre)
        rpf, base = (match.group(1), int(match.group(2))) if match else (nombre[:-5], 0)
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            _add_error(
                res,
                _unrecognized(
                    source_id,
                    "name_recover",
                    ruta,
                    f"JSON invalido: {exc}",
                    file=nombre,
                ),
            )
            continue
        if not isinstance(data, dict) or not isinstance(data.get("streams"), list):
            _add_error(
                res,
                _unrecognized(
                    source_id,
                    "name_recover",
                    ruta,
                    "el JSON no tiene una lista 'streams'",
                    file=nombre,
                ),
            )
            continue

        res.files += 1
        for row_number, stream in enumerate(data["streams"], 1):
            if not isinstance(stream, dict):
                _add_error(
                    res,
                    _unrecognized(
                        source_id,
                        "name_recover",
                        ruta,
                        "stream que no es un objeto",
                        line=row_number,
                        file=nombre,
                    ),
                )
                continue
            try:
                relative = int(stream.get("offset", 0) or 0)
                compressed = stream.get("compressed_bytes")
                compressed = int(compressed) if compressed is not None else 0
                inflated = stream.get("inflated_bytes")
                inflated = int(inflated) if inflated is not None else None
            except (TypeError, ValueError) as exc:
                _add_error(
                    res,
                    _unrecognized(
                        source_id,
                        "name_recover",
                        ruta,
                        f"offset o tamano invalido: {exc}",
                        line=row_number,
                        file=nombre,
                    ),
                )
                continue

            offset = base + relative
            paths = stream.get("full_paths") or []
            identifiers = stream.get("identifiers") or []
            if not isinstance(paths, list) or not isinstance(identifiers, list):
                _add_error(
                    res,
                    _unrecognized(
                        source_id,
                        "name_recover",
                        ruta,
                        "full_paths o identifiers no son listas",
                        line=row_number,
                        file=nombre,
                    ),
                )
                continue
            paths = [p for p in paths if isinstance(p, str) and p]
            identifiers = [i for i in identifiers if isinstance(i, str) and i]

            stream_type = str(stream.get("stream_type") or "?")
            state = str(stream.get("status") or "?")
            pretty = f"0x{offset:x}"
            candidate_sources = _candidate_sources(stream)
            xml_stream = stream_type in ("xml", "xml_chunk")

            def provenance_for(kind: str, name: str) -> str:
                sources = candidate_sources.get((kind, name))
                if sources:
                    return "literal" if "xml" in sources else "pattern"
                return "literal" if xml_stream else "pattern"

            res.streams += 1
            res.ranges.setdefault(rpf, []).append((offset, offset + compressed))
            res.stream_rows.append(
                (
                    rpf,
                    offset,
                    pretty,
                    compressed,
                    inflated if inflated is not None else 0,
                    stream_type,
                    state,
                    len(paths),
                    len(identifiers),
                )
            )

            for name in paths:
                provenance = provenance_for("full_path", name)
                res.mentions.append(
                    Mention(
                        source_id=source_id,
                        source_type="name_recover",
                        path=name,
                        rpf=rpf,
                        offset=offset,
                        compressed=compressed,
                        inflated=inflated,
                        provenance=provenance,
                    )
                )
                res.path_rows.append((name, rpf, offset))
                res.paths.add(name)
                res.path_mentions += 1
                if provenance == "literal":
                    res.literal_mentions += 1
                else:
                    res.pattern_mentions += 1

            for name in identifiers:
                res.mentions.append(
                    Mention(
                        source_id=source_id,
                        source_type="name_recover",
                        identifier=name,
                        rpf=rpf,
                        offset=offset,
                        compressed=compressed,
                        inflated=inflated,
                        provenance=provenance_for("identifier", name),
                    )
                )
                res.id_rows.append((name, rpf, offset))
                res.ids.add(name)
                res.id_mentions += 1

            if not paths:
                for name in identifiers:
                    res.orphans.append(
                        {
                            "identifier": name,
                            "rpf": rpf,
                            "offset": offset,
                            "offset_hex": f"0x{offset:x}",
                            "source": source_id,
                        }
                    )

    if res.files == 0:
        res.status = "unrecognized" if res.errors else "empty"
        if res.errors and not res.reason:
            res.reason = "ningun archivo se pudo leer"
    elif res.errors:
        res.status = "partial"
    return res


def load_paths(source_id: str, ruta: str) -> SourceResult:
    res = SourceResult(id=source_id, type="paths", path=ruta)
    if not os.path.isfile(ruta):
        res.status = "unrecognized"
        res.reason = f"no existe: {ruta}"
        _add_error(res, _unrecognized(source_id, "paths", ruta, res.reason))
        return res
    try:
        text = _read_text(ruta)
    except (OSError, UnicodeDecodeError) as exc:
        res.status = "unrecognized"
        res.reason = f"no se pudo leer: {exc}"
        _add_error(res, _unrecognized(source_id, "paths", ruta, res.reason))
        return res

    stripped = text.lstrip("\ufeff").strip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError as exc:
            res.status = "unrecognized"
            res.reason = f"JSON invalido: {exc}"
            _add_error(res, _unrecognized(source_id, "paths", ruta, res.reason))
            return res
        if not isinstance(data, dict) or not isinstance(data.get("paths"), list):
            res.status = "unrecognized"
            res.reason = "el JSON no tiene una lista 'paths'"
            _add_error(res, _unrecognized(source_id, "paths", ruta, res.reason))
            return res
        for line_number, name in enumerate(data["paths"], 1):
            if not isinstance(name, str) or not name.strip():
                _add_error(
                    res,
                    _unrecognized(
                        source_id,
                        "paths",
                        ruta,
                        "entrada de 'paths' que no es una ruta",
                        line=line_number,
                        file=os.path.basename(ruta),
                    ),
                )
                continue
            _add_path_mention(res, name.strip())
    else:
        for line_number, line in enumerate(text.splitlines(), 1):
            name = line.strip()
            if not name or name.startswith("#"):
                continue
            _add_path_mention(res, name)

    if res.errors and res.path_mentions == 0:
        res.status = "unrecognized"
        res.reason = "ninguna linea encaja con el formato de rutas"
    elif res.errors:
        res.status = "partial"
    return res


def _add_path_mention(res: SourceResult, name: str) -> None:
    res.mentions.append(
        Mention(
            source_id=res.id,
            source_type=res.type,
            path=name,
            provenance="declared",
        )
    )
    res.paths.add(name)
    res.path_mentions += 1


def load_inventory(source_id: str, ruta: str, delimiter: str) -> SourceResult:
    source_type = "inventory-tsv" if delimiter == "\t" else "inventory-csv"
    res = SourceResult(id=source_id, type=source_type, path=ruta)
    if not os.path.isfile(ruta):
        res.status = "unrecognized"
        res.reason = f"no existe: {ruta}"
        _add_error(res, _unrecognized(source_id, source_type, ruta, res.reason))
        return res

    try:
        with open(ruta, "r", encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh, delimiter=delimiter))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        res.status = "unrecognized"
        res.reason = f"no se pudo leer: {exc}"
        _add_error(res, _unrecognized(source_id, source_type, ruta, res.reason))
        return res

    header_checked = False
    for line_number, row in enumerate(rows, 1):
        if not row or not any(cell.strip() for cell in row):
            continue
        if row[0].strip().startswith("#"):
            continue
        if not header_checked:
            header_checked = True
            if _is_inventory_header(row):
                continue
        if len(row) < 3:
            _add_error(
                res,
                _unrecognized(
                    source_id,
                    source_type,
                    ruta,
                    "se esperaban 3 columnas: archivo, offset, ruta",
                    line=line_number,
                    file=os.path.basename(ruta),
                ),
            )
            continue
        archive = row[0].strip()
        path = delimiter.join(row[2:]).strip()
        if not path:
            _add_error(
                res,
                _unrecognized(
                    source_id,
                    source_type,
                    ruta,
                    "ruta vacia",
                    line=line_number,
                    file=os.path.basename(ruta),
                ),
            )
            continue
        try:
            offset = _parse_offset(row[1])
        except ValueError as exc:
            _add_error(
                res,
                _unrecognized(
                    source_id,
                    source_type,
                    ruta,
                    str(exc),
                    line=line_number,
                    file=os.path.basename(ruta),
                ),
            )
            continue
        res.mentions.append(
            Mention(
                source_id=source_id,
                source_type=source_type,
                path=path,
                rpf=archive or None,
                offset=offset,
                provenance="declared",
            )
        )
        res.paths.add(path)
        res.path_mentions += 1

    if res.path_mentions == 0 and res.errors:
        res.status = "unrecognized"
        res.reason = "ninguna fila encaja con archivo, offset, ruta"
    elif res.errors:
        res.status = "partial"
    return res


def _is_inventory_header(row: list[str]) -> bool:
    if len(row) < 3:
        return False
    first, second, third = (cell.strip().lower() for cell in row[:3])
    return first in HEADER_FIRST and second in HEADER_SECOND and third in HEADER_THIRD


def load_hashes(source_id: str, ruta: str) -> SourceResult:
    res = SourceResult(id=source_id, type="hashes", path=ruta)
    if not os.path.isfile(ruta):
        res.status = "unrecognized"
        res.reason = f"no existe: {ruta}"
        _add_error(res, _unrecognized(source_id, "hashes", ruta, res.reason))
        return res
    try:
        text = _read_text(ruta)
    except (OSError, UnicodeDecodeError) as exc:
        res.status = "unrecognized"
        res.reason = f"no se pudo leer: {exc}"
        _add_error(res, _unrecognized(source_id, "hashes", ruta, res.reason))
        return res

    for line_number, line in enumerate(text.splitlines(), 1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if not HASH_RE.match(raw):
            _add_error(
                res,
                _unrecognized(
                    source_id,
                    "hashes",
                    ruta,
                    "linea que no es un sha256 hexadecimal",
                    line=line_number,
                    file=os.path.basename(ruta),
                ),
            )
            continue
        digest = raw.lower()
        if digest in res.hashes:
            res.duplicate_hashes += 1
        res.hashes.add(digest)

    if not res.hashes and res.errors:
        res.status = "unrecognized"
        res.reason = "ningun hash valido en el archivo"
    elif res.errors:
        res.status = "partial"
    return res


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------


def _one(values: list[int]) -> int | None:
    return values[0] if len(values) == 1 else None


def _version_report(version: dict[str, Any], extra_sources: set[str]) -> dict[str, Any]:
    compressed_values = version["compressed_values"]
    inflated_values = version["inflated_values"]
    return {
        "offset": version["offset"],
        "offset_hex": f"0x{version['offset']:x}",
        "compressed": _one(compressed_values),
        "compressed_values": compressed_values,
        "inflated": _one(inflated_values),
        "inflated_values": inflated_values,
        "provenance": _provenance(version["provenance"]),
        "sources": sorted(version["sources"] | extra_sources),
        "mentions": version["mentions"],
    }


def _conflict_reason(versions: list[dict[str, Any]]) -> str:
    if len(versions) > 1:
        offsets = ", ".join(f"0x{v['offset']:x}" for v in versions)
        return f"different offsets for the same path: {offsets}"
    version = versions[0]
    details = []
    if len(version["compressed_values"]) > 1:
        details.append(
            "compressed=" + " vs ".join(str(v) for v in version["compressed_values"])
        )
    if len(version["inflated_values"]) > 1:
        details.append(
            "inflated=" + " vs ".join(str(v) for v in version["inflated_values"])
        )
    return f"same offset 0x{version['offset']:x} but different size: " + ", ".join(details)


def build_index(
    mentions: list[Mention],
) -> tuple[list[tuple[Any, ...]], list[dict[str, Any]], dict[str, set[str]]]:
    """Devuelve filas de index.tsv, conflictos y fuentes por ruta."""
    by_path: dict[str, list[Mention]] = defaultdict(list)
    for mention in mentions:
        if mention.path:
            by_path[mention.path].append(mention)

    rows: list[tuple[Any, ...]] = []
    conflicts: list[dict[str, Any]] = []
    path_sources: dict[str, set[str]] = {}

    for path in sorted(by_path):
        group = by_path[path]
        path_sources[path] = {m.source_id for m in group}
        annotations = [m for m in group if m.offset is None]
        versioned = [m for m in group if m.offset is not None]
        annotation_sources = {m.source_id for m in annotations}
        annotation_provenance = {m.provenance for m in annotations}

        by_rpf: dict[str | None, list[Mention]] = defaultdict(list)
        for mention in versioned:
            by_rpf[mention.rpf].append(mention)

        if not by_rpf:
            rows.append(
                (
                    path,
                    "",
                    "",
                    "",
                    "",
                    "",
                    _provenance(annotation_provenance),
                    "ok",
                    ";".join(sorted(annotation_sources)),
                    "",
                )
            )
            continue

        for rpf in sorted(by_rpf, key=lambda value: value or ""):
            rpf_mentions = by_rpf[rpf]
            by_offset: dict[int, list[Mention]] = defaultdict(list)
            for mention in rpf_mentions:
                by_offset[mention.offset].append(mention)

            versions: list[dict[str, Any]] = []
            for offset in sorted(by_offset):
                offset_mentions = by_offset[offset]
                compressed_values = sorted(
                    {m.compressed for m in offset_mentions if m.compressed is not None}
                )
                inflated_values = sorted(
                    {m.inflated for m in offset_mentions if m.inflated is not None}
                )
                versions.append(
                    {
                        "offset": offset,
                        "compressed_values": compressed_values,
                        "inflated_values": inflated_values,
                        "provenance": {m.provenance for m in offset_mentions},
                        "sources": {m.source_id for m in offset_mentions},
                        "mentions": len(offset_mentions),
                    }
                )

            size_conflict = any(
                len(v["compressed_values"]) > 1 or len(v["inflated_values"]) > 1
                for v in versions
            )
            conflict = len(versions) > 1 or size_conflict

            if not conflict:
                version = versions[0]
                compressed = _one(version["compressed_values"])
                inflated = _one(version["inflated_values"])
                rows.append(
                    (
                        path,
                        rpf or "",
                        version["offset"],
                        f"0x{version['offset']:x}",
                        "" if compressed is None else compressed,
                        "" if inflated is None else inflated,
                        _provenance(version["provenance"]),
                        "ok",
                        ";".join(sorted(version["sources"] | annotation_sources)),
                        "",
                    )
                )
                continue

            reason = _conflict_reason(versions)
            literal_versions = [v for v in versions if "literal" in v["provenance"]]
            if (
                len(versions) > 1
                and not size_conflict
                and len(literal_versions) == 1
            ):
                chosen = literal_versions[0]
                compressed = _one(chosen["compressed_values"])
                inflated = _one(chosen["inflated_values"])
                rows.append(
                    (
                        path,
                        rpf or "",
                        chosen["offset"],
                        f"0x{chosen['offset']:x}",
                        "" if compressed is None else compressed,
                        "" if inflated is None else inflated,
                        "literal",
                        "ok",
                        ";".join(sorted(chosen["sources"] | annotation_sources)),
                        "literal_over_pattern",
                    )
                )
                resolution = "literal"
            else:
                resolution = "unresolved"
                for version in versions:
                    compressed_choices = version["compressed_values"] or [None]
                    inflated_choices = version["inflated_values"] or [None]
                    for compressed in compressed_choices:
                        for inflated in inflated_choices:
                            rows.append(
                                (
                                    path,
                                    rpf or "",
                                    version["offset"],
                                    f"0x{version['offset']:x}",
                                    compressed if compressed is not None else "",
                                    inflated if inflated is not None else "",
                                    _provenance(version["provenance"]),
                                    "conflict",
                                    ";".join(
                                        sorted(version["sources"] | annotation_sources)
                                    ),
                                    reason,
                                )
                            )

            conflicts.append(
                {
                    "path": path,
                    "rpf": rpf,
                    "status": "conflict",
                    "reason": reason,
                    "resolution": resolution,
                    "versions": [
                        _version_report(version, annotation_sources) for version in versions
                    ],
                }
            )

    return rows, conflicts, path_sources


def collision_report(
    path_sources: dict[str, set[str]],
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    by_hash: dict[str, list[str]] = defaultdict(list)
    hashes_by_path: dict[str, str] = {}
    for path in sorted(path_sources):
        digest = path_hash(path)
        hashes_by_path[path] = digest
        by_hash[digest].append(path)

    collisions = []
    for digest in sorted(by_hash):
        paths = by_hash[digest]
        if len(paths) > 1:
            sources = sorted({source for path in paths for source in path_sources[path]})
            collisions.append({"hash": digest, "paths": paths, "sources": sources})
    return collisions, hashes_by_path


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------


def _write_tsv(path: str, header: str, rows: list[tuple[Any, ...]]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(header)
        for row in rows:
            fh.write("\t".join(str(value) for value in row) + "\n")


def _source_summary(
    res: SourceResult,
    hashes_by_path: dict[str, str],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "id": res.id,
        "type": res.type,
        "path": res.path,
        "status": res.status,
        "files": res.files,
        "streams": res.streams,
        "path_mentions": res.path_mentions,
        "id_mentions": res.id_mentions,
        "unique_paths": len(res.paths),
        "unique_ids": len(res.ids),
        "literal_mentions": res.literal_mentions,
        "pattern_mentions": res.pattern_mentions,
        "skipped": list(res.skipped),
        "errors": len(res.errors),
    }
    if res.reason:
        summary["reason"] = res.reason
    if res.type == "hashes":
        our_hashes = set(hashes_by_path.values())
        matches = len(res.hashes & our_hashes)
        summary["reference_hashes"] = len(res.hashes)
        summary["duplicate_hashes"] = res.duplicate_hashes
        summary["matched"] = matches
        summary["missing"] = len(res.hashes) - matches
        summary["extra"] = len(our_hashes - res.hashes)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fusiona indices de nombres de origenes distintos y reporta conflictos.",
        epilog=(
            "Forma historica: merge_index.py <dir_tramos> <dir_salida> [--skip ...]\n"
            "Forma multifuente: merge_index.py <dir_salida> --source TIPO=RUTA ...\n"
            "Tipos: name_recover, paths, inventory-tsv, inventory-csv, hashes"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "posicionales",
        nargs="*",
        metavar="RUTA",
        help="<dir_tramos> <dir_salida> (forma historica) o solo <dir_salida> con --source",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        metavar="TIPO=RUTA",
        help="fuente tipada; repetible. Tipos: " + ", ".join(SOURCE_TYPES),
    )
    parser.add_argument(
        "--skip",
        default="",
        help="nombres de archivo separados por coma a descartar (tramos duplicados)",
    )
    args = parser.parse_args(argv)

    if len(args.posicionales) > 2:
        parser.error("se esperaban como maximo <dir_tramos> <dir_salida>")
    if len(args.posicionales) == 2:
        legacy, output_dir = args.posicionales
    elif len(args.posicionales) == 1:
        legacy, output_dir = None, args.posicionales[0]
    else:
        parser.error("falta la carpeta de salida")
    if legacy is None and not args.source:
        parser.error("falta <dir_tramos> o al menos un --source TIPO=RUTA")
    if legacy is not None and not os.path.isdir(legacy):
        sys.exit(f"no existe la carpeta {legacy}")

    skip = {name.strip() for name in args.skip.split(",") if name.strip()}
    os.makedirs(output_dir, exist_ok=True)

    specs: list[tuple[str, str]] = []
    if legacy is not None:
        specs.append(("name_recover", legacy))
    for raw_spec in args.source:
        if "=" not in raw_spec:
            specs.append(("?", raw_spec))
            continue
        source_type, source_path = raw_spec.split("=", 1)
        specs.append((source_type.strip().lower(), source_path.strip()))

    results: list[SourceResult] = []
    unrecognized: list[dict[str, Any]] = []
    seen_ids: dict[str, int] = {}

    for source_type, source_path in specs:
        base_id = f"{source_type}:{source_path}"
        count = seen_ids.get(base_id, 0) + 1
        seen_ids[base_id] = count
        source_id = base_id if count == 1 else f"{base_id}#{count}"

        if source_type == "name_recover":
            result = load_name_recover(source_id, source_path, skip)
        elif source_type == "paths":
            result = load_paths(source_id, source_path)
        elif source_type in ("inventory-tsv", "inventory-csv"):
            result = load_inventory(
                source_id, source_path, "\t" if source_type == "inventory-tsv" else ","
            )
        elif source_type == "hashes":
            result = load_hashes(source_id, source_path)
        else:
            reason = f"tipo de fuente desconocido: {source_type or '(vacio)'}"
            result = SourceResult(
                id=source_id,
                type=source_type or "?",
                path=source_path,
                status="unrecognized",
                reason=reason,
            )
            result.errors.append(
                _unrecognized(source_id, result.type, source_path, reason)
            )
        results.append(result)
        unrecognized.extend(result.errors)

    if legacy is not None and len(specs) == 1:
        legacy_result = results[0]
        if legacy_result.files == 0:
            sys.exit("no hay tramos que fusionar")

    mentions: list[Mention] = []
    stream_rows: list[tuple[Any, ...]] = []
    path_rows: list[tuple[Any, ...]] = []
    id_rows: list[tuple[Any, ...]] = []
    orphans: list[dict[str, Any]] = []
    for result in results:
        mentions.extend(result.mentions)
        stream_rows.extend(result.stream_rows)
        path_rows.extend(result.path_rows)
        id_rows.extend(result.id_rows)
        orphans.extend(result.orphans)

    index_rows, conflicts, path_sources = build_index(mentions)
    collisions, hashes_by_path = collision_report(path_sources)

    _write_tsv(
        os.path.join(output_dir, "streams.tsv"),
        "rpf\tabs_offset\toffset_hex\tcompressed\tinflated\ttype\tstatus\tn_paths\tn_ids\n",
        stream_rows,
    )
    _write_tsv(
        os.path.join(output_dir, "paths.tsv"),
        "ruta\trpf\tabs_offset\n",
        path_rows,
    )
    _write_tsv(
        os.path.join(output_dir, "ids.tsv"),
        "identificador\trpf\tabs_offset\n",
        id_rows,
    )
    _write_tsv(
        os.path.join(output_dir, "index.tsv"),
        "ruta\trpf\tabs_offset\toffset_hex\tcompressed\tinflated\tprocedencia\t"
        "estado\tfuentes\tmotivo\n",
        index_rows,
    )

    por_rpf: dict[str, dict[str, Any]] = {}
    por_tipo: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    total_streams = 0
    total_nombrados = 0
    unique_paths: set[str] = set()
    unique_ids: set[str] = set()
    for result in results:
        if result.type != "name_recover":
            continue
        unique_paths.update(result.paths)
        unique_ids.update(result.ids)
        for row in result.stream_rows:
            rpf, _offset, _pretty, _compressed, _inflated, kind, _state, n_paths, n_ids = row
            total_streams += 1
            slow = por_rpf.setdefault(
                rpf, {"streams": 0, "named": 0, "rangos": []}
            )
            slow["streams"] += 1
            por_tipo[kind][0] += 1
            if n_paths or n_ids:
                total_nombrados += 1
                slow["named"] += 1
                por_tipo[kind][1] += 1
        for rpf, ranges in result.ranges.items():
            por_rpf.setdefault(rpf, {"streams": 0, "named": 0, "rangos": []})[
                "rangos"
            ].extend(ranges)

    for path in path_sources:
        unique_paths.add(path)

    resumen: dict[str, Any] = {
        "tramos": sum(r.files for r in results if r.type == "name_recover"),
        "streams": total_streams,
        "con_nombre": total_nombrados,
        "rutas_unicas": len(unique_paths),
        "ids_unicos": len(unique_ids),
        "por_rpf": {},
        "por_tipo": {},
        "solapes": [],
    }
    for rpf, value in sorted(por_rpf.items(), key=lambda item: -item[1]["named"]):
        ranges = sorted(value["rangos"])
        overlaps = sum(1 for left, right in zip(ranges, ranges[1:]) if right[0] < left[1])
        if overlaps:
            resumen["solapes"].append({"rpf": rpf, "casos": overlaps})
        resumen["por_rpf"][rpf] = {
            "streams": value["streams"],
            "nombrados": value["named"],
            "solapes": overlaps,
        }
    resumen["por_tipo"] = {
        kind: {
            "total": total,
            "nombrados": named,
            "cobertura": round(named / max(1, total) * 100, 2),
        }
        for kind, (total, named) in sorted(por_tipo.items(), key=lambda item: -item[1][0])
    }

    source_summaries = [
        _source_summary(result, hashes_by_path) for result in results
    ]
    resumen["fuentes"] = source_summaries
    resumen["indice"] = {
        "entradas": len(index_rows),
        "ok": sum(1 for row in index_rows if row[7] == "ok"),
        "conflictos": len(conflicts),
    }
    resumen["conflict"] = len(conflicts)
    resumen["collision"] = len(collisions)
    resumen["orphan"] = len(orphans)
    resumen["unrecognized"] = len(unrecognized)
    with open(os.path.join(output_dir, "summary.json"), "w", encoding="utf-8") as fh:
        json.dump(resumen, fh, indent=1, ensure_ascii=False)

    report = {
        "tool": "merge_index.py",
        "salt": SALT,
        "priority": PRIORITY,
        "summary": {
            "sources": len(results),
            "paths": len(path_sources),
            "index_entries": len(index_rows),
            "conflict": len(conflicts),
            "collision": len(collisions),
            "orphan": len(orphans),
            "unrecognized": len(unrecognized),
        },
        "sources": source_summaries,
        "conflict": conflicts,
        "collision": collisions,
        "orphan": orphans,
        "unrecognized": unrecognized,
    }
    with open(os.path.join(output_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, ensure_ascii=False)

    pct = total_nombrados / max(1, total_streams) * 100
    print(f"tramos      {resumen['tramos']}")
    print(f"streams     {total_streams:,}")
    print(f"con nombre  {total_nombrados:,} ({pct:.2f}%)")
    print(f"rutas       {len(unique_paths):,} unicas · ids {len(unique_ids):,} unicos")
    if conflicts:
        print(f"conflictos  {len(conflicts):,} rutas con versiones incompatibles")
    if collisions:
        print(f"colisiones  {len(collisions):,}")
    if orphans:
        print(f"huerfanos   {len(orphans):,} identificadores sin ruta")
    if unrecognized:
        print(f"no recon.   {len(unrecognized):,} entradas o fuentes")
    if resumen["solapes"]:
        print(
            f"ATENCION: solapes en {len(resumen['solapes'])} archivos: "
            f"{resumen['solapes']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
