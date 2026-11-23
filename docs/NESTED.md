# Nested RPF9 headers and the wider subtable

**English** · [Español](NESTED.es.md)

The 22 top-level archives all carry the same header shape: the high half of `+0x20` is 1 and the
table stride is 9 or 10 bytes. Earlier samples also showed headers where that half is 2 and the
table does not fit that stride. This document closes that question with measurement.

## Method

A streaming scan over six archives (5.6 GiB: `data`, `textures`, `packs`, `script`, `common`,
`shaders`) looks for the magic in both byte orders and keeps a hit only if the header validates:
`+0x18` equal to `0x47a00`, `+0x1c` in `0x150`/`0x154`/`0x158`, `w24` non-zero, and
`toc_end_offset` above `toc_subtable_offset` and below 64 MiB. Read-only; nothing is extracted.

Result: **122 valid headers**, 104 with `+0x20` high half 1 and **18 with high half 2**.

## The stride, per group

For each header it is tested which stride `s` satisfies

```
toc_end_offset - toc_subtable_offset == ceil(s * w24 / 16) * 16
```

| group | headers | stride that fits |
|---|---:|---|
| high half 1 | 104 | 9 or 10, selected by the low byte of `+0x2c` |
| high half 2 | 18 | **12** in 13 of them; 2 more fit 12 only if the count is `w24 + 1`; 1 fits 10 with `+0x2c` low byte 1 |

So the wider subtable is not a mystery: it is a **12-byte entry**. The two residuals are 16 bytes
larger than the formula predicts, which is exactly one 16-byte record, and the third is a
high-half-2 header that still uses the 10-byte stride.

The 13 clean cases repeat across `data.rpf`: thirteen headers with `w24 = 1115`, `+0x2c` low byte
2, region 13,392. `12 * 1115 = 13,380`, and `ceil(13380/16)*16 = 13,392`.

## What this changes

The caveat in `raw/cabeceras/README.md` said the high-half-2 case "is an open question, not a
solved one". It is now a measured rule with two accounted exceptions, and the table is in
`raw/cabeceras/nested.tsv` with one row per header.

## Limits of the method

- Only **uncompressed** nested headers are visible to a raw scan. One compressed inside a zlib
  stream does not show its magic and is not counted.
- Six archives were scanned, not all 22. The 5.6 GiB cover the container types that nest
  others; `levels` and `audio` were not included.
- Six of the 18 high-half-2 headers have `w24` between 3 and 76, where any stride between 8 and 16
  rounds to the same region. Those are consistent with 12 but do not prove it; the thirteen
  `w24 = 1115` cases are what carry the argument.

`docs/COMPARATIVA.md` compares this discovery with the 4 KiB-stepped scan of `rpf9-extract` and
`rpf9`, including the one sampled container (`core_restofworld @0xaa0`) that the step cannot see.
