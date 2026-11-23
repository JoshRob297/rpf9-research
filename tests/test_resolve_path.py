"""Tests for tools/resolve_path.py (compatible with pytest and unittest).

Real fixture: /home/sistver/idx-fixtures/resolver
  index/streams-*.tsv, index/paths-*.tsv, rpf/{data,script,core_restofworld001}.rpf

The synthetic fixture covers the branch the real index never exercises: a stream
whose bytes do not start with 0x78, which must be treated as raw data.
"""

from __future__ import annotations

import csv
import dataclasses
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import resolve_path as resolver  # noqa: E402

FIXTURE = Path("/home/sistver/idx-fixtures/resolver")
INDEX_DIR = FIXTURE / "index"
RPF_DIR = FIXTURE / "rpf"
HAS_FIXTURE = (
    (INDEX_DIR / "streams-data.tsv").is_file()
    and (INDEX_DIR / "paths-data.tsv").is_file()
    and (INDEX_DIR / "streams-core_restofworld001.tsv").is_file()
    and (INDEX_DIR / "paths-core_restofworld001.tsv").is_file()
    and (RPF_DIR / "data.rpf").is_file()
    and (RPF_DIR / "core_restofworld001.rpf").is_file()
)
TOOL = TOOLS / "resolve_path.py"

STREAM_HEADER = [
    "rpf",
    "abs_offset",
    "offset_hex",
    "compressed",
    "inflated",
    "type",
    "status",
    "n_paths",
    "n_ids",
]
PATH_HEADER = ["ruta", "rpf", "abs_offset"]

RAW_PAYLOAD = b"RAW\x00\x01\x02" + bytes(range(48))
ZLIB_PAYLOAD = b"<asset>compressed payload</asset>" * 40

KNOWN_PATH = "activity_launcher_menu/controls/info_label_banner"
KNOWN_OFFSETS = [298999808, 299003904, 299012096]
KNOWN_SIZES = [4353, 4424, 15961]
CORE_ROOT_PATH = "$(root)/changesets/ccs_core_restofworld001_ingame_animation.meta"


