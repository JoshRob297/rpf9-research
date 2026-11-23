# The PSIN chunk chain, walked

**English** · [Español](PSIN.es.md)

`open-vfs` documents the chain as `PSIN → LSCH → LENM → LSNS → LGID → LRSC → CHKS` and has an open
task to implement the parser. This measures it on a retail package so the implementation does not
start from an assumption.

## Population

Streams classified as `PSIN` across the 22 archives: **15,380**, spread over ten archives
(`levels`, `packs`, `anim`, `navmesh`, `story000`, `script`, and four smaller ones).

## The framing rule that makes it walk

Every chunk is `magic (4 bytes) + length (u32 big-endian) + body`, and **the length includes the
8-byte header**. Advancing by `8 + length` lands 8 bytes short of the next magic; advancing by
`length` lands exactly on it.

That single rule is the difference between a parser that reads one chunk and one that reads the
chain. Measured on 73 streams: the next magic sits at `offset + length` in 56 of 56 cases where the
stream is not truncated mid-chunk. A wider sweep of 78 windows repeats it: 23,829 of 23,829
successors land at `offset + length` and none at `offset + 8 + length`
(`raw/comparativa/psin_census.txt`).

## Result

Walking with that rule over 68 streams from ten archives:

```
PSIN -> LSCH -> LENM -> LSNS -> LGID -> LRSC -> CHKS     67 streams
PSIN -> LSCH -> LENM                                      1 stream (truncated sample)
```

The order matches the documented chain exactly, and it starts at offset 0 with no alignment
padding between chunks. Chunk counts across the sample: `PSIN` 68, `LSCH` 68, `LENM` 68, `LSNS` 67,
`LGID` 67, `LRSC` 67, `CHKS` 67.

## Shapes

Sizes vary by archive but repeat within it. Three examples:

```
anim@24576        PSIN(2,048) -> LSCH(440) -> LENM(8) -> LSNS(196) -> LGID(8) -> LRSC(88) -> CHKS(20)
anim@450162688    PSIN(9,168) -> LSCH(648) -> LENM(8) -> LSNS(68)  -> LGID(8) -> LRSC(88) -> CHKS(20)
anim@450179072    PSIN(22,608) -> LSCH(648) -> LENM(8) -> LSNS(68) -> LGID(8) -> LRSC(88) -> CHKS(20)
```

`LENM` and `LGID` are consistently 8 bytes — a header with no body. `CHKS` is 20. The variable parts
are `LSCH` and `LRSC`, which is where the resource metadata lives.

## Inside the bodies

The bodies are two-phase tables, not opaque blobs. `LSCH` holds `N` consecutive 32-byte struct
headers, each carrying the marker `[0xAA;8]` at `+0x10`, and then one 16-byte field record per count
stored in `+0x1C` (high half). `32*N + 16*sum(count)` equals the body length in all 3,983 `LSCH`
chunks that fit in their stream. `LENM` is the same pattern with 24-byte headers (marker `[0xEE;8]`
at `+0x08`) and 16-byte value records: 3,980 of 3,980 bodies equal `24*N + 16*sum(count)`. The
counts are in `raw/comparativa/psin_census.txt`.

## What this does not say

It says nothing about the meaning of the bytes inside each chunk; only that the chain, its order
and its framing are what the documentation claims. The bodies are not decoded here.

## Limits

- 68 streams walked out of 15,380. Ten archives were sampled, one of them (`anim`) more deeply
  than the rest.
- A stream whose declared length runs past its inflated size was skipped as truncated; those are
  real and worth handling, not a measurement error. In the 78-window sweep there are 107 of them,
  all inflating to exactly 65,536 bytes; their bodies are left out of the layout counts above.

`docs/COMPARATIVA.md` puts this framing next to the one public PSIN reader that walks it
(`PercyStar/src/psin.rs:188-201`, with its own table readers in `vehicle_data.rs`) and the two tools
that only label the stream.
