# RPF9 Payload Name Recovery (`tools/name_recover.py`)

**English** · [Español](NAMES.es.md)

## 1. Purpose and Design Alternatives

Because the RPF9 Head TOC (`[0x40..w04)`) and EOF trailer (`[EOF - w0c .. EOF)`) are encrypted and no decryption key is available (`docs/RPF9.md` §5, H3/H7/H13), original archive entry names cannot be read from the container directory. `tools/name_recover.py` recovers resource paths and identifiers directly from unencrypted payload streams and records explicit provenance per stream.

Three design alternatives were evaluated:

1. **Alternative A — Single `78 da` zlib scan + generic regex**: Reuses `rpf9.py`'s `78 da` scanner and runs one path/extension regex across all decompressed blobs. *Rejected*: misses all `SGD5` raw-deflate (`wbits=-15`) DXBC shader entries (`869` entries in `shaders.head.bin` and `shaders.q1.bin`), conflates structural binary tags (`LSCH`, `LENM`, `0DRPz`) or binary byte sequences with identifiers, and cannot attribute source provenance cleanly.
2. **Alternative B — Multi-source typed extractor (Chosen)**: Combines `78 da` zlib stream inflation (`xml`, `xml_chunk`, `PSIN`, `0DRP`, `rsc50`, `raw`) with `SGD5` inline symbol + raw-deflate `DXBC` parsing (`tools/name_recover.py`), applying ordered source-specific extractors (`xml` -> `psin`/`0drp` -> `sgd5` -> `rsc50`/`raw_stream`), separating `full_paths` from `identifiers`, deduplicating candidates, and marking streams without plaintext strings as `status="unnamed"`. *Chosen*: maximizes true recovery across all observed plaintext sources with linear $O(n)$ token scanning and zero fabricated names.
3. **Alternative C — Deep binary asset/hash decoder**: Attempts full `RSC8`/`rsc50`/`AWC`/`LSNS` structural decoding and Jenkins/JOAAT hash brute-forcing. *Rejected*: `LSNS` inside `PSIN` is high-entropy/opaque, `AWC`/`rsc50` store hashes rather than plaintext names without an external hash dictionary, and `METHODOLOGY.md` forbids unverified format assumptions.

## 2. Extraction Sources (Priority Order)

1. **Inflated XML & XML continuation chunks (`xml`, `xml_chunk`)**:
   - Extracts paths matching `$(var)/...`, `scheme:/...`, or game extensions (`ytd`, `ydr`, `yft`, `ybn`, `ymap`, `ytyp`, `ycd`, `awc`, `rpf`, `xml`, `meta`, `rel`, `dat`, plus `.bk2`/`.ityp`/`.clip`) as `full_paths`.
   - Extracts explicit identity elements (`<id>`, `<deviceName>`, `<dlcName>`, `<packFile>`, `<scriptName>`, `<audioBank>`, `<datFile>`, `<videoFileName>`, `<modelName>`, `<ModelName>`, `<filename>`, `<loadPath>`, `<exportPath>`, `<Name>`, `<name>`) and path attributes (`href`, `filename`, `loadPath`, etc.) as `identifiers` when non-generic.
   - Detects 64 KiB XML continuation fragments (`xml_chunk`, `929` streams) via closing XML tag validation (`</Tag>`).
2. **`PSIN` and `0DRP` containers (`psin`, `0drp`)**:
   - Extracts clean null-terminated C-strings (`(?:\x00|^)...(?=\x00)`) and `scheme:/...` paths while filtering out container tags (`PSIN`, `LSCH`, `LENM`, `LSNS`, `LGID`, `LRSC`, `CHKS`, `0DRPz`) and localized dialogue/binary artifacts.
3. **`SGD5` shader symbol tables (`sgd5`)**:
   - Matches `[VDHGMCP]S_*_Wrapped\0` followed by the 17-byte `<u8 kind><u32 stored><u32 id><u32 stored2><u32 raw_size>` header and raw-deflate (`wbits=-15`) `DXBC` stream (`shaders.head.bin @0x10e3e..`, `shaders.q1.bin @0x9100..`). Window-edge truncated entries are recorded as `sgd5_shader_truncated` with `inflated_bytes=null`.
