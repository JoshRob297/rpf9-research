# RPF9 Container Analysis (GTA VI Xbox Series X|S)

## 1. Sample Inventory and Scope Limits

- `/home/sistver/proyectos/rpf9-research/samples/` now contains all **22** RPF9 archives split across **78** binary files (`.head.bin`, `.q1.bin`, `.q3.bin`, `.tail.bin`, and 3 `.full.bin` complete packs; `appdata0.head.bin` is also complete) (`raw/cabeceras2.txt`, lines 5–6). Note: the worktree `samples/` directory holds `MANIFEST.md` only; the binaries reside directly under `/home/sistver/proyectos/rpf9-research/samples/` (no `pack/` subdirectory).
- Across those 78 files, **77** validated RPF9 headers (**76** unique `archive_id`s: 22 outer/pack + 55 nested occurrences; `script.head.bin @0xc4000` and `script.tail.bin @0x9bcd0` overlap) were identified (`raw/cabeceras2.txt`, lines 59–140).
- **Exact real archive sizes** (`raw/cabeceras2.txt`, lines 153–175):
  - **4 complete archives**: `story000_bvh4.full.bin` (**5,632** B, `0x1600`), `appdata0.head.bin` (**8,880** B, `0x22b0`), `core_licenses_data.full.bin` (**13,536** B, `0x34e0`), `core_restofworld001.full.bin` (**791,984** B, `0xc15b0`).
  - **2 overlap-reconstructed archives**: `common.rpf` (**6,642,192** B, `0x655a10`) and `script.rpf` (**4,358,960** B, `0x428330`).
  - **16 remaining archives** (`anim`, `audio`, `core_bvh4`, `core_restofworld`, `data`, `levels`, `movies`, `navmeshes`, `packs`, `shaders`, `shared_minigame000`, `shared_minigame000_bvh4`, `story000`, `story000_restofworld`, `story000_script`, `textures`): **> 16 MiB** estimated lower bound because `head`, `q1`, `q3`, and `tail` have zero overlaps (`raw/cabeceras2.txt`, lines 153–175).

## 2. Physical Container Layout

Every RPF9 container (outer and nested) follows a 5-region physical layout (`raw/cabeceras.txt`, lines 73–84; `raw/cabeceras2.txt`, lines 153–194; `raw/toc.txt`, §§1, 5):

1. **`[0x00 .. 0x40)` (64 bytes)**: Plaintext header (16 x `uint32` little-endian).
2. **`[0x40 .. w04)` (`w04 - 64` bytes)**: Encrypted Head TOC region (16-byte aligned; Shannon entropy `7.6043`–`7.9983` bits/byte). Split internally at `w08`: `[0x40 .. w08)` (`>= 512` bytes, `34,272` B in `shaders.head.bin`) and `[w08 .. w04)` (`9` or `10` bytes/entry for `w20_hi == 1`).
3. **`[w04 .. first_payload)`**: Zero-padding to `0x1000` (4,096-byte) alignment in most containers; in `appdata0` (`w04=0x360`), `common` (`w04=0x9580`), `story000_bvh4` (`w04=0x340`), and `core_restofworld` (`w04=0xaa0` -> nested RPF9 immediately at `0xaa0`), payload #0 starts directly at `w04` (`raw/cabeceras2.txt`, lines 154, 159, 171; `raw/payload.txt`, line 171).
4. **Payload entries**: Mixed unencrypted (`78 da` zlib streams, `SGD5` shader database, `KB2n` Bink 2 video, `EDUP`, `LRSC`/`0DRP`/`CHKS`/`LGID` resources, nested `RPF9`s) and high-entropy/encrypted payloads (`raw/payload.txt`, §§1–5).
5. **`[EOF - w0c .. EOF)` (`w0c` bytes)**: Encrypted trailer at the exact end of outer archives (preceded by `0` to `3,886` zero-padding bytes) and at the exact end of every bounded nested RPF9 (`raw/cabeceras2.txt`, lines 153–194; `raw/payload.txt`, lines 158–212).

## 3. Header Structure (`0x00 .. 0x3F`, 64 bytes LE)

