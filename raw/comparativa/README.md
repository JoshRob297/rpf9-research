# Comparison evidence

**English** · [Español](README.es.md)

Transcripts behind `docs/COMPARATIVA.md`. They were produced for task `T-RPF9-COMPARA` and are the
only source of the numbers in that page; nothing here was copied from a third-party run.

## Files

```
psin_census.py     read-only PSIN chunk census over the sample windows
psin_census.txt    its output: streams, shapes, framing, LSCH/LENM body layouts
nested_scan.py     read-only 4 KiB-stepped vs byte-by-byte nested-header scan
nested_scan.txt    its output for ten sample windows
```

Both scripts only open files for reading. They take paths on the command line and write nothing.

## How they were run

```
python3 raw/comparativa/psin_census.py <samples dir>              > raw/comparativa/psin_census.txt
python3 raw/comparativa/nested_scan.py <10 sample windows>        > raw/comparativa/nested_scan.txt
```

`psin_census.py` was pointed at the lab sample directory, 78 `.bin` windows (19 `.head` plus 59
`.q1`/`.q3`/`.tail` slices), 225,877,312 bytes in total. `nested_scan.py` received these ten files,
in this order:

```
core_restofworld.head.bin      core_restofworld001.full.bin   story000_bvh4.full.bin
core_licenses_data.full.bin    data.head.bin                  packs.head.bin
script.head.bin                common.head.bin                shaders.head.bin
textures.head.bin
```

## What the samples are, and what they are not

The sample binaries are **not in this repository** (`.gitignore`, `samples/*.bin`); only their
manifest with hashes is. Both transcripts therefore describe a run over data a reader has to obtain
separately, and the numbers are reproducible only against the same windows.

Five of the windows are full archives of a few kilobytes; the rest are 4 MiB slices of larger
`.rpf` files. A slice can cut a container, a compressed member or a PSIN stream in half, and the
transcripts say so where it matters: 107 PSIN streams hold a 64 KiB prefix whose last chunk
declares a length past the inflated body, and they are left out of the body-layout counts instead
of being counted as format violations.

`raw/` keeps command output as produced. The provenance header inside each `.txt` (command, sample
set, what the script does, where each rule comes from) was written before the run and is kept with
the output. Scripts and section headings are in English, like `raw/payload.txt` and
`raw/cabeceras.txt`, so the `file:line` claims in `docs/COMPARATIVA.md` can be checked against them
without translation.

## What each transcript supports

`psin_census.txt` supports, in `docs/COMPARATIVA.md`, section 1: the 4,066-stream count, the
23,829/0 framing split at `pos + length` versus `pos + 8 + length`, the zero chunks declaring a
length below 8, the exact `LSCH` (3,983/3,983) and `LENM` (3,980/3,980) body equations, the
2,929/3,980 reach of the interleaved `LENM` reading, and the 107 64 KiB prefixes.

`nested_scan.txt` supports section 2: the ten windows, the headers each scan finds at which offset,
the `0xaa0` header that only the byte scan reaches, and the fact that the six 4 MiB census windows
add no unaligned header.
