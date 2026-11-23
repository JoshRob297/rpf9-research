#!/usr/bin/env python3
"""Recover resource paths and identifiers from RPF9 payloads without the encrypted TOC.

Scans sample windows (.bin) or full .rpf archives, inflates zlib (78 da) streams
and SGD5 shader raw-deflate DXBC entries, and extracts candidate resource names
with explicit provenance in priority order:
  1. Inflated XML / XML continuation chunks (paths and identifiers)
  2. Internal references inside PSIN and 0DRP containers
  3. SGD5 shader symbol tables ([VDHGMCP]S_*_Wrapped)
  4. Clean internal resource paths inside rsc50 / raw streams (when present)

Every recovered name is also labelled by origin and strength (see the
"Provenance labels" block below and docs/NAMES.md section 3): ``source`` says
where the bytes came from, ``confidence`` says how much the evidence proves.
The labels travel in a parallel ``labeled`` structure so the published
``full_paths`` / ``identifiers`` arrays keep their type, length and order.

Streams without recoverable names are recorded explicitly with status="unnamed"
and never receive fabricated offset-based names.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
import zlib
from collections import Counter
from pathlib import Path
from typing import Any

TARGET_EXTENSIONS: tuple[str, ...] = (
    "ytd",
    "ydr",
    "yft",
    "ybn",
    "ymap",
    "ytyp",
    "ycd",
    "awc",
    "rpf",
    "xml",
    "meta",
    "rel",
    "dat",
)
EXTRA_ASSET_EXTENSIONS: tuple[str, ...] = ("bk2", "ityp", "clip", "skel")
ALL_EXTENSIONS = TARGET_EXTENSIONS + EXTRA_ASSET_EXTENSIONS

EXT_SUFFIX_RE = re.compile(rf"\.(?:{'|'.join(ALL_EXTENSIONS)})$", re.I)
TARGET_EXT_RE = re.compile(rf"\.(?:{'|'.join(TARGET_EXTENSIONS)})$", re.I)

SCHEME_PATH_RE = re.compile(r"^[a-z][a-z0-9_]{1,15}:[/\\][A-Za-z0-9_./\\\-]{2,}$")
VAR_PATH_RE = re.compile(r"^\$\([A-Za-z0-9_]+\)/[A-Za-z0-9_./\\\-]{2,}$")
UNDERSCORE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+$")
SIMPLE_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.\-]{2,120}$")

XML_TAG_VAL_RE = re.compile(r"<([A-Za-z0-9_]+)>\s*([^<\r\n]{2,260}?)\s*</\1>")
XML_ATTR_VAL_RE = re.compile(
    r'\b(?:href|filename|loadPath|exportPath|path|file|ref)\s*=\s*["\']([^"\']{3,260})["\']'
)
XML_TEXT_RE = re.compile(r">([^<\r\n]{3,260})<")
CSTR_RE = re.compile(rb"(?:\x00|^)([A-Za-z0-9_./:$\\\-]{5,180})(?=\x00)")
SGD5_SYM_RE = re.compile(rb"([VDHGMCP]S_[A-Za-z0-9_]+_Wrapped)\x00")
CLEAN_SCHEME_RE = re.compile(
    rb"(?:\$\([A-Za-z0-9_]+\)|[a-z][a-z0-9_]{1,15}:)/[A-Za-z0-9_./\-]{2,180}"
)

XML_ID_TAGS = frozenset(
    {
        "id",
        "deviceName",
        "dlcName",
        "packFile",
        "scriptName",
        "audioBank",
        "datFile",
        "videoFileName",
        "modelName",
        "ModelName",
        "filename",
        "loadPath",
        "exportPath",
        "Name",
        "name",
    }
)

XML_GENERIC_STOPWORDS = frozenset(
    {
        "true",
        "false",
        "null",
        "none",
        "default",
        "invalid",
        "unknown",
        "empty",
        "standard",
    }
)

BINARY_TAG_STOPWORDS = frozenset(
    {
        "PSIN",
        "LSCH",
        "LENM",
        "LSNS",
        "LGID",
        "LRSC",
        "CHKS",
        "0DRP",
        "0DRPz",
        "PMAP",
        "PSCH",
        "PSIG",
        "STNS",
        "pppppppp",
        "hpppppppp",
    }
)

MAX_ZLIB_WINDOW = 4 * 1024 * 1024

# ---------------------------------------------------------------------------
# Provenance labels
#
# Two closed vocabularies, documented in docs/NAMES.md section 3:
#
#   source      where the bytes came from
#               xml_mount | xml_chunk | literal | pattern | inferred
#   confidence  how much those bytes prove
#               confirmed | probable | candidate
#
# The classification is a rule table, not an opaque score. Each extractor tags
# a candidate with the *channel* that found it (which tag, which regex), and
# label_candidate() maps (stream_type, channel, kind, is_mount_xml) to exactly
# one (source, confidence) pair. Channels are internal: they are stripped from
# the published ``candidates`` arrays, whose shape does not change.
# ---------------------------------------------------------------------------

SOURCE_XML_MOUNT = "xml_mount"
SOURCE_XML_CHUNK = "xml_chunk"
SOURCE_LITERAL = "literal"
SOURCE_PATTERN = "pattern"
SOURCE_INFERRED = "inferred"

CONFIDENCE_CONFIRMED = "confirmed"
CONFIDENCE_PROBABLE = "probable"
CONFIDENCE_CANDIDATE = "candidate"

SOURCES: tuple[str, ...] = (
    SOURCE_XML_MOUNT,
    SOURCE_XML_CHUNK,
    SOURCE_LITERAL,
    SOURCE_PATTERN,
    SOURCE_INFERRED,
)
CONFIDENCES: tuple[str, ...] = (
    CONFIDENCE_CONFIRMED,
    CONFIDENCE_PROBABLE,
    CONFIDENCE_CANDIDATE,
)

CHANNEL_XML_PATH_TAG = "xml_path_tag"
CHANNEL_XML_ID_TAG = "xml_id_tag"
CHANNEL_XML_OTHER_TAG = "xml_other_tag"
CHANNEL_XML_ATTR = "xml_attr"
CHANNEL_XML_TEXT = "xml_text"
CHANNEL_CSTRING = "cstring"
CHANNEL_SCHEME = "scheme"
CHANNEL_SGD5 = "sgd5"

# Channels where an XML tag or attribute declares the value as a path or an
# identity. Everything else was matched by shape only.
DECLARED_XML_CHANNELS = frozenset(
    {CHANNEL_XML_PATH_TAG, CHANNEL_XML_ID_TAG, CHANNEL_XML_ATTR}
)

# When one stream yields the same (kind, name) twice, the strongest channel
# keeps the label. Rank is evidence strength, not source priority.
CHANNEL_RANK = {
    CHANNEL_XML_PATH_TAG: 5,
    CHANNEL_XML_ID_TAG: 5,
    CHANNEL_XML_ATTR: 4,
    CHANNEL_CSTRING: 4,
    CHANNEL_SGD5: 4,
    CHANNEL_XML_OTHER_TAG: 2,
    CHANNEL_SCHEME: 2,
    CHANNEL_XML_TEXT: 1,
}

# Tags that declare a path. Same set the value classifier already trusts in
# _classify_xml_value().
XML_PATH_TAGS = frozenset({"filename", "loadPath", "exportPath", "datFile", "packFile"})

# Root elements that make an inflated XML a mount manifest. Measured over the
# 78 sample windows: 52 CDataFileMgr__ContentChangeSetDef + 8
# CDataFileMgr__ContentDef = 60 of the 477 XML streams (raw/etiquetas.txt).
MOUNT_XML_ROOTS = frozenset({"CDataFileMgr__ContentChangeSetDef", "CDataFileMgr__ContentDef"})

XML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
XML_ROOT_RE = re.compile(r"^\s*(?:<\?xml[^>]*\?>\s*)?<([A-Za-z0-9_]+)")


def is_mount_xml(text: str) -> bool:
    """True when the document's root element is a mount manifest."""
    head = XML_COMMENT_RE.sub("", text[:8192])
    match = XML_ROOT_RE.match(head)
    return bool(match and match.group(1) in MOUNT_XML_ROOTS)


