#!/usr/bin/env python3
"""Read-only nested-RPF9 discovery check used by docs/COMPARATIVA.md (T-RPF9-COMPARA).

For every window given on the command line it runs two scans with the validation
rule of docs/NESTED.md:11-14 (magic in both byte orders, +0x18 == 0x47a00,
+0x1c in {0x150,0x154,0x158}, entry count non-zero, subtable below toc_end below
64 MiB, table width 16):

  * a 4 KiB-stepped scan, which is what rpf9-extract/src/container.rs:74 and
    zeozeozeo/rpf9 src/archive.rs:78 do;
  * a byte-by-byte scan, which is what tools/rpf9.py does.

Usage: python3 nested_scan.py <file> [<file> ...]
"""

import struct
import sys
from pathlib import Path

SECTOR = 0x1000
LIMIT = 64 * 1024 * 1024
VALID_1C = (0x150, 0x154, 0x158)


def header_at(data, off):
    """Return the 16 header words if off carries a valid RPF9 header, else None."""
    if off + 64 > len(data):
        return None
    if data[off:off + 4] not in (b"9FPR", b"RPF9"):
        return None
    w = struct.unpack_from("<16I", data, off)
    if w[6] != 0x47A00 or w[7] not in VALID_1C or w[9] == 0:
        return None
    if not (w[2] < w[1] < LIMIT) or w[12] != 16 or w[13:] != (0, 0, 0):
        return None
    return w


def scan_stepped(data):
    return [off for off in range(0, len(data) - 63, SECTOR) if header_at(data, off)]


def scan_bytes(data):
    hits = []
    for off in range(0, len(data) - 63):
        if data[off:off + 2] in (b"9F", b"RP") and header_at(data, off):
            hits.append(off)
    return hits


def describe(data, off):
    w = header_at(data, off)
    archive_id = (w[5] << 32) | w[4]
    return (f"0x{off:08x}  w04=0x{w[1]:05x} w08=0x{w[2]:05x} w0c=0x{w[3]:05x} "
            f"id=0x{archive_id:016x} w24={w[9]} w20_hi={w[8] >> 16} w2c={w[11] & 0xFF}")


def main():
    for arg in sys.argv[1:]:
        path = Path(arg)
        data = path.read_bytes()
        stepped = scan_stepped(data)
        bytewise = scan_bytes(data)
        extra = [off for off in bytewise if off not in stepped]
        print(f"### {path.name}  {len(data):,} B")
        print(f"  4 KiB-stepped scan : {len(stepped)} header(s)")
        for off in stepped:
            print(f"      {describe(data, off)}")
        print(f"  byte scan          : {len(bytewise)} header(s)")
        for off in bytewise:
            mark = "  <-- not 4 KiB-aligned" if off % SECTOR else ""
            print(f"      {describe(data, off)}{mark}")
        print(f"  found by byte scan only: {[hex(off) for off in extra]}")
        print()

    print("Stepped offsets follow rpf9-extract/src/container.rs:74 and")
    print("zeozeozeo/rpf9 src/archive.rs:78 (both step 0x1000 from the start of the")
    print("region). The byte scan follows tools/rpf9.py (_scan_nested_rpf9 starts at")
    print("HEADER_SIZE and tries every offset).")


if __name__ == "__main__":
    main()
