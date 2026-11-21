# RPF9 Container Analysis (GTA VI Xbox Series X|S)

## 1. Sample Inventory and Scope Limits

- `README.md` and the task brief reference 22 `.rpf` archives, whereas `/home/sistver/proyectos/rpf9-research/samples/` and `samples/MANIFEST.md` actually contain **12** RPF archives split into **47** binary windows (`head`, `q1`, `q3`, `tail`; `appdata0` has 3 windows) (`raw/cabeceras.txt`, lines 4–5, 73–84).
- Across those 47 windows, **31** valid RPF9 headers (**30** unique; `script.head.bin @0xc4000` and `script.tail.bin @0x9bcd0` overlap and represent the same nested container) were identified (`raw/cabeceras.txt`, lines 41–70).
- **Exact real archive sizes** reconstructed from overlapping windows (`raw/cabeceras.txt`, lines 73–84):
  - `appdata0.rpf`: **8,880** bytes (`0x22b0`, full file in `appdata0.head.bin`; `q1` starts at `2220`, `q3` at `6660`).
  - `common.rpf`: **6,642,192** bytes (`0x655a10`, `head->tail` overlap at `rel=2447888` + `4194304`).
  - `script.rpf`: **4,358,960** bytes (`0x428330`, `head->tail` overlap at `rel=164656` + `4194304`).
  - Remaining 9 archives (`anim`, `audio`, `data`, `levels`, `movies`, `navmeshes`, `packs`, `shaders`, `textures`): **> 16 MiB** estimated lower bound because `head` (4 MiB), `q1` (2 MiB), `q3` (2 MiB), and `tail` (4 MiB) have zero overlaps (`raw/cabeceras.txt`, lines 73–84).

## 2. Physical Container Layout

Every RPF9 container follows a 5-region physical layout (`raw/cabeceras.txt`, lines 73–84; `raw/toc.txt`, sections 1 & 5):

1. **`[0x00 .. 0x40)` (64 bytes)**: Plaintext header (16 x `uint32` little-endian).
2. **`[0x40 .. w04)` (`w04 - 64` bytes)**: Encrypted Head TOC region (16-byte aligned; Shannon entropy `7.6043` to `7.9983` bits/byte; `raw/toc.txt`, section 1). Internally split by `w08` (`64 < w08 < w04`).
3. **`[w04 .. first_payload)`**: Zero-padding to `0x1000` (4,096-byte) alignment in 10 of 12 outer archives and all observed nested RPF9s; in `appdata0` (`w04=0x360`) and `common` (`w04=0x9580`), small payload data begins immediately at `w04` (`raw/cabeceras.txt`, lines 74, 76).
4. **Payload entries**: Mixed unencrypted (`78 da` zlib streams, `KB2n` Bink 2 video, `SGD5` shaders, `LRSC`/`0DRP`/`CHKS`/`LGID` resources, nested `RPF9`s) and high-entropy/encrypted payloads (`raw/firmas.txt`, sections 2–3).
5. **`[EOF - w0c .. EOF)` (`w0c` bytes)**: Encrypted trailer at the exact end of outer archives (preceded by `4` to `3,886` zero-padding bytes in 10 of 12 archives; `0` preceding zeros in `appdata0` and `script`; `raw/toc.txt`, section 5) and after the final payload inside nested RPF9s (e.g., `anim.head.bin` `@0x62e0..0x6320` for `w0c=64`).

## 3. Header Structure (`0x00 .. 0x3F`, 64 bytes LE)

