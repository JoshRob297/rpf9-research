"""Tests for tools/rpf9.py (compatible with pytest and unittest)."""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import rpf9  # noqa: E402

SAMPLES_DIR = Path("/home/sistver/proyectos/rpf9-research/samples")
APPDATA0_HEAD = SAMPLES_DIR / "appdata0.head.bin"
LEVELS_HEAD = SAMPLES_DIR / "levels.head.bin"
SCRIPT_HEAD = SAMPLES_DIR / "script.head.bin"


class TestRpf9RealSamples(unittest.TestCase):
    @unittest.skipUnless(APPDATA0_HEAD.is_file(), "appdata0.head.bin not present")
    def test_small_sample_appdata0(self) -> None:
        report = rpf9.inspect_file(APPDATA0_HEAD)
        self.assertEqual(report["file_size_read"], 8880)
        hdr = report["header"]
        self.assertEqual(hdr["magic_hex"], "0x52504639")
        self.assertEqual(hdr["toc_end_offset"], 864)
        self.assertEqual(hdr["toc_length"], 800)
        self.assertEqual(hdr["toc_subtable_offset"], 832)
        self.assertEqual(hdr["trailer_length"], 64)
        self.assertEqual(hdr["entry_count_candidate"], 2)
        self.assertEqual(len(hdr["fields"]), 16)

        toc = report["toc"]
        self.assertTrue(toc["toc_present"])
        self.assertTrue(toc["toc_encrypted"])
        self.assertTrue(toc["matches_known_32b_toc_prefix"])
        self.assertEqual(toc["toc_intra_16b_dups"], 0)
        self.assertGreater(toc["toc_entropy"], 7.5)
        self.assertEqual(toc["entry_listing_status"], "blocked_encrypted_toc_no_key")
        self.assertEqual(toc["entries"], [])

    @unittest.skipUnless(LEVELS_HEAD.is_file(), "levels.head.bin not present")
    def test_large_sample_levels_and_nested(self) -> None:
        report = rpf9.inspect_file(LEVELS_HEAD, scan_nested=True)
        self.assertEqual(report["file_size_read"], 4194304)
        hdr = report["header"]
        self.assertEqual(hdr["toc_end_offset"], 110704)
        self.assertEqual(hdr["toc_length"], 110640)
        self.assertEqual(hdr["toc_subtable_offset"], 89920)
        self.assertEqual(hdr["trailer_length"], 119520)
        self.assertEqual(hdr["entry_count_candidate"], 2078)

        toc = report["toc"]
        self.assertTrue(toc["toc_encrypted"])
        self.assertTrue(toc["matches_known_32b_toc_prefix"])
        self.assertGreater(toc["toc_entropy"], 7.9)
        self.assertEqual(toc["entries"], [])
        self.assertEqual(len(toc["nested_rpf9_containers"]), 2)
        self.assertEqual(toc["nested_rpf9_containers"][0]["offset_hex"], "0x1c000")
        self.assertEqual(toc["nested_rpf9_containers"][1]["offset_hex"], "0x4d000")

    @unittest.skipUnless(SCRIPT_HEAD.is_file(), "script.head.bin not present")
    def test_cli_json_output_script(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "rpf9.py"), str(SCRIPT_HEAD), "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(proc.stdout)
        self.assertEqual(data["header"]["toc_end_offset"], 608)
        self.assertEqual(data["header"]["trailer_length"], 128)
        self.assertEqual(data["toc"]["entry_listing_status"], "blocked_encrypted_toc_no_key")
        self.assertEqual(data["toc"]["entries"], [])


class TestRpf9Synthetic(unittest.TestCase):
    def test_rejects_short_file(self) -> None:
        with self.assertRaises(ValueError):
            rpf9.parse_header(b"9FPR" + b"\x00" * 10)

    def test_rejects_bad_magic(self) -> None:
        with self.assertRaises(ValueError):
            rpf9.parse_header(b"7FPR" + b"\x00" * 60)

    def test_low_entropy_unverified_layout_does_not_invent_entries(self) -> None:
        hdr = struct.pack(
            "<16I",
            rpf9.RPF9_MAGIC,
            128,
            112,
            32,
            1,
            2,
            0x47A00,
            0x150,
            0x10006,
            1,
            0xDA72573E,
            0x00090F01,
            16,
            0,
            0,
            0,
        )
        blob = hdr + (b"\x00" * 64)
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(blob)
            tmp_path = Path(tf.name)
        try:
            report = rpf9.inspect_file(tmp_path)
            self.assertFalse(report["toc"]["toc_encrypted"])
            self.assertEqual(report["toc"]["entries"], [])
            self.assertEqual(
                report["toc"]["entry_listing_status"],
                "unencrypted_toc_layout_unverified",
            )
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
