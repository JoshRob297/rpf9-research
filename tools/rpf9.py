#!/usr/bin/env python3
"""RPF9 container inspector prototype (GTA VI Xbox Series X|S research).

Parses the 64-byte plaintext RPF9 header, explains each 32-bit field with its
measured/plausible/confirmed status, inspects the head TOC region [0x40..w04),
and with --payload locates and parses readable unencrypted payload elements
(zlib 78 da streams, SGD5 shader blocks, nested RPF9 containers, KB2n/EDUP/LRSC)
while explicitly reporting encrypted or unreadable regions without inventing data.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import Any

RPF9_MAGIC = 0x52504639  # "RPF9" as little-endian uint32 (bytes: 39 46 50 52)
RPF9_MAGIC_BYTES = b"9FPR"
HEADER_SIZE = 64
KNOWN_TOC_PREFIX_HEX = (
    "5f08daabecbdd40258c3516807024c24fb9f756755ef4be458785bfed8aa6989"
)

# Empirically observed trailer block-0 ciphertexts for w20_hi == 1 containers
KNOWN_TRAILER_BLK0_BY_W24: dict[int, bytes] = {
    1: bytes.fromhex("aa0405b99acd17960141dafc7abd482f"),
    2: bytes.fromhex("b7da7c1d963787c846fe15fd0e243364"),
    3: bytes.fromhex("f11ce775de6373e9dcc1007ab315d7eb"),
    4: bytes.fromhex("5a178c51e7b96189237e72453084db8a"),
    6: bytes.fromhex("082eadfa6a9aa2e364d86c00380db446"),
    10: bytes.fromhex("e0b5ed97a889dfc6170830886b3a0eb8"),
    22: bytes.fromhex("bae2486fd69205dfa8ffffea0db521e8"),
    39: bytes.fromhex("9b038e98400ce7e8009f8242bf31e4a8"),
}


def shannon_entropy(data: bytes) -> float:
    """Compute Shannon entropy in bits per byte (0.0 .. 8.0)."""
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    return -sum((c / n) * math.log2(c / n) for c in counts if c)


def is_valid_rpf9_header_at(data: bytes, offset: int) -> tuple[int, ...] | None:
    """Return unpacked 16 u32 words if offset holds a validated RPF9 header."""
    if offset < 0 or offset + HEADER_SIZE > len(data):
        return None
    if data[offset : offset + 4] != RPF9_MAGIC_BYTES:
        return None
    w = struct.unpack("<16I", data[offset : offset + HEADER_SIZE])
    if w[6] == 0x47A00 and w[7] == 0x150 and w[12] == 16 and w[13] == 0 and w[14] == 0 and w[15] == 0:
        return w
    return None


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

    w20_hi = w20 >> 16
    w2c_b0 = w2c & 0xFF
    if w20_hi == 1 and w2c_b0 in (1, 2):
        stride = 9 if w2c_b0 == 1 else 10
        pred_sub = ((stride * w24 + 15) // 16) * 16
        sub_note = f"matches ceil({stride}*w24/16)*16={pred_sub}" if (w04 - w08) == pred_sub else f"differs from {pred_sub}"
    else:
        sub_note = f"w20_hi={w20_hi} (non-9/10B stride)"

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
            "status": "confirmed_bounds_plausible_role",
            "description": (
                f"Internal boundary inside head TOC (<= toc_end_offset); "
                f"upper sub-region [0x{w08:x}..0x{w04:x}) is {w04 - w08} bytes ({sub_note})."
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
                f"in outer/nested containers (plausible name/metadata table)."
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
            "description": "Format constant 0x00047a00 (293376) observed across all 77 RPF9 headers.",
        },
        {
            "offset": "0x1c",
            "name": "const_0x1c",
            "value_u32": w1c,
            "value_hex": f"0x{w1c:08x}",
            "status": "confirmed_constant",
            "description": "Format constant 0x00000150 (336) observed across all 77 RPF9 headers.",
        },
        {
            "offset": "0x20",
            "name": "flags_or_version_u32",
            "value_u32": w20,
            "value_hex": f"0x{w20:08x}",
            "status": "plausible",
            "description": (
                f"Split u16=({w20 & 0xffff}, {w20_hi}); low u16 ranges 3..7, "
                f"high u16 (1 or 2) selects subtable stride and trailer block-0 format."
            ),
        },
        {
            "offset": "0x24",
            "name": "entry_count_candidate",
            "value_u32": w24,
            "value_hex": f"0x{w24:08x}",
            "status": "confirmed_on_complete_small_files",
            "description": (
                f"Entry count ({w24}); matches reconstructed payload counts in complete files "
                f"(4/4 story000_bvh4, 2/2 appdata0, 4/4 core_licenses_data, 6/6 core_restofworld001) "
                f"and drives [w08..w04) width and trailer block-0."
            ),
        },
        {
            "offset": "0x28",
            "name": "build_or_key_tag",
            "value_u32": w28,
            "value_hex": f"0x{w28:08x}",
            "status": "indeterminate",
            "description": "Takes 5 discrete values across 76 unique headers; does not alter 0x40..0x5f or trailer blk0.",
        },
        {
            "offset": "0x2c",
            "name": "subversion_or_page_flag",
            "value_u32": w2c,
            "value_hex": f"0x{w2c:08x}",
            "status": "confirmed_subtable_stride_flag",
            "description": (
                f"Observed as 0x00090f01 (9 B/entry in [w08..w04), w24<=194) or "
                f"0x00090f02 (10 B/entry in [w08..w04), w24>=265) (byte0={w2c_b0})."
            ),
        },
        {
            "offset": "0x30",
            "name": "block_alignment",
            "value_u32": w30,
            "value_hex": f"0x{w30:08x}",
            "status": "confirmed_constant",
            "description": "Constant 16 (0x10) across all 77 headers; matches 16-byte AES/TOC alignment.",
        },
        {
            "offset": "0x34",
            "name": "reserved_0x34",
            "value_u32": w34,
            "value_hex": f"0x{w34:08x}",
            "status": "confirmed_zero",
            "description": "Zero padding/reserved across all 77 headers.",
        },
        {
            "offset": "0x38",
            "name": "reserved_0x38",
            "value_u32": w38,
            "value_hex": f"0x{w38:08x}",
            "status": "confirmed_zero",
            "description": "Zero padding/reserved across all 77 headers.",
        },
        {
            "offset": "0x3c",
            "name": "reserved_0x3c",
            "value_u32": w3c,
            "value_hex": f"0x{w3c:08x}",
            "status": "confirmed_zero",
            "description": "Zero padding/reserved across all 77 headers.",
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
        "flags_or_version_u32": w20,
        "entry_count_candidate": w24,
        "archive_id_u64_hex": f"0x{(w14 << 32) | w10:016x}",
        "fields": fields,
    }


def _scan_nested_rpf9(data: bytes, start: int, end: int) -> list[dict[str, Any]]:
    """Locate nested RPF9 containers and reconstruct exact size where bounded."""
    hits: list[tuple[int, tuple[int, ...]]] = []
    pos = start
    while pos < end:
        idx = data.find(RPF9_MAGIC_BYTES, pos, end)
        if idx == -1:
            break
        w = is_valid_rpf9_header_at(data, idx)
        if w is not None and idx + HEADER_SIZE <= end:
            hits.append((idx, w))
        pos = idx + 4

    nested: list[dict[str, Any]] = []
    for i, (off, w) in enumerate(hits):
        w04, w08, w0c, w20, w24 = w[1], w[2], w[3], w[8], w[9]
        w20_hi = w20 >> 16
        exact_size: int | None = None
        trailer_range: str | None = None
        size_status = "unbounded_or_truncated_in_window"
        next_limit = hits[i + 1][0] if i + 1 < len(hits) else end

        if w20_hi == 1 and w24 in KNOWN_TRAILER_BLK0_BY_W24 and off + w04 < next_limit:
            tidx = data.find(KNOWN_TRAILER_BLK0_BY_W24[w24], off + w04, next_limit)
            if tidx != -1 and tidx + w0c <= next_limit:
                exact_size = (tidx + w0c) - off
                trailer_range = f"0x{tidx:x}..0x{tidx + w0c:x}"
                size_status = "exact_from_known_trailer_blk0"

        if exact_size is None and i + 1 < len(hits):
            last_nz = next_limit - 1
            while last_nz > off and data[last_nz] == 0:
                last_nz -= 1
            if next_limit - (last_nz + 1) >= 16:
                end_16 = ((last_nz + 1 + 15) // 16) * 16
                tr_s = end_16 - w0c
                if tr_s >= off + w04 and shannon_entropy(data[tr_s:end_16]) >= 6.0:
                    exact_size = end_16 - off
                    trailer_range = f"0x{tr_s:x}..0x{end_16:x}"
                    size_status = "exact_from_pre_next_rpf9_gap"

        nested.append(
            {
                "offset": off,
                "offset_hex": f"0x{off:x}",
                "archive_id_u64_hex": f"0x{(w[5] << 32) | w[4]:016x}",
                "toc_end_offset": w04,
                "toc_subtable_offset": w08,
                "trailer_length": w0c,
                "entry_count_candidate": w24,
                "reconstructed_size": exact_size,
                "trailer_range": trailer_range,
                "size_status": size_status,
            }
        )
    return nested


def _parse_sgd5_block(data: bytes, offset: int, limit: int) -> dict[str, Any]:
    """Parse SGD5 shader block header and sequential 8-byte parameter tables."""
    if offset + 20 > limit or data[offset : offset + 4] != b"SGD5":
        raise ValueError(f"Invalid SGD5 block at 0x{offset:x}")
    magic, u04, u08, sub_count, sec0_bytes = struct.unpack("<4s4I", data[offset : offset + 20])

    # Scan sequential 8-byte record tables [b0, b1, idx_u16, hash_u32]
    tables: list[dict[str, Any]] = []
    pos = offset + 20
    scan_limit = min(limit, offset + 0x10000)
    while pos + 32 <= scan_limit:
        ok = True
        for k in range(4):
            _, b1, idx, _ = struct.unpack("<BBHI", data[pos + k * 8 : pos + (k + 1) * 8])
            if idx != k or b1 not in (1, 2, 3, 4, 0x81, 0x83, 0x84):
                ok = False
                break
        if ok:
            k = 0
            while pos + (k + 1) * 8 <= scan_limit:
                _, _, idx, _ = struct.unpack("<BBHI", data[pos + k * 8 : pos + k * 8 + 8])
                if idx == k:
                    k += 1
                else:
                    break
            tables.append(
                {
                    "offset_hex": f"0x{pos:x}",
                    "end_hex": f"0x{pos + k * 8:x}",
                    "record_count": k,
                }
            )
            pos += k * 8
            continue
        pos += 4

    table_end = int(tables[-1]["end_hex"], 16) if tables else offset + 20
    # Find contiguous non-zero span containing shader symbol names following the block
    span_end = table_end
    while span_end < limit:
        if data[span_end : span_end + 128] == b"\x00" * 128:
            break
        span_end += 1
    while span_end > offset and data[span_end - 1] == 0:
        span_end -= 1

    syms = re.findall(rb"[VDHGMCP]S_[A-Za-z0-9_]+", data[offset:span_end])
    return {
        "offset": offset,
        "offset_hex": f"0x{offset:x}",
        "end_hex": f"0x{span_end:x}",
        "span_bytes": span_end - offset,
        "magic": magic.decode("ascii"),
        "u04_hex": f"0x{u04:08x}",
        "u08_hex": f"0x{u08:08x}",
        "sub_count_u32": sub_count,
        "first_section_bytes": sec0_bytes,
        "sequential_tables_found": len(tables),
        "sequential_records_total": sum(t["record_count"] for t in tables),
        "shader_symbol_count": len(syms),
        "sample_symbols": [s.decode("ascii", errors="replace") for s in syms[:5]],
    }


def _merge_spans(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not spans:
        return []
    ordered = sorted(spans)
    merged = [ordered[0]]
    for a, b in ordered[1:]:
        pa, pb = merged[-1]
        if a <= pb:
            merged[-1] = (pa, max(pb, b))
        else:
            merged.append((a, b))
    return merged


def _subtract_spans(start: int, end: int, covered: list[tuple[int, int]]) -> list[tuple[int, int]]:
    cur = start
    gaps: list[tuple[int, int]] = []
    for a, b in _merge_spans(covered):
        if b <= cur:
            continue
        if a >= end:
            break
        if a > cur:
            gaps.append((cur, min(a, end)))
        cur = max(cur, b)
    if cur < end:
        gaps.append((cur, end))
    return gaps


def scan_payload(data: bytes, header: dict[str, Any], file_path: Path | None = None) -> dict[str, Any]:
    """Scan and parse readable payload elements and report unreadable regions explicitly."""
    w04 = header["toc_end_offset"]
    w0c = header["trailer_length"]
    w24 = header["entry_count_candidate"]
    w20_hi = header["flags_or_version_u32"] >> 16
    file_len = len(data)

    if w04 > file_len:
        return {
            "payload_present": False,
            "reason": f"Payload start 0x{w04:x} exceeds available bytes ({file_len}).",
            "zlib_streams": [],
            "sgd5_blocks": [],
            "nested_rpf9_containers": [],
            "other_signatures": [],
            "unreadable_regions": [
                {
                    "region": "truncated_beyond_window",
                    "range": f"0x{file_len:x}..0x{w04:x}",
                    "status": "not_present_in_sample_window",
                }
            ],
        }

    # Detect whether complete EOF trailer is present inside data
    eof_trailer_detected = False
    if file_len >= w04 + w0c and w0c > 0:
        cand_tr = data[file_len - w0c :]
        if w20_hi == 1 and w24 in KNOWN_TRAILER_BLK0_BY_W24 and cand_tr[:16] == KNOWN_TRAILER_BLK0_BY_W24[w24]:
            eof_trailer_detected = True
        elif file_path is not None and file_path.name.endswith(".full.bin"):
            eof_trailer_detected = True

    scan_end = file_len - w0c if eof_trailer_detected else file_len
    readable_spans: list[tuple[int, int]] = []

    # 1. Nested RPF9 containers
    nested = _scan_nested_rpf9(data, w04, scan_end)
    for n in nested:
        noff = n["offset"]
        readable_spans.append((noff, min(scan_end, noff + HEADER_SIZE)))

    # 2. Valid zlib streams (78 da)
    zlib_streams: list[dict[str, Any]] = []
    pos = w04
    while pos < scan_end:
        idx = data.find(b"\x78\xda", pos, scan_end)
        if idx == -1:
            break
        try:
            dc = zlib.decompressobj()
            out = dc.decompress(data[idx:scan_end])
            if dc.eof and len(out) > 0:
                comp_len = (scan_end - idx) - len(dc.unused_data)
                head = out[:64]
                xml_info: dict[str, Any] | None = None
                if head.startswith(b"\xef\xbb\xbf<?xml") or head.startswith(b"<?xml"):
                    kind = "xml"
                    txt = out.decode("utf-8-sig", errors="replace")
                    m_root = re.search(r"<([A-Za-z0-9_]+)>", txt)
                    m_id = re.search(r"<id>([^<]+)</id>", txt)
                    m_dev = re.search(r"<deviceName>([^<]+)</deviceName>", txt)
                    paths = re.findall(r"<(?:filename|loadPath)>([^<]+)</(?:filename|loadPath)>", txt)
                    xml_info = {
                        "root": m_root.group(1) if m_root else None,
                        "id_or_device": m_id.group(1) if m_id else (m_dev.group(1) if m_dev else None),
                        "paths": paths[:8],
                    }
                elif head.startswith(b"PSIN"):
                    kind = "PSIN"
                elif b"0DRP" in head:
                    kind = "0DRP"
                elif len(head) >= 12 and head[:8] == b"\x00" * 8 and head[11] == 0x50:
                    kind = "rsc50"
                else:
                    kind = "raw"

                entry: dict[str, Any] = {
                    "offset": idx,
                    "offset_hex": f"0x{idx:x}",
                    "compressed_bytes": comp_len,
                    "decompressed_bytes": len(out),
                    "kind": kind,
                }
                if xml_info is not None:
                    entry["xml"] = xml_info
                zlib_streams.append(entry)
                readable_spans.append((idx, idx + comp_len))
                pos = idx + comp_len
                continue
        except Exception:
            pass
        pos = idx + 1

    # 3. SGD5 shader blocks
    sgd5_blocks: list[dict[str, Any]] = []
    pos = w04
    while pos < scan_end:
        idx = data.find(b"SGD5", pos, scan_end)
        if idx == -1:
            break
        blk = _parse_sgd5_block(data, idx, scan_end)
        sgd5_blocks.append(blk)
        readable_spans.append((idx, idx + blk["span_bytes"]))
        pos = idx + blk["span_bytes"]

    # 4. Other unencrypted signatures (KB2n, EDUP, LRSC/LGID)
    other_sigs: list[dict[str, Any]] = []
    for sig, label in [(b"KB2n", "bink2_video"), (b"EDUP", "tiled_texture_dupe"), (b"LRSC", "resource_chunk")]:
        pos = w04
        while pos < scan_end:
            idx = data.find(sig, pos, scan_end)
            if idx == -1:
                break
            other_sigs.append({"signature": sig.decode("ascii"), "kind": label, "offset_hex": f"0x{idx:x}"})
            if sig == b"EDUP":
                readable_spans.append((idx, min(scan_end, idx + 32)))
            else:
                readable_spans.append((idx, min(scan_end, idx + 16)))
            pos = idx + 4

    # 5. Explicitly enumerate unreadable regions (TOC, trailer, and non-zero uncovered spans)
    unreadable: list[dict[str, Any]] = [
        {
            "region": "head_toc",
            "range": f"0x{HEADER_SIZE:x}..0x{w04:x}",
            "bytes": max(0, w04 - HEADER_SIZE),
            "status": "encrypted_no_key",
        }
    ]
    for ga, gb in _subtract_spans(w04, scan_end, readable_spans):
        # Extract contiguous non-zero chunks >= 16 bytes inside [ga..gb)
        i = ga
        while i < gb:
            if data[i] == 0:
                i += 1
                continue
            s0 = i
            while i < gb:
                if data[i] != 0:
                    i += 1
                else:
                    j = i
                    while j < gb and data[j] == 0 and (j - i) < 16:
                        j += 1
                    if j - i >= 16 or j == gb:
                        break
                    i = j
            if i - s0 >= 16:
                unreadable.append(
                    {
                        "region": "payload_span",
                        "range": f"0x{s0:x}..0x{i:x}",
                        "bytes": i - s0,
                        "entropy": round(shannon_entropy(data[s0:i]), 4),
                        "status": "unreadable_encrypted_or_unknown_format_no_key",
                    }
                )

    if eof_trailer_detected:
        unreadable.append(
            {
                "region": "archive_trailer",
                "range": f"0x{scan_end:x}..0x{file_len:x}",
                "bytes": w0c,
                "entropy": round(shannon_entropy(data[scan_end:file_len]), 4),
                "status": "encrypted_no_key",
            }
        )
    else:
        unreadable.append(
            {
                "region": "archive_trailer",
                "range": "EOF - w0c .. EOF (outside_or_unverified_in_window)",
                "bytes": w0c,
                "status": "encrypted_no_key_or_truncated_window",
            }
        )

    return {
        "payload_present": True,
        "scan_range": f"0x{w04:x}..0x{scan_end:x}",
        "eof_trailer_detected": eof_trailer_detected,
        "zlib_stream_count": len(zlib_streams),
        "zlib_streams": zlib_streams,
        "sgd5_blocks": sgd5_blocks,
        "nested_rpf9_containers": nested,
        "other_signatures": other_sigs,
        "unreadable_regions": unreadable,
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

    printable_ratio = (
        sum(1 for b in toc_bytes if 32 <= b < 127) / len(toc_bytes) if toc_bytes else 0.0
    )
    toc_encrypted = ent >= 7.0 or (prefix_match and printable_ratio < 0.5)

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
        result["nested_rpf9_containers"] = _scan_nested_rpf9(data, HEADER_SIZE, file_len)

    return result


def inspect_file(path: Path, scan_nested: bool = False, include_payload: bool = False) -> dict[str, Any]:
    """Inspect a single RPF9 file or head window."""
    data = path.read_bytes()
    header = parse_header(data)
    toc_info = inspect_toc_and_entries(path, data, header, scan_nested=scan_nested)
    report: dict[str, Any] = {
        "file": str(path),
        "file_size_read": len(data),
        "header": header,
        "toc": toc_info,
    }
    if include_payload:
        report["payload"] = scan_payload(data, header, file_path=path)
    return report


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
            sz_txt = f"size={n['reconstructed_size']}" if n["reconstructed_size"] is not None else n["size_status"]
            lines.append(
                f"    @{n['offset_hex']} w04={n['toc_end_offset']} w0c={n['trailer_length']} w24={n['entry_count_candidate']} {sz_txt}"
            )

    if "payload" in report:
        pl = report["payload"]
        lines.extend(
            [
                "",
                "Payload scan (--payload):",
                f"  present       : {pl['payload_present']}",
                f"  scan_range    : {pl.get('scan_range')}",
                f"  eof_trailer   : {pl.get('eof_trailer_detected')}",
            ]
        )
        if pl["payload_present"]:
            lines.append(f"  zlib_streams  : {pl['zlib_stream_count']} readable")
            for z in pl["zlib_streams"][:25]:
                extra = ""
                if "xml" in z:
                    x = z["xml"]
                    extra = f" root=<{x['root']}> id={x['id_or_device']!r} paths={x['paths']}"
                lines.append(
                    f"    @{z['offset_hex']} comp={z['compressed_bytes']} raw={z['decompressed_bytes']} kind={z['kind']}{extra}"
                )
            if pl["zlib_stream_count"] > 25:
                lines.append(f"    ... ({pl['zlib_stream_count'] - 25} more zlib streams; use --json for full list)")

            lines.append(f"  sgd5_blocks   : {len(pl['sgd5_blocks'])}")
            for s in pl["sgd5_blocks"]:
                lines.append(
                    f"    @{s['offset_hex']}..{s['end_hex']} sub_count={s['sub_count_u32']} "
                    f"sec0={s['first_section_bytes']}B tables={s['sequential_tables_found']} "
                    f"recs={s['sequential_records_total']} syms={s['shader_symbol_count']}"
                )

            lines.append(f"  nested_rpf9   : {len(pl['nested_rpf9_containers'])}")
            for n in pl["nested_rpf9_containers"]:
                sz_txt = f"size={n['reconstructed_size']}" if n["reconstructed_size"] is not None else n["size_status"]
                lines.append(
                    f"    @{n['offset_hex']} w04={n['toc_end_offset']} w0c={n['trailer_length']} w24={n['entry_count_candidate']} ({sz_txt})"
                )

            if pl["other_signatures"]:
                lines.append(f"  other_sigs    : {len(pl['other_signatures'])}")
                for sig in pl["other_signatures"][:15]:
                    lines.append(f"    @{sig['offset_hex']} {sig['signature']} ({sig['kind']})")

            lines.append(f"  unreadable    : {len(pl['unreadable_regions'])} regions (explicitly cannot read without key/parser)")
            for u in pl["unreadable_regions"][:20]:
                ent_s = f" ent={u['entropy']}" if "entropy" in u else ""
                lines.append(f"    {u['region']} [{u['range']}] {u['bytes']}B{ent_s} -> {u['status']}")
            if len(pl["unreadable_regions"]) > 20:
                lines.append(f"    ... ({len(pl['unreadable_regions']) - 20} more unreadable spans; use --json)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect RPF9 container header, TOC status, and readable payloads."
    )
    parser.add_argument("path", type=Path, help="Path to .rpf, .head.bin, or .full.bin sample file")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument(
        "--scan-nested",
        action="store_true",
        help="Scan payload for unencrypted nested RPF9 container headers",
    )
    parser.add_argument(
        "--payload",
        action="store_true",
        help="Scan and parse readable payload items (zlib, SGD5, nested RPF9, signatures) and report unreadable regions",
    )
    args = parser.parse_args(argv)

    if not args.path.is_file():
        print(f"Error: file not found: {args.path}", file=sys.stderr)
        return 2

    try:
        report = inspect_file(args.path, scan_nested=args.scan_nested, include_payload=args.payload)
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