| Offset | Type | Observed Range / Values | Role & Certainty | Source (`raw/cabeceras.txt`) |
|---|---|---|---|---|
| `0x00` | `u32` | `0x52504639` (`39 46 50 52`) | **Confirmed**: Magic `"RPF9"` little-endian (31/31 headers) | lines 11–22, 41–70 |
| `0x04` | `u32` | `608` .. `219,840` (mult. of 16) | **Confirmed**: End offset (`w04`) of encrypted Head TOC `[0x40..w04)`; non-zero bytes stop at `w04 - 1` | lines 26–37, 73–84 |
| `0x08` | `u32` | `576` .. `187,600` (mult. of 16) | **Plausible**: Internal Head TOC boundary (`w08 <= w04`). Difference `w04 - w08` is `16`..`32,240` and scales with `w24` (~9–18 B/entry; exact `ceil(10*w24/16)*16` in 10/30 unique headers) | lines 26–70 |
| `0x0c` | `u32` | `48` .. `119,520` (mult. of 16) | **Confirmed location / Plausible role**: Exact byte length (`w0c`) of encrypted trailer at `[EOF - w0c .. EOF)`; scales ~9.5–105.9 B/`w24` (candidate encrypted name/metadata table) | lines 26–70, `raw/toc.txt` §5 |
| `0x10..0x17` | `u64` | Distinct 64-bit value per archive | **Indeterminate**: Unique archive ID / salt / hash (30/30 unique); does not alter `0x40..0x5f` ciphertext | lines 41–70 |
| `0x18` | `u32` | `0x00047a00` (`293,376`) | **Confirmed constant**: Identical across all 31 headers | lines 26–37, 41–70 |
| `0x1c` | `u32` | `0x00000150` (`336`) | **Confirmed constant**: Identical across all 31 headers | lines 26–37, 41–70 |
| `0x20` | `u32` | `0x00010003`..`0x00020006` | **Indeterminate**: `u16` low `3..7`, `u16` high `1..2`; candidate flags/depth/version | lines 26–70 |
| `0x24` | `u32` | `1` .. `3,224` | **Plausible**: Entry/node count (`w24`); drives `w04 - w08` and trailer first-block match (`w24=2` in `appdata0` and `script`) | lines 26–70, `raw/toc.txt` §5 |
| `0x28` | `u32` | 5 discrete values (`0xd98004d5`, `0xda72573e`, `0xc0a92754`, `0xd5c19f6b`, `0x5a5b4c6f`) | **Indeterminate**: Build/key-tag candidate; does not alter `0x40..0x5f` ciphertext | lines 26–70 |
| `0x2c` | `u32` | `0x00090f01` (`w24<=194`) or `0x00090f02` (`w24>=265`) | **Plausible**: Subversion/page flag whose low byte switches `1 -> 2` between `w24=194` and `w24=265` | lines 41–70 |
| `0x30` | `u32` | `0x00000010` (`16`) | **Confirmed constant**: 16-byte alignment/block unit across all 31 headers | lines 26–70 |
| `0x34..0x3c` | `3xu32` | `0, 0, 0` | **Confirmed zero**: Reserved padding across all 31 headers | lines 26–70 |

**Coherence with real file sizes**: In all 3 archives with exact reconstructed sizes (`appdata0` = `8,880`, `common` = `6,642,192`, `script` = `4,358,960`), `w04 + w0c <= real_size`, and **no** 32-bit header field stores the total archive size (`size_in_hdr=False`, `raw/cabeceras.txt`, lines 73–84).

## 4. Cryptography, Entropy, and Signatures

- **TOC Encryption**: Every outer TOC (`[0x40..w04)`) exhibits Shannon entropy `7.6043`–`7.9983` bits/byte (`raw/toc.txt`, §1).
- **Mode Evidence (`raw/toc.txt`, §2–§3)**:
  - **0** intra-TOC 16-byte block repetitions across all 12 outer TOCs + 6 largest nested TOCs (`62,487` total 16-byte blocks checked, including `13,736` blocks in `navmeshes @0x1000` and `12,200` in `packs @0x306000`).
  - **Identical first 32 bytes** (`5f08daabecbdd40258c3516807024c24fb9f756755ef4be458785bfed8aa6989`) at `[0x40..0x60)` across all 12 outer archives (and nested RPF9s), despite varying `w04`, `w10..w17`, `w24`, and `w28`.
  - **XOR refutation of stream cipher / fixed-nonce CTR**: `C1 ^ C2` from `0x60` onward yields entropy `7.561`–`7.989` and `0.20%`–`0.39%` zeros (matching uniform random noise, `raw/toc.txt`, §3).
  - Together, these measurements point to **chained block encryption (such as AES-CBC with fixed IV)** over an identical 32-byte TOC prefix, rather than ECB (which would collide on padded/repeated inner blocks) or fixed-nonce CTR.
- **Trailer Encryption (`raw/toc.txt`, §5)**: `[EOF - w0c .. EOF)` has entropy `7.82`–`8.00` (for full trailers), `0` intra-trailer 16-byte duplicates, and `appdata0` + `script` (both `w24=2`) share the exact first 16-byte ciphertext block `b7da7c1d963787c846fe15fd0e243364`.
- **RPF7 Key & Candidate Key Testing (`raw/toc.txt`, §6)**:
  - Trivial/header-derived AES-128/256 ECB and CBC-IV0 keys all fail on `appdata0` TOC (`266–313 / 800` printable bytes, entropy ~`7.74`).
  - Proprietary RPF7 AES keys: **no verificado** — open-source RPF7 tools (`CodeWalker`, `RageLib`, `LibertyV`) do not embed static GTA V keys and instead extract them from local `GTA5.exe` / `gta5keys.bin`, which are not present in this environment.
