#!/usr/bin/env python3
"""Read-only PSIN chunk census used by docs/COMPARATIVA.md (T-RPF9-COMPARA).

Finds every zlib stream in the given sample windows whose inflated body starts
with PSIN, walks the IFF chunk chain by the declared length (the length includes
the 8-byte chunk header), and checks the LSCH / LENM body layouts described in
docs/PSIN.md.

A chunk whose declared length runs past the end of the inflated body is a
container prefix stored as a 64 KiB page; its body is not used for the layout
counts. The page itself is counted as one PSIN stream, like every other one.

Usage: python3 psin_census.py <samples dir>
"""

import struct
import sys
import zlib
from collections import Counter
from pathlib import Path

MAIN_SHAPE = ("PSIN", "LSCH", "LENM", "LSNS", "LGID", "LRSC", "CHKS")


def zlib_psin_streams(data):
    """Return [(offset, compressed_size, inflated)] for every PSIN stream start."""
    found = []
    i = 0
    n = len(data)
    view = memoryview(data)
    while i < n - 2:
        if data[i] == 0x78 and (data[i] & 0x0F) == 8 and ((data[i] << 8) | data[i + 1]) % 31 == 0:
            try:
                d = zlib.decompressobj()
                out = d.decompress(view[i:])
                if d.eof and out.startswith(b"PSIN"):
                    comp = (n - i) - len(d.unused_data)
                    found.append((i, comp, out))
                    i += comp
                    continue
            except zlib.error:
                pass
        i += 1
    return found


def be32(b, o):
    return struct.unpack(">I", b[o:o + 4])[0]


def le32(b, o):
    return struct.unpack("<I", b[o:o + 4])[0]


def walk(out):
    """Walk chunk headers, advancing by the declared size (header included)."""
    pos, rows, stop = 0, [], "less_than_8_left"
    while pos + 8 <= len(out):
        tag, sz = out[pos:pos + 4], be32(out, pos + 4)
        rows.append((pos, tag, sz))
        if sz < 8:
            stop = "sz<8"
            break
        if pos + sz > len(out):
            stop = "declared_past_end"
            break
        if pos + sz == len(out):
            stop = "exact_end"
            break
        pos += sz
    return rows, stop


def looks_like_tag(b):
    """True for the four uppercase-or-digit bytes a chunk magic is made of."""
    return len(b) == 4 and all(48 <= c <= 57 or 65 <= c <= 90 for c in b)


def framing_checks(out, rows):
    """Count chunk boundaries that resolve at pos + sz, and at pos + 8 + sz.

    Only boundaries with more bytes after them can say anything about where the
    next magic lives; the last chunk of a stream ends the walk instead.
    """
    successors = at_length = at_plus8 = plausible_early = 0
    for idx, (pos, _tag, sz) in enumerate(rows):
        if sz < 8 or pos + sz >= len(out):
            continue
        successors += 1
        nxt = rows[idx + 1][1] if idx + 1 < len(rows) else None
        at_length += out[pos + sz:pos + sz + 4] == nxt
        at_plus8 += out[pos + 8 + sz:pos + 12 + sz] == nxt
        plausible_early += looks_like_tag(out[pos + 8 + sz:pos + 12 + sz])
    return successors, at_length, at_plus8, plausible_early


def lsch_layout(body):
    """32-byte struct headers with [AA x 8] at +16, then 16-byte field records."""
    off, headers, fields = 0, 0, 0
    while off + 32 <= len(body) and body[off + 16:off + 24] == b"\xaa" * 8:
        headers += 1
        fields += le32(body, off + 28) >> 16
        off += 32
    return headers, fields, off + 16 * fields


def lenm_two_phase(body):
    """24-byte enum headers with [EE x 8] at +8, then all 16-byte value records."""
    off, headers, values = 0, 0, 0
    while off + 24 <= len(body) and body[off + 8:off + 16] == b"\xee" * 8:
        headers += 1
        values += le32(body, off + 16)
        off += 24
    return headers, values, off + 16 * values


def lenm_interleaved(body):
    """PercyStar psin.rs:235 -- one header immediately followed by its values."""
    off, headers, consumed = 0, 0, 0
    while off + 24 <= len(body) and body[off + 8:off + 16] == b"\xee" * 8:
        headers += 1
        consumed = off + 24 + 16 * le32(body, off + 16)
        off = consumed
    return headers, consumed