| Offset | Type | Observed Values (77 Headers) | Role & Certainty | Source |
|---|---|---|---|---|
| `0x00` | `u32` | `0x52504639` (`39 46 50 52`) | **Confirmed**: Magic `"RPF9"` little-endian (77/77 headers) | `raw/cabeceras2.txt` lines 7–140 |
| `0x04` | `u32` | `608` .. `219,840` (mult. of 16) | **Confirmed**: End offset (`w04`) of encrypted Head TOC `[0x40..w04)` | `raw/cabeceras2.txt` lines 31–140, 153–175 |
| `0x08` | `u32` | `576` .. `187,600` (mult. of 16) | **Confirmed bounds / Plausible role**: Internal TOC split (`w08 <= w04`). For `w20_hi == 1` (**69/69**), `w04 - w08 = ceil(9*w24/16)*16` when `w2c_b0 == 1` (`54/54`) and `ceil(10*w24/16)*16` when `w2c_b0 == 2` (`15/15`); `w08 - 64 >= 512` B (`34,272` B in `shaders`) | `raw/cabeceras2.txt` lines 142–150; `raw/toc-chico.txt` H-C3 |
| `0x0c` | `u32` | `48` .. `135,600` (mult. of 16) | **Confirmed location / Plausible name-table role**: Exact byte length (`w0c`) of encrypted trailer at `[EOF - w0c .. EOF)`; fits `32 B + sum(len(path)+1)` on complete XML packs (`137<=144`, `143<=144`, `215<=240`) | `raw/cabeceras2.txt` §5–6; `raw/toc-chico.txt` H-C4, H-C5 |
| `0x10..0x17` | `u64` | Distinct 64-bit value per unique archive | **Indeterminate**: Unique archive ID / salt (76/76 unique); does not alter `0x40..0x5f` or trailer block 0 | `raw/cabeceras2.txt` lines 60–140 |
| `0x18` | `u32` | `0x00047a00` (`293,376`) | **Confirmed constant**: Identical across all 77 headers | `raw/cabeceras2.txt` lines 31–140 |
| `0x1c` | `u32` | `0x00000150` (`336`) | **Confirmed constant**: Identical across all 77 headers | `raw/cabeceras2.txt` lines 31–140 |
| `0x20` | `u32` | `0x00010003`..`0x00020007` | **Plausible**: `u16` low `3..7`, `u16` high `1..2`; `w20_hi == 2` (`8/77` headers) selects wider `[w08..w04)` stride and alters trailer block 0 (`w24=3`) | `raw/cabeceras2.txt` lines 146–150; `raw/toc-chico.txt` H-C4 |
| `0x24` | `u32` | `1` .. `3,224` | **Confirmed on complete small files**: Exact payload entry count (`4==4` `story000_bvh4`, `2==2` `appdata0`, `4==4` `core_licenses_data`, `2==2` nested `@0x1000`, `6==6` `core_restofworld001`, `22==22` page-aligned groups in nested `@0x1000`); determines `[w08..w04)` size and trailer block 0 | `raw/cabeceras2.txt` lines 177–194 |
| `0x28` | `u32` | 5 discrete values (`0xd98004d5`, `0xda72573e`, `0xc0a92754`, `0xd5c19f6b`, `0x5a5b4c6f`) | **Indeterminate**: Build/key-tag candidate; does not alter `0x40..0x5f` or trailer block 0 | `raw/cabeceras2.txt` lines 31–140; `raw/toc-chico.txt` H-C4 |
| `0x2c` | `u32` | `0x00090f01` (`w24<=194`) or `0x00090f02` (`w24>=265`) | **Confirmed flag**: Low byte `1 -> 2` switches `[w08..w04)` stride from `9` to `10` bytes/entry across all 69 `w20_hi == 1` headers | `raw/cabeceras2.txt` lines 143–145; `raw/toc-chico.txt` H-C3 |
| `0x30` | `u32` | `0x00000010` (`16`) | **Confirmed constant**: 16-byte alignment/block unit across all 77 headers | `raw/cabeceras2.txt` lines 31–140 |
| `0x34..0x3c` | `3xu32` | `0, 0, 0` | **Confirmed zero**: Reserved padding across all 77 headers | `raw/cabeceras2.txt` lines 31–140 |

**Coherence with real file sizes**: Across all 4 complete files and 2 overlap-reconstructed archives (`appdata0` `8,880`, `story000_bvh4` `5,632`, `core_licenses_data` `13,536`, `core_restofworld001` `791,984`, `common` `6,642,192`, `script` `4,358,960`), `w04 + w0c <= real_size` and **no** 32-bit header field stores the total archive size (`size_in_hdr=False`, `raw/cabeceras2.txt`, lines 153–175).

## 4. Payload Findings (`raw/payload.txt`)

