"""Tests for tools/merge_index.py (compatible with pytest and unittest).

All fixtures are synthetic. No path or identifier comes from the game package:
the tests only exercise the merge rules, never the published index.
"""

from __future__ import annotations

import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import merge_index  # noqa: E402


def _stream(offset: int, paths=(), identifiers=(), source: str = "xml") -> dict:
    candidates = [
        {"name": name, "kind": "full_path", "source": source} for name in paths
    ]
    candidates += [
        {"name": name, "kind": "identifier", "source": source} for name in identifiers
    ]
    return {
        "offset": offset,
        "compressed_bytes": 100,
        "inflated_bytes": 300,
        "stream_type": "xml" if source == "xml" else source,
        "status": "named" if paths or identifiers else "unnamed",
        "full_paths": list(paths),
        "identifiers": list(identifiers),
        "candidates": candidates,
    }


class MergeIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.out = self.tmp / "out"
        self.chunks = self.tmp / "chunks"
        self.chunks.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # -- helpers ---------------------------------------------------------

    def _tramo(self, name: str, streams: list[dict], folder: Path | None = None) -> Path:
        folder = folder or self.chunks
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_text(json.dumps({"streams": streams}, indent=1), encoding="utf-8")
        return path

    def _run(self, sources: list[str], positional: list[str] | None = None) -> dict:
        argv = [str(self.out)] if positional is None else positional + [str(self.out)]
        for source in sources:
            argv.extend(["--source", source])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(merge_index.main(argv), 0)
        with open(self.out / "report.json", encoding="utf-8") as fh:
            return json.load(fh)

    def _index(self) -> list[dict]:
        with open(self.out / "index.tsv", encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh, delimiter="\t"))

    def _paths(self) -> list[dict]:
        with open(self.out / "paths.tsv", encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh, delimiter="\t"))

    def _ids(self) -> list[dict]:
        with open(self.out / "ids.tsv", encoding="utf-8", newline="") as fh:
            return list(csv.DictReader(fh, delimiter="\t"))

    def _summary(self) -> dict:
        with open(self.out / "summary.json", encoding="utf-8") as fh:
            return json.load(fh)

    # -- required cases --------------------------------------------------

    def test_same_path_same_offset_merges_without_conflict(self) -> None:
        self._tramo(
            "alpha.rpf__0.json",
            [_stream(0x100, paths=["fixtures/alpha.ydr"])],
        )
        inventory = self.tmp / "inventory.tsv"
        inventory.write_text(
            "archivo\toffset\truta\n"
            "alpha.rpf\t0x100\tfixtures/alpha.ydr\n",
            encoding="utf-8",
        )

        report = self._run(
            [
                f"name_recover={self.chunks}",
                f"inventory-tsv={inventory}",
            ]
        )

        rows = self._index()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ruta"], "fixtures/alpha.ydr")
        self.assertEqual(rows[0]["abs_offset"], "256")
        self.assertEqual(rows[0]["compressed"], "100")
        self.assertEqual(rows[0]["estado"], "ok")
        self.assertEqual(report["conflict"], [])
        # paths.tsv stays the name_recover mention log, so the inventory does
        # not duplicate the mention there.
        self.assertEqual(len(self._paths()), 1)

    def test_same_path_different_offsets_is_a_conflict(self) -> None:
        self._tramo(
            "alpha.rpf__0.json",
            [_stream(0x100, paths=["fixtures/beta.yft"], source="rsc50")],
        )
        inventory = self.tmp / "inventory.csv"
        inventory.write_text(
            "archive,offset,path\n"
            "alpha.rpf,512,fixtures/beta.yft\n",
            encoding="utf-8",
        )

        report = self._run(
            [
                f"name_recover={self.chunks}",
                f"inventory-csv={inventory}",
            ]
        )

        self.assertEqual(len(report["conflict"]), 1)
        conflict = report["conflict"][0]
        self.assertEqual(conflict["path"], "fixtures/beta.yft")
        self.assertEqual(conflict["resolution"], "unresolved")
        self.assertEqual(
            sorted(version["offset"] for version in conflict["versions"]),
            [0x100, 0x200],
        )
        rows = self._index()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["estado"] == "conflict" for row in rows))
        self.assertEqual({row["abs_offset"] for row in rows}, {"256", "512"})

    def test_two_paths_with_the_same_hash_are_a_collision(self) -> None:
        paths = self.tmp / "dictionary.json"
        paths.write_text(
            json.dumps({"paths": ["fixtures/one.bin", "fixtures/two.bin"]}),
            encoding="utf-8",
        )

        with mock.patch.object(merge_index, "path_hash", return_value="f" * 64):
            report = self._run([f"paths={paths}"])

        self.assertEqual(len(report["collision"]), 1)
        collision = report["collision"][0]
        self.assertEqual(collision["hash"], "f" * 64)
        self.assertEqual(
            sorted(collision["paths"]), ["fixtures/one.bin", "fixtures/two.bin"]
        )
        self.assertEqual(report["conflict"], [])

    def test_identifier_without_path_is_an_orphan(self) -> None:
        self._tramo(
            "alpha.rpf__0.json",
            [_stream(0x200, identifiers=["invented_asset_01"], source="psin")],
        )

        report = self._run([f"name_recover={self.chunks}"])

        self.assertEqual(len(report["orphan"]), 1)
        orphan = report["orphan"][0]
        self.assertEqual(orphan["identifier"], "invented_asset_01")
        self.assertEqual(orphan["rpf"], "alpha.rpf")
        self.assertEqual(orphan["offset"], 0x200)
        self.assertEqual(self._index(), [])
        self.assertEqual(len(self._ids()), 1)

    def test_hash_source_only_compares_coverage(self) -> None:
        paths = self.tmp / "dictionary.txt"
        paths.write_text("fixtures/alpha.ydr\n", encoding="utf-8")
        expected = merge_index.path_hash("fixtures/alpha.ydr")
        reference = self.tmp / "paths.sha256"
        reference.write_text(
            "# invented reference\n"
            f"{expected}\n"
            f"{'0' * 64}\n",
            encoding="utf-8",
        )

        report = self._run(
            [
                f"paths={paths}",
                f"hashes={reference}",
            ]
        )

        rows = self._index()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ruta"], "fixtures/alpha.ydr")
        hash_source = next(
            source for source in report["sources"] if source["type"] == "hashes"
        )
        self.assertEqual(hash_source["reference_hashes"], 2)
        self.assertEqual(hash_source["matched"], 1)
        self.assertEqual(hash_source["missing"], 1)
        self.assertEqual(hash_source["extra"], 0)
        self.assertEqual(report["unrecognized"], [])

    def test_unknown_formats_are_reported_not_raised(self) -> None:
        bad = self.tmp / "bad.txt"
        bad.write_text("this is not a recovery JSON\n", encoding="utf-8")

        report = self._run(
            [
                f"name_recover={bad}",
                "mystery=whatever",
            ]
        )

        self.assertGreaterEqual(len(report["unrecognized"]), 2)
        types = {item["type"] for item in report["unrecognized"]}
        self.assertIn("name_recover", types)
        self.assertIn("mystery", types)
        self.assertEqual(self._index(), [])

    def test_skip_still_skips_the_named_files(self) -> None:
        self._tramo(
            "alpha.rpf__0.json",
            [_stream(0x100, paths=["fixtures/alpha.ydr"])],
        )
        self._tramo(
            "alpha.rpf__1000.json",
            [_stream(0x100, paths=["fixtures/alpha.ydr"])],
        )

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(
                merge_index.main(
                    [
                        str(self.chunks),
                        str(self.out),
                        "--skip",
                        "alpha.rpf__1000.json",
                    ]
                ),
                0,
            )
        with open(self.out / "report.json", encoding="utf-8") as fh:
            report = json.load(fh)
        summary = self._summary()
        self.assertEqual(summary["tramos"], 1)
        self.assertEqual(summary["streams"], 1)
        self.assertEqual(len(self._index()), 1)
        self.assertEqual(
            report["sources"][0]["skipped"], ["alpha.rpf__1000.json"]
        )

    # -- additional rule coverage ---------------------------------------

    def test_literal_xml_beats_a_conflicting_pattern(self) -> None:
        self._tramo(
            "alpha.rpf__0.json",
            [_stream(0x100, paths=["fixtures/priority.bin"], source="xml")],
        )
        inventory = self.tmp / "inventory.tsv"
        inventory.write_text(
            "archivo\toffset\truta\n"
            "alpha.rpf\t0x200\tfixtures/priority.bin\n",
            encoding="utf-8",
        )

        report = self._run(
            [
                f"name_recover={self.chunks}",
                f"inventory-tsv={inventory}",
            ]
        )

        self.assertEqual(len(report["conflict"]), 1)
        self.assertEqual(report["conflict"][0]["resolution"], "literal")
        self.assertEqual(len(report["conflict"][0]["versions"]), 2)
        rows = self._index()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["abs_offset"], "256")
        self.assertEqual(rows[0]["procedencia"], "literal")
        self.assertEqual(rows[0]["motivo"], "literal_over_pattern")

    def test_same_offset_with_different_size_is_a_conflict(self) -> None:
        other = self.tmp / "other"
        self._tramo(
            "alpha.rpf__0.json",
            [_stream(0x100, paths=["fixtures/gamma.bin"])],
        )
        self._tramo(
            "alpha.rpf__0.json",
            [_stream(0x100, paths=["fixtures/gamma.bin"])],
            folder=other,
        )
        # Make the size differ without touching the path or the offset.
        payload = json.loads((other / "alpha.rpf__0.json").read_text())
        payload["streams"][0]["compressed_bytes"] = 200
        (other / "alpha.rpf__0.json").write_text(json.dumps(payload))

        report = self._run(
            [
                f"name_recover={self.chunks}",
                f"name_recover={other}",
            ]
        )

        self.assertEqual(len(report["conflict"]), 1)
        conflict = report["conflict"][0]
        self.assertEqual(conflict["resolution"], "unresolved")
        self.assertIn("different size", conflict["reason"])
        self.assertEqual(
            conflict["versions"][0]["compressed_values"], [100, 200]
        )


if __name__ == "__main__":
    unittest.main()