4. **`rsc50` and `raw` fallback (`rsc50`, `raw_stream`)**:
   - Extracts clean internal references (e.g. `pack:/...clip`, `audio:/config/waveslots2.xml`, `AMB_STREAM_*`, `AGC_Scan_*`) when present; otherwise records `status="unnamed"`.

## 3. Measured Coverage (`raw/nombres.txt`)

Run across all **78** sample files in `samples` (`raw/nombres.txt` §1–§2):

- **Total streams**: `17,082` (`16,213` zlib `78 da` + `869` `SGD5` shader entries)
- **Named streams**: `1,509` (**8.83%**)
- **Unnamed streams (`sin nombre`)**: `15,573` (**91.17%**)
- **Unique deduplicated entries**: `13,402` `full_paths`, `14,282` `identifiers`
- **Target extension mentions**: `.rpf` (`7,592`), `.xml` (`221`), `.meta` (`142`), `.dat` (`15`); `.ytd`/`.ydr`/`.yft`/`.ybn`/`.ymap`/`.ytyp`/`.ycd`/`.awc` had `0` plaintext mentions in the sampled XMLs (plus `.bk2` and `.ityp` in XML paths).

| `stream_type` | Total | Named | Unnamed | Coverage |
|---|---:|---:|---:|---:|
| `sgd5_shader_dxbc` | 867 | 867 | 0 | **100.00%** |
| `sgd5_shader_truncated` | 2 | 2 | 0 | **100.00%** |
| `xml` | 477 | 181 | 296 | **37.95%** |
| `xml_chunk` | 929 | 179 | 750 | **19.27%** |
| `rsc50` | 4,357 | 197 | 4,160 | **4.52%** |
| `raw` | 5,512 | 69 | 5,443 | **1.25%** |
| `0DRP` | 872 | 8 | 864 | **0.92%** |
| `PSIN` | 4,066 | 6 | 4,060 | **0.15%** |

By archive group (`raw/nombres.txt` §2): small complete XML packs (`core_licenses_data`, `core_restofworld001`, `story000_bvh4`) reach **100.00%**; `shaders` reaches **83.24%** (`869/1,044`); `core_restofworld` **46.97%**; `story000_restofworld` **46.73%**; `common` **18.16%**; while `script` (`0/2,977`) and `story000_script` (`0/673`) are **0.00%**.

## 4. Real Examples and Mandatory Payload Validation (`raw/nombres.txt` §1, §3)

- **XML (`xml`)**: `common.head.bin @0xb000` (`comp=2568`, `inf=65536`) -> `full_paths=['$(common)/movies/ArcadeGames/BFYB_IDLE_SCREEN_BINK.bk2', ...]`, `identifiers=['core_binks']`.
- **XML continuation (`xml_chunk`)**: `common.head.bin @0xba10` (`comp=397`, `inf=8732`) -> `full_paths=['$(common)/movies/TV/SPRT/BSKT/R_GM_WIN_11.bk2', ...]`.
- **PSIN (`psin`)**: `data.head.bin @0x13000` (`comp=1138`, `inf=2568`) -> `identifiers=['TEMP_0653AU_AAAA', 'TEMP_0653_TEMP_1']`; `navmeshes.tail.bin @0x3cdb50` -> `identifiers=['ambrosiaraceway_dirtracerfinalemission', ...]`.
- **0DRP (`0drp`)**: `story000.head.bin @0xc5010` (`comp=7812`, `inf=131072`) -> `full_paths=['cutscene_exclusive/AIR_TRAIN_INT_PHONE.bk2']`; `story000.head.bin @0x212010` -> `identifiers=['CSC_DRT_FINALAU', ...]`.
- **SGD5 (`sgd5`)**: `shaders.head.bin @0x10e3e` (`comp=2321`, `inf=2640`) -> `identifiers=['VS_AlphaTransmissionFullScreenTri_4f16bf6c_Wrapped']`.
- **Unnamed (`unnamed`)**: `anim.head.bin @0x6000` (`PSIN`), `anim.head.bin @0x14010` (`0DRP`), `common.head.bin @0x15770` (`xml`), `anim.q1.bin @0x91d6c` (`rsc50`).

