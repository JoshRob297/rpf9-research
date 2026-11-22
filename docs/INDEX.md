# Full-scan coverage

**English** · [Español](INDEX.es.md)

The sweep covered the **22 `.rpf` containers** of the package: 150.2 GiB out of 208.5 GiB. What
sits outside are 57 `.ttpf` files (57.9 GiB) that were measured and discarded — header `RDS5`,
7.97 bits per byte of entropy, zero recoverable paths. That is not an omission, it is a result:
without the key there is nothing to extract there.

- 71 chunks of 2.2 GB, processed one at a time
- 1,489,677 streams walked
- **177,087 streams carry a name (11.89%)**
- **155,214 unique paths** and **200,184 unique identifiers**
- 526,581 path mentions in total

## Coverage by stream type

| type | streams | named | coverage |
|---|---:|---:|---:|
| `sgd5_shader_dxbc` | 25,043 | 25,043 | **100.00%** |
| `xml` | 332 | 191 | 57.53% |
| `rsc50` | 531,370 | 123,889 | 23.32% |
| `xml_chunk` | 504 | 109 | 21.63% |
| `raw` | 690,003 | 26,766 | 3.88% |
| `PSIN` | 15,380 | 465 | 3.02% |
| `0DRP` | 227,045 | 624 | 0.27% |

Shaders come out complete because their header block stores the program name in plain text.
`0DRP` stays closed: 227 thousand containers and 624 names.

## Per container

| archive | streams | named | path mentions | identifiers |
|---|---:|---:|---:|---:|
| `anim.rpf` | 130,509 | 64,785 | 367,190 | 3,547 |
| `levels.rpf` | 1,020,092 | 62,228 | 6,448 | 447,167 |
| `shaders.rpf` | 29,248 | 25,050 | 7 | 25,043 |
| `packs.rpf` | 144,364 | 16,634 | 166 | 917,698 |
| `story000.rpf` | 58,828 | 6,962 | 142,012 | 3,208 |
| `story000_restofworld` | 624 | 415 | 2,102 | 2,768 |
| `core_restofworld` | 2,371 | 386 | 56 | 6,166 |
| `common.rpf` | 954 | 226 | 8,261 | 8,399 |
| `shared_minigame000` | 5,074 | 163 | 158 | 3,195 |
| `navmeshes.rpf` | 90,304 | 96 | 95 | 231 |
| `audio.rpf` | 838 | 68 | 17 | 9,010 |
| `textures.rpf` | 2,749 | 41 | 4 | 1,875 |
| `core_restofworld001` | 33 | 33 | 65 | 47 |
| `movies.rpf` | 0 | 0 | 0 | 0 |
| `script.rpf` | 1,057 | 0 | 0 | 0 |
| `story000_script` | 2,632 | 0 | 0 | 0 |

## Two negative results, measured

`movies.rpf` produced zero streams: its whole content is Bink 2, with no zlib streams and no mount
XML. `script.rpf` and `story000_script` do have streams, but none with a name.

## What these numbers do not say

A named stream is **not** a table-of-contents entry. The TOC is still encrypted and was not
decoded: the names come from the mount XMLs that travel in plain text inside the payload. That is
why coverage is 11.89% and not 100% — there is no known method to close the gap without the key.

There is also no one-to-one mapping between name and block: several streams can declare the same
path, and `paths.tsv` keeps every mention with its absolute offset so that this stays auditable.

## What the names look like

They are not classical filesystem paths. Three shapes coexist:

```
pack:/get_out_walk_90.clip                        animation clips
Tequesta/Perschars/Peds/Player/bk_lucia_...       character models, per district
platform:/levels/americas/gameshapes/...          level meshes
doorinfo/uidoors_TR_ABI_Airbase_Islands.pso.meta  door metadata
```

`raw/muestra-rutas.txt` holds 20 examples with their archive and offset of origin.

## Verifying without publishing the names

The full index is not published: 155,214 paths would reconstruct the game's asset manifest. What
is published instead lets anyone check their own extraction against ours.

```
raw/paths.sha256       155,214 hashes, sorted
raw/ids.sha256         200,184 hashes, sorted
raw/index.schema.json  column layout and counts
```

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

Running both over the same package reproduces the counts in this document exactly: 68 chunks,
1,489,677 streams, 177,087 named, 155,214 unique paths.