- **Signatures (`raw/firmas.txt`, §1–§3)**:
  - Requested signatures (`ISG1`, `OSG1`, `DXBC`, `RSC7`, `RDS5`, `DDS `, `RIFF`, `BINK`): **0 exact matches** across all 47 files.
  - Observed real unencrypted signatures: `9FPR` (nested `RPF9`, 19 nested hits), `KB2n` (Bink 2 video at `movies.head.bin @0x7000`, `@0x3b1000`, `movies.tail.bin @0x133610`, `@0x28a610`), `SGD5` (`shaders.head.bin @0x9000`), `LGID`/`LRSC`/`0DRP`/`CHKS` (resource chunks in `anim`, `data`, `levels`, `navmeshes`, `packs`), and thousands of valid unencrypted `78 da` zlib streams decompressing to `<?xml ... CDataFileMgr__ContentChangeSetGroups>`, `PSIN`, and `0DRP`.

## 5. Hypothesis Table

| ID | Hypothesis | Prediction | Test & Evidence | Result |
|---|---|---|---|---|
| H1 | RPF9 starts with a 64-byte plaintext header and `w04` marks the end of the TOC | Non-zero TOC starts at `0x40` and ends at `w04 - 1`, followed by zeros to `0x1000` | Measured across 12 outer `.head.bin` files; 10/12 have `00` padding starting exactly at `w04`, and `appdata0`/`common` pack payload #0 at `w04` (`raw/cabeceras.txt` §4) | **confirmed** |
| H2 | A header field stores total archive byte size | One of the 16 `u32` header fields equals `8,880` (`appdata0`), `6,642,192` (`common`), or `4,358,960` (`script`) | Reconstructed exact sizes via window overlaps and compared against all 16 `u32` header fields (`raw/cabeceras.txt` §4, `size_in_hdr=False`) | **refuted** |
| H3 | Name table lives in plaintext at the end of the archive (`tail`) | Last 4 KB of `.tail.bin` / `appdata0` has low entropy and readable ASCII filenames | Measured last 4 KB entropy `7.42`–`7.96` (`raw/toc.txt` §5) and 0 plaintext path strings; instead discovered an encrypted `w0c`-byte trailer at `[EOF - w0c .. EOF)` | **refuted** (for plaintext at EOF) |
| H4 | `w0c` is the byte length of an encrypted end-of-archive trailer (candidate name/metadata table) | `[EOF - w0c .. EOF)` is bounded by zero-padding before `EOF - w0c` and scales with `w24` | Measured `4`–`3,886` preceding zero bytes before `EOF - w0c` in 10/12 outer archives, exact boundary in nested RPF9s, and identical `b7da7c1d...` first block when `w24=2` (`raw/toc.txt` §5) | **confirmed** (location/size); **indeterminate** (semantic role without key) |
| H5 | TOC `[0x40..w04)` is encrypted with AES-ECB | Large TOCs repeat 16-byte ciphertext blocks on padded/identical fields | Checked `62,487` 16-byte blocks across 12 outer + 6 largest nested TOCs: `0` intra-TOC duplicates (`raw/toc.txt` §2) | **refuted** |
| H6 | TOC `[0x40..w04)` is encrypted with fixed-nonce stream cipher / AES-CTR | XOR of two TOCs (`0x60..`) exhibits low entropy and high zero-byte rate | `C1 ^ C2` on 4 pairs yields entropy `7.561`–`7.989` and `0.20%`–`0.39%` zeros (`raw/toc.txt` §3) | **refuted** |
| H7 | TOC `[0x40..w04)` uses chained block cipher (e.g. AES-CBC fixed IV) with constant 32-byte prefix | First 32 bytes (`0x40..0x5f`) match across archives while `0x60..` diverges with `0` intra-TOC dups | All 12 outer and nested headers share `5f08daab...` at `+0x40..+0x5f`, diverge at `+0x60`, and have `0` intra-TOC dups (`raw/toc.txt` §2–§3) | **confirmed** (behavioral signature); exact cipher/key **indeterminate** without key |
| H8 | `w24` is the entry/node count and `w08` splits an entry-indexed subtable `[w08..w04)` | `w04 - w08` scales linearly with `w24` | Measured `w04 - w08 = ceil(10*w24/16)*16` in 10/30 headers and ~9–18 B/`w24` across all 30 (`raw/cabeceras.txt` §3); exact table meaning requires key | **indeterminate** (strong correlation, unverified without key) |
| H9 | Payloads inside RPF9 are uniformly encrypted | No standard asset magic or zlib streams can be read directly in payloads | Found unencrypted `KB2n`, `SGD5`, nested `9FPR`, `LRSC`/`0DRP`, and >3,000 valid `78 da` zlib streams decompressing to XML/`PSIN` (`raw/firmas.txt` §2–§3) | **refuted** (many payloads are unencrypted/zlib-only) |
| H10 | Public RPF7 keys decrypt RPF9 TOC | Applying public RPF7 AES keys yields readable TOC fields | Static GTA V RPF7 AES keys are not published in open-source tools (`CodeWalker`/`RageLib`/`LibertyV`); trivial/header keys fail (`raw/toc.txt` §6) | **indeterminate** (`no verificado` for proprietary RPF7 key) |
