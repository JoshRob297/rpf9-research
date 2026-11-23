#!/usr/bin/env python3
"""Rebuild the consolidated RPF9 scan index with absolute offsets.

Input: a directory of ``{rpf}__{base}.json`` slices produced by
``tools/name_recover.py``, where ``base`` is the absolute offset (decimal) at
which the slice starts inside the ``.rpf``.  Output: ``streams.tsv``,
``paths.tsv``, ``ids.tsv`` and ``summary.json``.

Rules implemented here (from the T-IDX-MERGE-B brief):

* ``abs_offset = base + offset`` and ``offset_hex`` is the hexadecimal form of
  the absolute offset.
* A stream is named when ``full_paths`` or ``identifiers`` is non-empty; the
  ``status`` field is copied but never used to decide named/unnamed.
* ``packs_1``, ``packs_2`` and ``packs_3`` slices are discarded as overlapping
  re-scans of the same stretch.
* Slices are processed in ascending ``(rpf, base)`` order.  Streams are
  deduplicated by ``(rpf, abs_offset)`` keeping the first occurrence.
* ``paths.tsv`` has one row per distinct ``(ruta, rpf, abs_offset)`` triple and
  ``ids.tsv`` one row per distinct ``(identificador, rpf, abs_offset)`` triple.
* The three TSVs are sorted by their primary-key columns, which is also the
  SQLite primary key, so the export never needs an external sort.

The staging database is a temporary file inside the output directory.  It is
removed after a successful export unless ``--keep-db`` is given.  Memory use is
bounded by the largest single JSON slice (one slice is loaded at a time), not
by the full corpus.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

SLICE_RE = re.compile(r"^(?P<rpf>.+)__(?P<base>\d+)\.json$")
EXCLUDED_RPFS = frozenset(
    {"packs_1", "packs_2", "packs_3", "packs_1.rpf", "packs_2.rpf", "packs_3.rpf"}
)
EXCLUDED_FILES = frozenset(
    {
        "packs_1.json",
        "packs_2.json",
        "packs_3.json",
        "packs_1.rpf.json",
        "packs_2.rpf.json",
        "packs_3.rpf.json",
    }
)

STREAMS_HEADER = (
    "rpf\tabs_offset\toffset_hex\tcompressed\tinflated\ttype\tstatus\tn_paths\tn_ids"
)
PATHS_HEADER = "ruta\trpf\tabs_offset"
IDS_HEADER = "identificador\trpf\tabs_offset"

DEFAULT_DB_NAME = "index.sqlite3"
DEFAULT_BATCH_SIZE = 10_000
WARN_LIMIT = 10

SCHEMA = (
    """
    CREATE TABLE streams (
        rpf        TEXT    NOT NULL,
        abs_offset INTEGER NOT NULL,
        offset_hex TEXT    NOT NULL,
        compressed INTEGER NOT NULL,
        inflated   INTEGER NOT NULL,
        type       TEXT    NOT NULL,
        status     TEXT    NOT NULL,
        n_paths    INTEGER NOT NULL,
        n_ids      INTEGER NOT NULL,
        PRIMARY KEY (rpf, abs_offset)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE paths (
        ruta       TEXT    NOT NULL,
        rpf        TEXT    NOT NULL,
        abs_offset INTEGER NOT NULL,
        PRIMARY KEY (ruta, rpf, abs_offset)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE ids (
        identificador TEXT    NOT NULL,
        rpf           TEXT    NOT NULL,
        abs_offset    INTEGER NOT NULL,
        PRIMARY KEY (identificador, rpf, abs_offset)
    ) WITHOUT ROWID
    """,
)

INSERT_STREAM = (
    "INSERT OR IGNORE INTO streams "
    "(rpf, abs_offset, offset_hex, compressed, inflated, type, status, n_paths, n_ids) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
)
INSERT_PATH = "INSERT OR IGNORE INTO paths (ruta, rpf, abs_offset) VALUES (?, ?, ?)"
INSERT_ID = (
    "INSERT OR IGNORE INTO ids (identificador, rpf, abs_offset) VALUES (?, ?, ?)"
)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _as_int(value: Any) -> int | None:
    """Return an integer value or None; booleans and floats are not offsets."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value, 10)
        except ValueError:
            return None
    return None


def _number_or_zero(value: Any) -> int:
    number = _as_int(value)
    return number if number is not None else 0


def _text(value: Any, default: str = "?") -> str:
    if value is None:
        return default
    return value if isinstance(value, str) else str(value)


def _names(value: Any) -> list[str]:
    """Keep only non-empty strings; the source lists are otherwise untouched."""
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _tsv(value: Any) -> str:
    """Escape the characters that would break a tab-separated line."""
    text = value if isinstance(value, str) else str(value)
    if "\\" not in text and "\t" not in text and "\n" not in text and "\r" not in text:
        return text
    return (
        text.replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def _pct(named: int, total: int) -> float:
    return round(named / total * 100, 2) if total else 0.0


def _warn(message: str) -> None:
    print(f"aviso: {message}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Input discovery
# ---------------------------------------------------------------------------


def discover_slices(input_dir: Path) -> tuple[list[tuple[str, int, Path]], list[str], list[str]]:
    """Return sorted ``(rpf, base, path)`` slices plus excluded and ignored names."""
    slices: list[tuple[str, int, Path]] = []
    excluded: list[str] = []
    ignored: list[str] = []
    for path in input_dir.iterdir():
        if not path.is_file():
            continue
        name = path.name
        if name in EXCLUDED_FILES:
            excluded.append(name)
            continue
        match = SLICE_RE.match(name)
        if match is None:
            if name.endswith(".json"):
                ignored.append(name)
            continue
        rpf = match.group("rpf")
        if rpf in EXCLUDED_RPFS:
            excluded.append(name)
            continue
        slices.append((rpf, int(match.group("base")), path))
    slices.sort(key=lambda item: (item[0], item[1], item[2].name))
    excluded.sort()
    ignored.sort()
    return slices, excluded, ignored


# ---------------------------------------------------------------------------
# SQLite staging
# ---------------------------------------------------------------------------


def _open_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        if db_path.is_dir():
            raise IsADirectoryError(f"la ruta de la base es un directorio: {db_path}")
        db_path.unlink()
    conn = sqlite3.connect(str(db_path))
    conn.isolation_level = None  # explicit BEGIN/COMMIT
    # Bulk-load settings: no rollback journal, no fsync per statement, bounded
    # page cache, temp files on disk.  A crash leaves an unusable staging file,
    # never a partial final export, because the TSVs are written afterwards.
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=FILE")
    conn.execute("PRAGMA cache_size=-65536")  # 64 MiB
    conn.execute("PRAGMA locking_mode=EXCLUSIVE")
    for statement in SCHEMA:
        conn.execute(statement)
    return conn


def _flush(
    conn: sqlite3.Connection,
    streams: list[tuple[Any, ...]],
    paths: list[tuple[Any, ...]],
    ids: list[tuple[Any, ...]],
) -> None:
    if streams:
        conn.executemany(INSERT_STREAM, streams)
        streams.clear()
    if paths:
        conn.executemany(INSERT_PATH, paths)
        paths.clear()
    if ids:
        conn.executemany(INSERT_ID, ids)
        ids.clear()


def _ingest(
    conn: sqlite3.Connection,
    slices: Sequence[tuple[str, int, Path]],
    batch_size: int,
    quiet: bool,
) -> dict[str, int]:
    stream_batch: list[tuple[Any, ...]] = []
    path_batch: list[tuple[Any, ...]] = []
    id_batch: list[tuple[Any, ...]] = []
    path_mentions = 0
    id_mentions = 0
    discarded = 0
    stream_records = 0
    warned = 0

    conn.execute("BEGIN")
    try:
        for position, (rpf, base, path) in enumerate(slices, start=1):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"{path.name}: no se pudo leer el JSON: {exc}") from exc
            if not isinstance(data, dict) or not isinstance(data.get("streams"), list):
                raise ValueError(f"{path.name}: falta la lista streams")
            file_streams = 0
            for index, stream in enumerate(data["streams"]):
                if not isinstance(stream, dict):
                    discarded += 1
                    if warned < WARN_LIMIT:
                        _warn(f"{path.name}: stream #{index} no es un objeto")
                        warned += 1
                    continue
                relative = _as_int(stream.get("offset"))
                if relative is None or relative < 0:
                    discarded += 1
                    if warned < WARN_LIMIT:
                        _warn(f"{path.name}: stream #{index} tiene offset invalido")
                        warned += 1
                    continue
                abs_offset = base + relative
                full_paths = _names(stream.get("full_paths"))
                identifiers = _names(stream.get("identifiers"))
                path_mentions += len(full_paths)
                id_mentions += len(identifiers)
                stream_batch.append(
                    (
                        rpf,
                        abs_offset,
                        f"0x{abs_offset:x}",
                        _number_or_zero(stream.get("compressed_bytes")),
                        _number_or_zero(stream.get("inflated_bytes")),
                        _text(stream.get("stream_type")),
                        _text(stream.get("status")),
                        len(full_paths),
                        len(identifiers),
                    )
                )
                for name in full_paths:
                    path_batch.append((name, rpf, abs_offset))
                for name in identifiers:
                    id_batch.append((name, rpf, abs_offset))
                file_streams += 1
                stream_records += 1
                if len(stream_batch) >= batch_size:
                    _flush(conn, stream_batch, path_batch, id_batch)
            if not quiet:
                print(
                    f"  [{position:>3}/{len(slices)}] {path.name}: {file_streams} streams",
                    file=sys.stderr,
                )
        _flush(conn, stream_batch, path_batch, id_batch)
        conn.execute("COMMIT")
    except BaseException:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.Error:
            pass
        raise

    return {
        "stream_records": stream_records,
        "path_mentions": path_mentions,
        "id_mentions": id_mentions,
        "discarded": discarded,
    }


# ---------------------------------------------------------------------------
# Summary and export
# ---------------------------------------------------------------------------


def _breakdown(conn: sqlite3.Connection) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Aggregate unique streams per container and per type in one table scan.

    Done in Python over the primary-key scan so the summary never needs a
    temporary GROUP BY b-tree and its memory stays O(#rpfs + #types).
    """
    containers: dict[str, list[int]] = {}
    types: dict[str, list[int]] = {}
    cursor = conn.execute("SELECT rpf, type, n_paths, n_ids FROM streams")
    for rpf, stream_type, n_paths, n_ids in cursor:
        named = 1 if (n_paths or n_ids) else 0
        for table, key in ((containers, rpf), (types, stream_type)):
            value = table.setdefault(key, [0, 0])
            value[0] += 1
            value[1] += named

    def pack(values: dict[str, list[int]]) -> dict[str, dict[str, Any]]:
        packed: dict[str, dict[str, Any]] = {}
        for key in sorted(values):
            total, named = values[key]
            packed[key] = {
                "streams": total,
                "named": named,
                "unnamed": total - named,
                "cobertura_pct": _pct(named, total),
            }
        return packed

    return pack(containers), pack(types)


def _count_distinct(conn: sqlite3.Connection, table: str, column: str) -> int:
    """Count distinct values by walking the (column, ...) primary-key order."""
    total = 0
    previous: object = object()
    previous_set = False
    for (value,) in conn.execute(f"SELECT {column} FROM {table} ORDER BY {column}"):
        if not previous_set or value != previous:
            total += 1
            previous = value
            previous_set = True
    return total


def _build_summary(
    conn: sqlite3.Connection,
    *,
    path_mentions: int,
    id_mentions: int,
    files: int,
    excluded: list[str],
    ignored: list[str],
    discarded: int,
) -> dict[str, Any]:
    streams = conn.execute("SELECT COUNT(*) FROM streams").fetchone()[0]
    named = conn.execute(
        "SELECT COUNT(*) FROM streams WHERE n_paths > 0 OR n_ids > 0"
    ).fetchone()[0]
    paths_rows = conn.execute("SELECT COUNT(*) FROM paths").fetchone()[0]
    ids_rows = conn.execute("SELECT COUNT(*) FROM ids").fetchone()[0]
    containers, types = _breakdown(conn)
    return {
        "streams": streams,
        "named": named,
        "cobertura_pct": _pct(named, streams),
        # Distinct name strings, matching the notion used by name_recover.py.
        "paths_unicos": _count_distinct(conn, "paths", "ruta"),
        "path_mentions": path_mentions,
        # Rows of paths.tsv: distinct (ruta, rpf, abs_offset) triples.
        "paths_filas": paths_rows,
        "ids_unicos": _count_distinct(conn, "ids", "identificador"),
        "id_mentions": id_mentions,
        "ids_filas": ids_rows,
        "por_contenedor": containers,
        "por_tipo": types,
        "archivos_leidos": files,
        "archivos_excluidos": excluded,
        "archivos_ignorados": ignored,
        "streams_descartados": discarded,
    }


def _export(conn: sqlite3.Connection, query: str, header: str, target: Path) -> None:
    with open(target, "w", encoding="utf-8", newline="") as fh:
        fh.write(header + "\n")
        for row in conn.execute(query):
            fh.write("\t".join(_tsv(value) for value in row) + "\n")


def _write_outputs(conn: sqlite3.Connection, output_dir: Path, summary: dict[str, Any]) -> None:
    _export(
        conn,
        "SELECT rpf, abs_offset, offset_hex, compressed, inflated, type, status, "
        "n_paths, n_ids FROM streams ORDER BY rpf, abs_offset",
        STREAMS_HEADER,
        output_dir / "streams.tsv",
    )
    _export(
        conn,
        "SELECT ruta, rpf, abs_offset FROM paths ORDER BY ruta, rpf, abs_offset",
        PATHS_HEADER,
        output_dir / "paths.tsv",
    )
    _export(
        conn,
        "SELECT identificador, rpf, abs_offset FROM ids "
        "ORDER BY identificador, rpf, abs_offset",
        IDS_HEADER,
        output_dir / "ids.tsv",
    )
    with open(output_dir / "summary.json", "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reconstruye el indice consolidado de los tramos "
            "{rpf}__{base}.json con offsets absolutos, usando SQLite como "
            "almacen intermedio."
        )
    )
    parser.add_argument("input", type=Path, help="directorio con los tramos JSON")
    parser.add_argument("output", type=Path, help="directorio de salida")
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help=f"SQLite intermedio (por defecto <salida>/{DEFAULT_DB_NAME})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"filas por executemany (por defecto {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="conserva el SQLite intermedio despues de exportar",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="no imprime el progreso por archivo",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    started = time.monotonic()
    args = build_parser().parse_args(argv)

    if args.batch_size <= 0:
        print("error: --batch-size debe ser mayor que cero", file=sys.stderr)
        return 2
    if not args.input.is_dir():
        print(f"error: no existe el directorio de entrada: {args.input}", file=sys.stderr)
        return 2

    slices, excluded, ignored = discover_slices(args.input)
    if not slices:
        print(
            f"error: no hay tramos {{rpf}}__{{base}}.json en {args.input}",
            file=sys.stderr,
        )
        return 2

    output_dir: Path = args.output
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"error: no se pudo crear {output_dir}: {exc}", file=sys.stderr)
        return 2
    if not output_dir.is_dir():
        print(f"error: la salida no es un directorio: {output_dir}", file=sys.stderr)
        return 2

    db_path: Path = args.db if args.db is not None else output_dir / DEFAULT_DB_NAME
    conn: sqlite3.Connection | None = None
    try:
        conn = _open_db(db_path)
        stats = _ingest(conn, slices, args.batch_size, args.quiet)
        summary = _build_summary(
            conn,
            path_mentions=stats["path_mentions"],
            id_mentions=stats["id_mentions"],
            files=len(slices),
            excluded=excluded,
            ignored=ignored,
            discarded=stats["discarded"],
        )
        _write_outputs(conn, output_dir, summary)
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(
            f"error: {exc}; SQLite intermedio conservado en {db_path}",
            file=sys.stderr,
        )
        return 2
    finally:
        if conn is not None:
            conn.close()

    if not args.keep_db:
        try:
            db_path.unlink(missing_ok=True)
        except OSError as exc:
            _warn(f"no se pudo borrar {db_path}: {exc}")

    elapsed = time.monotonic() - started
    print(
        "streams={streams} named={named} cobertura_pct={cobertura_pct} "
        "paths_unicos={paths_unicos} path_mentions={path_mentions} "
        "paths_filas={paths_filas} ids_unicos={ids_unicos} "
        "id_mentions={id_mentions} ids_filas={ids_filas}".format(**summary)
    )
    if not args.quiet:
        print(f"segundos={elapsed:.2f} sqlite={db_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
