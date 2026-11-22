"""Tests for tools/rpf9.py (compatible with pytest and unittest)."""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import rpf9  # noqa: E402

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
APPDATA0_HEAD = SAMPLES_DIR / "appdata0.head.bin"
LEVELS_HEAD = SAMPLES_DIR / "levels.head.bin"
SCRIPT_HEAD = SAMPLES_DIR / "script.head.bin"
SHADERS_HEAD = SAMPLES_DIR / "shaders.head.bin"
STORY_BVH4_FULL = SAMPLES_DIR / "story000_bvh4.full.bin"
CORE_LICENSES_FULL = SAMPLES_DIR / "core_licenses_data.full.bin"
CORE_ROW001_FULL = SAMPLES_DIR / "core_restofworld001.full.bin"


class TestRpf9RealSamples(unittest.TestCase):
    @unittest.skipUnless(APPDATA0_HEAD.is_file(), "appdata0.head.bin not present")
    def test_small_sample_appdata0(self) -> None:
        report = rpf9.inspect_file(APPDATA0_HEAD, include_payload=True)
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

        pl = report["payload"]
        self.assertTrue(pl["payload_present"])
        self.assertTrue(pl["eof_trailer_detected"])
        self.assertEqual(pl["zlib_stream_count"], 0)
        span_ranges = [u["range"] for u in pl["unreadable_regions"] if u["region"] == "payload_span"]
        self.assertEqual(span_ranges, ["0x360..0x550", "0x1000..0x2270"])

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
        self.assertEqual(toc["nested_rpf9_containers"][0]["reconstructed_size"], 197776)
        self.assertEqual(toc["nested_rpf9_containers"][1]["offset_hex"], "0x4d000")

    @unittest.skipUnless(STORY_BVH4_FULL.is_file(), "story000_bvh4.full.bin not present")
    def test_payload_story000_bvh4_full(self) -> None:
        report = rpf9.inspect_file(STORY_BVH4_FULL, include_payload=True)
        pl = report["payload"]
        self.assertTrue(pl["eof_trailer_detected"])
        self.assertEqual(pl["zlib_stream_count"], 4)
        self.assertEqual([z["kind"] for z in pl["zlib_streams"]], ["xml", "xml", "xml", "xml"])
        self.assertEqual(pl["zlib_streams"][3]["xml"]["root"], "SSetupData")
        self.assertEqual(pl["zlib_streams"][3]["xml"]["id_or_device"], "story000_bvh")
        # Only head_toc and archive_trailer should be unreadable
        self.assertEqual([u["region"] for u in pl["unreadable_regions"]], ["head_toc", "archive_trailer"])

    @unittest.skipUnless(CORE_LICENSES_FULL.is_file(), "core_licenses_data.full.bin not present")
    def test_payload_core_licenses_full(self) -> None:
        report = rpf9.inspect_file(CORE_LICENSES_FULL, include_payload=True)
        pl = report["payload"]
        self.assertTrue(pl["eof_trailer_detected"])
        self.assertEqual(pl["zlib_stream_count"], 3)
        self.assertEqual(len(pl["nested_rpf9_containers"]), 1)
        nested = pl["nested_rpf9_containers"][0]
        self.assertEqual(nested["offset_hex"], "0x1000")
        self.assertEqual(nested["reconstructed_size"], 7760)
        self.assertEqual(nested["entry_count_candidate"], 2)

    @unittest.skipUnless(CORE_ROW001_FULL.is_file(), "core_restofworld001.full.bin not present")
    def test_payload_core_restofworld001_full(self) -> None:
        report = rpf9.inspect_file(CORE_ROW001_FULL, include_payload=True)
        pl = report["payload"]
        self.assertTrue(pl["eof_trailer_detected"])
        self.assertEqual(pl["zlib_stream_count"], 33)
        self.assertEqual(len(pl["nested_rpf9_containers"]), 1)
        self.assertEqual(pl["nested_rpf9_containers"][0]["reconstructed_size"], 785200)
        self.assertEqual(pl["nested_rpf9_containers"][0]["entry_count_candidate"], 22)
        edup = [s for s in pl["other_signatures"] if s["signature"] == "EDUP"]
        self.assertEqual(len(edup), 1)
        self.assertEqual(edup[0]["offset_hex"], "0xc14a0")

    @unittest.skipUnless(SHADERS_HEAD.is_file(), "shaders.head.bin not present")
    def test_payload_shaders_sgd5(self) -> None:
        report = rpf9.inspect_file(SHADERS_HEAD, include_payload=True)
        pl = report["payload"]
        self.assertEqual(len(pl["sgd5_blocks"]), 1)
        sgd = pl["sgd5_blocks"][0]
        self.assertEqual(sgd["offset_hex"], "0x9000")
        self.assertEqual(sgd["sub_count_u32"], 33)
        self.assertEqual(sgd["first_section_bytes"], 2112)
        self.assertEqual(sgd["sequential_tables_found"], 31)
        self.assertEqual(sgd["sequential_records_total"], 2419)
        self.assertGreater(sgd["shader_symbol_count"], 700)

    @unittest.skipUnless(SCRIPT_HEAD.is_file(), "script.head.bin not present")
    def test_cli_json_output_script(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "rpf9.py"), str(SCRIPT_HEAD), "--json", "--payload"],
            capture_output=True,
            text=True,
            check=True,
        )
        data = json.loads(proc.stdout)
        self.assertEqual(data["header"]["toc_end_offset"], 608)
        self.assertEqual(data["header"]["trailer_length"], 128)
        self.assertEqual(data["toc"]["entry_listing_status"], "blocked_encrypted_toc_no_key")
        self.assertEqual(data["toc"]["entries"], [])
        self.assertIn("payload", data)
        self.assertGreater(data["payload"]["zlib_stream_count"], 900)
        self.assertEqual(data["payload"]["nested_rpf9_containers"][0]["reconstructed_size"], 797584)


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
        xml_comp = zlib.compress(b'<?xml version="1.0"?><SSetupData><deviceName>test</deviceName></SSetupData>', 9)
        blob = hdr + (b"\x00" * 64) + xml_comp
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(blob)
            tmp_path = Path(tf.name)
        try:
            report = rpf9.inspect_file(tmp_path, include_payload=True)
            self.assertFalse(report["toc"]["toc_encrypted"])
            self.assertEqual(report["toc"]["entries"], [])
            self.assertEqual(
                report["toc"]["entry_listing_status"],
                "unencrypted_toc_layout_unverified",
            )
            self.assertEqual(report["payload"]["zlib_stream_count"], 1)
            self.assertEqual(report["payload"]["zlib_streams"][0]["kind"], "xml")
            self.assertEqual(report["payload"]["zlib_streams"][0]["xml"]["id_or_device"], "test")
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
