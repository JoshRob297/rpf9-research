#!/usr/bin/env python3
"""Resolve manifest paths to asset bytes inside RPF9 containers (GTA VI research).

The resolver is index-driven: it never parses the encrypted RPF9 table of
contents. For every ``(rpf, abs_offset)`` mention found in ``paths-*.tsv`` it
looks up the matching row in ``streams-*.tsv``, seeks to ``abs_offset`` inside
the container, reads exactly ``compressed`` bytes and, if that slice starts
with 0x78, inflates it with zlib. The result must be exactly ``inflated`` bytes.

Only the standard library is used.
"""

from __future__ import annotations

import argparse
import csv
import random
import re
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

# No hay rutas por defecto: el indice y los contenedores los pone quien llama. Un
# default apuntando al arbol de quien lo escribio solo funciona en esa maquina.
DEFAULT_INDEX_DIR = None
DEFAULT_RPF_DIR = None

ZLIB_PREFIX = b"\x78"

STREAM_COLUMNS = (
    "rpf",
    "abs_offset",
    "offset_hex",
    "compressed",
    "inflated",
    "type",
    "status",
    "n_paths",
    "n_ids",
)
PATH_COLUMNS = ("ruta", "rpf", "abs_offset")
_RPF_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class ResolveError(RuntimeError):
    """A resolution failure with a stable machine-readable ``reason``."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class Stream:
    """One row of ``streams-*.tsv``: a unique compressed stream in a container."""

    rpf: str
    abs_offset: int
    offset_hex: str
    compressed: int
    inflated: int
    stream_type: str
    status: str
    n_paths: int
    n_ids: int


@dataclass(frozen=True)
class Mention:
    """One row of ``paths-*.tsv``: a route mentioning a stream."""

    path: str
    rpf: str
    abs_offset: int


@dataclass(frozen=True)
class Resolution:
    """The bytes of one mention, plus the bookkeeping needed to explain them."""

    mention: Mention
    stream: Stream
    data: bytes
    decompressed: bool


@dataclass(frozen=True)
class VerifyFailure:
    path: str
    mention_index: int
    mention_total: int
    mention: Mention
    error: ResolveError


@dataclass(frozen=True)
class VerifyReport:
    requested: int
    sampled: int
    available: int
    seed: int
    rpf: str | None
    sampled_paths: tuple[str, ...]
    mentions: int
    passed: int
    failed: int
    paths_passed: int
    paths_failed: int
    failures: tuple[VerifyFailure, ...]


# ---------------------------------------------------------------------------
# Index loading
# ---------------------------------------------------------------------------


def _validate_rpf_name(name: str, source: str) -> str:
    if not name or name in {".", ".."} or not _RPF_NAME_RE.fullmatch(name):
        raise ResolveError(
            "index_error", f"{source}: invalid rpf name {name!r} (expected [A-Za-z0-9_.-]+)"
        )
    return name


def _read_tsv(path: Path, required: tuple[str, ...]) -> list[tuple[int, dict[str, str]]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            fieldnames = reader.fieldnames or []
            missing = [column for column in required if column not in fieldnames]
            if missing:
                raise ResolveError(
                    "index_error",
                    f"{path}: missing column(s): {', '.join(missing)}; "
                    f"found header: {', '.join(fieldnames) or '(empty)'}",
                )
            rows: list[tuple[int, dict[str, str]]] = []
            for lineno, row in enumerate(reader, start=2):
                if None in row:
                    raise ResolveError(
                        "index_error", f"{path}:{lineno}: too many columns"
                    )
                values = [value for value in row.values() if isinstance(value, str)]
                if not values or all(not value.strip() for value in values):
                    continue
                rows.append((lineno, row))
            return rows
    except OSError as exc:
        raise ResolveError("index_error", f"cannot read {path}: {exc}") from exc


def _text_field(row: dict[str, str], column: str, path: Path, lineno: int) -> str:
    value = row.get(column)
    if value is None or not value.strip():
        raise ResolveError(
            "index_error", f"{path}:{lineno}: column '{column}' is empty"
        )
    return value.strip()


def _int_field(row: dict[str, str], column: str, path: Path, lineno: int) -> int:
    value = _text_field(row, column, path, lineno)
    try:
        number = int(value)
    except ValueError:
        raise ResolveError(
            "index_error",
            f"{path}:{lineno}: column '{column}' is not an integer: {value!r}",
        ) from None
    if number < 0:
        raise ResolveError(
            "index_error", f"{path}:{lineno}: column '{column}' is negative: {number}"
        )
    return number


def load_streams(index_dir: Path) -> dict[tuple[str, int], Stream]:
    """Load every ``streams-*.tsv`` into a ``(rpf, abs_offset) -> Stream`` map."""
    index_dir = Path(index_dir)
    if not index_dir.is_dir():
        raise ResolveError("index_error", f"index directory not found: {index_dir}")
    files = sorted(index_dir.glob("streams-*.tsv"))
    if not files:
        raise ResolveError("index_error", f"no streams-*.tsv files in {index_dir}")

    streams: dict[tuple[str, int], Stream] = {}
    origins: dict[tuple[str, int], str] = {}
    for path in files:
        for lineno, row in _read_tsv(path, STREAM_COLUMNS):
            source = f"{path}:{lineno}"
            rpf = _validate_rpf_name(_text_field(row, "rpf", path, lineno), source)
            abs_offset = _int_field(row, "abs_offset", path, lineno)
            offset_hex = _text_field(row, "offset_hex", path, lineno)
            try:
                hex_offset = int(offset_hex, 16)
            except ValueError:
                raise ResolveError(
                    "index_error",
                    f"{source}: column 'offset_hex' is not hexadecimal: {offset_hex!r}",
                ) from None
            if hex_offset != abs_offset:
                raise ResolveError(
                    "index_error",
                    f"{source}: offset_hex {offset_hex} != abs_offset {abs_offset}",
                )
            key = (rpf, abs_offset)
            if key in streams:
                raise ResolveError(
                    "index_error",
                    f"duplicate stream (rpf={rpf}, abs_offset={abs_offset}) "
                    f"in {source} and {origins[key]}",
                )
            streams[key] = Stream(
                rpf=rpf,
                abs_offset=abs_offset,
                offset_hex=offset_hex,
                compressed=_int_field(row, "compressed", path, lineno),
                inflated=_int_field(row, "inflated", path, lineno),
                stream_type=_text_field(row, "type", path, lineno),
                status=_text_field(row, "status", path, lineno),
                n_paths=_int_field(row, "n_paths", path, lineno),
                n_ids=_int_field(row, "n_ids", path, lineno),
            )
            origins[key] = source
    return streams


def load_mentions(index_dir: Path) -> list[Mention]:
    """Load every ``paths-*.tsv`` row, in file order, as a Mention."""
    index_dir = Path(index_dir)
    if not index_dir.is_dir():
        raise ResolveError("index_error", f"index directory not found: {index_dir}")
    files = sorted(index_dir.glob("paths-*.tsv"))
    if not files:
        raise ResolveError("index_error", f"no paths-*.tsv files in {index_dir}")

    mentions: list[Mention] = []
    for path in files:
        for lineno, row in _read_tsv(path, PATH_COLUMNS):
            source = f"{path}:{lineno}"
            route = _text_field(row, "ruta", path, lineno)
            rpf = _validate_rpf_name(_text_field(row, "rpf", path, lineno), source)
            mentions.append(
                Mention(
                    path=route,
                    rpf=rpf,
                    abs_offset=_int_field(row, "abs_offset", path, lineno),
                )
            )
    return mentions


def group_mentions(mentions: list[Mention]) -> dict[str, list[Mention]]:
    """Group mentions by route, preserving index order."""
    by_path: dict[str, list[Mention]] = {}
    for mention in mentions:
        by_path.setdefault(mention.path, []).append(mention)
    return by_path


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def container_path(rpf_dir: Path, rpf: str) -> Path:
    return Path(rpf_dir) / f"{_validate_rpf_name(rpf, 'container')}.rpf"


def find_mentions(
    path: str,
    mentions_by_path: dict[str, list[Mention]],
    rpf: str | None = None,
) -> list[Mention]:
    """Return every mention of ``path`` (optionally filtered by container)."""
    mentions = mentions_by_path.get(path)
    if not mentions:
        raise ResolveError("path_not_found", f"path not found in index: {path!r}")
    if rpf is None:
        return list(mentions)
    filtered = [mention for mention in mentions if mention.rpf == rpf]
    if not filtered:
        raise ResolveError(
            "path_not_found",
            f"path not found in index for rpf={rpf!r}: {path!r}",
        )
    return filtered


def resolve_mention(
    mention: Mention,
    streams: dict[tuple[str, int], Stream],
    rpf_dir: Path,
) -> Resolution:
    """Seek to one mention, read its stream slice and validate its size."""
    key = (mention.rpf, mention.abs_offset)
    stream = streams.get(key)
    if stream is None:
        raise ResolveError(
            "stream_missing",
            f"no stream row for rpf={mention.rpf} abs_offset={mention.abs_offset} "
            f"(path={mention.path!r})",
        )

    container = container_path(rpf_dir, mention.rpf)
    if not container.is_file():
        raise ResolveError(
            "container_missing",
            f"container not found: {container} (rpf={mention.rpf}, "
            f"path={mention.path!r})",
        )

    try:
        with container.open("rb") as fh:
            fh.seek(mention.abs_offset)
            raw = fh.read(stream.compressed)
    except OSError as exc:
        raise ResolveError(
            "container_read_error", f"cannot read {container}: {exc}"
        ) from exc

    if len(raw) != stream.compressed:
        raise ResolveError(
            "short_read",
            f"short read from {container} at offset {mention.abs_offset}: "
            f"expected {stream.compressed} bytes, read {len(raw)} "
            f"(container size {container.stat().st_size})",
        )

    decompressed = raw[: len(ZLIB_PREFIX)] == ZLIB_PREFIX
    if decompressed:
        try:
            payload = zlib.decompress(raw)
        except zlib.error as exc:
            raise ResolveError(
                "zlib_error",
                f"zlib decompression failed for {mention.path!r} at "
                f"{container}:{mention.abs_offset}: {exc}",
            ) from exc
    else:
        payload = raw

    if len(payload) != stream.inflated:
        raise ResolveError(
            "size_mismatch",
            f"size check failed for {mention.path!r} at "
            f"{container}:{mention.abs_offset}: expected {stream.inflated} inflated "
            f"bytes, got {len(payload)} (decompressed={decompressed}, "
            f"compressed={stream.compressed})",
        )

    return Resolution(
        mention=mention,
        stream=stream,
        data=payload,
        decompressed=decompressed,
    )


def resolve_path(
    path: str,
    mentions_by_path: dict[str, list[Mention]],
    streams: dict[tuple[str, int], Stream],
    rpf_dir: Path,
    rpf: str | None = None,
) -> list[Resolution]:
    """Resolve every mention of ``path`` (the CLI may use only the first one)."""
    mentions = find_mentions(path, mentions_by_path, rpf=rpf)
    return [resolve_mention(mention, streams, rpf_dir) for mention in mentions]


# ---------------------------------------------------------------------------
# Random verification
# ---------------------------------------------------------------------------


def verify(
    index_dir: Path,
    rpf_dir: Path,
    n: int,
    rpf: str | None = None,
    seed: int = 0,
) -> VerifyReport:
    """Resolve ``n`` random routes (all their mentions) and summarize size checks."""
    if n <= 0:
        raise ValueError("n must be positive")

    streams = load_streams(index_dir)
    mentions_by_path = group_mentions(load_mentions(index_dir))

    available_paths = sorted(
        path
        for path, mentions in mentions_by_path.items()
        if rpf is None or any(mention.rpf == rpf for mention in mentions)
    )
    if not available_paths:
        raise ResolveError(
            "path_not_found", f"no paths in index for rpf={rpf!r}" if rpf else "index has no paths"
        )

    sampled = min(n, len(available_paths))
    rng = random.Random(seed)
    chosen = tuple(rng.sample(available_paths, sampled))

    mentions_total = 0
    passed = 0
    failed = 0
    paths_passed = 0
    paths_failed = 0
    failures: list[VerifyFailure] = []

    for path in chosen:
        mentions = [
            mention
            for mention in mentions_by_path[path]
            if rpf is None or mention.rpf == rpf
        ]
        path_failed = False
        for index, mention in enumerate(mentions, start=1):
            mentions_total += 1
            try:
                resolve_mention(mention, streams, rpf_dir)
            except ResolveError as exc:
                failed += 1
                path_failed = True
                failures.append(
                    VerifyFailure(
                        path=path,
                        mention_index=index,
                        mention_total=len(mentions),
                        mention=mention,
                        error=exc,
                    )
                )
            else:
                passed += 1
        if path_failed:
            paths_failed += 1
        else:
            paths_passed += 1

    return VerifyReport(
        requested=n,
        sampled=sampled,
        available=len(available_paths),
        seed=seed,
        rpf=rpf,
        sampled_paths=chosen,
        mentions=mentions_total,
        passed=passed,
        failed=failed,
        paths_passed=paths_passed,
        paths_failed=paths_failed,
        failures=tuple(failures),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not an integer: {text!r}") from None
    if value <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="resolve_path.py",
        description=(
            "Resolve a manifest route to the bytes of its asset inside an RPF9 "
            "container, using streams-*.tsv / paths-*.tsv as the index."
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="route exactly as listed in paths-*.tsv (quote it if it starts with '$(...)')",
    )
    parser.add_argument(
        "--index-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help=f"directory with streams-*.tsv and paths-*.tsv (default: {DEFAULT_INDEX_DIR})",
    )
    parser.add_argument(
        "--rpf-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help=f"directory with the .rpf containers (default: {DEFAULT_RPF_DIR})",
    )
    parser.add_argument(
        "--rpf",
        metavar="NAME",
        help="only consider mentions in this container (e.g. data)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        metavar="FILE",
        help="write the resolved bytes to FILE instead of stdout",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--info",
        action="store_true",
        help="print rpf, offset, type, sizes and whether zlib was used",
    )
    mode.add_argument(
        "--all",
        action="store_true",
        help="list and check every mention of the route",
    )
    mode.add_argument(
        "--verify",
        type=_positive_int,
        metavar="N",
        help="resolve N random routes from the index and report size-check results",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="random seed for --verify (default: 0, reproducible sampling)",
    )
    return parser


def _print_info(path: str, mentions: list[Mention], resolution: Resolution) -> None:
    total = len(mentions)
    suffix = f" (first of {total}; use --all to list every mention)" if total > 1 else ""
    print(f"path: {path}")
    print(f"mentions: {total}")
    print(f"mention: 1/{total}{suffix}")
    print(f"rpf: {resolution.mention.rpf}")
    print(
        f"offset: {resolution.mention.abs_offset} ({resolution.stream.offset_hex})"
    )
    print(f"type: {resolution.stream.stream_type}")
    print(f"compressed: {resolution.stream.compressed}")
    print(f"inflated: {resolution.stream.inflated}")
    print(f"decompressed: {'yes' if resolution.decompressed else 'no'}")
    print(
        f"size_check: ok ({len(resolution.data)} == {resolution.stream.inflated})"
    )


def _print_all(
    path: str,
    mentions: list[Mention],
    streams: dict[tuple[str, int], Stream],
    rpf_dir: Path,
) -> int:
    total = len(mentions)
    passed = 0
    failed = 0
    lines = [f"path: {path}", f"mentions: {total}"]
    for index, mention in enumerate(mentions, start=1):
        prefix = f"[{index}/{total}] rpf={mention.rpf} offset={mention.abs_offset}"
        try:
            resolution = resolve_mention(mention, streams, rpf_dir)
        except ResolveError as exc:
            failed += 1
            lines.append(f"{prefix} error={exc.reason}: {exc}")
        else:
            passed += 1
            lines.append(
                f"{prefix} ({resolution.stream.offset_hex}) "
                f"type={resolution.stream.stream_type} "
                f"compressed={resolution.stream.compressed} "
                f"inflated={resolution.stream.inflated} "
                f"decompressed={'yes' if resolution.decompressed else 'no'} "
                f"check=ok"
            )
    lines.append(f"summary: {total} mentions, {passed} passed, {failed} failed")
    print("\n".join(lines))
    return 0 if failed == 0 else 1


def _print_verify(report: VerifyReport) -> None:
    details = [f"seed={report.seed}"]
    if report.rpf is not None:
        details.append(f"rpf={report.rpf}")
    if report.requested != report.sampled:
        details.append(f"requested {report.requested}, capped")
    print(
        f"verify: sampled {report.sampled} of {report.available} paths "
        f"({'; '.join(details)})"
    )
    print(
        f"mentions: {report.mentions} resolved, {report.passed} passed, "
        f"{report.failed} failed"
    )
    print(
        f"paths: {report.paths_passed} passed, {report.paths_failed} failed"
    )
    if report.failures:
        counts: dict[str, int] = {}
        for failure in report.failures:
            counts[failure.error.reason] = counts.get(failure.error.reason, 0) + 1
        print(
            "failure reasons: "
            + ", ".join(f"{reason}={count}" for reason, count in sorted(counts.items()))
        )
        print("failures:")
        for failure in report.failures:
            print(
                f"  path={failure.path} "
                f"mention={failure.mention_index}/{failure.mention_total} "
                f"rpf={failure.mention.rpf} "
                f"offset={failure.mention.abs_offset} "
                f"reason={failure.error.reason}: {failure.error}"
            )
    else:
        print("failure reasons: none")
    print("verify: PASS" if report.failed == 0 else "verify: FAIL")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    faltan = [n for n, v in (("--index-dir", args.index_dir), ("--rpf-dir", args.rpf_dir)) if v is None]
    if faltan:
        parser.error(
            "faltan " + " y ".join(faltan) + ": el indice y los contenedores no tienen ruta por defecto"
        )

    if args.verify is not None:
        if args.path is not None:
            parser.error("a PATH argument cannot be combined with --verify")
        if args.out is not None:
            parser.error("--out cannot be combined with --verify")
        try:
            report = verify(
                args.index_dir,
                args.rpf_dir,
                args.verify,
                rpf=args.rpf,
                seed=args.seed,
            )
        except ResolveError as exc:
            print(f"{parser.prog}: error: {exc}", file=sys.stderr)
            return 1
        _print_verify(report)
        return 0 if report.failed == 0 else 1

    if args.path is None:
        parser.error("a PATH argument is required unless --verify is used")
    if args.out is not None and (args.info or args.all):
        parser.error("--out cannot be combined with --info or --all")

    try:
        streams = load_streams(args.index_dir)
        mentions_by_path = group_mentions(load_mentions(args.index_dir))
        mentions = find_mentions(args.path, mentions_by_path, rpf=args.rpf)

        if args.all:
            return _print_all(args.path, mentions, streams, args.rpf_dir)

        resolution = resolve_mention(mentions[0], streams, args.rpf_dir)

        if args.info:
            _print_info(args.path, mentions, resolution)
            return 0

        if args.out is not None:
            try:
                args.out.write_bytes(resolution.data)
            except OSError as exc:
                raise ResolveError(
                    "write_error", f"cannot write {args.out}: {exc}"
                ) from exc
            print(
                f"wrote {len(resolution.data)} bytes to {args.out}", file=sys.stderr
            )
            return 0

        if sys.stdout.isatty():
            raise ResolveError(
                "stdout_is_tty",
                "refusing to write binary asset bytes to a terminal; "
                "use --out FILE or redirect stdout",
            )
        sys.stdout.buffer.write(resolution.data)
        sys.stdout.buffer.flush()
        return 0
    except ResolveError as exc:
        print(f"{parser.prog}: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