def _xml_tag_channel(tag: str) -> str:
    """Evidence channel for a value found inside <tag>...</tag>.

    The channel follows the tag, not the inferred kind: ``<id>common:/x.meta</id>``
    is classified as a full path by shape, but the manifest is still declaring
    an identity, so it belongs to the identity channel.
    """
    if tag in XML_PATH_TAGS:
        return CHANNEL_XML_PATH_TAG
    if tag in XML_ID_TAGS:
        return CHANNEL_XML_ID_TAG
    return CHANNEL_XML_OTHER_TAG


def label_candidate(
    *,
    stream_type: str,
    channel: str,
    kind: str,
    mount_xml: bool = False,
) -> tuple[str, str]:
    """Return (source, confidence) for one recovered name.

    Rules are evaluated top to bottom and the first match wins. The table is
    exhaustive over the channels this module emits; an unknown channel falls
    through to the weakest label instead of dropping the name.
    """
    # 1. SGD5 shader symbol: stored inline as name\\0 + 17-byte header + DXBC.
    #    Complete literal with a declaring structure.
    if channel == CHANNEL_SGD5:
        return SOURCE_LITERAL, CONFIDENCE_CONFIRMED

    # 2. scheme:/ path matched by regex anywhere in inflated bytes. The path
    #    template is known; the declaring structure is not.
    if channel == CHANNEL_SCHEME:
        return SOURCE_PATTERN, CONFIDENCE_PROBABLE

    # 3. Null-terminated string (both ends delimited). A full path is a
    #    literal name; a bare token only matches the identifier grammar.
    if channel == CHANNEL_CSTRING:
        if kind == "full_path":
            return SOURCE_LITERAL, CONFIDENCE_CONFIRMED
        return SOURCE_INFERRED, CONFIDENCE_CANDIDATE

    # 4. XML channels. "Declared" means the value sits in a tag or attribute
    #    known to carry paths or identities; otherwise it was matched by shape.
    declared = channel in DECLARED_XML_CHANNELS
    strength = CONFIDENCE_CONFIRMED if declared else CONFIDENCE_PROBABLE

    if stream_type == "xml_chunk":
        # Continuation fragment: the root element is cut off, so it cannot be
        # proven to be a mount manifest even when the tags survive.
        return SOURCE_XML_CHUNK, strength
    if stream_type == "xml" and mount_xml:
        return SOURCE_XML_MOUNT, strength
    if stream_type == "xml":
        # A full XML document that is not a mount manifest: declared values are
        # still literals in a stream, but they mount nothing.
        if declared:
            return SOURCE_LITERAL, CONFIDENCE_CONFIRMED
        return SOURCE_PATTERN, CONFIDENCE_PROBABLE

    return SOURCE_INFERRED, CONFIDENCE_CANDIDATE


