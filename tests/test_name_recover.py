"""Tests for tools/name_recover.py (compatible with pytest and unittest)."""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import name_recover  # noqa: E402

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
COMMON_HEAD = SAMPLES_DIR / "common.head.bin"
SHADERS_HEAD = SAMPLES_DIR / "shaders.head.bin"
DATA_HEAD = SAMPLES_DIR / "data.head.bin"
STORY_HEAD = SAMPLES_DIR / "story000.head.bin"
STORY_BVH4_FULL = SAMPLES_DIR / "story000_bvh4.full.bin"


def _raw_deflate(payload: bytes) -> bytes:
    co = zlib.compressobj(level=6, wbits=-15)
    return co.compress(payload) + co.flush()


class TestNameRecoverRealSamples(unittest.TestCase):
    @unittest.skipUnless(STORY_BVH4_FULL.is_file(), "story000_bvh4.full.bin not present")
    def test_story_bvh4_full_xml_recovery_and_validation(self) -> None:
        report = name_recover.recover_path(STORY_BVH4_FULL, validate=True)
        summary = report["summary"]
        self.assertEqual(summary["files_scanned"], 1)
        self.assertEqual(summary["total_streams"], 4)
        self.assertEqual(summary["named_streams"], 4)
        self.assertEqual(summary["coverage_pct"], 100.0)

        streams = report["streams"]
        all_paths = {p for s in streams for p in s["full_paths"]}
        all_ids = {i for s in streams for i in s["identifiers"]}
        self.assertIn("$(root)/changesets/ccs_story000_environment_bvh.meta", all_paths)
        self.assertIn("story000_environment_bvh", all_ids)
        self.assertIn("story000_bvh", all_ids)
        # Paths and identifiers must be cleanly separated
        self.assertTrue(all("/" in p or "." in p for p in all_paths))
        self.assertNotIn("$(root)/changesets/ccs_story000_environment_bvh.meta", all_ids)
        self.assertTrue(report["validation"]["all_verified"])

    @unittest.skipUnless(COMMON_HEAD.is_file(), "common.head.bin not present")
    def test_common_head_xml_and_unnamed_streams(self) -> None:
        report = name_recover.recover_path(COMMON_HEAD, validate=True)
        streams = report["streams"]
        self.assertGreater(len(streams), 500)
        named = [s for s in streams if s["status"] == "named"]
        unnamed = [s for s in streams if s["status"] == "unnamed"]
        self.assertGreater(len(named), 50)
        self.assertGreater(len(unnamed), 50)
        for s in unnamed:
            self.assertEqual(s["candidates"], [])
            self.assertEqual(s["full_paths"], [])
            self.assertEqual(s["identifiers"], [])
        self.assertTrue(report["validation"]["all_verified"])

    @unittest.skipUnless(SHADERS_HEAD.is_file(), "shaders.head.bin not present")
    def test_shaders_head_sgd5_dxbc_and_truncated(self) -> None:
        streams = name_recover.recover_file(SHADERS_HEAD)
        dxbc = [s for s in streams if s["stream_type"] == "sgd5_shader_dxbc"]
        trunc = [s for s in streams if s["stream_type"] == "sgd5_shader_truncated"]
        self.assertEqual(len(dxbc), 735)
        self.assertEqual(len(trunc), 1)
        self.assertEqual(
            dxbc[0]["identifiers"],
            ["VS_AlphaTransmissionFullScreenTri_4f16bf6c_Wrapped"],
        )
        self.assertEqual(dxbc[0]["candidates"][0]["source"], "sgd5")
        self.assertIsNotNone(dxbc[0]["inflated_bytes"])
        self.assertIsNone(trunc[0]["inflated_bytes"])

    @unittest.skipUnless(DATA_HEAD.is_file() and STORY_HEAD.is_file(), "data/story samples not present")
    def test_psin_and_0drp_real_extraction(self) -> None:
        data_streams = name_recover.recover_file(DATA_HEAD)
        psin_named = [s for s in data_streams if s["stream_type"] == "PSIN" and s["status"] == "named"]
        self.assertGreaterEqual(len(psin_named), 2)
        self.assertIn("TEMP_0653AU_AAAA", psin_named[0]["identifiers"])

        story_streams = name_recover.recover_file(STORY_HEAD)
        odrp_named = [s for s in story_streams if s["stream_type"] == "0DRP" and s["status"] == "named"]
        self.assertGreaterEqual(len(odrp_named), 5)
        odrp_paths = {p for s in odrp_named for p in s["full_paths"]}
        self.assertIn("cutscene_exclusive/AIR_TAIL_INT", odrp_paths)
        self.assertIn("cutscene_exclusive/AIR_TRAIN_INT_PHONE.bk2", odrp_paths)