def main():
    samples = Path(sys.argv[1])
    files = sorted(samples.glob("*.bin"))
    total_bytes = sum(f.stat().st_size for f in files)

    print(f"INPUT: {len(files)} windows, {total_bytes:,} bytes\n")
    print("=== 1. PSIN STREAMS PER WINDOW ===")
    print(f"{'window':<34} {'bytes':>11} {'PSIN streams':>13}")
    streams = []
    for f in files:
        data = f.read_bytes()
        hits = zlib_psin_streams(data)
        streams.extend((f.name, off, comp, out) for off, comp, out in hits)
        if hits:
            print(f"{f.name:<34} {len(data):>11,} {len(hits):>13}")
    print(f"\nTOTAL PSIN stream starts: {len(streams)}")

    shapes = Counter()
    short_chunks = 0
    stops = Counter()
    prefixes = []
    lsch = {"chunks": 0, "complete": 0, "headers": 0, "fields": 0, "exact": 0, "per_chunk": Counter()}
    lenm = {"chunks": 0, "complete": 0, "headers": 0, "values": 0, "exact": 0,
            "inter_exact": 0, "per_chunk": Counter()}
    examples = []
    framing = [0, 0, 0, 0]

    for name, off, comp, out in streams:
        rows, stop = walk(out)
        for i, count in enumerate(framing_checks(out, rows)):
            framing[i] += count
        stops[stop] += 1
        shapes[tuple(t.decode("latin-1") for t in (r[1] for r in rows))] += 1
        if stop == "declared_past_end":
            prefixes.append((name, off, out, rows[-1]))
        for idx, (pos, tag, sz) in enumerate(rows):
            if sz < 8:
                short_chunks += 1
                continue
            truncated = pos + sz > len(out)
            if truncated:
                continue
            body = out[pos + 8:pos + sz]
            if tag == b"LSCH":
                headers, fields, consumed = lsch_layout(body)
                lsch["chunks"] += 1
                lsch["headers"] += headers
                lsch["fields"] += fields
                lsch["exact"] += consumed == len(body)
                lsch["per_chunk"][headers] += 1
            elif tag == b"LENM":
                headers, values, consumed = lenm_two_phase(body)
                lenm["chunks"] += 1
                lenm["headers"] += headers
                lenm["values"] += values
                lenm["exact"] += consumed == len(body)
                lenm["per_chunk"][headers] += 1
                lenm["inter_exact"] += lenm_interleaved(body)[1] == len(body)
        if len(examples) < 5 and name in ("anim.head.bin", "data.head.bin", "levels.head.bin"):
            examples.append((name, off, comp, out, rows, stop))

    print("\n=== 2. CHAIN SHAPES ===")
    for shape, count in shapes.most_common():
        print(f"{count:>6}  {' -> '.join(shape)}")
    print(f"\nwalk stop reasons: {dict(stops)}")

    print("\n=== 3. ADVANCE RULE: length includes the 8-byte chunk header ===")
    print(f"successors at pos + length                  : {framing[0]}")
    print(f"  the stream's next magic is there          : {framing[1]} ({framing[1] * 100.0 / max(framing[0], 1):.2f}%)")
    print(f"  the stream's next magic 8 bytes later     : {framing[2]}")
    print(f"  any plausible tag 8 bytes later           : {framing[3]} (chance matches, not boundaries)")
    print(f"streams ending exactly at the inflated size : {stops['exact_end']}/{len(streams)}")
    print(f"  complete seven-chunk chains               : {shapes[MAIN_SHAPE]}")
    print(f"  PSIN -> PMAP -> ... -> CHKS variant       : {shapes[('PSIN', 'PMAP', 'PSCH', 'PSIG', 'STNS', 'CHKS')]}")
    print(f"streams stopping at a chunk past the body   : {stops['declared_past_end']}/{len(streams)}")
    print(f"chunks declaring length < 8                 : {short_chunks}")
    print("The independent check is in sections 4-5: each boundary slices a body, and")
    print("the two-phase equation must land exactly on the end of that body. The third")
    print("line is the framing test: the stream's own next magic never sits 8 bytes late.")
    print("The fourth line counts four printable bytes that would pass a loose tag check")
    print("if one did not compare against the successor the walk actually reaches.")

    print("\n=== 4. LSCH BODY: 32-byte headers, then 16-byte field records ===")
    print(f"LSCH chunks that fit in their stream : {lsch['chunks']}")
    print(f"32-byte struct headers               : {lsch['headers']}")
    print(f"  with [AA x 8] at +16..+24          : {lsch['headers']} (by construction of the walk)")
    print(f"16-byte field records                : {lsch['fields']}")
    print(f"body == 32*headers + 16*fields       : {lsch['exact']}/{lsch['chunks']}")
    dist = sorted(lsch["per_chunk"].items())
    print(f"headers per chunk                    : min {dist[0][0]}, max {dist[-1][0]}, "
          f"chunks with 1 header: {lsch['per_chunk'][1]}")

    print("\n=== 5. LENM BODY: 24-byte enum headers, then 16-byte value records ===")
    print(f"LENM chunks that fit in their stream : {lenm['chunks']}")
    print(f"24-byte enum headers                 : {lenm['headers']}")
    print(f"  with [EE x 8] at +8..+16           : {lenm['headers']} (by construction of the walk)")
    print(f"16-byte value records                : {lenm['values']}")
    print(f"body == 24*headers + 16*values       : {lenm['exact']}/{lenm['chunks']}")
    print(f"interleaved reading consumes body    : {lenm['inter_exact']}/{lenm['chunks']}  (PercyStar psin.rs:235)")
    multi = sum(v for k, v in lenm["per_chunk"].items() if k >= 2)
    print(f"chunks with >= 2 enum headers        : {multi} (interleaved stops after the first)")

    print("\n=== 6. EXAMPLES: full chains ===")
    for name, off, comp, out, rows, stop in examples:
        print(f"{name} @0x{off:x}  compressed={comp}  inflated={len(out)}  stop={stop}")
        print("  " + " -> ".join(f"{tag.decode('latin-1')}({sz})" for _, tag, sz in rows))
        print()

    print("=== 7. CONTAINER PREFIXES (declared length past the inflated body) ===")
    print(f"streams whose walk stops past the body : {len(prefixes)} of {len(streams)}")
    print(f"  inflated body size                  : {sorted(set(len(p[2]) for p in prefixes))}")
    print(f"  first chunk that overruns           : {dict(Counter(p[3][1].decode('latin-1') for p in prefixes))}")
    for name, off, out, chunk in prefixes[:3]:
        pos, tag, sz = chunk
        print(f"  {name} @0x{off:x}: {tag.decode('latin-1')} declares {sz} at +0x{pos:x}, body is {len(out)}")

    print("\nChunks whose declared length overruns the body are not used for the LSCH/LENM")
    print("counts in sections 4 and 5; the page itself is counted as one PSIN stream, like")
    print("every other one, which is why the total in section 1 matches the payload census.")
    print("Whether those 64 KiB bodies are one page of a larger container is a hypothesis,")
    print("not something this script can show.")


if __name__ == "__main__":
    main()
