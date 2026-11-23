#!/usr/bin/env python3
"""Lista funciones del binario Go `agy` usando el pclntab embebido.

El binario esta stripped, pero Go conserva el nombre de cada funcion en el
pclntab. Este script localiza el pclntab, recorre la functab y permite buscar
funciones por regex, imprimiendo su direccion virtual y su tamano, para luego
desensamblar un rango con `objdump --start-address/--stop-address`.

Uso:
    go_symbols.py --grep UserAgent
    go_symbols.py --grep getUserAgentName --json

Supone Go >= 1.20 (magic 0xFFFFFFF1). Verificado sobre agy 1.5.14.
"""

from __future__ import annotations

import argparse
import json
import mmap
import re
import struct
import sys

DEFAULT_BIN = "/home/sistver/re/agy.bin"
MAGIC = b"\xf1\xff\xff\xff\x00\x00"


def find_pclntab(mm: mmap.mmap) -> int:
    pos = 0
    while True:
        idx = mm.find(MAGIC, pos)
        if idx < 0:
            raise SystemExit("pclntab no encontrado")
        # minLC/ptrsize validos y nfunc razonable
        min_lc, ptr_size = mm[idx + 6], mm[idx + 7]
        if min_lc in (1, 2, 4) and ptr_size in (4, 8):
            nfunc = struct.unpack_from("<Q", mm, idx + 8)[0]
            if 100 < nfunc < 5_000_000:
                return idx
        pos = idx + 1


class Pclntab:
    TEXT_BASE = 0x72BF080  # runtime.text; el header pclntab trae textStart=0 en este PIE

    def __init__(self, mm: mmap.mmap, base: int) -> None:
        self.mm = mm
        self.base = base
        (self.nfunc, self.nfiles, self.text_start, self.funcname_off,
         self.cu_off, self.filetab_off, self.pctab_off, self.pcln_off) = struct.unpack_from(
            "<8Q", mm, base + 8)
        self.ptr_size = mm[base + 7]

    def name_at(self, off: int) -> str:
        start = self.base + self.funcname_off + off
        end = self.mm.find(b"\x00", start)
        return self.mm[start:end].decode("utf-8", "replace")

    def functions(self):
        # functab: nfunc entradas de (entryoff uint32, funcoff uint32)
        tab = self.base + self.pcln_off
        for i in range(self.nfunc):
            entry_off, func_off = struct.unpack_from("<II", self.mm, tab + i * 8)
            name_off = struct.unpack_from("<i", self.mm, self.base + self.pcln_off + func_off + 4)[0]
            yield (self.text_start or self.TEXT_BASE) + entry_off, self.name_at(name_off)

    def entries(self):
        rows = list(self.functions())
        rows.sort()
        for i, (addr, name) in enumerate(rows):
            end = rows[i + 1][0] if i + 1 < len(rows) else addr
            yield addr, end, name


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", default=DEFAULT_BIN)
    p.add_argument("--grep", default=".")
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    rx = re.compile(args.grep)
    out = []
    with open(args.binary, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        tab = Pclntab(mm, find_pclntab(mm))
        for addr, end, name in tab.entries():
            if rx.search(name):
                out.append({"addr": addr, "end": end, "size": end - addr, "name": name})
    if args.json:
        json.dump(out, sys.stdout, indent=2)
        print()
    else:
        for row in out:
            print(f"0x{row['addr']:x}\t0x{row['end']:x}\t{row['size']:6d}\t{row['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