def _add_candidate(
    candidates: list[dict[str, str]],
    index: dict[tuple[str, str], int],
    value: str,
    kind: str,
    source: str,
    channel: str,
) -> None:
    key = (kind, value)
    position = index.get(key)
    if position is not None:
        current = candidates[position]["channel"]
        if CHANNEL_RANK.get(channel, 0) > CHANNEL_RANK.get(current, 0):
            candidates[position]["channel"] = channel
        return
    index[key] = len(candidates)
    candidates.append(
        {"name": value, "kind": kind, "source": source, "channel": channel}
    )


def _split_names(candidates: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    """Sorted, deduplicated names, exactly as published in full_paths/identifiers."""
    return (
        sorted({c["name"] for c in candidates if c["kind"] == "full_path"}),
        sorted({c["name"] for c in candidates if c["kind"] == "identifier"}),
    )


def _labeled_block(
    candidates: list[dict[str, str]],
    stream_type: str,
    mount_xml: bool,
    full_paths: list[str],
    identifiers: list[str],
) -> dict[str, list[dict[str, str]]]:
    """Build ``labeled``, index by index parallel to the two published arrays."""
    by_key = {(c["kind"], c["name"]): c for c in candidates}

    def entry(kind: str, name: str) -> dict[str, str]:
        channel = by_key[(kind, name)]["channel"]
        source, confidence = label_candidate(
            stream_type=stream_type,
            channel=channel,
            kind=kind,
            mount_xml=mount_xml,
        )
        return {"name": name, "source": source, "confidence": confidence}

    return {
        "full_paths": [entry("full_path", name) for name in full_paths],
        "identifiers": [entry("identifier", name) for name in identifiers],
    }


def _public_candidates(candidates: list[dict[str, str]]) -> list[dict[str, str]]:
    """Strip the internal channel; the published candidate shape is unchanged."""
    return [
        {"name": c["name"], "kind": c["kind"], "source": c["source"]}
        for c in candidates
    ]


def _classify_xml_value(value: str, from_tag: str | None = None) -> str | None:
    s = value.strip()
    if not s or len(s) < 3 or len(s) > 260:
        return None
    if any(ch in s for ch in (" ", "\t", "\r", "\n")):
        return None
    if s.startswith(("http://", "https://")):
        return None

    if VAR_PATH_RE.match(s) or SCHEME_PATH_RE.match(s):
        return "full_path"
    if "/" in s and re.match(r"^[A-Za-z0-9_.$:\-]+(?:/[A-Za-z0-9_.\-]+)+$", s):
        if EXT_SUFFIX_RE.search(s) or from_tag in ("filename", "loadPath", "exportPath", "datFile"):
            return "full_path"
        segs = [seg for seg in s.split("/") if seg]
        if len(segs) >= 2 and any(len(seg) >= 3 for seg in segs):
            return "full_path"
    if EXT_SUFFIX_RE.search(s) and re.match(r"^[A-Za-z0-9_$/\\\-]+\.[A-Za-z0-9]+$", s):
        stem = s.rsplit(".", 1)[0].split("/")[-1]
        if len(stem) >= 2 and sum(c.isalpha() for c in stem) >= 2:
            return "full_path"

    if from_tag in XML_ID_TAGS and SIMPLE_ID_RE.match(s):
        if s.lower() in XML_GENERIC_STOPWORDS:
            return None
        # Reject pure version/float-like tokens such as 1.0 or v1.2
        if re.match(r"^[0-9.]+$", s):
            return None
        return "identifier"
    return None


def extract_from_xml(out: bytes, source: str = "xml") -> list[dict[str, str]]:
    """Extract deduplicated full paths and identifiers from inflated XML or XML chunks."""
    txt = out.decode("utf-8-sig", errors="replace")
    candidates: list[dict[str, str]] = []
    index: dict[tuple[str, str], int] = {}

    # Pass 1: structured XML tags known to carry paths or resource identifiers
    for tag, val in XML_TAG_VAL_RE.findall(txt):
        kind = _classify_xml_value(val, from_tag=tag)
        if kind is not None:
            _add_candidate(
                candidates,
                index,
                val.strip(),
                kind,
                source,
                _xml_tag_channel(tag),
            )

    # Pass 2: path/file XML attributes (e.g. xi:include href="...meta")
    for val in XML_ATTR_VAL_RE.findall(txt):
        kind = _classify_xml_value(val, from_tag="filename")
        if kind is not None:
            _add_candidate(
                candidates, index, val.strip(), kind, source, CHANNEL_XML_ATTR
            )

    # Pass 3: any text node containing a path or target extension
    for m in XML_TEXT_RE.finditer(txt):
        val = m.group(1).strip()
        if "/" in val or EXT_SUFFIX_RE.search(val) or val.startswith("$(") or ":/" in val:
            kind = _classify_xml_value(val, from_tag=None)
            if kind is not None:
                _add_candidate(
                    candidates, index, val, kind, source, CHANNEL_XML_TEXT
                )

    return candidates


def classify_binary_string(s: str) -> str | None:
    """Classify a null-terminated binary string into full_path, identifier, or None."""
    if s in BINARY_TAG_STOPWORDS or len(s) < 5 or len(s) > 180:
        return None
    if any(ch in s for ch in (" ", "\t", "\r", "\n", "?", "!", ",")):
        return None
    if s.startswith(("http://", "https://")):
        return None

    if VAR_PATH_RE.match(s) or SCHEME_PATH_RE.match(s):
        return "full_path"

    if "/" in s and re.match(r"^[A-Za-z0-9_.$:\-]+(?:/[A-Za-z0-9_.\-]+)+$", s):
        segs = [seg for seg in s.split("/") if seg]
        if len(segs) >= 2 and all(len(seg) >= 2 for seg in segs) and ("_" in s or EXT_SUFFIX_RE.search(s)):
            return "full_path"

    if EXT_SUFFIX_RE.search(s) and re.match(r"^[A-Za-z0-9_$/\\\-]+\.[A-Za-z0-9]+$", s):
        stem = s.rsplit(".", 1)[0].split("/")[-1]
        if len(stem) >= 3 and sum(c.isalpha() for c in stem) >= 2:
            return "full_path"

    if UNDERSCORE_ID_RE.match(s):
        parts = s.split("_")
        if len(s) >= 8:
            long_parts = sum(len(pt) >= 3 for pt in parts)
            camel_tail = len(parts[-1]) >= 8 and any(c.islower() for c in parts[-1]) and any(c.isupper() for c in parts[-1])
            if (long_parts >= 2 or camel_tail) and not re.match(r"^[a-z]{1,2}_[A-Za-z0-9]{1,2}_[A-Za-z0-9]{1,2}$", s):
                return "identifier"

    return None


def extract_from_container(out: bytes, source: str) -> list[dict[str, str]]:
    """Extract clean paths/identifiers from PSIN, 0DRP, rsc50, or raw binary payloads."""
    candidates: list[dict[str, str]] = []
    index: dict[tuple[str, str], int] = {}

    for m in CLEAN_SCHEME_RE.finditer(out):
        s = m.group(0).decode("ascii", errors="ignore")
        if len(s) >= 5:
            _add_candidate(candidates, index, s, "full_path", source, CHANNEL_SCHEME)

    for m in CSTR_RE.finditer(out):
        s = m.group(1).decode("ascii", errors="ignore")
        kind = classify_binary_string(s)
        if kind is not None:
            _add_candidate(candidates, index, s, kind, source, CHANNEL_CSTRING)

    return candidates


def _is_xml_continuation(out: bytes) -> bool:
    sample = out[:2048]
    if b"</" not in sample:
        return False
    if not re.search(rb"</[A-Za-z0-9_]+>", sample):
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _classify_zlib_stream(out: bytes) -> str:
    head = out[:64]
    if head.startswith(b"\xef\xbb\xbf<?xml") or head.startswith(b"<?xml"):
        return "xml"
    if head.startswith(b"PSIN"):
        return "PSIN"
    if b"0DRP" in head:
        return "0DRP"
    if len(head) >= 12 and head[:8] == b"\x00" * 8 and head[11] == 0x50:
        return "rsc50"
    if _is_xml_continuation(out):
        return "xml_chunk"
    return "raw"


def _inflate_zlib_at(data: bytes, mv: memoryview, idx: int) -> tuple[bytes, int] | None:
    n = len(data)
    end_slice = min(n, idx + MAX_ZLIB_WINDOW)
    try:
        dc = zlib.decompressobj()
        out = dc.decompress(mv[idx:end_slice])
        if not dc.eof and end_slice < n:
            dc = zlib.decompressobj()
            out = dc.decompress(mv[idx:])
            end_slice = n
        if dc.eof and out:
            comp_bytes = (end_slice - idx) - len(dc.unused_data)
            return out, comp_bytes
    except zlib.error:
        return None
    return None


def _scan_sgd5_entries(data: bytes, file_name: str) -> list[dict[str, Any]]:
    """Extract shader symbol entries and raw-deflate DXBC sizes from SGD5 shader tables."""
    entries: list[dict[str, Any]] = []
    n = len(data)
    for m in SGD5_SYM_RE.finditer(data):
        sym = m.group(1).decode("ascii", errors="replace")
        hdr_off = m.end()
        if hdr_off + 17 > n:
            continue
        _kind = data[hdr_off]
        stored, _shader_id, stored2, raw_size = struct.unpack_from("<4I", data, hdr_off + 1)
        if stored != stored2 or not (16 < stored < 64 * 1024 * 1024) or raw_size == 0:
            continue
        payload_off = hdr_off + 17
        stream_type = "sgd5_shader_truncated"
        inflated_bytes: int | None = None
        if payload_off + stored <= n:
            try:
                out = zlib.decompressobj(-15).decompress(
                    data[payload_off : payload_off + stored], raw_size + 1
                )
                if len(out) == raw_size and out[:4] == b"DXBC":
                    stream_type = "sgd5_shader_dxbc"
                    inflated_bytes = raw_size
            except zlib.error:
                pass

        candidates = [
            {
                "name": sym,
                "kind": "identifier",
                "source": "sgd5",
                "channel": CHANNEL_SGD5,
            }
        ]
        full_paths, identifiers = _split_names(candidates)
        entries.append(
            {
                "file": file_name,
                "offset": m.start(),
                "offset_hex": f"0x{m.start():x}",
                "compressed_bytes": stored,
                "inflated_bytes": inflated_bytes,
                "stream_type": stream_type,
                "status": "named",
                "full_paths": full_paths,
                "identifiers": identifiers,
                "labeled": _labeled_block(
                    candidates, stream_type, False, full_paths, identifiers
                ),
                "candidates": _public_candidates(candidates),
            }
        )
    return entries


def recover_file(path: Path) -> list[dict[str, Any]]:
    """Inflate streams in a single .bin or .rpf file and recover resource names."""
    data = path.read_bytes()
    mv = memoryview(data)
    n = len(data)
    streams: list[dict[str, Any]] = []

    pos = 0
    while pos < n:
        idx = data.find(b"\x78\xda", pos)
        if idx == -1:
            break
        res = _inflate_zlib_at(data, mv, idx)
        if res is not None:
            out, comp_bytes = res
            stype = _classify_zlib_stream(out)
            mount_xml = False
            if stype in ("xml", "xml_chunk"):
                candidates = extract_from_xml(out, source="xml")
                if stype == "xml":
                    mount_xml = is_mount_xml(
                        out.decode("utf-8-sig", errors="replace")
                    )
            elif stype == "PSIN":
                candidates = extract_from_container(out, source="psin")
            elif stype == "0DRP":
                candidates = extract_from_container(out, source="0drp")
            elif stype == "rsc50":
                candidates = extract_from_container(out, source="rsc50")
            else:
                candidates = extract_from_container(out, source="raw_stream")

            full_paths, identifiers = _split_names(candidates)
            streams.append(
                {
                    "file": path.name,
                    "offset": idx,
                    "offset_hex": f"0x{idx:x}",
                    "compressed_bytes": comp_bytes,
                    "inflated_bytes": len(out),
                    "stream_type": stype,
                    "status": "named" if candidates else "unnamed",
                    "full_paths": full_paths,
                    "identifiers": identifiers,
                    "labeled": _labeled_block(
                        candidates, stype, mount_xml, full_paths, identifiers
                    ),
                    "candidates": _public_candidates(candidates),
                }
            )
            pos = idx + comp_bytes
            continue
        pos = idx + 1

    # Also extract SGD5 shader symbol entries (raw deflate DXBC following symbol\0 + 17B header)
    if b"SGD5" in data or b"_Wrapped" in data:
        streams.extend(_scan_sgd5_entries(data, path.name))

    streams.sort(key=lambda s: s["offset"])
    return streams


def build_summary(streams: list[dict[str, Any]], files_scanned: int) -> dict[str, Any]:
    total = len(streams)
    named = sum(1 for s in streams if s["status"] == "named")
    unnamed = total - named
    by_type: dict[str, dict[str, Any]] = {}
    source_hits: Counter[str] = Counter()
    unique_paths: set[str] = set()
    unique_ids: set[str] = set()
    target_ext_hits: Counter[str] = Counter()
    labeled_total = 0
    by_confidence: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    confidence_by_type: dict[str, Counter[str]] = {}

    for s in streams:
        st = s["stream_type"]
        bucket = by_type.setdefault(st, {"total": 0, "named": 0, "unnamed": 0})
        bucket["total"] += 1
        if s["status"] == "named":
            bucket["named"] += 1
        else:
            bucket["unnamed"] += 1
        unique_paths.update(s["full_paths"])
        unique_ids.update(s["identifiers"])
        for c in s["candidates"]:
            source_hits[c["source"]] += 1
            m = TARGET_EXT_RE.search(c["name"])
            if m:
                target_ext_hits[m.group(0).lower()] += 1
        # Label counts are name mentions (one per stream entry), not unique
        # strings: they describe the same mention stream as candidates[].
        type_counter = confidence_by_type.setdefault(st, Counter())
        for entry in s["labeled"]["full_paths"] + s["labeled"]["identifiers"]:
            labeled_total += 1
            by_confidence[entry["confidence"]] += 1
            by_source[entry["source"]] += 1
            type_counter[entry["confidence"]] += 1

    for bucket in by_type.values():
        t = bucket["total"]
        bucket["coverage_pct"] = round((bucket["named"] / t) * 100.0, 2) if t else 0.0

    return {
        "files_scanned": files_scanned,
        "total_streams": total,
        "named_streams": named,
        "unnamed_streams": unnamed,
        "coverage_pct": round((named / total) * 100.0, 2) if total else 0.0,
        "unique_full_paths": len(unique_paths),
        "unique_identifiers": len(unique_ids),
        "by_stream_type": by_type,
        "candidate_mentions_by_source": dict(source_hits),
        "target_extension_mentions": dict(sorted(target_ext_hits.items())),
        "labeled": {
            "total_names": labeled_total,
            "by_confidence": {conf: by_confidence.get(conf, 0) for conf in CONFIDENCES},
            "by_source": {src: by_source.get(src, 0) for src in SOURCES},
            "by_stream_type": {
                st: {
                    "total": sum(counter.values()),
                    **{conf: counter.get(conf, 0) for conf in CONFIDENCES},
                }
                for st, counter in sorted(confidence_by_type.items())
            },
        },
    }


def validate_recovered_names(
    streams: list[dict[str, Any]], base_dir: Path, min_checks: int = 3
) -> dict[str, Any]:
    """Re-inflate streams from disk and verify recovered names exist inside the payload."""
    # Prefer picking at least one sample from each distinct source if available
    selected: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for preferred_src in ("xml", "psin", "0drp", "sgd5", "rsc50", "raw_stream"):
        for s in streams:
            if s["status"] != "named" or not s["candidates"]:
                continue
            cand = s["candidates"][0]
            if cand["source"] == preferred_src and preferred_src not in seen_sources:
                selected.append(s)
                seen_sources.add(preferred_src)
                break

    for s in streams:
        if len(selected) >= max(min_checks, len(seen_sources)):
            break
        if s["status"] == "named" and s not in selected:
            selected.append(s)

    checks: list[dict[str, Any]] = []
    cache: dict[str, bytes] = {}
    for s in selected:
        fpath = base_dir / s["file"] if base_dir.is_dir() else base_dir
        if s["file"] not in cache:
            cache[s["file"]] = fpath.read_bytes()
        data = cache[s["file"]]
        off = s["offset"]
        cand = s["candidates"][0]
        name = cand["name"]
        needle = name.encode("utf-8")

        if s["stream_type"].startswith("sgd5_shader"):
            # Verify symbol exists in file at offset and DXBC inflates when complete
            sym_end = off + len(needle) + 1
            sym_match = data[off : off + len(needle)] == needle and data[sym_end - 1 : sym_end] == b"\x00"
            dxbc_ok = False
            if s["stream_type"] == "sgd5_shader_dxbc":
                hdr_off = sym_end
                stored, _, _, raw_size = struct.unpack_from("<4I", data, hdr_off + 1)
                payload_off = hdr_off + 17
                out = zlib.decompressobj(-15).decompress(
                    data[payload_off : payload_off + stored], raw_size + 1
                )
                dxbc_ok = len(out) == raw_size and out[:4] == b"DXBC"
            verified = sym_match and (dxbc_ok or s["stream_type"] == "sgd5_shader_truncated")
            checks.append(
                {
                    "file": s["file"],
                    "offset_hex": s["offset_hex"],
                    "stream_type": s["stream_type"],
                    "source": cand["source"],
                    "name": name,
                    "verified_in_payload": verified,
                    "payload_offset": 0 if sym_match else -1,
                }
            )
        else:
            mv = memoryview(data)
            res = _inflate_zlib_at(data, mv, off)
            if res is None:
                checks.append(
                    {
                        "file": s["file"],
                        "offset_hex": s["offset_hex"],
                        "stream_type": s["stream_type"],
                        "source": cand["source"],
                        "name": name,
                        "verified_in_payload": False,
                        "payload_offset": -1,
                    }
                )
            else:
                out, _ = res
                pos_in_out = out.find(needle)
                checks.append(
                    {
                        "file": s["file"],
                        "offset_hex": s["offset_hex"],
                        "stream_type": s["stream_type"],
                        "source": cand["source"],
                        "name": name,
                        "verified_in_payload": pos_in_out != -1,
                        "payload_offset": pos_in_out,
                    }
                )

    all_ok = len(checks) >= min_checks and all(c["verified_in_payload"] for c in checks)
    return {
        "checked_count": len(checks),
        "all_verified": all_ok,
        "checks": checks,
    }


def recover_path(target: Path, limit_files: int | None = None, validate: bool = False) -> dict[str, Any]:
    if target.is_file():
        files = [target]
    elif target.is_dir():
        files = sorted(
            p for p in target.iterdir() if p.is_file() and p.suffix.lower() in (".bin", ".rpf")
        )
        if limit_files is not None:
            files = files[:limit_files]
    else:
        raise FileNotFoundError(f"Input path not found: {target}")

    all_streams: list[dict[str, Any]] = []
    for fpath in files:
        all_streams.extend(recover_file(fpath))

    summary = build_summary(all_streams, len(files))
    report: dict[str, Any] = {
        "tool": "name_recover.py",
        "target": str(target),
        "summary": summary,
        "streams": all_streams,
    }
    if validate:
        report["validation"] = validate_recovered_names(all_streams, target)
    return report


def format_human(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        f"Target: {report['target']} ({s['files_scanned']} files)",
        f"Total streams: {s['total_streams']} | named: {s['named_streams']} ({s['coverage_pct']}%) | unnamed (sin nombre): {s['unnamed_streams']}",
        f"Unique full_paths: {s['unique_full_paths']} | Unique identifiers: {s['unique_identifiers']}",
        "",
        "Coverage by stream_type:",
    ]
    for st, info in sorted(s["by_stream_type"].items()):
        lines.append(
            f"  {st:<22} total={info['total']:>5} named={info['named']:>5} unnamed={info['unnamed']:>5} ({info['coverage_pct']:>6.2f}%)"
        )
    lines.append("")
    lines.append(f"Candidate mentions by source: {s['candidate_mentions_by_source']}")
    lines.append(f"Target extension mentions: {s['target_extension_mentions']}")
    lab = s["labeled"]
    conf = lab["by_confidence"]
    lines.append(
        "Labeled name mentions: total={} confirmed={} probable={} candidate={}".format(
            lab["total_names"],
            conf["confirmed"],
            conf["probable"],
            conf["candidate"],
        )
    )
    if "validation" in report:
        val = report["validation"]
        lines.append("")
        lines.append(f"Payload validation (checked={val['checked_count']}, all_verified={val['all_verified']}):")
        for c in val["checks"]:
            lines.append(
                f"  [{c['source']}] {c['file']} @{c['offset_hex']} ({c['stream_type']}) -> {c['name']!r} verified={c['verified_in_payload']} payload_off={c['payload_offset']}"
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inflate RPF9 streams and recover resource names with provenance."
    )
    parser.add_argument("target", type=Path, help="Path to .bin/.rpf file or directory of samples")
    parser.add_argument("--out", "-o", type=Path, default=None, help="Write index.json to this path")
    parser.add_argument("--json", action="store_true", help="Emit JSON output to stdout")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Re-inflate >=3 recovered entries and verify names exist in payload bytes",
    )
    parser.add_argument("--limit-files", type=int, default=None, help="Limit number of files scanned")
    args = parser.parse_args(argv)

    try:
        report = recover_path(args.target, limit_files=args.limit_files, validate=args.validate)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        tmp = args.out.with_suffix(args.out.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        os.replace(tmp, args.out)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(format_human(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
