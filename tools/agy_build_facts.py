#!/usr/bin/env python3
"""Hechos de build extraidos de /home/sistver/re/agy.bin (agy 1.5.14, ELF Go).

No ejecuta el binario. Lee el ELF, resuelve el CL del build por la cadena de
relacion R_X86_64_RELATIVE que usa `codeassistclient.userAgent`, y localiza las
cadenas del User-Agent, la telemetria y los identificadores del body.

Las direcciones virtuales estan fijadas a ESTE build. El script aborta si el
md5 no coincide, para que nadie confunda la evidencia con otro binario.

Uso:
    agy_build_facts.py [--binary RUTA] [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import re
import struct
import sys
from pathlib import Path

DEFAULT_BIN = "/home/sistver/re/agy.bin"
EXPECTED_MD5 = "485ac1f779f3e0b8d5acc84868c49cdb"

# Direcciones de este build (vaddr == offset en las secciones de solo lectura).
CL_GLOBAL = 0xD82B440       # global string {ptr,len}; ptr se rellena por RELA
CL_LEN_ADDR = 0xD82B448
CL_EXPECTED = "1027820220"
UA_BUILDER = 0x95DE840      # codeassistclient.userAgent
SET_HEADERS = 0x95DF3E0     # (CodeAssistClient).setHeaders
CHANGELOG = 0x6F3991E       # "## 1.5.14"
ANTHROPIC_BETA_VALUE = 0x665CDBF  # "thinking-binding-controls-2026-08-01"
ANTHROPIC_BETA_FUNC = 0x95E1E80   # (*anthropicConverter).ToRequestPayload
BUILDINFO = 0xDBA7760       # .go.buildinfo

UA_LITERALS = [
    (0x64CBBC3, b"antigravity"),
    (0x64B052F, b"os_type=%s"),
    (0x6466A71, b"arch=%s"),
    (0x64E76E2, b"aidev_client"),
    (0x64468D7, b"cl=%d"),
    (0x6518D7D, b"auth_method=%s"),
    (0x6432AD2, b"; "),
    (0x64B0543, b"%s/%s (%s)"),
    (0x6603EBF, b"datacollection_opt_in=false"),
]

BODY_KEYS = [
    b"requestType",
    b"userAgent",
    b"requestId",
    b"root_cascade_id",
    b"last_step_index",
    b"used_non_gemini_model",
    b"MODEL_PLACEHOLDER_M0",
    b"%s/%s/%d/%s",
    b"agent-%s",
]

TELEMETRY = [
    b"https://play.googleapis.com/log",
    b"--disable_telemetry",
    b"datacollection_opt_in=false",
    b"antigravity_ide_installation_id",
    b"clearcut_go_client_telemetry",
    b"clearcut.Client",
]

HEADERS = [
    b"X-Goog-Request-Reason",
    b"Content-Type",
    b"application/json",
    b"User-Agent",
    b"X-Goog-Api-Client",
    b"x-goog-api-client",
    b"Client-Metadata",
]

ENDPOINTS = [
    b"daily-cloudcode-pa.googleapis.com",
    b"cloudcode-pa.googleapis.com",
    b"daily-cloudcode-pa.sandbox.googleapis.com",
    b"preprod-daily-cloudcode-pa.sandbox.googleapis.com",
    b"autopush-cloudcode-pa.sandbox.googleapis.com",
]


class Elf:
    def __init__(self, mm: mmap.mmap) -> None:
        self.mm = mm
        if mm[:4] != b"\x7fELF" or mm[4] != 2:
            raise SystemExit("no es un ELF64")
        self.phoff = struct.unpack_from("<Q", mm, 32)[0]
        self.phentsize = struct.unpack_from("<H", mm, 54)[0]
        self.phnum = struct.unpack_from("<H", mm, 56)[0]
        self.shoff = struct.unpack_from("<Q", mm, 40)[0]
        self.shentsize = struct.unpack_from("<H", mm, 58)[0]
        self.shnum = struct.unpack_from("<H", mm, 60)[0]
        self.loads = []
        for i in range(self.phnum):
            off = self.phoff + i * self.phentsize
            p_type, _flags, p_offset, p_vaddr, _p_paddr, p_filesz, _memsz, _align = struct.unpack_from(
                "<IIQQQQQQ", mm, off)
            if p_type == 1:  # PT_LOAD
                self.loads.append((p_vaddr, p_vaddr + p_filesz, p_offset))

    def off(self, vaddr: int) -> int:
        for start, end, file_off in self.loads:
            if start <= vaddr < end:
                return file_off + (vaddr - start)
        raise KeyError(f"vaddr {vaddr:#x} no mapeada")

    def read(self, vaddr: int, size: int) -> bytes:
        o = self.off(vaddr)
        return self.mm[o:o + size]

    def rela_addend(self, target: int) -> int | None:
        for i in range(self.shnum):
            off = self.shoff + i * self.shentsize
            sh_type = struct.unpack_from("<I", self.mm, off + 4)[0]
            sh_offset = struct.unpack_from("<Q", self.mm, off + 24)[0]
            sh_size = struct.unpack_from("<Q", self.mm, off + 32)[0]
            sh_entsize = struct.unpack_from("<Q", self.mm, off + 56)[0]
            if sh_type != 4 or sh_entsize == 0:  # SHT_RELA
                continue
            for j in range(sh_size // sh_entsize):
                e = sh_offset + j * sh_entsize
                r_offset, r_info, r_addend = struct.unpack_from("<QQq", self.mm, e)
                if r_offset == target:
                    return r_addend
        return None


def find_all(mm: mmap.mmap, needle: bytes, limit: int = 5) -> list[int]:
    out, pos = [], 0
    while len(out) < limit:
        i = mm.find(needle, pos)
        if i < 0:
            break
        out.append(i)
        pos = i + 1
    return out


def cstr(mm: mmap.mmap, off: int, maxlen: int = 64) -> str:
    raw = mm[off:off + maxlen].split(b"\x00")[0]
    return raw.decode("latin1")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--binary", default=DEFAULT_BIN)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    path = Path(args.binary)
    data = path.read_bytes()
    md5 = hashlib.md5(data).hexdigest()
    sha256 = hashlib.sha256(data).hexdigest()
    if md5 != EXPECTED_MD5:
        print(f"ERROR: md5 {md5} != {EXPECTED_MD5}; las direcciones de este script no aplican", file=sys.stderr)
        return 2

    with open(path, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        elf = Elf(mm)
        addend = elf.rela_addend(CL_GLOBAL)
        cl_len = struct.unpack_from("<Q", elf.read(CL_LEN_ADDR, 8))[0]
        cl = elf.read(addend, cl_len).decode("ascii") if addend is not None else None
        changelog_raw = elf.read(CHANGELOG - 400, 900).decode("latin1")
        version_match = re.search(r"##\s+(\d+\.\d+\.\d+)", changelog_raw)
        header_match = re.search(r"#\s+Antigravity CLI Changelog", changelog_raw)
        buildinfo = elf.read(BUILDINFO + 0x20, 96).split(b"\x00")[0].decode("latin1")

        def lea_targets(start: int, end: int) -> list[dict]:
            rows = []
            pos = start
            while True:
                i = mm.find(b"\x8d", pos, end)
                if i < 0:
                    break
                if i - 1 >= start and 0x48 <= mm[i - 1] <= 0x4F:
                    modrm = mm[i + 1]
                    if modrm in (0x05, 0x0D, 0x15, 0x1D, 0x25, 0x2D, 0x35, 0x3D):
                        disp = struct.unpack_from("<i", mm, i + 2)[0]
                        target = i + 6 + disp
                        if 0x6432A80 <= target < 0x72B8360:
                            text = elf.read(target, 48).split(b"\x00")[0].decode("latin1")
                            rows.append({"insn": hex(i - 1), "target": hex(target), "text": text})
                pos = i + 1
            return rows

        facts = {
            "binary": str(path),
            "size": len(data),
            "md5": md5,
            "sha256": sha256,
            "go_buildinfo": buildinfo,
            "changelog_head": header_match.group(0) if header_match else "",
            "changelog_version": version_match.group(1) if version_match else None,
            "cl_relocation": {
                "global": hex(CL_GLOBAL),
                "rela_addend": hex(addend) if addend is not None else None,
                "length": cl_len,
                "value": cl,
                "ok": cl == CL_EXPECTED,
            },
            "ua_builder": hex(UA_BUILDER),
            "set_headers": hex(SET_HEADERS),
            "ua_literals": [],
            "set_headers_literals": lea_targets(SET_HEADERS, SET_HEADERS + 0x3E0),
            "anthropic_beta": {
                "value": elf.read(ANTHROPIC_BETA_VALUE, 36).decode("latin1"),
                "func": hex(ANTHROPIC_BETA_FUNC),
            },
            "body_keys": {},
            "telemetry": {},
            "headers": {},
            "endpoints": {},
        }

        for vaddr, expected in UA_LITERALS:
            got = elf.read(vaddr, len(expected)).decode("latin1")
            facts["ua_literals"].append({"vaddr": hex(vaddr), "expected": expected.decode(), "got": got,
                                         "ok": got == expected.decode()})

        for needle in BODY_KEYS:
            facts["body_keys"][needle.decode()] = [hex(h) for h in find_all(mm, needle)]
        for needle in TELEMETRY:
            facts["telemetry"][needle.decode()] = [hex(h) for h in find_all(mm, needle)]
        for needle in HEADERS:
            facts["headers"][needle.decode()] = [hex(h) for h in find_all(mm, needle)]
        for needle in ENDPOINTS:
            facts["endpoints"][needle.decode()] = [hex(h) for h in find_all(mm, needle)]

    if args.json:
        json.dump(facts, sys.stdout, indent=2, ensure_ascii=False)
        print()
    else:
        print(f"binary            : {facts['binary']}")
        print(f"size              : {facts['size']}")
        print(f"md5               : {facts['md5']}")
        print(f"sha256            : {facts['sha256']}")
        print(f"go buildinfo      : {facts['go_buildinfo']!r}")
        print(f"changelog         : {facts['changelog_head']!r}  version={facts['changelog_version']}")
        print(f"CL                : {cl}  (global {CL_GLOBAL:#x} -> RELA {addend:#x}, len {cl_len})")
        print(f"UA builder        : {UA_BUILDER:#x}")
        print(f"setHeaders        : {SET_HEADERS:#x}")
        print("\nUA literals:")
        for row in facts["ua_literals"]:
            print(f"  {row['vaddr']}  {row['got']!r}")
        print("\nsetHeaders literals:")
        for row in facts["set_headers_literals"]:
            print(f"  {row['insn']} -> {row['target']}  {row['text']!r}")
        print(f"\nanthropic-beta value: {facts['anthropic_beta']['value']!r} (func {facts['anthropic_beta']['func']})")
        print("\nbody keys (offsets):")
        for k, v in facts["body_keys"].items():
            print(f"  {k!r:34} {v}")
        print("\ntelemetry:")
        for k, v in facts["telemetry"].items():
            print(f"  {k!r:44} {v}")
        print("\nheaders:")
        for k, v in facts["headers"].items():
            print(f"  {k!r:30} {v}")
        print("\nendpoints:")
        for k, v in facts["endpoints"].items():
            print(f"  {k!r:56} {v}")
    return 0 if cl == CL_EXPECTED else 3


if __name__ == "__main__":
    raise SystemExit(main())
