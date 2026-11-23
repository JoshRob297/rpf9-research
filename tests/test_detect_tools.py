"""Tests for the detection extractors (compatible with pytest and unittest).

These tests do not need the 273 MB `agy.bin`; they exercise the parsing logic on
small synthetic fixtures. The real-binary outputs used by `docs/DETECCION.md`
are transcribed in `raw/deteccion-agy.txt`.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import agy_extract  # noqa: E402
import plugin_surface  # noqa: E402


class TestAgyExtract(unittest.TestCase):
    def test_find_all_offsets(self) -> None:
        data = b"xxaidev_client\x00aidev_client\x00"
        self.assertEqual(agy_extract.find_all(data, b"aidev_client"), [2, 15])
        self.assertEqual(agy_extract.find_all(data, b"absent"), [])

    def test_iter_strings_skips_binary_runs(self) -> None:
        data = b"\x00\x01abc\xff\x00a longer string\x00"
        found = list(agy_extract.iter_strings(data, min_len=3))
        self.assertEqual(found, [(2, "abc"), (7, "a longer string")])

    def test_extract_ua_facts_offsets_and_template(self) -> None:
        payload = (
            b"\x00antigravity\x00cli\x001.5.14\x00"
            b"%s/%s/%s (%s)\x00aidev_client\x00os_type=%s\x00arch=%s\x00"
            b"cl=%d\x00auth_method=%s\x00; \x00"
            b"1027820220\x00"
            b"1027820220\x00"
            b"1795406304\x00"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fake.bin"
            path.write_bytes(payload)
            facts = agy_extract.extract_ua_facts(path)

        self.assertEqual(facts["literals"]["template"]["offset"], 24)
        self.assertEqual(facts["literals"]["aidev_client"]["text"], "aidev_client")
        self.assertEqual(facts["literals"]["separator"]["text"], "; ")
        texts = [c["text"] for c in facts["numeric_candidates"]]
        self.assertIn("1027820220", texts)
        self.assertIn("1795406304", texts)
        self.assertEqual(facts["template"], "antigravity/cli/<version> (<parts joined by '; '>)")
        self.assertTrue(any(part.startswith("os_type") for part in facts["parts"]))

    def test_extract_ua_facts_requires_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.bin"
            path.write_bytes(b"nothing here")
            with self.assertRaises(agy_extract.MissingEvidence):
                agy_extract.extract_ua_facts(path)


class TestPluginSurface(unittest.TestCase):
    CONSTANTS = """
export const ANTIGRAVITY_ENDPOINT_DAILY = "https://daily-cloudcode-pa.sandbox.googleapis.com";
export const ANTIGRAVITY_ENDPOINT_DAILY_DIRECT = "https://daily-cloudcode-pa.googleapis.com";
export const ANTIGRAVITY_VERSION_FALLBACK = "2.0.6";
export const ANTIGRAVITY_CLI_VERSION_FALLBACK = "1.5.8";
export function getAntigravityCliUserAgent(): string {
  return `antigravity/cli/${getAntigravityCliVersion()} (aidev_client; os_type=linux; arch=amd64; cl=962369648; auth_method=consumer)`;
}
const PLATFORM_CHOICES = ["darwin", "win32"] as const;
const x = `{"ideType":"ANTIGRAVITY","platform":"${process.platform === "win32" ? "WINDOWS" : "MACOS"}","pluginType":"GEMINI"}`;
"""

    REQUEST = """
const transformedUrl = `${baseEndpoint}/v1internal:${rawAction}${streaming ? "?alt=sse" : ""}`;
headers.delete("x-api-key");
headers.delete("x-goog-api-key");
headers.delete("x-goog-user-project");
headers.set("Accept", "text/event-stream");
headers.set("User-Agent", userAgent);
const wrappedBody: Record<string, unknown> = { project: effectiveProjectId, model: effectiveModel, request: requestPayload };
wrappedBody.requestType = "agent";
wrappedBody.userAgent = "antigravity";
wrappedBody.requestId = "agent-" + crypto.randomUUID();
"""

    def test_parse_constants(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "constants.js"
            path.write_text(self.CONSTANTS, encoding="utf-8")
            facts = plugin_surface.parse_constants(path)

        self.assertEqual(facts["cli_version_fallback"], "1.5.8")
        self.assertEqual(facts["cli_ua"]["cl"], "962369648")
        self.assertEqual(facts["cli_ua"]["os_type"], "linux")
        self.assertEqual(facts["cli_ua"]["arch"], "amd64")
        self.assertEqual(facts["cli_ua"]["auth_method"], "consumer")
        self.assertEqual(facts["endpoints"]["ANTIGRAVITY_ENDPOINT_DAILY_DIRECT"]["url"], "https://daily-cloudcode-pa.googleapis.com")
        self.assertEqual(facts["platform_choices"], ["darwin", "win32"])
        self.assertIn("MACOS", facts["client_metadata_platform_expr"]["expr"])

    def test_parse_request(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "request.js"
            path.write_text(self.REQUEST, encoding="utf-8")
            facts = plugin_surface.parse_request(path)

        self.assertEqual(
            facts["deleted_headers"], ["x-api-key", "x-goog-api-key", "x-goog-user-project"]
        )
        self.assertEqual(facts["set_headers"].get("Accept"), "text/event-stream")
        self.assertIn("v1internal", facts["transformed_url"])
        self.assertEqual(facts["body_fields"]["requestType"], "agent")
        self.assertEqual(facts["body_fields"]["userAgent"], "antigravity")
        self.assertIn("agent-", facts["body_fields"]["requestId"])

    def test_missing_file_is_reported(self) -> None:
        with self.assertRaises(FileNotFoundError):
            plugin_surface.parse_constants(Path("/nonexistent/constants.js"))


if __name__ == "__main__":
    unittest.main()
