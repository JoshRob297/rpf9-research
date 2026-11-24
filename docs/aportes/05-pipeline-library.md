# 05 — The pipeline library: a warm-up source and a coverage denominator

**Status:** proposal, measured inventory, and a reader patch.
**Game data:** none. Everything below is a count, an offset, a size or a field
layout. No archive name, container name, asset path or package hash appears.
**Relation to the comparison:** this is §4.5 of
[`VICTORY-VS-OURS.md`](../VICTORY-VS-OURS.md). It does not repeat §1 of that
page; the only pieces here that VIctory does not already have are the pairing
table, the manifest order it enables, and the reader in
`crates/victory-game/src/pipeline_library.rs`.

**Labels:** *Fact* means measured and cited. *Inference* means reasoned from
facts and marked as such. Nothing in this document has been exercised against
the shipped package by VIctory code: the reader has only run on synthetic
files.

---

## 1. What the package ships

*Fact.* The shader entry file of the shipped package ends in 4,205 zlib
streams (4,204 of 65,536 bytes and one of 27,436) that concatenate into a
single 275,540,780-byte file. Nothing we know of read it before: the shader
carver reads only the raw-deflate entries. Source: our
`docs/shader_library.md:3-6,10-14` (the measurement and the reassembly rule;
the tool fails if the concatenated size differs from the header's).

*Fact.* Its header and tables, all little-endian, are:

| offset | size | field |
|---|---:|---|
| `0x00` | 4 | magic `'P' 'S' 00 09` |
| `0x04` | 32 | name, NUL-padded |
| `0x24` | 36 | version string, NUL-padded |
| `0x48` | 8 | hash |
| `0x50` | 4 × 4 | graphics G = 25,471, compute C = 2,693, blobs B = 54,576, programs P = 21,522 |
| `0x60` | 4 | blob section size, 31,120,020 |
| `0x64` | 4 | code section size, 240,894,464 |
| `0x80` | G × `0x70` | graphics pipeline records |
| | C × 24 | compute pipeline records |
| | B × 8 | blob table: (offset, size) into the blob section |
| | P × 8 | program table: (offset, size) into the code section |

Source: `docs/shader_library.md:29-44`.

*Fact.* The sections add up to the file size exactly:

```text
0x80 + 25471*0x70 + 2693*24 + 54576*8 + 21522*8
     + 31,120,020 + 240,894,464 = 275,540,780
```

Every blob and program entry lies inside its section, the blob entries are
contiguous, and the program offsets are in increasing order and 256-byte
aligned. Source: `docs/shader_library.md:46-48`.

*Fact.* A graphics record is `0x70` bytes: `u64` hash, `u32` state blob,
`u32` pipeline blob, 40 bytes not decoded, then seven `(u32 program, u32 stage
blob)` pairs. `0xFFFFFFFF` means none. Slot 0 is the pixel shader, slot 1 the
vertex shader, slot 2 the mesh shader, slots 3 to 5 are never used and slot 6
is unidentified. Source: `docs/shader_library.md:50-55`.

*Fact.* The stage pairing over the 25,471 graphics records is:

| stages | pipelines |
|---|---:|
| VS + PS | 13,383 |
| MS + PS | 10,726 |
| MS only | 1,336 |
| VS only | 24 |
| VS + PS + slot 6 | 2 |
| **total** | **25,471** |

Source: `docs/shader_library.md:57-64`. The table is consistent with the per-
slot counts on the same page: slot-1 uses are 13,383 + 24 + 2 = 13,409 and
slot-0 uses are 13,383 + 10,726 + 2 = 24,111, both matching
`docs/shader_library.md:53-54`. The two slot-6 rows are their own category and
also carry a VS and a PS; they are not double-counted above.

*Fact.* A compute record is 24 bytes: `u64` hash, `u32` state blob, `u32`
kind-1 blob, `u32` program, `u32` layout blob. Source:
`docs/shader_library.md:69-77`.

*Fact.* The 21,522 programs are 52 to 239,464 bytes each (median 3,968;
238,829,764 bytes in total), padded to 256 bytes. 21,463 begin with the
36-byte prologue the FSPX programs have; 59 have none. Each program belongs to
exactly one stage: 9,996 PS, 7,498 MS, 2,684 CS, 1,343 VS and one slot-6
program. Source: `docs/shader_library.md:82-88`.

*Fact.* Each graphics stage blob and each compute layout blob ends in a
16-byte digest. In the container format that digest is the source container's
`HASH`. 21,509 of the 21,522 programs match one of the 6,522 distinct carved
shader containers; in every linked case the stage of the program and the stage
of the container agree. The 13 programs whose digest matches no carved
container are the only ones with no source in the shader entries. Source:
`docs/shader_library.md:90-104`.

*Fact.* The library holds **pipeline builds**, not copies of the carved FSSM
code: none of the programs is byte-identical to its source's FSSM code, and
only 47 distinct code bodies occur on both sides. Source:
`docs/shader_library.md:101-104`.

*Fact.* With our translator at `main` `aa2988cc` (llvm-mc 23, `gfx1013`),
17,955 of the 21,522 programs translate and pass `spirv-val`: VS 1,333/1,343,
MS 7,059/7,498, PS 7,719/9,996, CS 1,844/2,684, slot 6 0/1. Source:
`docs/shader_library.md:130-139`. The largest blocker, 2,533 programs, is
scalar register tuples that run into `vcc`; the same tuples are rare in FSSM
shaders and common in pipeline builds (`docs/shader_library.md:143-148`).

*Inference.* The library is the console's precompiled-pipeline store: the
records name stages, the blobs have the shapes of the platform's pipeline
state kinds, and the programs are per-pipeline builds. For VIctory this makes
it the only in-package source of "which pipelines exist and which stages they
pair", independent of what a frame happens to touch. The package reading it is
not evidence that the title reads it; §5 lists that open question.

---

## 2. A minimal reader

### 2.1 What it takes as input

The reader takes the 275,540,780 bytes after the zlib streams have been
reassembled, not the archive. Reassembly is a separate job: 4,205 streams with
0–12 bytes of gap, and the header's size as the stopping rule
(`docs/shader_library.md:10-17`). A reader over the reassembled bytes can be
written and tested without an archive parser, which is why this patch is
self-contained.

### 2.2 Parse order

```text
parse(file):
    require len(file) >= 0x80
    require file[0..4] == 'P' 'S' 00 09
    G = u32(0x50); C = u32(0x54); B = u32(0x58); P = u32(0x5c)
    blob_size = u32(0x60); code_size = u32(0x64)

    tables_end = 0x80 + G*0x70 + C*24 + B*8 + P*8
    blob_section = tables_end
    code_section = blob_section + blob_size
    require code_section + code_size == len(file)        # exact, not <=

    for i in 0..B:                                       # blob table
        (off, size) = entry(tables_end - B*8 - P*8, i)
        require off + size <= blob_size

    previous = -1
    for i in 0..P:                                       # program table
        (off, size) = entry(tables_end - P*8, i)
        require off % 256 == 0
        require off > previous; previous = off
        require off + size <= code_size

    for i in 0..G:                                       # graphics records
        rec = 0x80 + i*0x70
        check_blob(u32(rec+0x08))                        # state
        check_blob(u32(rec+0x0c))                        # pipeline blob
        for slot in 0..7:
            program = u32(rec+0x38 + slot*8)
            blob    = u32(rec+0x3c + slot*8)
            require program == NONE or program < P
            require blob    == NONE or blob < B
            require not (program == NONE and blob != NONE)

    for i in 0..C:                                       # compute records
        rec = 0x80 + G*0x70 + i*24
        require u32(rec+0x10) < P                        # program
        check_blob(u32(rec+0x08)); check_blob(u32(rec+0x0c))
        check_blob(u32(rec+0x14))                        # layout

check_blob(v): require v == NONE or v < B
```

`entry(table, i)` reads `(u32 offset, u32 size)` at `table + i*8`; the blob
table starts after the compute records and the program table after the blob
table. The reader exposes `graphics()`, `compute()`, `program(index)`,
`blob(index)` and `stage_blob(slot)`. `stage_blob` returns `None` for the
slot-6 records, whose program is present but whose stage blob is `NONE`
(`docs/shader_library.md:54-55`).

Pairing falls out of the slot set without decoding anything:

```text
slots  = {0,1}   -> VS + PS
slots  = {0,2}   -> MS + PS
slots  = {2}     -> MS only
slots  = {1}     -> VS only
slots  = {0,1,6} -> VS + PS + slot 6
```

### 2.3 What makes a file or a record malformed

The reader rejects a file at the first of:

* wrong magic or fewer than `0x80` bytes;
* a table that does not fit before the blob section;
* `code_start + code_size != len(file)` — this one check catches nearly every
  truncation, because the header's own size arithmetic is exact
  (`docs/shader_library.md:46-47`);
* a blob or program entry that leaves its section;
* a program offset that is not 256-byte aligned or does not increase;
* a record naming a program or blob outside its table;
* a slot with a stage blob but no program.

The last two are the only checks that need to walk the records; all the
others are header and table checks. Blob contiguity is checked by the source
study but not required by the reader, only in-section bounds, so a variant
that pads a blob is still read. A corruption inside the 40 undecoded bytes
of a graphics record is not detectable, by construction.

### 2.4 The patch

`crates/victory-game/src/pipeline_library.rs` (new, ~570 lines) implements
exactly §2.2–2.3, with `thiserror` for the rejection reasons and two unit
tests that build libraries by hand: one reads a VS+PS / MS+PS / VS-only set
with a compute record and checks the sections, the other mutates a built file
into every rejection class in §2.3. `crates/victory-game/src/lib.rs` gains one line and
`Cargo.toml` gains the `thiserror` dependency already used elsewhere in the
workspace. The tests generate their own bytes; no game data enters the tree,
which keeps the patch inside `docs/asset-policy.md:24` (synthetic test data
generated by our own code).

The patch is deliberately not a tool: it does not find the zlib streams, does
not decode a blob, does not match a digest to a container and does not touch
D3D12. It has been run on synthetic files only, so the first useful next step
is a smoke test against a user's reassembled copy.

---

## 3. How it connects to the cache and to the loader's warm-up

### 3.1 What VIctory does today

*Fact.* The shader cache is keyed by the content of a container and the build
of the executable: the input is `[BLAKE3(current_exe) ‖ container]`, the
converter is identified as `"shader.dxil"` version 1, and `convert` treats
`input[32..]` as the container (`crates/victory-gpu/src/shader_cache.rs:40-56,
76-99`). The cache key is the BLAKE3 of converter id, NUL, version and that
input (`crates/victory-pipeline/src/cache.rs:12-19`), written atomically
per key (`:47-64`) and refused inside the repository (`:34-39`).

*Fact.* Translation is lazy: the title creates about 60,000 pipelines in its
first 20 s and draws with a few dozen; containers are shared by content hash
and translated once, on first use (`crates/victory-gpu/src/pipeline.rs:5-11,
53-58,110-160`). A failed translation is not written to the cache
(`crates/victory-gpu/src/shader_cache.rs:320-324`), so failures are retried on
every run.

*Fact.* An offline batch already exists: `victory translate` with
`VICTORY_PAIRS` and `--pipelines` builds host pipelines from individual
containers with a stub pixel shader, not from the shipped library
(`apps/victory/src/translate.rs:148-149,175,440-450`). This proposal feeds
that machinery; it does not replace it.

*Fact.* Their architecture already states the position: shaders are translated
from the bytes the title passes at pipeline creation, and converting them
ahead of time from files is only a warm-up (`docs/architecture.md:24-26`).

### 3.2 What the library adds

1. **A pipeline list that is not frame-dependent.** 25,471 graphics and 2,693
   compute records exist in the package whether or not the first 20 s reaches
   them. The bind log can only report what was drawn.
2. **Stage pairing without a run.** Nothing in the current cache states
   which stages a pipeline pairs; it is only observable from which containers
   a frame uses. The library states it for every record, including the 1,336
   MS-only and 24 VS-only rows that the "VS+PS" mental model misses.
3. **A program-level denominator.** Translation is per container, but a
   container can produce several programs; the program index (21,522) is the
   real unit of "translated or not", and each program's stage and size are
   known before any translation (`docs/shader_library.md:82-88`).

### 3.3 What it costs, and where it does not fit

*Fact.* The library stores stage and layout blobs plus a 16-byte digest; it
does not store the container bytes. VIctory's cache is keyed by the BLAKE3 of
the container (`crates/victory-gpu/src/shader_cache.rs:90-99`), so a manifest
entry `(digest → program)` cannot produce a cache key until the container
behind that digest is in hand. That resolution is exactly the "not measured"
item: 21,509 programs link to 6,522 carved containers in our offline study
(`docs/shader_library.md:96-99`), but whether VIctory can obtain those
containers without the title is a run-time question (§5).

*Fact.* The build BLAKE3 is part of the key (`crates/victory-gpu/src/shader_cache.rs:40-56`).
Every VIctory rebuild changes the key and invalidates every warmed entry, so a
warm-up is a recurring startup cost, not a one-time one. The same fact makes
"warm once, ship the cache" impossible.

*Fact.* Failed translations are not stored (`crates/victory-gpu/src/shader_cache.rs:320-324`).
A pass over all 21,522 programs would retry the 3,567 that fail today on every
run unless a separate negative cache is added. The coverage metric therefore
cannot be read back out of the cache directory; it has to be computed by the
pass that attempts the translations.

*Inference.* Two integration shapes are possible, and they should not be
confused:

* **A. Manifest only (small).** A manifest step over the reader's output adds
  the 16-byte digest at the tail of each stage blob
  (`docs/shader_library.md:92-96`) and emits a digest → (stage, program)
  order; the existing `translate` path consumes containers resolved by
  whatever means. Gain: deduplication and ordering, and a per-record coverage
  report. Cost: the digest → container mapping, and the existing build-key
  invalidation. No new cache namespace.
* **B. Direct library translation (large).** A new converter id (not
  `"shader.dxil"` v1, and not reusing its `input[32..]` framing) translates a
  program index to DXIL. Gain: warm-up without the title and without the FSSM
  containers. Cost: a second cache namespace, translations that the title may
  never request, and the open question of whether the library build or the
  FSSM container is the form the title runs
  (`docs/shader_library.md:101-104,163-172`). Measure A first; B is
  justified only if §5 shows the library form is the executed one.

*Inference.* The 60,000 pipelines the title creates in 20 s and the 25,471
library records do not have to be the same set: the library covers at most
about 42% of that count even if every record corresponded, and the
correspondence is unmeasured (`crates/victory-gpu/src/pipeline.rs:7-9`). That
ceiling belongs in any coverage claim.

---

## 4. The coverage metric, and why it leaves the black frame black

### 4.1 Definition

Program coverage is the fraction of the 21,522 programs that translate
(17,955 = 83.4% today, `docs/shader_library.md:130-139`). It is the wrong
headline, because one untranslated stage kills a whole pipeline. The useful
metric is **record coverage**:

```text
buildable(record) = every named stage program translates
                      and (for graphics) every named stage blob is present
coverage(class)   = buildable records of that class / records of that class
```

Reported per pairing class (VS+PS, MS+PS, MS-only, VS-only, VS+PS+slot 6) and
for compute, this is stricter than 83.4% and has the same form as the
README's "10,617 of 12,346" numbers (`README.md:43`), though the denominators
differ (§4.1, last paragraph). It also says where the failures are: the PS
alone accounts for 2,277 of the 3,567 failing programs, and the 2,533
"normalized encoding" blocker concentrates in pipeline builds
(`docs/shader_library.md:143-148`), so a record metric will look worse than
the program percentage and will say why.

*Fact.* Two denominators must not be mixed: the library has 25,471 graphics
records, while the README counts 8,506 mesh and 12,346 vertex/pixel *shader
entries* in the shader archive (`README.md:43`). They are different objects
(pipelines vs carved shaders) and the library's 9,996 PS programs are not the
same population as the archive's PS entries.

### 4.2 Why it does not fix the black frame

*Fact.* The world's black frame has causes the library cannot address: most
geometry is drawn indirectly and untranslated shaders drop the rest
(`README.md:42`), the first world frame stalls with indirect execution off
(`README.md:117`), and real queries, depth bounds, HDR and scaling are
missing (`README.md:42`). Translation success is not pixels.

*Fact.* The library has no binding information: the 40 bytes per graphics
record are undecoded, the graphics state blob and the compute kind-1 blob are
undecoded, and the records inside the stage blobs are undecoded
(`docs/shader_library.md:69-77,171-172`). A reader can name a pipeline's
stages and programs; it cannot say which resources the pipeline binds.

*Inference.* A 100% record coverage result would still leave the frame under
the other failures: the world would still draw a few dozen pipelines
(`crates/victory-gpu/src/pipeline.rs:7-9`), indirect draws would still be
clamped or stalled, and the library's pipelines are not proven to be the ones
the title requests. What the metric buys is a defensible answer to "is the
untranslated part still a plausible cause, and how big is it", with the
denominator fixed by the package instead of by a frame.

---

## 5. What needs a real run

These are the items this document cannot settle from static files.

1. **Does the title read the library at all?** Measure: watch the loader's
   file reads (their `victory-hle` redirects virtual paths to host files,
   `crates/victory-hle/src/modules/files.rs`) and/or scan the title's mapped
   memory for the magic `'P' 'S' 00 09` after boot. If it never appears, the
   library is shipped for the console's own use and is only a build artifact.
2. **Which compiled form runs?** Measure: capture the container bytes a
   pipeline is created with, take the 16-byte digest of its stage blob, and
   compare the DXIL of the bound pipeline with a translation of the library
   program for the same digest and with the carved FSSM container
   (`docs/shader_library.md:101-104,163-172`).
3. **Can digest → container be resolved without the archive?** Measure: count
   the 6,522 distinct digests that appear among the containers logged at bind
   in one world run. This decides whether shape A in §3.3 is viable.
4. **What does a warm-up pass cost?** Measure: read + parse + translate all
   programs on their machine, against the first-use cost it removes. The
   library is 275 MB; the translation dominates.
5. **How do the ~60,000 created pipelines distribute over the 25,471
   records?** Measure: join the bind log with the reader's output. This is the
   only way to state the metric's real denominator.

Until 1 and 2 are measured, the honest claim is: the library is a complete
list of the package's precompiled pipelines, with their pairing and their
programs; it is a better denominator for translation coverage; and it is not a
fix for the black frame.

---

## Appendix — where each side was read

| Side | Location | What |
|---|---|---|
| Ours | `docs/shader_library.md:3-17,29-104,130-172` | counts, layout, pairing, linkage, translation |
| VIctory | `crates/victory-gpu/src/shader_cache.rs:1-10,40-56,60-99,320-324` | cache key, converter, failures |
| VIctory | `crates/victory-pipeline/src/cache.rs:12-19,34-39,47-64` | key construction, placement, atomic write |
| VIctory | `crates/victory-gpu/src/pipeline.rs:5-11,53-58,110-160` | lazy translation, sharing, 60,000 pipelines |
| VIctory | `apps/victory/src/translate.rs:148-149,175,440-450` | existing offline batch |
| VIctory | `docs/architecture.md:24-26` | "warm-up only" position |
| VIctory | `README.md:42-43,117` | black frame, coverage numbers, indirect draws |
| Comparison | `docs/VICTORY-VS-OURS.md:262-274` | §4.5 scope and "does not fix" |