`--validate` re-inflates recovered streams from disk and checks exact byte-for-byte substring presence (`raw/nombres.txt` §1, 6/6 verified):
- `[xml] common.head.bin @0xb000 -> 'core_binks'` (`verified=True`, `payload_off=141`)
- `[psin] data.head.bin @0x13000 -> 'TEMP_0653AU_AAAA'` (`verified=True`, `payload_off=464`)
- `[0drp] story000.head.bin @0xbe010 -> 'cutscene_exclusive/AIR_TAIL_INT'` (`verified=True`, `payload_off=169584`)
- `[sgd5] shaders.head.bin @0x10e3e -> 'VS_AlphaTransmissionFullScreenTri_4f16bf6c_Wrapped'` (`verified=True`, `DXBC` 2,640 B verified)
- `[rsc50] anim.q1.bin @0x5cd6c -> 'pack:/biped_q5'` (`verified=True`, `payload_off=304952`)
- `[raw_stream] anim.q1.bin @0x53b5c -> 'pack:/biped_q5'` (`verified=True`, `payload_off=39992`)

## 5. Limitations

- **Encrypted TOC/Trailer ceiling**: Without the RPF9 AES key, the `91.17%` (`15,573/17,082`) of streams lacking inline strings (`PSIN` `LSNS` opaque bodies, `0DRP` page tables, `rsc50` geometry/textures, numeric tuning XMLs) cannot be mapped back to their original archive entry paths.
- **Referenced vs self-owning names**: XML manifests (`CDataFileMgr__ContentChangeSetDef`) list *referenced* child paths (`$(target)/data/credits/credits.rpf`) rather than the TOC path of the XML stream itself (`content.xml`), and `xml_chunk` continuation fragments only expose names inside the carved 64 KiB slice.
- **Sample window truncation**: 2 `SGD5` shader entries (`shaders.head.bin @0x3ff36c`, `shaders.q1.bin @0x1facd3`) and any zlib streams split across window boundaries are incomplete in the 2–4 MiB `.bin` windows.
- **Unencrypted non-zlib assets**: Raw `KB2n` Bink 2 streams and uncompressed `AWC` audio banks do not go through zlib inflation and are outside `name_recover.py`'s stream-inflation index.

## 6. Comparison vs Leonida's Offset-Based Naming

Per `ItsNotRexed/Leonida` (`docs/rpf.md`, `tools/rpf9_carve.py`, `tools/shader_carve.py`, GPL-3.0 reference):

| Dimension | Leonida (`rpf9_carve.py` / `rpf9dump`) | `rpf9-research` (`tools/name_recover.py`) |
|---|---|---|
| **Naming strategy** | Assigns synthetic offset-based paths (`recovered/...`, `off`) to every carved zlib stream (`docs/rpf.md`); `shader_carve.py` uses inline `<name>\0` before raw-deflate DXBC. | Extracts real paths/identifiers from inflated payloads with source provenance (`xml`, `psin`, `0drp`, `sgd5`, `rsc50`, `raw_stream`); marks the remaining 91.17% as `unnamed`. |
| **Coverage for extraction** | 100% of carved zlib streams get unique disk filenames for bulk export. | 8.83% overall (100% on `SGD5` shaders and small XML packs, 37.95% on `xml`, 0% on `script`). |
| **Semantic fidelity** | Offset names give physical location, not game resource identity (except shaders in `shader_carve.py`). | Every emitted name is verified inside the real payload; separates `full_paths` vs `identifiers` and never invents synthetic filenames. |
| **Complementarity** | Best for deterministic disk carving without TOC. | Best for indexing semantic asset references, verifying payload ground truth, and annotating offset-indexed streams. |