class TestNameRecoverSynthetic(unittest.TestCase):
    def test_dedup_separation_and_unnamed_honesty(self) -> None:
        xml_payload = (
            b'<?xml version="1.0" encoding="utf-8"?>'
            b"<CDataFileMgr__ContentChangeSetDef>"
            b"<id>sample_pack</id>"
            b"<filename>$(target)/data/sample.rpf</filename>"
            b"<filename>$(target)/data/sample.rpf</filename>"
            b"<Name>Default</Name>"
            b"</CDataFileMgr__ContentChangeSetDef>"
        )
        psin_payload = (
            b"PSIN\x00\x00\x00\x10\x16\x00\x00\x00\x00\x00\x00\x00"
            b"LSCH\x00\x00\x00\x08"
            b"\x00sc_DemoMission\x00Gracias.\x00h06_Cn_J\x00z/afsqQ\x00"
        )
        # 0DRP payload with only binary/dialogue noise -> must stay unnamed
        odrp_unnamed_payload = b"\x00" * 16 + b"0DRPz\x00\x00\x00Gracias.\x00Hola.\x00"
        dxbc_body = b"DXBC" + bytes(range(256))
        dxbc_comp = _raw_deflate(dxbc_body)
        sym = b"PS_TestShader_1234abcd_Wrapped\x00"
        sgd5_entry = sym + struct.pack(
            "<B4I", 0x32, len(dxbc_comp), 0x11223344, len(dxbc_comp), len(dxbc_body)
        ) + dxbc_comp

        blob = (
            b"\x00" * 64
            + zlib.compress(xml_payload, 9)
            + zlib.compress(psin_payload, 9)
            + zlib.compress(odrp_unnamed_payload, 9)
            + b"SGD5"
            + b"\x00" * 16
            + sgd5_entry
        )

        with tempfile.TemporaryDirectory() as td:
            sample_path = Path(td) / "synthetic.bin"
            out_json = Path(td) / "index.json"
            sample_path.write_bytes(blob)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "name_recover.py"),
                    str(sample_path),
                    "--validate",
                    "--out",
                    str(out_json),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("all_verified=True", proc.stdout)
            rep = json.loads(out_json.read_text(encoding="utf-8"))

        self.assertEqual(rep["summary"]["total_streams"], 4)
        self.assertEqual(rep["summary"]["named_streams"], 3)
        self.assertEqual(rep["summary"]["unnamed_streams"], 1)
        self.assertTrue(rep["validation"]["all_verified"])

        by_type = {s["stream_type"]: s for s in rep["streams"]}
        self.assertEqual(by_type["xml"]["full_paths"], ["$(target)/data/sample.rpf"])
        self.assertEqual(by_type["xml"]["identifiers"], ["sample_pack"])
        self.assertEqual(len(by_type["xml"]["candidates"]), 2)
        self.assertEqual(by_type["PSIN"]["identifiers"], ["sc_DemoMission"])
        self.assertEqual(by_type["PSIN"]["full_paths"], [])
        self.assertEqual(by_type["0DRP"]["status"], "unnamed")
        self.assertEqual(by_type["0DRP"]["candidates"], [])
        self.assertEqual(by_type["sgd5_shader_dxbc"]["identifiers"], ["PS_TestShader_1234abcd_Wrapped"])
        self.assertEqual(by_type["sgd5_shader_dxbc"]["inflated_bytes"], len(dxbc_body))