def write_tsv(path: Path, header: list[str], rows: list[list[object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(header)
        writer.writerows(rows)


def run_cli(*args: object) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [sys.executable, str(TOOL), *[str(a) for a in args]],
        capture_output=True,
    )


def build_synthetic_fixture(root: Path) -> tuple[Path, Path, int, int, Path]:
    """Build a tiny container + index pair. Returns index, rpf dir, offsets, container."""
    index_dir = root / "index"
    rpf_dir = root / "rpf"
    index_dir.mkdir()
    rpf_dir.mkdir()

    container = rpf_dir / "synthetic.rpf"
    raw_offset = 64
    zlib_offset = raw_offset + len(RAW_PAYLOAD) + 16
    zlib_bytes = zlib.compress(ZLIB_PAYLOAD)

    blob = bytearray(b"\x00" * zlib_offset)
    blob[0:4] = b"9FPR"
    blob[raw_offset : raw_offset + len(RAW_PAYLOAD)] = RAW_PAYLOAD
    blob[zlib_offset : zlib_offset + len(zlib_bytes)] = zlib_bytes
    container.write_bytes(bytes(blob))

    streams = [
        [
            "synthetic",
            raw_offset,
            hex(raw_offset),
            len(RAW_PAYLOAD),
            len(RAW_PAYLOAD),
            "raw",
            "named",
            1,
            1,
        ],
        [
            "synthetic",
            zlib_offset,
            hex(zlib_offset),
            len(zlib_bytes),
            len(ZLIB_PAYLOAD),
            "rsc50",
            "named",
            1,
            1,
        ],
    ]
    paths = [
        ["assets/raw_asset", "synthetic", raw_offset],
        ["assets/zlib_asset", "synthetic", zlib_offset],
        ["assets/dup", "synthetic", raw_offset],
        ["assets/dup", "synthetic", zlib_offset],
    ]
    write_tsv(index_dir / "streams-synthetic.tsv", STREAM_HEADER, streams)
    write_tsv(index_dir / "paths-synthetic.tsv", PATH_HEADER, paths)
    return index_dir, rpf_dir, raw_offset, zlib_offset, container


class TestSyntheticIndex(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        (
            self.index_dir,
            self.rpf_dir,
            self.raw_offset,
            self.zlib_offset,
            self.container,
        ) = build_synthetic_fixture(self.root)
        self.streams = resolver.load_streams(self.index_dir)
        self.by_path = resolver.group_mentions(resolver.load_mentions(self.index_dir))

    # -- index ---------------------------------------------------------

    def test_load_counts(self) -> None:
        self.assertEqual(len(self.streams), 2)
        self.assertEqual(len(self.by_path), 3)
        self.assertEqual(sum(len(v) for v in self.by_path.values()), 4)

    # -- resolution ----------------------------------------------------

    def test_raw_payload_is_not_inflated(self) -> None:
        resolutions = resolver.resolve_path(
            "assets/raw_asset", self.by_path, self.streams, self.rpf_dir
        )
        self.assertEqual(len(resolutions), 1)
        res = resolutions[0]
        self.assertFalse(res.decompressed)
        self.assertEqual(res.data, RAW_PAYLOAD)
        self.assertEqual(res.stream.stream_type, "raw")
        self.assertEqual(res.mention.abs_offset, self.raw_offset)

    def test_zlib_payload_is_inflated(self) -> None:
        resolutions = resolver.resolve_path(
            "assets/zlib_asset", self.by_path, self.streams, self.rpf_dir
        )
        self.assertEqual(len(resolutions), 1)
        res = resolutions[0]
        self.assertTrue(res.decompressed)
        self.assertEqual(res.data, ZLIB_PAYLOAD)
        self.assertEqual(len(res.data), res.stream.inflated)

    def test_duplicate_path_returns_every_mention(self) -> None:
        resolutions = resolver.resolve_path(
            "assets/dup", self.by_path, self.streams, self.rpf_dir
        )
        self.assertEqual(len(resolutions), 2)
        self.assertEqual(
            [r.mention.abs_offset for r in resolutions],
            [self.raw_offset, self.zlib_offset],
        )
        self.assertEqual(resolutions[0].data, RAW_PAYLOAD)
        self.assertEqual(resolutions[1].data, ZLIB_PAYLOAD)

    def test_rpf_filter_selects_mention(self) -> None:
        resolutions = resolver.resolve_path(
            "assets/dup", self.by_path, self.streams, self.rpf_dir, rpf="synthetic"
        )
        self.assertEqual(len(resolutions), 2)
        with self.assertRaises(resolver.ResolveError) as ctx:
            resolver.resolve_path(
                "assets/dup", self.by_path, self.streams, self.rpf_dir, rpf="absent"
            )
        self.assertEqual(ctx.exception.reason, "path_not_found")

    # -- clear errors --------------------------------------------------

    def test_path_not_found(self) -> None:
        with self.assertRaises(resolver.ResolveError) as ctx:
            resolver.resolve_path(
                "assets/does_not_exist", self.by_path, self.streams, self.rpf_dir
            )
        self.assertEqual(ctx.exception.reason, "path_not_found")

    def test_stream_missing(self) -> None:
        mention = resolver.Mention("assets/raw_asset", "synthetic", self.zlib_offset + 999999)
        with self.assertRaises(resolver.ResolveError) as ctx:
            resolver.resolve_mention(mention, self.streams, self.rpf_dir)
        self.assertEqual(ctx.exception.reason, "stream_missing")

    def test_container_missing(self) -> None:
        ghost = dataclasses.replace(
            self.streams[("synthetic", self.raw_offset)], rpf="ghost"
        )
        streams = dict(self.streams)
        streams[("ghost", self.raw_offset)] = ghost
        mention = resolver.Mention("assets/raw_asset", "ghost", self.raw_offset)
        with self.assertRaises(resolver.ResolveError) as ctx:
            resolver.resolve_mention(mention, streams, self.rpf_dir)
        self.assertEqual(ctx.exception.reason, "container_missing")

    def test_size_mismatch(self) -> None:
        stream = dataclasses.replace(
            self.streams[("synthetic", self.raw_offset)],
            inflated=len(RAW_PAYLOAD) + 1,
        )
        streams = dict(self.streams)
        streams[("synthetic", self.raw_offset)] = stream
        mention = resolver.Mention("assets/raw_asset", "synthetic", self.raw_offset)
        with self.assertRaises(resolver.ResolveError) as ctx:
            resolver.resolve_mention(mention, streams, self.rpf_dir)
        self.assertEqual(ctx.exception.reason, "size_mismatch")

    def test_short_read(self) -> None:
        size = self.container.stat().st_size
        stream = dataclasses.replace(
            self.streams[("synthetic", self.raw_offset)],
            compressed=size - self.raw_offset + 100,
        )
        streams = dict(self.streams)
        streams[("synthetic", self.raw_offset)] = stream
        mention = resolver.Mention("assets/raw_asset", "synthetic", self.raw_offset)
        with self.assertRaises(resolver.ResolveError) as ctx:
            resolver.resolve_mention(mention, streams, self.rpf_dir)
        self.assertEqual(ctx.exception.reason, "short_read")

    def test_zlib_error(self) -> None:
        stream = dataclasses.replace(
            self.streams[("synthetic", self.zlib_offset)], compressed=6
        )
        streams = dict(self.streams)
        streams[("synthetic", self.zlib_offset)] = stream
        mention = resolver.Mention("assets/zlib_asset", "synthetic", self.zlib_offset)
        with self.assertRaises(resolver.ResolveError) as ctx:
            resolver.resolve_mention(mention, streams, self.rpf_dir)
        self.assertEqual(ctx.exception.reason, "zlib_error")

    # -- CLI -----------------------------------------------------------

    def test_cli_default_writes_bytes_to_stdout(self) -> None:
        proc = run_cli("assets/raw_asset", "--index-dir", self.index_dir, "--rpf-dir", self.rpf_dir)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, RAW_PAYLOAD)

    def test_cli_out_writes_file(self) -> None:
        out = self.root / "asset.bin"
        proc = run_cli(
            "assets/zlib_asset",
            "--index-dir",
            self.index_dir,
            "--rpf-dir",
            self.rpf_dir,
            "--out",
            out,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, b"")
        self.assertEqual(out.read_bytes(), ZLIB_PAYLOAD)
        self.assertIn(b"wrote", proc.stderr)

    def test_cli_info(self) -> None:
        proc = run_cli(
            "assets/zlib_asset",
            "--index-dir",
            self.index_dir,
            "--rpf-dir",
            self.rpf_dir,
            "--info",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout.decode()
        self.assertIn("path: assets/zlib_asset", out)
        self.assertIn("rpf: synthetic", out)
        self.assertIn(f"offset: {self.zlib_offset}", out)
        self.assertIn("type: rsc50", out)
        self.assertIn(f"compressed: {len(zlib.compress(ZLIB_PAYLOAD))}", out)
        self.assertIn(f"inflated: {len(ZLIB_PAYLOAD)}", out)
        self.assertIn("decompressed: yes", out)
        self.assertIn("size_check: ok", out)

    def test_cli_info_mentions_and_raw_flag(self) -> None:
        proc = run_cli(
            "assets/dup",
            "--index-dir",
            self.index_dir,
            "--rpf-dir",
            self.rpf_dir,
            "--info",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout.decode()
        self.assertIn("mentions: 2", out)
        self.assertIn("mention: 1/2", out)
        self.assertIn("decompressed: no", out)

    def test_cli_all_lists_mentions(self) -> None:
        proc = run_cli(
            "assets/dup",
            "--index-dir",
            self.index_dir,
            "--rpf-dir",
            self.rpf_dir,
            "--all",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout.decode()
        self.assertIn("mentions: 2", out)
        self.assertIn("[1/2]", out)
        self.assertIn("[2/2]", out)
        self.assertIn("summary: 2 mentions, 2 passed, 0 failed", out)

    def test_cli_missing_path_exits_1(self) -> None:
        proc = run_cli(
            "assets/nope", "--index-dir", self.index_dir, "--rpf-dir", self.rpf_dir
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn(b"path not found", proc.stderr)

    def test_cli_out_rejected_with_all(self) -> None:
        proc = run_cli(
            "assets/dup",
            "--index-dir",
            self.index_dir,
            "--rpf-dir",
            self.rpf_dir,
            "--all",
            "--out",
            self.root / "x.bin",
        )
        self.assertEqual(proc.returncode, 2)

    def test_cli_verify(self) -> None:
        proc = run_cli(
            "--verify",
            2,
            "--seed",
            5,
            "--index-dir",
            self.index_dir,
            "--rpf-dir",
            self.rpf_dir,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout.decode()
        self.assertIn("verify: sampled 2 of 3 paths", out)
        self.assertIn("paths: 2 passed, 0 failed", out)
        self.assertIn("verify: PASS", out)

    def test_cli_verify_caps_sample_at_available_paths(self) -> None:
        proc = run_cli(
            "--verify",
            99,
            "--index-dir",
            self.index_dir,
            "--rpf-dir",
            self.rpf_dir,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout.decode()
        self.assertIn("verify: sampled 3 of 3 paths", out)
        self.assertIn("requested 99", out)


@unittest.skipUnless(HAS_FIXTURE, "resolver fixture not present at /home/sistver/idx-fixtures/resolver")
class TestRealIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.streams = resolver.load_streams(INDEX_DIR)
        cls.mentions = resolver.load_mentions(INDEX_DIR)
        cls.by_path = resolver.group_mentions(cls.mentions)

    def test_index_counts(self) -> None:
        self.assertEqual(len(self.streams), 29599)
        self.assertEqual(len(self.mentions), 4704)
        self.assertEqual(len(self.by_path), 2295)

    def test_known_stream_row_fields(self) -> None:
        stream = self.streams[("data", 74544)]
        self.assertEqual(stream.offset_hex, "0x12330")
        self.assertEqual(stream.compressed, 536)
        self.assertEqual(stream.inflated, 1288)
        self.assertEqual(stream.stream_type, "PSIN")
        self.assertEqual(stream.status, "unnamed")

    def test_known_path_resolves_all_mentions(self) -> None:
        resolutions = resolver.resolve_path(
            KNOWN_PATH, self.by_path, self.streams, RPF_DIR
        )
        self.assertEqual(
            [r.mention.abs_offset for r in resolutions], KNOWN_OFFSETS
        )
        self.assertEqual([len(r.data) for r in resolutions], KNOWN_SIZES)
        self.assertEqual([r.decompressed for r in resolutions], [True, True, True])
        for res in resolutions:
            self.assertEqual(len(res.data), res.stream.inflated)

    def test_core_root_path(self) -> None:
        resolutions = resolver.resolve_path(
            CORE_ROOT_PATH, self.by_path, self.streams, RPF_DIR
        )
        self.assertEqual(len(resolutions), 1)
        self.assertEqual(resolutions[0].mention.rpf, "core_restofworld001")
        self.assertEqual(
            len(resolutions[0].data), resolutions[0].stream.inflated
        )

    def test_every_path_mention_has_a_stream_row(self) -> None:
        missing = [
            m for m in self.mentions if (m.rpf, m.abs_offset) not in self.streams
        ]
        self.assertEqual(missing, [])

    def test_verify_samples_data_container(self) -> None:
        report = resolver.verify(INDEX_DIR, RPF_DIR, 20, rpf="data", seed=0)
        self.assertEqual(report.available, 2273)
        self.assertEqual(report.sampled, 20)
        self.assertEqual(report.failed, 0)
        self.assertEqual(report.paths_failed, 0)
        self.assertEqual(report.passed, report.mentions)
        self.assertGreaterEqual(report.mentions, 20)
        self.assertTrue(all(p in self.by_path for p in report.sampled_paths))

    def test_verify_is_deterministic(self) -> None:
        first = resolver.verify(INDEX_DIR, RPF_DIR, 10, rpf="data", seed=7)
        second = resolver.verify(INDEX_DIR, RPF_DIR, 10, rpf="data", seed=7)
        self.assertEqual(first.sampled_paths, second.sampled_paths)
        self.assertEqual(first.passed, second.passed)

    def test_cli_info_real_path(self) -> None:
        proc = run_cli(
            KNOWN_PATH, "--index-dir", INDEX_DIR, "--rpf-dir", RPF_DIR, "--info"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout.decode()
        self.assertIn("path: " + KNOWN_PATH, out)
        self.assertIn("mentions: 3", out)
        self.assertIn("mention: 1/3", out)
        self.assertIn("rpf: data", out)
        self.assertIn("offset: 298999808", out)
        self.assertIn("type: raw", out)
        self.assertIn("compressed: 852", out)
        self.assertIn("inflated: 4353", out)
        self.assertIn("decompressed: yes", out)
        self.assertIn("size_check: ok", out)

    def test_cli_all_real_path(self) -> None:
        proc = run_cli(
            KNOWN_PATH, "--index-dir", INDEX_DIR, "--rpf-dir", RPF_DIR, "--all"
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = proc.stdout.decode()
        self.assertIn("mentions: 3", out)
        self.assertIn("[1/3]", out)
        self.assertIn("[2/3]", out)
        self.assertIn("[3/3]", out)
        self.assertIn("summary: 3 mentions, 3 passed, 0 failed", out)


if __name__ == "__main__":
    unittest.main()