- **Valid `78 da` zlib streams (`raw/payload.txt`, lines 4–115)**: **16,213** valid streams across the 78 files: **477** XML (`CDataFileMgr__ContentChangeSetDef`, `CDataFileMgr__ContentDef`, `SSetupData`, gameplay metadata), **4,066** `PSIN` (compiled scripts), **872** `0DRP`, **4,357** `rsc50` (`\x00*8...0x50` paged RAGE resources, e.g., 22 page-aligned groups / 29 chunks inside `core_restofworld001 @0x1000`), and **6,441** raw/other (including AMD shader microcode chunks in `shaders.q3/tail.bin`).
- **`SGD5` shader block (`raw/payload.txt`, lines 117–154)**: Located at `shaders.head.bin @0x9000` (`magic="SGD5"`, `u04=0xa08b72b3`, `u08=0x60555dc2`, `sub_count_u32=33`, `first_section_bytes=2112` ending at `0x9858`). Contains **31** sequential 8-byte record tables (`2,419` total `[b0, b1, idx_u16, hash_u32]` records in `[0x9030..0xdf68)`), followed by **737** `[VDHGMCP]S_*_Wrapped` symbol strings in `shaders.head.bin` (`133` in `shaders.q1.bin`).
- **Nested `RPF9` containers (`raw/payload.txt`, lines 156–212)**: **55** occurrences (**54** unique `archive_id`s). Exact byte sizes are reconstructed for **29** bounded nested RPF9s (via known trailer block-0 or pre-next-RPF9 zero gaps, e.g. `core_licenses_data @0x1000` = `7,760` B, `core_restofworld001 @0x1000` = `785,200` B, `core_restofworld @0xaa0` = `912` B, `script @0x1000` = `797,584` B, `anim @0x5000` = `4,896` B, `levels @0x1c000` = `197,776` B, `textures @0x1000` = `2,249,840` B); the remaining **26** are truncated/unbounded in their sample window.
- **Other unencrypted signatures**: `KB2n` (`movies.head/tail.bin`), `EDUP` (`core_restofworld001 @0xc14a0` corresponding to `ttdb/globalduplicates`, `shared_minigame000.tail @0x3fe8f0`, `story000.tail @0x3f7af0`), `LRSC`/`0DRP`/`CHKS`/`LGID`.

## 5. Cryptography, Small-TOC Attack, and Hypothesis Table

- **TOC & Trailer Encryption (`raw/toc.txt`; `raw/toc-chico.txt`)**:
  - All 77 headers exhibit high-entropy TOCs (`[0x40..w04)`) sharing the 32-byte prefix `5f08daab...` at `[0x40..0x60)` and diverging with zero intra-TOC duplicates and high-entropy XOR (`ent=7.57..7.71`) from `0x60` onward.
  - Trailers `[EOF - w0c .. EOF)` exhibit **exact block-0 collisions** determined purely by `(w24, w20_hi)` (`w24=1 -> aa0405b9...`, `w24=2 -> b7da7c1d...`, `w24=3 -> f11ce775...`, `w24=4 -> 5a178c51...`, `w24=10 -> e0b5ed97...`, `w24=22 -> bae2486f...`, `w24=39 -> 9b038e98...`), and **exact 32-byte (block 0 + block 1) collisions** whenever `(w24, w20_hi, w0c)` match across completely unrelated archives: `appdata0` vs `script @0x1000` (`w24=2, w0c=64`) and `core_licenses_data` vs `story000_bvh4` (`w24=4, w0c=144`), diverging at block 2 (`[32..)`) where archive-specific names begin (`raw/toc-chico.txt`, H-C4).
- **RPF7 Keys**: **no verificado** — proprietary GTA V AES keys (`GTA5.exe` / `gta5keys.bin`) are absent from open-source tools and this environment (`raw/toc.txt`, §6).

