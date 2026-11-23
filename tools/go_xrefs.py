#!/usr/bin/env python3
"""Busca referencias RIP-relativas (LEA) a una dirección de .rodata en .text.

El binario `agy` esta stripped y sin simbolos, pero las cadenas se referencian
con `lea disp32(%rip), reg` (7 bytes: 48 8d <modrm> <disp32>). Este script
recorre un rango de .text, decodifica esos LEA y reporta los que apuntan a la
direccion pedida. Sirve para localizar la funcion que usa una cadena.

Uso:
    go_xrefs.py --target 0x64e76e2
    go_xrefs.py --target 0x64468d7 --start 0x72bf020 --end 0xb713ef0
"""

from __future__ import annotations

import argparse
import mmap
import struct

DEFAULT_BIN = "/home/sistver/re/agy.bin"
DEFAULT_START = 0x72BF080  # runtime.text (primer funcion Go; 0x20 de stub rt0 + 0x60 de alineacion)
DEFAULT_END = 0xB713EF0    # fin de .text

# 48 8d /r  con ModRM mod=00 rm=101 => RIP+disp32
MODRM_RIP = {0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D}


def scan(mm: mmap.mmap, start: int, end: int):
    pos = start
    while True:
        idx = mm.find(b"\x8d", pos, end)
        if idx < 0:
            return
        # REX.W / REX.WR / ... (0x48..0x4f) inmediatamente antes de 0x8d
        if idx - 1 >= start and 0x48 <= mm[idx - 1] <= 0x4F and idx + 6 <= end:
            modrm = mm[idx + 1]
            if modrm in MODRM_RIP:
                disp = struct.unpack_from("<i", mm, idx + 2)[0]
                target = idx + 6 + disp
                yield idx - 1, target, modrm
        pos = idx + 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", default=DEFAULT_BIN)
    p.add_argument("--target", type=lambda s: int(s, 0), required=True)
    p.add_argument("--start", type=lambda s: int(s, 0), default=DEFAULT_START)
    p.add_argument("--end", type=lambda s: int(s, 0), default=DEFAULT_END)
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    with open(args.binary, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        hits = [(a, t, m) for a, t, m in scan(mm, args.start, args.end) if t == args.target]
    for a, t, m in hits[: args.limit or None]:
        print(f"0x{a:x}\tmodrm=0x{m:02x}\ttarget=0x{t:x}")
    print(f"total={len(hits)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
