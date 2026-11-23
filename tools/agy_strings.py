#!/usr/bin/env python3
"""Extractor de cadenas y contextos sobre el binario del CLI `agy`.

Sin dependencias externas: mmap + busqueda de bytes. Pensado para dejar
transcripciones reproducibles en raw/deteccion/.

Uso:
    agy_strings.py find "aidev_client" --radius 300
    agy_strings.py find "os_type=" --radius 200 --limit 50
    agy_strings.py strings --min 6 --grep "antigravity" --out raw/deteccion/x.txt
    agy_strings.py window --offset 105805538 --radius 400

Todas las coincidencias se numeran y se imprimen con su offset absoluto, de
modo que cualquier cita del documento se puede reproducir con `window`.
"""

from __future__ import annotations

import argparse
import mmap
import re
import sys
from pathlib import Path

DEFAULT_BIN = "/home/sistver/re/agy.bin"

PRINTABLE = bytes(range(0x20, 0x7F))


def read_window(mm: mmap.mmap, offset: int, radius: int) -> str:
    start = max(0, offset - radius)
    end = min(len(mm), offset + radius)
    chunk = mm[start:end]
    text = "".join(chr(b) if b in PRINTABLE or b in (0x09, 0x0A, 0x0D) else "." for b in chunk)
    return text


def iter_matches(mm: mmap.mmap, needle: bytes, overlap: int = 0):
    pos = 0
    while True:
        idx = mm.find(needle, pos)
        if idx < 0:
            return
        yield idx
        pos = idx + max(1, len(needle) - overlap)


def cmd_find(args: argparse.Namespace) -> int:
    needle = args.pattern.encode("utf-8")
    with open(args.binary, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        for i, off in enumerate(iter_matches(mm, needle, args.overlap)):
            if args.limit and i >= args.limit:
                print(f"[... limit={args.limit} alcanzado]", file=sys.stderr)
                break
            print(f"=== match {i} offset={off} (0x{off:x}) pattern={args.pattern!r}")
            print(read_window(mm, off, args.radius))
            print()
    return 0


def cmd_window(args: argparse.Namespace) -> int:
    with open(args.binary, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        print(read_window(mm, args.offset, args.radius))
    return 0


def cmd_strings(args: argparse.Namespace) -> int:
    pattern = re.compile(rb"[\x20-\x7e]{%d,}" % args.min)
    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    try:
        with open(args.binary, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            for match in pattern.finditer(mm):
                text = match.group().decode("ascii")
                if args.grep and not re.search(args.grep, text):
                    continue
                out.write(f"{match.start()}\t{text}\n")
    finally:
        if args.out:
            out.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", default=DEFAULT_BIN)
    sub = p.add_subparsers(dest="command", required=True)

    pf = sub.add_parser("find", help="buscar bytes y volcar ventanas de contexto")
    pf.add_argument("pattern")
    pf.add_argument("--radius", type=int, default=300)
    pf.add_argument("--limit", type=int, default=0)
    pf.add_argument("--overlap", type=int, default=0)
    pf.set_defaults(func=cmd_find)

    pw = sub.add_parser("window", help="volcar una ventana por offset")
    pw.add_argument("--offset", type=lambda s: int(s, 0), required=True)
    pw.add_argument("--radius", type=int, default=400)
    pw.set_defaults(func=cmd_window)

    ps = sub.add_parser("strings", help="volcar cadenas ASCII (offset<TAB>texto)")
    ps.add_argument("--min", type=int, default=6)
    ps.add_argument("--grep", default=None)
    ps.add_argument("--out", default=None)
    ps.set_defaults(func=cmd_strings)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