| ID | Hypothesis | Prediction | Test & Evidence | Result |
|---|---|---|---|---|
| H1 | RPF9 starts with 64-byte plaintext header; `w04` ends TOC | Non-zero TOC spans `[0x40..w04)` followed by zeros or payload #0 | Verified across all 22 outer headers (`raw/cabeceras.txt` §4; `raw/cabeceras2.txt` §5) | **confirmed** |
| H2 | A header field stores total archive byte size | One of the 16 `u32` fields equals exact archive size | Checked against 4 `.full`/complete + 2 overlap sizes (`raw/cabeceras2.txt` §5, `size_in_hdr=False`) | **refuted** |
| H3 | Plaintext ASCII paths exist at EOF (`tail`) or in small TOCs | Low-entropy plaintext paths in `[0x40..w04)` or `[EOF-w0c..EOF)` | Entropy `7.42`–`7.96` at EOF; 0 ASCII path hits in `appdata0`, `story000_bvh4`, `core_licenses_data`, `core_restofworld001` (`raw/toc.txt` §5; `raw/toc-chico.txt` H-C1) | **refuted** |
| H4 | `w0c` is encrypted trailer length at `[EOF - w0c .. EOF)` | Every outer & nested container ends with `w0c` high-entropy bytes | Verified on 4 outer complete files + 29 bounded nested RPF9s (`raw/cabeceras2.txt` §5; `raw/payload.txt` §4) | **confirmed** |
| H5 | TOC `[0x40..w04)` uses AES-ECB | Large TOCs repeat 16-byte ciphertext blocks | 0 intra-TOC duplicates in 62,487 blocks (`raw/toc.txt` §2) | **refuted** |
| H6 | TOC `[0x40..w04)` uses fixed-nonce CTR / stream cipher | `C1 ^ C2` from `0x60` shows low entropy / high zero rate | `C1 ^ C2` yields entropy `7.57`–`7.99` even on small `w24=2,4` pairs (`raw/toc.txt` §3; `raw/toc-chico.txt` H-C6) | **refuted** |
| H7 | TOC uses chained block cipher (e.g. AES-CBC fixed IV) with 32B constant prefix | `[0x40..0x60)` matches across archives; `0x60..` diverges | `5f08daab...` at `0x40..0x5f` across all RPF9s; 0 intra-TOC dups (`raw/toc.txt` §2–§3) | **confirmed** (behavioral signature); cipher/key **indeterminate** |
| H8 | `[w08..w04)` width follows `9`/`10` B per `w24` entry (`w20_hi==1`) | `w04-w08 == ceil(9*w24/16)*16` (`w2c_b0=1`) or `ceil(10*w24/16)*16` (`w2c_b0=2`) | Tested across all 77 headers: **54/54** (`9 B`) and **15/15** (`10 B`) exact for `w20_hi==1`; `8/77` `w20_hi==2` use larger stride (`raw/cabeceras2.txt` §4; `raw/toc-chico.txt` H-C3) | **confirmed** (size formula); internal layout **indeterminate** |
| H9 | Payloads inside RPF9 are uniformly encrypted | No unencrypted headers or zlib streams exist | **16,213** valid `78 da` zlib streams, `SGD5`, `KB2n`, `EDUP`, `LRSC`, 55 nested `RPF9`s (`raw/payload.txt` §§1–5) | **refuted** |
| H10 | Public RPF7 keys decrypt RPF9 TOC | Applying static RPF7 keys yields readable TOC | `no verificado` (GTA V keys absent from open repos/environment; trivial keys fail; `raw/toc.txt` §6) | **indeterminate** |
| H11 | `w24` is the exact entry count of an RPF9 container | Countable payloads in complete containers equal `w24` | Verified `4==4` (`story000_bvh4`), `2==2` (`appdata0`), `4==4` (`core_licenses_data`), `2==2` (`core_licenses_data @0x1000`), `6==6` (`core_restofworld001`), `22==22` groups (`core_restofworld001 @0x1000`) (`raw/cabeceras2.txt` §6) | **confirmed** |
| H12 | Small complete files store plaintext `u16`/`u32` sizes or offsets in TOC/trailer | Known sizes (`433`, `496`, `4720`, `0x340`, `0x1000`) appear in `[0x40..w04)` or `[EOF-w0c..EOF)` | 0 `u32le`/`u32be`/`u16le` matches across 4 small complete containers; 1 random `u16be` hit (`raw/toc-chico.txt` H-C2) | **refuted** |
| H13 | Trailer `[0..32)` encodes `(w24, w20_hi, w0c)` and `[32..)` holds archive-specific names | Same `(w24, w20_hi)` share `blk0`; same `(w24, w20_hi, w0c)` share `blk0..1` and diverge at `blk2`; `32 + sum(len(path)+1) <= w0c` | Confirmed on `(2,64)` `appdata0` vs `script @0x1000`, `(4,144)` `core_licenses` vs `story000_bvh4`, and path-length sums `137<=144`, `143<=144`, `215<=240` (`raw/toc-chico.txt` H-C4, H-C5) | **confirmed** (32B header role & capacity); exact string encoding **indeterminate** without key |
