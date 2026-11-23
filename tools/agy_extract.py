#!/usr/bin/env python3
"""Extract reproducible evidence from the Antigravity CLI (`agy`) Go binary.

Used by `docs/DETECCION.md` (task T-RE-DETECT). It does not execute the binary:
everything here is read-only static extraction.

Examples
--------
    python3 tools/agy_extract.py /home/sistver/re/agy.bin --ua
    python3 tools/agy_extract.py /home/sistver/re/agy.bin --exact aidev_client
    python3 tools/agy_extract.py /home/sistver/re/agy.bin --strings 'x-goog-[a-z-]+'
    python3 tools/agy_extract.py /home/sistver/re/agy.bin --function userAgent

The Go function finder parses the pclntab and the ELF section table; it prints
the function's virtual address so `objdump -d --start-address=...` can be run
against the same offsets. This is how the UA format string, the `cl` literal and
the `Atoi` call were pinned.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from pathlib import Path
from typing import Iterable, Iterator

PRINTABLE = re.compile(rb"[\x20-\x7e]{4,}")
DIGITS10 = re.compile(r"^1\d{9}$")


class MissingEvidence(RuntimeError):
    """Raised when a curated extraction cannot find its anchor."""


def find_all(data: bytes, needle: bytes) -> list[int]:
    """Return every non-overlapping offset of *needle* in *data*."""
    out: list[int] = []
    start = 0
    while True:
        idx = data.find(needle, start)
        if idx < 0:
            return out
        out.append(idx)
        start = idx + len(needle)


def iter_strings(data: bytes, min_len: int = 4) -> Iterator[tuple[int, str]]:
    """Yield (offset, printable string) runs of at least *min_len* bytes."""
    pattern = PRINTABLE if min_len == 4 else re.compile(rb"[\x20-\x7e]{%d,}" % min_len)
    for match in pattern.finditer(data):
        yield match.start(), match.group().decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# ELF / pclntab helpers
# ---------------------------------------------------------------------------


def elf_section(data: bytes, wanted: str) -> tuple[int, int, int]:
    """Return (address, file_offset, size) for an ELF64 section name."""
    if data[:4] != b"\x7fELF" or data[4] != 2:
        raise MissingEvidence("not an ELF64 file")
    (e_shoff,) = struct.unpack_from("<Q", data, 0x28)
    e_shentsize = struct.unpack_from("<H", data, 0x3A)[0]
    e_shnum = struct.unpack_from("<H", data, 0x3C)[0]
    e_shstrndx = struct.unpack_from("<H", data, 0x3E)[0]

    def section(index: int) -> tuple[int, int, int, int, int]:
        off = e_shoff + index * e_shentsize
        sh_name, sh_type = struct.unpack_from("<II", data, off)
        sh_addr, sh_offset, sh_size = struct.unpack_from("<QQQ", data, off + 16)
        return sh_name, sh_type, sh_addr, sh_offset, sh_size

    _, _, _, str_off, _ = section(e_shstrndx)
    for index in range(e_shnum):
        name_off, _, addr, offset, size = section(index)
        end = data.index(b"\x00", str_off + name_off)
        name = data[str_off + name_off:end].decode("utf-8", "replace")
        if name == wanted:
            return addr, offset, size
    raise MissingEvidence(f"section {wanted!r} not found")


def parse_pclntab(data: bytes) -> tuple[int, int, int, int]:
    """Return (base, nfunc, funcname_offset, functab_offset) for a Go pclntab.

    Supports the Go 1.20+ magic (`0xfffffff1`). The functab entries point to a
    `_func` record at `functab + funcoff`, which is the layout measured on this
    Go 1.28 binary.
    """
    base = data.find(b"\xf1\xff\xff\xff")
    if base < 0:
        raise MissingEvidence("Go 1.20+ pclntab magic not found")
    nfunc, _nfiles, _textstart = struct.unpack_from("<QQQ", data, base + 8)
    funcname, _cu, _filetab, _pctab, pcln = struct.unpack_from("<QQQQQ", data, base + 32)
    return base, nfunc, funcname, base + pcln


def iter_functions(data: bytes) -> Iterator[tuple[str, int, int]]:
    """Yield (name, entry_offset, virtual_address) for every Go function."""
    text_addr, _text_off, _text_size = elf_section(data, ".text")
    base, nfunc, funcname_off, functab = parse_pclntab(data)
    for index in range(nfunc):
        entryoff, funcoff = struct.unpack_from("<II", data, functab + index * 8)
        _entry2, nameoff = struct.unpack_from("<Ii", data, functab + funcoff)
        start = base + funcname_off + nameoff
        end = data.index(b"\x00", start)
        yield data[start:end].decode("utf-8", "replace"), entryoff, text_addr + entryoff


# ---------------------------------------------------------------------------
# Curated UA extraction
# ---------------------------------------------------------------------------

UA_LITERALS = {
    "template": b"%s/%s/%s (%s)",
    "aidev_client": b"aidev_client",
    "os_type": b"os_type=%s",
    "arch": b"arch=%s",
    "cl": b"cl=%d",
    "auth_method": b"auth_method=%s",
    "separator": b"; ",
    "datacollection": b"datacollection_opt_in=false",
    "host_path": b"host_path=%s",
    "proxy_client": b"proxy_client=%s",
    "purpose": b"purpose=%s",
}


def extract_ua_facts(path: Path) -> dict:
    """Locate the UA-building literals and the numeric candidate strings.

    The numeric candidates are 10-digit strings (the CLI's `cl` is a 10-digit
    build changelist). Pinning *which* candidate feeds `cl=%d` needs the
    disassembly/relocation step documented in `docs/DETECCION.md`; this function
    only guarantees the raw material and its offsets.
    """
    data = path.read_bytes()
    literals: dict[str, dict] = {}
    for name, needle in UA_LITERALS.items():
        offsets = find_all(data, needle)
        if not offsets and name in {"template", "aidev_client", "os_type", "arch", "cl", "auth_method", "separator"}:
            raise MissingEvidence(f"UA literal {name!r} not found")
        if offsets:
            # `"; "` appears all over the string table; the UA builder's copy is
            # the one referenced from the disassembled `codeassistclient.userAgent`
            # function. Keep every offset instead of pretending the first is it.
            offset = None if name == "separator" else offsets[0]
            literals[name] = {"offset": offset, "offsets": offsets, "text": needle.decode()}

    numeric: list[dict] = []
    for offset, text in iter_strings(data, min_len=10):
        if DIGITS10.match(text):
            after = data[offset + len(text):offset + len(text) + 1]
            if after == b"\x00":
                numeric.append({"offset": offset, "text": text})

    return {
        "literals": literals,
        "numeric_candidates": numeric,
        "template": "antigravity/cli/<version> (<parts joined by '; '>)",
        "parts": [
            "aidev_client",
            "os_type=<runtime GOOS>",
            "arch=<runtime GOARCH>",
            "cl=<10-digit build changelist>",
            "auth_method=<auth method>",
            "optional: datacollection_opt_in=false",
            "optional: host_path=<path>",
            "optional: proxy_client=<name>",
            "optional: purpose=<purpose>",
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--strings", metavar="REGEX", help="print printable strings matching REGEX")
    parser.add_argument("--exact", metavar="TEXT", help="print offsets of an exact byte string")
    parser.add_argument("--function", metavar="NAME", help="find Go functions whose name contains NAME")
    parser.add_argument("--ua", action="store_true", help="curated CLI User-Agent extraction")
    parser.add_argument("--json", action="store_true", help="JSON output where applicable")
    args = parser.parse_args(argv)

    if not args.binary.is_file():
        print(f"error: {args.binary} is not a file", file=sys.stderr)
        return 2
    data = args.binary.read_bytes()

    if args.ua:
        facts = extract_ua_facts(args.binary)
        if args.json:
            print(json.dumps(facts, indent=2, ensure_ascii=False))
        else:
            print(f"binary: {args.binary} ({len(data)} bytes)")
            for name, info in facts["literals"].items():
                if info["offset"] is None:
                    shown = ", ".join(f"{o:#x}" for o in info["offsets"][:8])
                    print(f"{name:16s} @ [{shown}]  {info['text']!r}")
                else:
                    print(f"{name:16s} @ {info['offset']:#x}  {info['text']!r}")
            print("\nnumeric candidates (10 digits, NUL-terminated):")
            for item in facts["numeric_candidates"]:
                print(f"  {item['text']} @ {item['offset']:#x}")
            print(f"\ntemplate: {facts['template']}")
            for part in facts["parts"]:
                print(f"  - {part}")
        return 0

    if args.exact is not None:
        needle = args.exact.encode()
        offsets = find_all(data, needle)
        print(json.dumps({"needle": args.exact, "offsets": offsets, "hex": [hex(o) for o in offsets]}, indent=2))
        return 0 if offsets else 1

    if args.strings:
        regex = re.compile(args.strings)
        hits = []
        for offset, text in iter_strings(data):
            if regex.search(text):
                hits.append({"offset": offset, "hex": hex(offset), "text": text})
        if args.json:
            print(json.dumps(hits, indent=2, ensure_ascii=False))
        else:
            for hit in hits:
                print(f"{hit['hex']:>12}  {hit['text']}")
        return 0

    if args.function:
        matches = []
        for name, entryoff, addr in iter_functions(data):
            if args.function.lower() in name.lower():
                matches.append({"name": name, "entryoff": entryoff, "hex": hex(entryoff), "address": hex(addr)})
        if args.json:
            print(json.dumps(matches, indent=2))
        else:
            for match in matches:
                print(f"{match['address']:>12}  entryoff={match['hex']:<10} {match['name']}")
        return 0 if matches else 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
