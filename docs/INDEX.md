# Full-scan coverage

**English** · [Español](INDEX.es.md)

The package is 208.5 GiB. The **22 `.rpf` containers** account for 150.2 GiB of it; the other
57.9 GiB are 57 `.ttpf` files that were measured and discarded — header `RDS5`, 7.97 bits per byte
of entropy, zero recoverable paths. That is not an omission, it is a result: without the key there
is nothing to extract there.

The first pass read **123.0 GiB (81.9%)** of them in 68 slices of 2.2 GB. A gap pass read 13 of the
15 slices that were missing, and a completion pass read the last two — `core_bvh4` (7.7 GiB, cut into
eight pieces after the whole file exhausted the container's memory) and one `story000` slice. The
containers are now **fully covered**.

- 92 slices of 2.2 GB or less, in three rounds
- 2,235,084 streams walked
- **215,028 streams carry a name (9.62%)**
- **168,660 unique paths** and **511,526 unique identifiers**
- 611,264 path mentions in total

The ratio fell from 11.89% to 9.62% because the last 27.2 GiB were dense in streams and thin in
names: `core_bvh4` alone holds 565,591 streams and names 12 of them. The counts went up; the
percentage followed the data rather than the other way round.

## Coverage by stream type

| type | streams | named | coverage |
|---|---:|---:|---:|
| `sgd5_shader_dxbc` | 25,043 | 25,043 | **100.00%** |
| `xml` | 349 | 208 | 59.60% |
| `xml_chunk` | 510 | 115 | 22.55% |
| `rsc50` | 872,918 | 154,782 | 17.73% |
| `PSIN` | 18,590 | 1,129 | 6.07% |
| `raw` | 1,032,855 | 30,826 | 2.98% |
| `0DRP` | 284,819 | 2,925 | 1.03% |

Shaders come out complete because their header block stores the program name in plain text.
`0DRP` stays closed: 285 thousand containers and 2,925 names, up from 227 thousand and 624 when only
the first pass had run.

## Per container

| archive | streams | named | path mentions | identifiers |
|---|---:|---:|---:|---:|
| `levels` | 1,086,499 | 62,743 | 6,692 | 447,622 |
| `core_bvh4` | 565,591 | 12 | 3,827 | 4 |
| `packs` | 144,364 | 16,634 | 166 | 917,698 |
| `story000` | 141,161 | 39,664 | 217,907 | 311,264 |
| `anim` | 130,509 | 64,785 | 367,190 | 3,547 |
| `navmeshes` | 90,304 | 96 | 95 | 231 |
| `shaders` | 29,248 | 25,050 | 7 | 25,043 |
| `data` | 28,509 | 4,700 | 4,639 | 84,675 |
| `shared_minigame000` | 5,074 | 163 | 158 | 3,195 |
| `textures` | 2,749 | 41 | 4 | 1,875 |
| `story000_script` | 2,632 | 0 | 0 | 0 |
| `shared_minigame000_bvh4` | 2,560 | 5 | 12 | 4 |
| `core_restofworld` | 2,371 | 386 | 56 | 6,166 |
| `script` | 1,057 | 0 | 0 | 0 |
| `common` | 954 | 226 | 8,261 | 8,399 |
| `audio` | 838 | 68 | 17 | 9,010 |
| `story000_restofworld` | 624 | 415 | 2,102 | 2,768 |
| `core_restofworld001` | 33 | 33 | 65 | 47 |
| `story000_bvh4` | 4 | 4 | 63 | 3 |
| `core_licenses_data` | 3 | 3 | 3 | 2 |
| `movies.rpf` | 0 | 0 | 0 | 0 |

## Two negative results, now measured on the whole file

`movies.rpf` produced zero streams across its **entire 8.8 GiB**, both halves read: everything in it is
Bink 2, with no zlib streams and no mount XML. The first pass had only reached 52% of the file, so this
result used to be partial; the completion pass closed it.

`script.rpf` and `story000_script` do have streams, but none with a name. Both were read end to end.

## The gap, and what it held

The first pass read 123.0 GiB of the 150.2 GiB and left 27.2 GiB in 15 uncarved slices. The completion
pass read all of them, so the containers are now covered in full:

| archive | slice that was missing | what it returned |
|---|---|---|
| `core_bvh4` | 7.73 GiB | 565,591 streams, 12 named |
| `story000` | 6.44 GiB | 82,333 streams, 32,702 named |
| `audio.rpf` | 4.30 GiB | 0 streams |
| `levels.rpf` | 4.30 GiB | 66,407 streams, 515 named |
| `movies.rpf` | 3.93 GiB | 0 streams |
| `data.rpf` | 0.45 GiB | 28,509 streams, 4,700 named |
| `shared_minigame000_bvh4` | 0.06 GiB | 2,560 streams, 5 named |
| `appdata0`, `story000_bvh4`, `core_licenses_data` | < 1 MiB | 7 streams |

Between the two rounds the gap added **745,407 streams**, of which **37,941 carry a name**, plus
**13,446 paths** and **311,342 identifiers** that were not in the first index. `data.rpf` had never
been walked, and `core_bvh4` turned out to be the opposite of what its size suggests: a quarter of
the package's streams and a dozen names.

## What the names look like

They are not classical filesystem paths. Three shapes coexist:

```
pack:/get_out_walk_90.clip                        animation clips
Tequesta/Perschars/Peds/Player/bk_lucia_...       character models, per district
platform:/levels/americas/gameshapes/...          level meshes
doorinfo/uidoors_TR_ABI_Airbase_Islands.pso.meta  door metadata
```

`raw/muestra-rutas.txt` holds 20 examples with their archive and offset of origin, and
`raw/muestra-rutas-v2.txt` holds 200 drawn from the complete index.

## Verifying without publishing the names

The full index is not published: 168,660 paths would reconstruct the game's asset manifest. What is
published instead lets anyone check their own extraction against ours.

```
raw/paths.sha256        155,214 hashes, sorted   (first pass)
raw/ids.sha256          200,184 hashes, sorted   (first pass)
raw/paths.v2.sha256     168,660 hashes, sorted   (complete index)
raw/ids.v2.sha256       511,526 hashes, sorted   (complete index)
raw/muestra-rutas-v2.txt  200 paths with archive and offset
raw/index.schema.json   column layout and counts
```

Both versions stay published. The v1 set is the fingerprint of what the first sweep found; anyone who
already diffed against it keeps a stable reference. The v2 set is the complete one, and it is a
superset: every v1 hash appears in v2.

The hash is `sha256("rpf9-research/2026-11" + "\t" + name)`. The salt is public on purpose: it
lets two parties compare coverage without either revealing a name.

To compare: run `tools/name_recover.py` over the same chunks of your own package, take your unique
names, apply the same salt, sort, and diff against the file. Missing hashes are streams your
walker did not reach; extra ones are names we did not recover. Counts, not contents.

## Relation to the TOC geometry

The 9–10 byte entry stride documented in `docs/RPF9.md` (and the 16-byte alignment of the table
region) is a separate measurement: it describes the table layout, not the name coverage. This
document only reports how many streams carry a name and where those names come from.

## Reproduce

```
tools/name_recover.py <chunk.bin> --out <output>.json      # one 2.2 GB chunk
tools/merge_index.py <chunks_dir> <output_dir> \
    --skip packs_1.json,packs_2.json,packs_3.json          # merges, adding each chunk base
```

Running both over the same package reproduces the counts in this document exactly: 92 slices (68 in
the first pass, 13 in the gap pass, 11 in the completion pass), 2,235,084 streams, 215,028 named,
168,660 unique paths.
