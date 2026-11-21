#!/usr/bin/env python3
"""RPF9 container inspector prototype (GTA VI Xbox Series X|S research).

Parses the 64-byte plaintext RPF9 header, explains each 32-bit field with its
measured/plausible/unknown status, inspects the head TOC region [0x40..w04),
and makes an honest attempt to list entries without inventing data when the
TOC is encrypted and no decryption key is available.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
from pathlib import Path
from typing import Any

RPF9_MAGIC = 0x52504639  # "RPF9" as little-endian uint32 (bytes: 39 46 50 52)
RPF9_MAGIC_BYTES = b"9FPR"
HEADER_SIZE = 64
KNOWN_TOC_PREFIX_HEX = (
    "5f08daabecbdd40258c3516807024c24fb9f756755ef4be458785bfed8aa6989"
)


def shannon_entropy(data: bytes) -> float:
    """Compute Shannon entropy in bits per byte (0.0 .. 8.0)."""
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts if c)


def parse_header(data: bytes) -> dict[str, Any]:
    """Parse and explain the 64-byte RPF9 header."""
    if len(data) < HEADER_SIZE:
        raise ValueError(f"File too small for RPF9 header: {len(data)} < {HEADER_SIZE} bytes")

    words = struct.unpack("<16I", data[:HEADER_SIZE])
    magic = words[0]
    if magic != RPF9_MAGIC:
        raise ValueError(
            f"Invalid magic 0x{magic:08x} ({data[:4].hex()}); expected RPF9 LE 0x{RPF9_MAGIC:08x} (39465052)"
        )

    w04, w08, w0c = words[1], words[2], words[3]
    w10, w14 = words[4], words[5]
    w18, w1c = words[6], words[7]
    w20, w24 = words[8], words[9]
    w28, w2c = words[10], words[11]
    w30, w34, w38, w3c = words[12], words[13], words[14], words[15]

    fields = [
        {
            "offset": "0x00",
            "name": "magic",
            "value_u32": magic,
            "value_hex": f"0x{magic:08x}",
            "status": "confirmed",
            "description": "Container magic 'RPF9' in little-endian (bytes 39 46 50 52).",
        },
        {
            "offset": "0x04",
            "name": "toc_end_offset",
            "value_u32": w04,
            "value_hex": f"0x{w04:08x}",
            "status": "confirmed",
            "description": (
                f"End offset of encrypted head TOC region [0x40..0x{w04:x}); "
                f"TOC length = {max(0, w04 - HEADER_SIZE)} bytes."
            ),
        },
        {
            "offset": "0x08",
            "name": "toc_subtable_offset",
            "value_u32": w08,
            "value_hex": f"0x{w08:08x}",
            "status": "plausible",
            "description": (
                f"Internal boundary inside head TOC (<= toc_end_offset); "
                f"upper sub-region [0x{w08:x}..0x{w04:x}) is {w04 - w08} bytes "
                f"(scales with entry_count_candidate w24)."
            ),
        },
        {
            "offset": "0x0c",
            "name": "trailer_length",
            "value_u32": w0c,
            "value_hex": f"0x{w0c:08x}",
            "status": "confirmed_location_plausible_role",
            "description": (
                f"Byte length ({w0c}) of encrypted trailer located at [EOF - {w0c} .. EOF) "
                f"in outer archives (plausible name/metadata table)."
            ),
        },
        {
            "offset": "0x10",
            "name": "archive_id_lo",
            "value_u32": w10,
            "value_hex": f"0x{w10:08x}",
            "status": "indeterminate",
            "description": "Low 32 bits of unique 64-bit per-archive identifier/salt/hash.",
        },
        {
            "offset": "0x14",
            "name": "archive_id_hi",
            "value_u32": w14,
            "value_hex": f"0x{w14:08x}",
            "status": "indeterminate",
            "description": "High 32 bits of unique 64-bit per-archive identifier/salt/hash.",
        },
        {
            "offset": "0x18",
            "name": "const_0x18",
            "value_u32": w18,
            "value_hex": f"0x{w18:08x}",
            "status": "confirmed_constant",
            "description": "Format constant 0x00047a00 (293376) observed across all 31 RPF9 headers.",
        },
        {
            "offset": "0x1c",
            "name": "const_0x1c",
            "value_u32": w1c,
            "value_hex": f"0x{w1c:08x}",
            "status": "confirmed_constant",
            "description": "Format constant 0x00000150 (336) observed across all 31 RPF9 headers.",
        },
        {
            "offset": "0x20",
            "name": "flags_or_version_u32",
            "value_u32": w20,
            "value_hex": f"0x{w20:08x}",
            "status": "indeterminate",
            "description": (
                f"Split u16=({w20 & 0xffff}, {w20 >> 16}); low u16 ranges 3..7, "
                f"high u16 is 1 or 2. Candidate flags/depth/version."
            ),
        },
        {
            "offset": "0x24",
            "name": "entry_count_candidate",
            "value_u32": w24,
            "value_hex": f"0x{w24:08x}",
            "status": "plausible",
            "description": (
                f"Plausible entry/node count ({w24}); (w04 - w08) = {w04 - w08} scales "
                f"linearly with this field (~9-18 B/entry) and trailers collide when w24 matches."
            ),
        },
        {
            "offset": "0x28",
            "name": "build_or_key_tag",
            "value_u32": w28,
            "value_hex": f"0x{w28:08x}",
            "status": "indeterminate",
            "description": "Takes 5 discrete values across 30 unique headers; does not alter 0x40..0x5f ciphertext.",
        },
        {
            "offset": "0x2c",
            "name": "subversion_or_page_flag",
            "value_u32": w2c,
            "value_hex": f"0x{w2c:08x}",
            "status": "plausible",
            "description": (
                f"Observed as 0x00090f01 when w24 <= 194 and 0x00090f02 when w24 >= 265 "
                f"(byte0={w2c & 0xff})."
            ),
        },
        {
            "offset": "0x30",
            "name": "block_alignment",
            "value_u32": w30,
            "value_hex": f"0x{w30:08x}",
            "status": "confirmed_constant",
            "description": "Constant 16 (0x10) across all 31 headers; matches 16-byte AES/TOC alignment.",
        },
        {
            "offset": "0x34",
            "name": "reserved_0x34",
            "value_u32": w34,
            "value_hex": f"0x{w34:08x}",
            "status": "confirmed_zero",
            "description": "Zero padding/reserved across all 31 headers.",
        },
        {
            "offset": "0x38",
            "name": "reserved_0x38",
            "value_u32": w38,
            "value_hex": f"0x{w38:08x}",
            "status": "confirmed_zero",
            "description": "Zero padding/reserved across all 31 headers.",
        },
        {
            "offset": "0x3c",
            "name": "reserved_0x3c",
            "value_u32": w3c,
            "value_hex": f"0x{w3c:08x}",
            "status": "confirmed_zero",
            "description": "Zero padding/reserved across all 31 headers.",
        },
    ]

    return {
        "header_size": HEADER_SIZE,
        "magic_hex": f"0x{magic:08x}",
        "toc_offset": HEADER_SIZE,
        "toc_end_offset": w04,
        "toc_length": max(0, w04 - HEADER_SIZE),
        "toc_subtable_offset": w08,
        "toc_upper_subtable_length": max(0, w04 - w08),
        "trailer_length": w0c,
        "entry_count_candidate": w24,
        "archive_id_u64_hex": f"0x{(w14 << 32) | w10:016x}",
        "fields": fields,
    }


def inspect_toc_and_entries(
    file_path: Path, data: bytes, header: dict[str, Any], scan_nested: bool = False
) -> dict[str, Any]:
    """Inspect TOC region for encryption and attempt entry listing without inventing data."""
    toc_start = header["toc_offset"]
    toc_end = header["toc_end_offset"]
    file_len = len(data)

    if toc_end < toc_start or toc_end > file_len:
        return {
            "toc_present": False,
            "toc_encrypted": None,
            "toc_entropy": None,
            "entry_listing_status": "truncated_or_invalid_toc_bounds",
            "reason": (
                f"TOC bounds [0x{toc_start:x}..0x{toc_end:x}) exceed available bytes ({file_len})."
            ),
            "entries": [],
        }

    toc_bytes = data[toc_start:toc_end]
    ent = shannon_entropy(toc_bytes)
    blks = [toc_bytes[i : i + 16] for i in range(0, len(toc_bytes) - (len(toc_bytes) % 16), 16)]
    intra_dups = len(blks) - len(set(blks))
    prefix_match = toc_bytes[:32].hex() == KNOWN_TOC_PREFIX_HEX

    # Detect plaintext ASCII paths vs high-entropy ciphertext
    printable_ratio = (
        sum(1 for b in toc_bytes if 32 <= b < 127) / len(toc_bytes) if toc_bytes else 0.0
    )
    toc_encrypted = ent >= 7.0 or (prefix_match and printable_ratio < 0.5)

    # Check if zero-padded right after toc_end
    zero_pad_after_toc = 0
    for b in data[toc_end : min(file_len, toc_end + 4096)]:
        if b == 0:
            zero_pad_after_toc += 1
        else:
            break

    result: dict[str, Any] = {
        "toc_present": True,
        "toc_range": f"0x{toc_start:x}..0x{toc_end:x}",
        "toc_bytes": len(toc_bytes),
        "toc_aligned_16": (len(toc_bytes) % 16) == 0,
        "toc_entropy": round(ent, 4),
        "toc_intra_16b_dups": intra_dups,
        "matches_known_32b_toc_prefix": prefix_match,
        "zero_padding_after_toc": zero_pad_after_toc,
        "toc_encrypted": toc_encrypted,
        "entries": [],
    }

    if toc_encrypted:
        result["entry_listing_status"] = "blocked_encrypted_toc_no_key"
        result["reason"] = (
            f"Head TOC [{toc_start:#x}..{toc_end:#x}) is encrypted "
            f"(Shannon entropy {ent:.4f} bits/byte, 16-byte aligned, "
            f"known_prefix={prefix_match}). Decryption key is unavailable; "
            f"no entries invented."
        )
    else:
        result["entry_listing_status"] = "unencrypted_toc_layout_unverified"
        result["reason"] = (
            f"Head TOC entropy is low ({ent:.4f} bits/byte), but plaintext RPF9 "
            f"entry struct layout has not been observed in encrypted samples; "
            f"no entries invented."
        )

    if scan_nested:
        nested = []
        pos = HEADER_SIZE
        while True:
            idx = data.find(RPF9_MAGIC_BYTES, pos)
            if idx == -1:
                break
            if idx + HEADER_SIZE <= file_len:
                w = struct.unpack("<16I", data[idx : idx + HEADER_SIZE])
                if w[6] == 0x47A00 and w[7] == 0x150:
                    nested.append(
                        {
                            "offset": idx,
                            "offset_hex": f"0x{idx:x}",
                            "toc_end_offset": w[1],
                            "trailer_length": w[3],
                            "entry_count_candidate": w[9],
                        }
                    )
            pos = idx + 4
        result["nested_rpf9_containers"] = nested

    return result


def inspect_file(path: Path, scan_nested: bool = False) -> dict[str, Any]:
    """Inspect a single RPF9 file or head window."""
    data = path.read_bytes()
    header = parse_header(data)
    toc_info = inspect_toc_and_entries(path, data, header, scan_nested=scan_nested)
    return {
        "file": str(path),
        "file_size_read": len(data),
        "header": header,
        "toc": toc_info,
    }


def format_human(report: dict[str, Any]) -> str:
    """Format inspection report as human-readable text."""
    lines = [
        f"File: {report['file']} ({report['file_size_read']} bytes read)",
        "",
        "Header fields (64 bytes, little-endian uint32):",
    ]
    for f in report["header"]["fields"]:
        lines.append(
            f"  {f['offset']}  {f['name']:<24} {f['value_hex']} ({f['value_u32']:>10}) [{f['status']}]"
        )
        lines.append(f"        {f['description']}")

    toc = report["toc"]
    lines.extend(
        [
            "",
            "TOC & entry listing:",
            f"  present       : {toc['toc_present']}",
            f"  range         : {toc.get('toc_range')}",
            f"  entropy       : {toc.get('toc_entropy')} bits/byte",
            f"  encrypted     : {toc.get('toc_encrypted')}",
            f"  known_prefix  : {toc.get('matches_known_32b_toc_prefix')}",
            f"  intra_16b_dups: {toc.get('toc_intra_16b_dups')}",
            f"  status        : {toc['entry_listing_status']}",
            f"  detail        : {toc['reason']}",
            f"  entries       : {len(toc['entries'])} (not invented)",
        ]
    )
    if "nested_rpf9_containers" in toc:
        nested = toc["nested_rpf9_containers"]
        lines.append(f"  nested_rpf9   : {len(nested)} found")
        for n in nested:
            lines.append(
                f"    @{n['offset_hex']} w04={n['toc_end_offset']} w0c={n['trailer_length']} w24={n['entry_count_candidate']}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect RPF9 container header and TOC status."
    )
    parser.add_argument("path", type=Path, help="Path to .rpf or .head.bin sample file")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument(
        "--scan-nested",
        action="store_true",
        help="Scan payload for unencrypted nested RPF9 container headers",
    )
    args = parser.parse_args(argv)

    if not args.path.is_file():
        print(f"Error: file not found: {args.path}", file=sys.stderr)
        return 2

    try:
        report = inspect_file(args.path, scan_nested=args.scan_nested)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_human(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
