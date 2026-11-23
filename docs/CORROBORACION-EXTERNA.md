# Independent corroboration from a separate working copy

**English** · [Español](CORROBORACION-EXTERNA.es.md)

An independent reproduction of two measured results from this repository, produced on a
*different* v1.0.2.1 working copy with a from-scratch implementation (no code shared with
`tools/`). Offered as corroboration only — relocate, merge or drop it as you prefer; happy
to convert to an issue if that fits the project's flow better.

## What was reproduced

1. **H8 — `[w08..w04)` entry-grid size formula** (`docs/RPF9.md` §3, table row `0x08`):
   `w04 − w08 == ceil(9·w24/16)·16` (or `ceil(10·w24/16)·16`), verified on **six headers**
   from a separate copy, including one nested child (`script.rpf` @0x1000) parsed without
   any use of the encrypted TOC.
2. **H13 — trailer block structure** (`docs/RPF9.md` §5): the encrypted trailer
   `[EOF−w0c..EOF)` of `story000_bvh4` and `core_licenses_data` (same `w24=4`,
   `w20_hi=1`, `w0c=144`) shares **exactly its first 32 bytes**, diverging from byte 32
   onward (the region where archive-specific names begin). The measured block 0 of the
   pair — `5a178c51e7b96189237e72453084db8a` — reproduces the published constant
   byte-for-byte.

Transcript (commands and raw output, Spanish in-file), within this repository's
evidence classes (container-header slices only, no payload names, no binaries):

- [`raw/corrobora_externa_w08_trailer_v1021.txt`](../raw/corrobora_externa_w08_trailer_v1021.txt)

## Method and limits

- Working copy: a separate v1.0.2.1 install on another machine; only the header
  (64 B) and the final `w0c` bytes of each container were read.
- Six containers measured: the four complete small files referenced in `docs/RPF9.md`
  §3's coherence table plus two nested headers. All six satisfy the H8 formula exactly.
- Nothing here claims anything new about the cipher, the key, or payload contents.
- No game data of any kind is included; the transcript contains only header field
  values and the first 32 bytes of trailers.