class TestNameRecoverLabels(unittest.TestCase):
    """Provenance/confidence labels on synthetic streams (all names invented)."""

    def test_label_rule_table(self) -> None:
        cases = [
            ("xml", "xml_path_tag", "full_path", True, ("xml_mount", "confirmed")),
            ("xml", "xml_id_tag", "identifier", True, ("xml_mount", "confirmed")),
            ("xml", "xml_id_tag", "full_path", True, ("xml_mount", "confirmed")),
            ("xml", "xml_text", "full_path", True, ("xml_mount", "probable")),
            ("xml", "xml_other_tag", "full_path", True, ("xml_mount", "probable")),
            ("xml_chunk", "xml_path_tag", "full_path", False, ("xml_chunk", "confirmed")),
            ("xml_chunk", "xml_text", "full_path", False, ("xml_chunk", "probable")),
            ("xml", "xml_path_tag", "full_path", False, ("literal", "confirmed")),
            ("xml", "xml_text", "full_path", False, ("pattern", "probable")),
            ("raw", "cstring", "full_path", False, ("literal", "confirmed")),
            ("raw", "cstring", "identifier", False, ("inferred", "candidate")),
            ("raw", "scheme", "full_path", False, ("pattern", "probable")),
            ("sgd5_shader_dxbc", "sgd5", "identifier", False, ("literal", "confirmed")),
        ]
        for stream_type, channel, kind, mount, expected in cases:
            with self.subTest(stream_type=stream_type, channel=channel, kind=kind):
                self.assertEqual(
                    name_recover.label_candidate(
                        stream_type=stream_type,
                        channel=channel,
                        kind=kind,
                        mount_xml=mount,
                    ),
                    expected,
                )

    def test_mount_root_detection(self) -> None:
        mount = (
            '<?xml version="1.0" encoding="utf-8"?>'
            "<CDataFileMgr__ContentChangeSetDef><id>fixture_pack</id>"
            "</CDataFileMgr__ContentChangeSetDef>"
        )
        tuning = '<?xml version="1.0"?><timecycle_modifier_data><Item/></timecycle_modifier_data>'
        self.assertTrue(name_recover.is_mount_xml(mount))
        self.assertFalse(name_recover.is_mount_xml(tuning))

    def test_synthetic_streams_get_expected_labels(self) -> None:
        # Every name below is invented for the fixture ("fixture" prefix).
        mount_xml = (
            b'<?xml version="1.0" encoding="utf-8"?>'
            b"<CDataFileMgr__ContentChangeSetDef>"
            b"<id>fixture_pack</id>"
            b"<filename>$(fixture)/data/fixture_pack.rpf</filename>"
            b"<deviceName>$(fixture)/dev/fixture_device.meta</deviceName>"
            b"</CDataFileMgr__ContentChangeSetDef>"
        )
        # XML continuation fragment: closing tag, no XML declaration -> xml_chunk
        chunk_xml = (
            b"</FixturePack>"
            b"<filename>$(fixture)/data/fixture_chunk.bk2</filename>"
        )
        # PSIN carrying an identifier-shaped token with no path context.
        psin_payload = (
            b"PSIN\x00\x00\x00\x10\x16\x00\x00\x00\x00\x00\x00\x00"
            b"LSCH\x00\x00\x00\x08"
            b"\x00fixture_TokenName\x00Gracias.\x00"
        )
        # Same stream, two channels: a scheme path only in prose (pattern) and
        # a null-terminated scheme path (literal; C-string wins the dedup).
        raw_payload = (
            b"see phy:/fixture_pattern/mesh in prose\x00"
            b"phy:/fixture_literal/mesh\x00"
        )
        # Nothing to recover: must stay unnamed with empty labels.
        empty_payload = b"\x00" * 16 + b"0DRPz\x00\x00\x00Gracias.\x00Hola.\x00"

        blob = (
            b"\x00" * 64
            + zlib.compress(mount_xml, 9)
            + zlib.compress(chunk_xml, 9)
            + zlib.compress(psin_payload, 9)
            + zlib.compress(raw_payload, 9)
            + zlib.compress(empty_payload, 9)
        )

        with tempfile.TemporaryDirectory() as td:
            sample_path = Path(td) / "synthetic_labels.bin"
            out_json = Path(td) / "index.json"
            sample_path.write_bytes(blob)

            proc = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools" / "name_recover.py"),
                    str(sample_path),
                    "--validate",
                    "--out",
                    str(out_json),
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("all_verified=True", proc.stdout)
            rep = json.loads(out_json.read_text(encoding="utf-8"))

        by_type = {s["stream_type"]: s for s in rep["streams"]}

        xml_stream = by_type["xml"]
        self.assertEqual(
            xml_stream["full_paths"],
            [
                "$(fixture)/data/fixture_pack.rpf",
                "$(fixture)/dev/fixture_device.meta",
            ],
        )
        self.assertEqual(xml_stream["identifiers"], ["fixture_pack"])
        self.assertEqual(
            xml_stream["labeled"]["full_paths"],
            [
                {
                    "name": "$(fixture)/data/fixture_pack.rpf",
                    "source": "xml_mount",
                    "confidence": "confirmed",
                },
                {
                    "name": "$(fixture)/dev/fixture_device.meta",
                    "source": "xml_mount",
                    "confidence": "confirmed",
                },
            ],
        )
        self.assertEqual(
            xml_stream["labeled"]["identifiers"],
            [
                {
                    "name": "fixture_pack",
                    "source": "xml_mount",
                    "confidence": "confirmed",
                }
            ],
        )

        chunk_stream = by_type["xml_chunk"]
        self.assertEqual(
            chunk_stream["labeled"]["full_paths"],
            [
                {
                    "name": "$(fixture)/data/fixture_chunk.bk2",
                    "source": "xml_chunk",
                    "confidence": "confirmed",
                }
            ],
        )

        psin_stream = by_type["PSIN"]
        self.assertEqual(psin_stream["identifiers"], ["fixture_TokenName"])
        self.assertEqual(
            psin_stream["labeled"]["identifiers"],
            [
                {
                    "name": "fixture_TokenName",
                    "source": "inferred",
                    "confidence": "candidate",
                }
            ],
        )

        raw_stream = by_type["raw"]
        self.assertEqual(
            raw_stream["full_paths"],
            ["phy:/fixture_literal/mesh", "phy:/fixture_pattern/mesh"],
        )
        self.assertEqual(
            [(e["name"], e["source"], e["confidence"]) for e in raw_stream["labeled"]["full_paths"]],
            [
                ("phy:/fixture_literal/mesh", "literal", "confirmed"),
                ("phy:/fixture_pattern/mesh", "pattern", "probable"),
            ],
        )

        empty_stream = by_type["0DRP"]
        self.assertEqual(empty_stream["status"], "unnamed")
        self.assertEqual(empty_stream["labeled"], {"full_paths": [], "identifiers": []})

        # Compatibility: labeled is parallel to the published arrays, and the
        # published arrays/candidates keep their exact types and keys.
        for stream in rep["streams"]:
            for kind in ("full_paths", "identifiers"):
                self.assertIsInstance(stream[kind], list)
                self.assertTrue(all(isinstance(name, str) for name in stream[kind]))
                self.assertEqual(
                    [entry["name"] for entry in stream["labeled"][kind]],
                    stream[kind],
                )
            for candidate in stream["candidates"]:
                self.assertEqual(set(candidate), {"name", "kind", "source"})

        summary = rep["summary"]
        self.assertEqual(summary["total_streams"], 5)
        self.assertEqual(summary["named_streams"], 4)
        labeled = summary["labeled"]
        self.assertEqual(labeled["total_names"], 7)
        self.assertEqual(
            labeled["by_confidence"],
            {"confirmed": 5, "probable": 1, "candidate": 1},
        )
        self.assertEqual(
            labeled["by_source"],
            {
                "xml_mount": 3,
                "xml_chunk": 1,
                "literal": 1,
                "pattern": 1,
                "inferred": 1,
            },
        )
        self.assertEqual(labeled["by_stream_type"]["xml"]["total"], 3)
        self.assertEqual(labeled["by_stream_type"]["xml"]["confirmed"], 3)
        self.assertEqual(labeled["by_stream_type"]["raw"]["probable"], 1)
        self.assertEqual(labeled["by_stream_type"]["PSIN"]["candidate"], 1)
        self.assertEqual(labeled["by_stream_type"]["0DRP"]["total"], 0)


if __name__ == "__main__":
    unittest.main()
