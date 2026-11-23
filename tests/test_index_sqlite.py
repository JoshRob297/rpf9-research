"""Tests for tools/index_full_sqlite.py (compatible with pytest and unittest).

The synthetic fixtures exercise every merge rule: absolute offsets, the
``packs_1/2/3`` exclusion, first-occurrence deduplication by ``rpf + abs_offset``,
triple deduplication in ``paths.tsv``/``ids.tsv``, and the ORDER BY contract.

The real-fixture test compares the tool against a deliberately naive in-memory
oracle and pins the exact totals for ``/home/sistver/idx-fixtures``.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import re
import sys
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import index_full_sqlite  # noqa: E402

FIXTURES = Path("/home/sistver/idx-fixtures")
REAL_FILES = (
    "core_bvh4__0.json",
    "levels__13841203200.json",
    "levels__36909875200.json",
)
SLICE_RE = re.compile(r"^(?P<rpf>.+)__(?P<base>\d+)\.json$")
EXCLUDED_RPFS = {
    "packs_1",
    "packs_2",
    "packs_3",
    "packs_1.rpf",
    "packs_2.rpf",
    "packs_3.rpf",
}


def _plain_stream(
    offset: int,
    *,
    compressed: int = 1,
    inflated: int = 2,
    stream_type: str = "raw",
    status: str = "named",
    paths: list[str] | None = None,
    identifiers: list[str] | None = None,
) -> dict:
    return {
        "file": "synthetic",
        "offset": offset,
        "offset_hex": f"0x{offset:x}",
        "compressed_bytes": compressed,
        "inflated_bytes": inflated,
        "stream_type": stream_type,
        "status": status,
        "full_paths": list(paths or []),
        "identifiers": list(identifiers or []),
        "candidates": [],
    }


# ---------------------------------------------------------------------------
# Oracle and readers
# ---------------------------------------------------------------------------


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _naive_merge(input_dir: Path) -> dict:
    """In-memory reference implementation of the brief, used as an oracle."""
    files = []
    for path in input_dir.iterdir():
        if not path.is_file():
            continue
        match = SLICE_RE.match(path.name)
        if not match:
            continue
        rpf = match.group("rpf")
        if rpf in EXCLUDED_RPFS or path.name in {
            "packs_1.json",
            "packs_2.json",
            "packs_3.json",
            "packs_1.rpf.json",
            "packs_2.rpf.json",
            "packs_3.rpf.json",
        }:
            continue
        files.append((rpf, int(match.group("base")), path.name))
    files.sort()

    streams: dict[tuple[str, int], tuple] = {}
    paths: set[tuple[str, str, int]] = set()
    ids: set[tuple[str, str, int]] = set()
    path_mentions = 0
    id_mentions = 0
    for rpf, base, name in files:
        with open(input_dir / name, encoding="utf-8") as fh:
            data = json.load(fh)
        for stream in data["streams"]:
            offset = base + int(stream["offset"])
            full_paths = [p for p in (stream.get("full_paths") or []) if p]
            identifiers = [i for i in (stream.get("identifiers") or []) if i]
            path_mentions += len(full_paths)
            id_mentions += len(identifiers)
            key = (rpf, offset)
            if key not in streams:
                streams[key] = (
                    rpf,
                    offset,
                    f"0x{offset:x}",
                    int(stream.get("compressed_bytes") or 0),
                    int(stream.get("inflated_bytes") or 0),
                    str(stream.get("stream_type") or "?"),
                    str(stream.get("status") or "?"),
                    len(full_paths),
                    len(identifiers),
                )
            for value in full_paths:
                paths.add((value, rpf, offset))
            for value in identifiers:
                ids.add((value, rpf, offset))
    return {
        "files": [item[2] for item in files],
        "streams": [streams[key] for key in sorted(streams)],
        "paths": sorted(paths),
        "ids": sorted(ids),
        "path_mentions": path_mentions,
        "id_mentions": id_mentions,
    }


def _run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = index_full_sqlite.main(argv)
    return code, out.getvalue(), err.getvalue()


# ---------------------------------------------------------------------------
# Synthetic tests: one rule per assertion, plus the end-to-end shape
# ---------------------------------------------------------------------------


class SyntheticRuleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.inp = self.tmp / "in"
        self.out = self.tmp / "out"
        self.inp.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _slice(self, name: str, streams: list[dict], folder: Path | None = None) -> Path:
        folder = folder or self.inp
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_text(json.dumps({"streams": streams}), encoding="utf-8")
        return path

    def _run_ok(self) -> dict:
        code, stdout, stderr = _run([str(self.inp), str(self.out)])
        self.assertEqual(code, 0, stderr)
        self.assertIn("streams", stdout)
        with open(self.out / "summary.json", encoding="utf-8") as fh:
            return json.load(fh)

    def _make_full_case(self) -> None:
        # alpha.rpf base 0: one unnamed-by-list stream whose status lies, one
        # stream with duplicated mentions, and one stream named by lists only.
        self._slice(
            "alpha.rpf__0.json",
            [
                _plain_stream(
                    4096,
                    compressed=100,
                    inflated=200,
                    stream_type="rsc50",
                    status="named",
                ),
                _plain_stream(
                    8192,
                    compressed=10,
                    inflated=20,
                    stream_type="xml",
                    paths=["$(root)/a.ydr", "$(root)/a.ydr"],
                    identifiers=["id_a", "id_a"],
                ),
                _plain_stream(
                    12288,
                    compressed=30,
                    inflated=40,
                    stream_type="xml",
                    status="unnamed",
                    paths=["$(root)/a.ydr"],
                    identifiers=["id_a"],
                ),
            ],
        )
        # Same absolute offset as the first alpha stream, later base: the first
        # occurrence must win and this metadata must not overwrite it.
        self._slice(
            "alpha.rpf__4096.json",
            [
                _plain_stream(
                    0,
                    compressed=999,
                    inflated=888,
                    status="named",
                )
            ],
        )
        self._slice(
            "beta.rpf__0.json",
            [_plain_stream(0, paths=["zeta"], identifiers=["zzz"])],
        )
        self._slice(
            "beta.rpf__1024.json",
            [_plain_stream(8, paths=["alpha"], identifiers=["aaa"])],
        )
        # Re-scans of the same stretch: must be discarded entirely.
        for index in (1, 2, 3):
            self._slice(
                f"packs_{index}__0.json",
                [_plain_stream(0, paths=["should/not/appear"])],
            )
            self._slice(
                f"packs_{index}.json",
                [_plain_stream(0, paths=["should/not/appear"])],
            )
        # Files that do not follow the slice naming contract are not tramos.
        (self.inp / "notes.json").write_text(
            json.dumps({"streams": [_plain_stream(0, paths=["ignored"])]}),
            encoding="utf-8",
        )
        (self.inp / "broken__notanumber.json").write_text(
            json.dumps({"streams": [_plain_stream(0, paths=["ignored"])]}),
            encoding="utf-8",
        )

    def test_end_to_end_rules_outputs_and_summary(self) -> None:
        self._make_full_case()
        summary = self._run_ok()

        self.assertEqual(
            (self.out / "streams.tsv").read_text(encoding="utf-8").splitlines()[0],
            "rpf\tabs_offset\toffset_hex\tcompressed\tinflated\ttype\tstatus\tn_paths\tn_ids",
        )
        self.assertEqual(
            (self.out / "paths.tsv").read_text(encoding="utf-8").splitlines()[0],
            "ruta\trpf\tabs_offset",
        )
        self.assertEqual(
            (self.out / "ids.tsv").read_text(encoding="utf-8").splitlines()[0],
            "identificador\trpf\tabs_offset",
        )

        streams = _read_tsv(self.out / "streams.tsv")
        self.assertEqual(
            [tuple(row.values()) for row in streams],
            [
                ("alpha.rpf", "4096", "0x1000", "100", "200", "rsc50", "named", "0", "0"),
                ("alpha.rpf", "8192", "0x2000", "10", "20", "xml", "named", "2", "2"),
                ("alpha.rpf", "12288", "0x3000", "30", "40", "xml", "unnamed", "1", "1"),
                ("beta.rpf", "0", "0x0", "1", "2", "raw", "named", "1", "1"),
                ("beta.rpf", "1032", "0x408", "1", "2", "raw", "named", "1", "1"),
            ],
        )
        # packs_1/2/3 and non-slice files never reach the tables.
        self.assertNotIn("packs", {row["rpf"] for row in streams})
        self.assertNotIn(
            "should/not/appear",
            {row["ruta"] for row in _read_tsv(self.out / "paths.tsv")},
        )

        paths = _read_tsv(self.out / "paths.tsv")
        self.assertEqual(
            [tuple(row.values()) for row in paths],
            [
                ("$(root)/a.ydr", "alpha.rpf", "8192"),
                ("$(root)/a.ydr", "alpha.rpf", "12288"),
                ("alpha", "beta.rpf", "1032"),
                ("zeta", "beta.rpf", "0"),
            ],
        )

        ids = _read_tsv(self.out / "ids.tsv")
        self.assertEqual(
            [tuple(row.values()) for row in ids],
            [
                ("aaa", "beta.rpf", "1032"),
                ("id_a", "alpha.rpf", "8192"),
                ("id_a", "alpha.rpf", "12288"),
                ("zzz", "beta.rpf", "0"),
            ],
        )

        self.assertEqual(summary["streams"], 5)
        self.assertEqual(summary["named"], 4)
        self.assertEqual(summary["cobertura_pct"], 80.0)
        self.assertEqual(summary["paths_unicos"], 3)
        self.assertEqual(summary["path_mentions"], 5)
        self.assertEqual(summary["paths_filas"], 4)
        self.assertEqual(summary["ids_unicos"], 3)
        self.assertEqual(summary["id_mentions"], 5)
        self.assertEqual(summary["ids_filas"], 4)
        self.assertEqual(set(summary["por_contenedor"]), {"alpha.rpf", "beta.rpf"})
        self.assertEqual(
            summary["por_contenedor"]["alpha.rpf"],
            {"streams": 3, "named": 2, "unnamed": 1, "cobertura_pct": 66.67},
        )
        self.assertEqual(
            summary["por_contenedor"]["beta.rpf"],
            {"streams": 2, "named": 2, "unnamed": 0, "cobertura_pct": 100.0},
        )
        self.assertEqual(
            summary["por_tipo"],
            {
                "rsc50": {"streams": 1, "named": 0, "unnamed": 1, "cobertura_pct": 0.0},
                "xml": {"streams": 2, "named": 2, "unnamed": 0, "cobertura_pct": 100.0},
                "raw": {"streams": 2, "named": 2, "unnamed": 0, "cobertura_pct": 100.0},
            },
        )

    def test_default_run_removes_the_sqlite_staging_file(self) -> None:
        self._make_full_case()
        self._run_ok()
        self.assertFalse((self.out / "index.sqlite3").exists())
        self.assertEqual(
            sorted(path.name for path in self.out.iterdir()),
            ["ids.tsv", "paths.tsv", "streams.tsv", "summary.json"],
        )

    def test_keep_db_flag_preserves_the_sqlite_staging_file(self) -> None:
        self._make_full_case()
        code, _stdout, stderr = _run(
            [str(self.inp), str(self.out), "--keep-db"]
        )
        self.assertEqual(code, 0, stderr)
        self.assertTrue((self.out / "index.sqlite3").exists())

    def test_empty_input_directory_fails_with_exit_code_2(self) -> None:
        code, _stdout, stderr = _run([str(self.inp), str(self.out)])
        self.assertEqual(code, 2)
        self.assertIn("no hay tramos", stderr)
        self.assertFalse((self.out / "summary.json").exists())

    def test_missing_input_directory_fails_with_exit_code_2(self) -> None:
        code, _stdout, stderr = _run([str(self.tmp / "nope"), str(self.out)])
        self.assertEqual(code, 2)
        self.assertIn("no existe", stderr)

    def test_invalid_records_and_empty_strings_handled(self) -> None:
        self._slice(
            "test.rpf__0.json",
            [
                "not-a-dict",  # discarded
                {"offset": -10},  # negative offset discarded
                {"offset": "invalid"},  # invalid offset discarded
                _plain_stream(
                    100,
                    status="named",
                    paths=["", "   "],
                    identifiers=[],
                ),
            ],
        )
        summary = self._run_ok()
        self.assertEqual(summary["streams"], 1)
        self.assertEqual(summary["named"], 1)  # "   " is non-empty string, "" is filtered
        self.assertEqual(summary["streams_descartados"], 3)
        self.assertEqual(summary["paths_unicos"], 1)
        paths = _read_tsv(self.out / "paths.tsv")
        self.assertEqual(paths[0]["ruta"], "   ")

    def test_empty_string_only_is_unnamed(self) -> None:
        self._slice(
            "test.rpf__0.json",
            [
                _plain_stream(
                    100,
                    status="named",
                    paths=[""],
                    identifiers=[],
                ),
            ],
        )
        summary = self._run_ok()
        self.assertEqual(summary["streams"], 1)
        self.assertEqual(summary["named"], 0)
        self.assertEqual(summary["paths_unicos"], 0)

    def test_custom_batch_and_custom_db_and_quiet(self) -> None:
        self._make_full_case()
        custom_db = self.tmp / "custom_index.sqlite"
        code, stdout, stderr = _run(
            [
                str(self.inp),
                str(self.out),
                "--batch-size",
                "1",
                "--db",
                str(custom_db),
                "--quiet",
                "--keep-db",
            ]
        )
        self.assertEqual(code, 0, stderr)
        self.assertTrue(custom_db.exists())
        self.assertNotIn("alpha.rpf__0.json", stderr)

    def test_invalid_batch_size_fails(self) -> None:
        code, _stdout, stderr = _run(
            [str(self.inp), str(self.out), "--batch-size", "0"]
        )
        self.assertEqual(code, 2)
        self.assertIn("--batch-size", stderr)


# ---------------------------------------------------------------------------
# Real fixtures: oracle comparison and pinned totals
# ---------------------------------------------------------------------------


@unittest.skipUnless(
    all((FIXTURES / name).is_file() for name in REAL_FILES),
    f"fixtures not present in {FIXTURES}",
)
class RealFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name) / "out"
        expected = _naive_merge(FIXTURES)
        self.expected = expected

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run_and_read(self) -> tuple[dict, list[dict], list[dict], list[dict]]:
        code, stdout, stderr = _run([str(FIXTURES), str(self.out)])
        self.assertEqual(code, 0, stderr)
        self.assertIn("138422", stdout)
        streams = _read_tsv(self.out / "streams.tsv")
        paths = _read_tsv(self.out / "paths.tsv")
        ids = _read_tsv(self.out / "ids.tsv")
        with open(self.out / "summary.json", encoding="utf-8") as fh:
            summary = json.load(fh)
        return summary, streams, paths, ids

    def test_outputs_match_naive_oracle(self) -> None:
        summary, streams, paths, ids = self._run_and_read()

        self.assertEqual(
            [tuple(row.values()) for row in streams],
            [tuple(str(value) for value in row) for row in self.expected["streams"]],
        )
        self.assertEqual(
            [tuple(row.values()) for row in paths],
            [tuple(str(value) for value in row) for row in self.expected["paths"]],
        )
        self.assertEqual(
            [tuple(row.values()) for row in ids],
            [tuple(str(value) for value in row) for row in self.expected["ids"]],
        )
        self.assertEqual(summary["path_mentions"], self.expected["path_mentions"])
        self.assertEqual(summary["paths_filas"], len(self.expected["paths"]))
        self.assertEqual(summary["id_mentions"], self.expected["id_mentions"])
        self.assertEqual(summary["ids_filas"], len(self.expected["ids"]))

    def test_exact_fixture_totals(self) -> None:
        summary, streams, paths, ids = self._run_and_read()
        self.assertEqual(summary["streams"], 138422)
        self.assertEqual(summary["named"], 515)
        self.assertEqual(summary["cobertura_pct"], 0.37)
        self.assertEqual(summary["paths_unicos"], 243)
        self.assertEqual(summary["path_mentions"], 244)
        self.assertEqual(summary["paths_filas"], 244)
        self.assertEqual(summary["ids_unicos"], 400)
        self.assertEqual(summary["id_mentions"], 455)
        self.assertEqual(summary["ids_filas"], 455)
        self.assertEqual(len(streams), 138422)
        self.assertEqual(len(paths), 244)
        self.assertEqual(len(ids), 455)

        self.assertEqual(
            summary["por_contenedor"],
            {
                "core_bvh4": {
                    "streams": 72015,
                    "named": 0,
                    "unnamed": 72015,
                    "cobertura_pct": 0.0,
                },
                "levels": {
                    "streams": 66407,
                    "named": 515,
                    "unnamed": 65892,
                    "cobertura_pct": 0.78,
                },
            },
        )
        self.assertEqual(
            summary["por_tipo"],
            {
                "rsc50": {
                    "streams": 51099,
                    "named": 406,
                    "unnamed": 50693,
                    "cobertura_pct": 0.79,
                },
                "raw": {
                    "streams": 70171,
                    "named": 40,
                    "unnamed": 70131,
                    "cobertura_pct": 0.06,
                },
                "0DRP": {
                    "streams": 16958,
                    "named": 57,
                    "unnamed": 16901,
                    "cobertura_pct": 0.34,
                },
                "PSIN": {
                    "streams": 194,
                    "named": 12,
                    "unnamed": 182,
                    "cobertura_pct": 6.19,
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
