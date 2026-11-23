# How our measurements compare with rpf9-extract and PercyStar

**English** · [Español](COMPARATIVA.es.md)

Three things in this repository come from measurement rather than from an existing implementation:
the PSIN chunk framing, the way nested containers are found, and the size of a TOC entry. This page
puts each of them next to three public RPF9 tools and says where the numbers agree, where they
disagree, and which side is better for what.

| tool | commit read | what it is |
|---|---|---|
| [offs/rpf9-extract](https://github.com/offs/rpf9-extract/tree/46ca608975b749fc3e77a62435d46fdc115a97e0) | `46ca6089` | Rust extractor + report, 4 KiB-sector discovery |
| [rpatty-dev/PercyStar](https://github.com/rpatty-dev/PercyStar/tree/6a64e53f6d1c48aae250109232eebb02a2a68e36) | `6a64e53f` | Rust game-data browser, the only one of the three with a PSIN body decoder |
| [zeozeozeo/rpf9](https://github.com/zeozeozeo/rpf9/tree/3d8d4fbbf49fe54cb3e91a8a6dee01ff41858c7b) | `3d8d4fbb` | Rust reader/writer library, same discovery shape as rpf9-extract |

## Method

The three repositories were cloned into a scratch directory and **read**, with `nl -ba` for line
numbers; none of their binaries was built or run, so every statement below about their behavior is
a statement about their source, not about a run [verified]. Our side of each comparison comes from
the checks recorded in `docs/PSIN.md`, `docs/NESTED.md`, `docs/RPF9.md` and from the transcripts in
`raw/comparativa/` [verified].

The table links open each project at the commit that was read; `path:line` references are relative
to that commit.

Every claim is tagged: `[verified]` means it was read at the cited `path:line` or produced by a run
whose transcript is in this repository; `[hypothesis]` means it is an interpretation that the
evidence supports but does not close.

## 1. PSIN

### What they do

`rpf9-extract` treats PSIN as a payload label, not a structure: when an inflated stream starts
with `PSIN`, the scan records the file as `pso`/`PSO` (`rpf9-extract/src/scan.rs:116-117`) and the
inflate loop then jumps over the compressed member in one step (`rpf9-extract/src/scan.rs:99-107`)
[verified]. Nothing ever walks the chunks. Its `-v` report prints the eight header fields and the
body/trailer ranges (`rpf9-extract/src/report.rs:125-142`) and its README advertises a PSIN table
under `-v` (`rpf9-extract/README.md:7`); in the code read here the PSIN content is classified by
prefix only [verified]. `zeozeozeo/rpf9` does the same thing in one line
(`rpf9/src/scan.rs:285`) [verified].

`PercyStar` is different: it has a full reader. `parse_iff_chunks` reads a 4-byte tag and a
big-endian `u32` length, takes the body as `[pos+8 .. pos+sz]` and advances `pos += sz`
(`PercyStar/src/psin.rs:188-201`) [verified]. `parse_lsch` reads 32-byte struct headers while the
8 bytes at `+16` are `0xAA`, takes the field count from the high half of `+28`, and then reads
16-byte field records (`PercyStar/src/psin.rs:203-232`) [verified]. `parse_lenm` reads a 24-byte
enum header and then that enum's 16-byte values before looking for the next header
(`PercyStar/src/psin.rs:235-255`) [verified]. A second, independent reader in
`PercyStar/src/vehicle_data.rs:288-340` reads both tables **headers first**, which is what we
measure below [verified]. Both readers are used: `PercyStar/src/psin.rs:418-419` and
`PercyStar/src/psin_xml.rs:45,80-81` call the first pair [verified].

### What we measured

`raw/comparativa/psin_census.py` walks every PSIN stream in 78 sample windows and writes
`raw/comparativa/psin_census.txt`: **4,066** streams, the same count as the payload inventory line
`raw/payload.txt:62` reports for those windows [verified]. The walk reaches the exact end of the
inflated body in 3,959 streams: 3,958 complete seven-chunk chains and the single PMAP variant; the
other 107 stop at a chunk whose declared length crosses the end, the 64 KiB prefixes discussed below
[verified]. No chunk in the sweep declared a length below 8 [verified]. The exact ends and the
two-phase body equations below are what corroborate the framing: boundaries shifted by 8 bytes would
slice bodies mid-record and fail those equations [hypothesis]. The body layouts are exact, not
approximate: `32*N + 16*sum(field count)` equals the body length in 3,983 of 3,983 `LSCH` chunks
(48,475 struct headers, 344,446 field records), and `24*N + 16*sum(values)` equals it in 3,980 of
3,980 `LENM` chunks (11,806 enum headers, 72,455 values) [verified]. The marker counts themselves are
by construction — the walk advances only while `[0xAA;8]` at `+0x10` or `[0xEE;8]` at `+0x08` is
present (`raw/comparativa/psin_census.py`), so what is measured independently is that the two-phase
equation lands exactly on the body end, not that the markers exist [verified]. Those numbers are new
in this task and are also written up in `docs/PSIN.md:53-60` [verified].

### Where we agree

1. **The length includes the 8-byte header.** Their `pos += sz` with body `[pos+8..pos+sz]`
   ([PercyStar/src/psin.rs:193-198](https://github.com/rpatty-dev/PercyStar/blob/6a64e53f6d1c48aae250109232eebb02a2a68e36/src/psin.rs#L193-L198))
   is the same rule our census walker uses, and the rule that produces the 3,958 complete chains
   above [verified].
2. **The PSIN magic lives in the inflated body.** All three tools classify after inflation, not in
   the container (`rpf9-extract/src/scan.rs:99-107`, `PercyStar/src/psin.rs:388`, our
   `raw/payload.txt`) [verified].
3. **`LSCH` is headers first, gated by `0xAA`.** `PercyStar/src/vehicle_data.rs:287-320` states the
   rule in a comment and implements it; our census finds the headers-first reading exact in 3,983 of
   3,983 `LSCH` bodies [verified]. Both implementations agree, which is the useful part.
4. **A short or overrunning chunk ends the chain.** `PercyStar/src/psin.rs:194` breaks on
   `sz < 8 || pos + sz > len`; our census stops on the same overrun and skips the whole stream, the
   policy `docs/PSIN.md:70-72` describes [verified]. The `sz < 8` branch never fired in the sweep, so
   it is a guard both sides keep for the same reason, not a difference [verified].

### Where we differ

**Depth, and the direction is in their favor.** `PercyStar` decodes instances, structs, fields,
enums, name hashes and builds a vehicle database from them (`PercyStar/src/vehicle_data.rs:270-361`)
and can export PSIN to XML (`PercyStar/src/psin_xml.rs`) [verified]. Our tooling does not walk PSIN
bodies at all: `tools/rpf9.py:481-482` stops at `head.startswith(b"PSIN")` and labels the file
[verified]. Everything we know about the body layout is in the census script and in the docs, not
in the tool. For extracting PSIN content, their approach is the better one; ours is a measurement
of the container, and it should be read that way.

**One table is read in the other direction.** `PercyStar/src/psin.rs:235-255` reads `LENM` as
header, values, header, values. The bodies say the opposite: all headers come first. Two-phase
consumption reaches the exact end of the body in 3,980 of 3,980 chunks, while the interleaved
reading does so only in 2,929 — exactly the chunks with a single enum; 1,051 chunks hold two or
more, and those are where it stops short [verified]. The same repository already contains the
correct reading in `PercyStar/src/vehicle_data.rs:322-340`, so this is one function disagreeing with
the other, and the measurement sides with `vehicle_data.rs` [verified]. This changes what a
multi-enum body decodes to, which is a real bug for anyone using the `psin.rs` path; it does not
affect single-enum resources, which is why it can survive [hypothesis].

**They clamp, we skip.** Their field loops stop when the body runs out rather than reading past it
(`PercyStar/src/psin.rs:217-220`, `PercyStar/src/vehicle_data.rs:300-306`) [verified]. That is the
better shape for a parser that meets a truncated body. Our first census version had the opposite
bug — it sliced bodies that ran past the inflated member and produced false layout mismatches — and
the fix was to skip those chunks entirely (`raw/comparativa/psin_census.py`) [verified]. Their
clamp and our skip reach the same place for different reasons; ours keeps the counts clean, theirs
still returns partial data.

### What neither of us has measured

One stream out of 4,066 walks a different chain: `PSIN → PMAP → PSCH → PSIG → STNS → CHKS`
(`anim.tail.bin @0x3ed8b0`, sizes 260/56/144/20/1,352/20) [verified]. No repository read here
mentions `PMAP`, `PSCH`, `PSIG` or `STNS` (grep over all three sources returns nothing) [verified],
and our own docs describe only the main chain (`docs/PSIN.md:27-39`). One stream in 4,066 is not a
second format, but it is not explained either [hypothesis: a variant used by a different resource
kind]. It is the first thing to sample when a PSIN parser is written against these numbers.

The 107 streams whose declared length runs past the inflated body all inflate to exactly 65,536
bytes [verified]. They are windows of larger members cut by our sample windows, not malformed
data [hypothesis], which is why they are excluded from the layout counts rather than treated as a
format feature (`docs/PSIN.md:70-72`) [verified].

## 2. Nested RPF9

### What they do

`rpf9-extract` looks for nested containers while it lays out the archive. `layout` walks the gaps
between known files in 4 KiB steps (`rpf9-extract/src/container.rs:74`), validates each candidate
with `Header::parse`, takes the first hit as the outer archive and the rest as nested ones
(`rpf9-extract/src/container.rs:71-89`) [verified]. The step is only half the filter: `parse`
rejects any header whose declared length would run past the buffer (`.../container.rs:32`), so a
header that validates describes a whole container that is present in the data [verified].
`zeozeozeo/rpf9` has the same shape in `discover` (`rpf9/src/archive.rs:65-97`), stepping from 0 and
skipping ranges already carved, with a looser header check that still enforces the size and
16-byte alignment rules (`rpf9/src/header.rs:56-97`) [verified]. `PercyStar` does not look for
nested containers at all: its archive reader reads one 64-byte header at offset 0
(`PercyStar/src/main.rs:4833-4841`), and the only `9FPR` search in the code base is a diagnostic
that counts string hits in a boot executable, capped at 16, with no validation
(`PercyStar/src/boot.rs:99-113`) [verified].

### What we measured

Our scan looks for the magic bytes at **every** offset, not every 4 KiB, and accepts a header only
when it passes the constant checks: `+0x18 == 0x47A00`, `+0x1c == 0x150`, `+0x30 == 16` and three
zero words — about 28 constrained bytes (`tools/rpf9.py:54-64`) [verified]. Each hit is then
censused: the size is reconstructed from a known trailer block or from the zero gap before the next
header (`tools/rpf9.py:260-299`) [verified], which is what `docs/RPF9.md:48` reports as 29 exact
sizes out of 55 occurrences [verified].

The measured result is narrower than the argument suggests: all 122 headers in the census sit at
multiples of 4,096 (`raw/cabeceras/nested.tsv`), and over the six 4 MiB windows that the census
covers (`data`, `packs`, `script`, `common`, `shaders`, `textures`) the byte scan finds the same 15
headers as the stepping scan, with no extras (`raw/comparativa/nested_scan.txt:125-129`)
[verified]. The difference shows up in one file:
`core_restofworld.head.bin` holds a nested container at `0xaa0` that the stepping scan cannot see,
because it starts at `0x1000`; the byte scan finds it and its header matches the independent
inventory in `raw/payload.txt:171` (`w04=0x2c0`, `w24=2`, id `0x162b7cc3d164fea3`, 912 B)
[verified]. So sector stepping lost exactly one known container in the ten sampled windows, and
won nothing on the six census windows [verified].

### Where they are better

1. **Completeness is part of their validity test.** Requiring `at + length <= buffer` means a
   reported nested container is a container you can read. Our 26 unbounded headers out of 55
   (`docs/RPF9.md:48`) would be reported by them as nothing, and that is the right answer for an
   extractor: it never hands out a truncated archive [verified]. This is the stronger design for
   extraction, and if our scan is ever used to extract rather than to measure, this check should be
   imported [hypothesis: it can be added without changing the census counts].
2. **Their stepping is also a false-positive filter, and a free one.** A candidate must both parse
   and describe a whole container; ours trusts the magic and six constant words
   (`tools/rpf9.py:54-64`), with an ordering check (`w08 < w04`) only in the census script
   (`raw/comparativa/nested_scan.py:32`), and no size coherence at all [verified]. On complete
   archives their gate is strictly stronger.
3. **Cost.** A 4 KiB step is 1/4096 of the offsets; our scan pays a magic search plus a constant
   check per hit, and the byte scan over the ten windows in `raw/comparativa/nested_scan.txt` runs in
   one pass [verified]. Theirs is cheaper; ours is affordable, which is why the alignment assumption
   could be dropped.

### Where ours adds

The 4 KiB assumption is a bet on the writer's alignment, and it is a bet that can lose: `0xaa0` is
evidence that the sample set contains at least one nested header that a stepping scan misses
[verified]. It also means their census of nested containers is a lower bound, while ours — after
reconstruction — can state a count per window and a size per container [verified]. Neither tool
decrypts the TOC, so both are guessing container extents from the trailer; ours uses a table of
observed block-0 values keyed by `w24` plus an entropy check (`tools/rpf9.py:282-299`), theirs uses
the last non-zero byte before the next archive (`rpf9-extract/src/container.rs:95-105`) [verified].
Ours is exact when the block-0 table has the `w24`; otherwise it falls back to the zero gap before
the next header and reports `unbounded` when there is no next header in the window. Theirs is
general but heuristic. That is a real trade, not a clear win.

## 3. Table geometry

### Their model: 16 bytes per record

Both Rust readers fix the record width at 16 bytes — `RECORD` in
`rpf9-extract/src/container.rs:11` and `RECORD_SIZE` in `rpf9/src/lib.rs:14` — and derive the record
count by dividing the table length (`rpf9-extract/src/container.rs:50-52`) [verified]. Both reject a
header whose tables are not multiples of 16 (`rpf9-extract/src/container.rs:32`,
`rpf9/src/header.rs:86-97`) [verified]. Neither has any code for a 9-, 10- or 12-byte stride: a
grep for `stride` over both source trees returns nothing [verified]. They do read the fields that
select the stride — `0x2c` is parsed as a `u32` (`rpf9/src/header.rs:111`) and printed as an unknown
(`rpf9-extract/src/report.rs:138`) — but nothing acts on its low byte [verified]. `0x20` is split
into two `u16` and named `version`/`platform` in `rpf9/src/header.rs:107-108`; the high half that
selects the wider subtable is stored, not interpreted [verified].

The consequence is visible on a real archive: `levels.rpf` has `w24 = 2,078` and a
`[w08..w04)` region of 20,784 B, which their arithmetic reads as 1,299 records for 2,078 entries
(`raw/cabeceras/README.md:47-48`) [verified].

### Our model: the header predicts the table

`w04 - w08 == ceil(stride * w24 / 16) * 16` with `stride = 9` or `10` selected by the low byte of
`+0x2c`, and `12` in the clean high-half-2 cases (`docs/RPF9.md:30`, `docs/NESTED.md:26-33`)
[verified]. It holds 54/54 for 9, 15/15 for 10 (69/69 for the high-half-1 set) and 22/22 on the 22
outer fixtures (`raw/cabeceras/README.md:42`); for high-half-2 it fits 12 in 13 clean cases plus 2
that need `w24 + 1`, with one header that still uses stride 10 (`docs/NESTED.md:29-33`) [verified].
That is what lets a header predict its own subtable size and lets the nested census report entry
counts without decrypting anything [verified].

### Which is better, and for what

For **carving**, the 16-byte model is enough and simpler. Both tools skip the encrypted TOC
entirely, find payload members by scanning for zlib/known formats
(`rpf9-extract/src/scan.rs:95-107`, `rpf9/src/scan.rs:282-291`) and reconstruct the archive extent
from the trailer [verified]. The record count never feeds a file offset, so 1,299 instead of 2,078
costs them a printed number, not an extraction [verified]. The alignment check they do enforce is
also a useful false-positive filter that our header validator does not have [verified].

For **describing the container**, the stride model is the one that matches the format: it explains
the width of `[w08..w04)`, why that region is padded to 16, and gives the width for the 18
high-half-2 headers [verified]. Without it, the only honest
output is "the region is N bytes", which is what their `records()` amounts to.

Two soft spots on our side, stated plainly. Our tool computes the formula but does not enforce it:
`tools/rpf9.py:86-92` records whether the prediction matches as a note and accepts the header either
way [verified]. Their alignment gate would reject a malformed table; ours would report it. And our
stride table is a measured rule with two accounted exceptions (`docs/NESTED.md:31-33`) over 22
header fixtures (`raw/cabeceras/README.md:42`) and 122 nested headers from six archives
(`docs/NESTED.md:16`), not a law [verified].

## What to take from each side

- From `PercyStar`: a PSIN body decoder (structs, enums, instances, fixups) and the habit of clamping
  at the end of a short body; our census is the measurement, their code is the reader [verified].
- From `rpf9-extract` / `zeozeozeo/rpf9`: the completeness check `at + length <= buffer` before a
  nested header is accepted, and 4 KiB stepping as a cheap prefilter; both fit the current scan
  without changing the census counts [hypothesis].
- From this repository: the 9/10/12-byte stride formula, the two-phase `LSCH`/`LENM` layouts, and the
  `0xaa0` nested header as a test vector for any discovery loop that assumes 4 KiB alignment
  [verified].

## What this comparison does not cover

- **No third-party binary was executed.** Claims about their behavior on real archives are
  inferences from their source, not from a run [verified]; a build could behave differently
  [hypothesis].
- **Only the parser, discovery and report modules were read.** Each repository has more code
  (PercyStar alone is a large browser); a feature could exist elsewhere [verified].
- **Our PSIN census is a 78-window sample**, not the 22-archive population of 15,380 streams
  (`docs/PSIN.md:9-12`); the counts above describe the windows and say so [verified].
- **The 107 truncated streams and the 26 unbounded nested sizes** are limits of windowed sampling,
  not measured format properties [hypothesis].
- **`open-vfs`**, which our PSIN doc quotes for the chain order, was not cloned or reviewed here
  [verified].
