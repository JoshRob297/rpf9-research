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

## 3. Provenance and Confidence Labels

A recovered string is evidence, not a table-of-contents entry: it can be a path declared by a mount manifest, a `pack:/...` substring found inside inflated bytes, or a bare word that only matches the identifier grammar. An index that treats the three the same cannot be audited. Every name now carries two labels:

| field | values | question it answers |
|---|---|---|
| `source` | `xml_mount`, `xml_chunk`, `literal`, `pattern`, `inferred` | where the bytes came from |
| `confidence` | `confirmed`, `probable`, `candidate` | how much those bytes prove |

### 3.1 Where the labels live

`full_paths` and `identifiers` keep their type, length and order. The labels travel in a parallel object, same length and index:

```json
"full_paths": ["$(target)/data/credits/credits.rpf"],
"labeled": {
  "full_paths": [
    {"name": "$(target)/data/credits/credits.rpf",
     "source": "xml_mount", "confidence": "confirmed"}
  ],
  "identifiers": []
}
```

Three placements were considered:

1. **`source`/`confidence` inside each `candidates[]` entry**: rejected. `candidates[].source` already exists with another meaning (the legacy stream bucket `xml`, `psin`, `0drp`, `sgd5`, `rsc50`, `raw_stream`), which `merge_index.py` reads and `candidate_mentions_by_source` publishes. Reusing the name would silently change an existing field.
2. **One `labeled` list parallel to `candidates`**: rejected. `candidates` is the union of both kinds, so a consumer joining `full_paths` to its labels would have to re-derive the sort order, and a mixed-up index would go unnoticed.
3. **Chosen**: `labeled.full_paths` and `labeled.identifiers`, same length and index as the arrays they shadow, each entry `{"name", "source", "confidence"}`. Repeating the name makes an entry readable on its own and makes any length mismatch detectable.

The extractor keeps the *channel* that found each value (which tag, which regex) and `label_candidate()` maps it to exactly one pair. Channels are internal and are stripped from `candidates`, whose shape is unchanged.

### 3.2 `source`: where the bytes came from

| `source` | rule in `label_candidate()` | measured example |
|---|---|---|
| `xml_mount` | XML document whose root element is `CDataFileMgr__ContentChangeSetDef` or `CDataFileMgr__ContentDef` (60 of the 477 XML streams), value taken from a tag or attribute | `$(common)/movies/ArcadeGames/BFYB_IDLE_SCREEN_BINK.bk2`, `common.head.bin @0xb000` |
| `xml_chunk` | XML continuation fragment (`xml_chunk`: closing tag, no XML declaration), so the root is unknown | `$(common)/movies/TV/SPRT/BSKT/R_GM_WIN_11.bk2`, `common.head.bin @0xba10` |
| `literal` | complete literal in another stream: a null-terminated C-string that is a full path, an SGD5 symbol, or a value declared by a path/identity tag in a non-mount XML | `pack:/enter_front_lf.clip`, `anim.q1.bin @0x53b5c`; `VS_AlphaTransmissionFullScreenTri_4f16bf6c_Wrapped`, `shaders.head.bin @0x10e3e` |
| `pattern` | path template with no declaring structure: a `scheme:/` regex hit inside inflated bytes, or a path-shaped value in a tag not known to declare paths (non-mount XML) | `pack:/biped_q5`, `anim.q1.bin @0x5cd6c` |
| `inferred` | only the token grammar matched: an identifier-shaped null-terminated string with no path syntax and no declaring context | `TEMP_0653AU_AAAA`, `data.head.bin @0x13000` |

The mount roots are the two `CDataFileMgr__*` manifests; the other 417 XML streams in the sample set are tuning data (`timecycle_modifier_data` 147, `timecycle_keyframe_data` 52, `CVehiclePoints` 32, ...), and their names are `literal` or `pattern` according to the channel, never `xml_mount` (`raw/etiquetas.txt` section 4).

### 3.3 `confidence`: how much the evidence proves

| `confidence` | rule | measured example |
|---|---|---|
| `confirmed` | delimited literal, or value in a tag/attribute that declares paths or identities | `core_binks` from `<id>core_binks</id>`, `common.head.bin @0xb000` |
| `probable` | matches a path template (scheme, `$(var)/`, multi-segment or known extension) but no declaring structure proves it is a name | `pack:/biped_q5`, `anim.q1.bin @0x5cd6c`; `common:/data/anim/anim.meta` in an `<Item>`, `common.head.bin @0x129000` |
| `candidate` | only the identifier grammar matched: no path syntax, no context | `TEMP_0653AU_AAAA`, `data.head.bin @0x13000`; fragments such as `ion_Female`, `anim.tail.bin @0x3f3ed0` |

The channel follows the tag, not the inferred kind: `<id>common:/data/anim/anim.meta</id>` is classified as a full path by shape, but the manifest declares it, so it is `confirmed`; the same string listed as `<Item>common:/data/anim/anim.meta</Item>` in another manifest is `probable`. A fragment carved mid-tag loses the declaration and drops to `probable` as well: `DowntownNorth/Perschars/Peds/Shop_Clerks/dn_21_accessories_shop_clerk_1` (`common.head.bin @0x48fc0`) starts where the `<Name>` opening tag was cut, so only the path shape remains.

`confirmed` means "this literal is in the payload and its scope is delimited, so the tool did not invent it". It does **not** mean "the asset exists at this path": several streams may declare the same path, and a mount XML declares *referenced* paths, not the TOC path of the stream itself (section 6).

### 3.4 Rule order

`label_candidate()` applies these rules in order and stops at the first match; the table is exhaustive over the channels the tool emits, and an unknown channel falls back to `inferred`/`candidate` instead of dropping the name:

1. SGD5 symbol -> `literal`/`confirmed`.
2. `scheme:/` regex hit in binary bytes -> `pattern`/`probable`.
3. Null-terminated C-string -> `literal`/`confirmed` for a path, `inferred`/`candidate` for an identifier.
4. `xml_chunk` -> `xml_chunk`, `confirmed` when the value's tag or attribute survives, `probable` otherwise.
5. XML document with a mount root -> `xml_mount`, same declared/probable split.
6. XML document without a mount root -> `literal`/`confirmed` when declared, `pattern`/`probable` otherwise.
7. Anything else -> `inferred`/`candidate`.

When one stream finds the same name twice, the strongest channel keeps the label. In `anim.q1.bin @0x53b5c`, `pack:/enter_front_lf.clip` is a complete null-terminated string (`literal`/`confirmed`) while `pack:/biped_q5` in the same stream is only matched by the scheme regex (`pattern`/`probable`).

### 3.5 The number behind the published percentage

The published figure is **1,509 named streams out of 17,082 (8.83%)**. It is `summary.named_streams / summary.total_streams`, a stream-level ratio that counts any stream with at least one candidate, whatever its label; the full-scan index in `docs/INDEX.md` follows the same rule (177,087 of 1,489,677 streams, 11.89%). The new breakdown in `summary.labeled` counts *name mentions*: 39,487, of which 31,238 `confirmed`, 224 `probable` and 8,025 `candidate` (`raw/etiquetas.txt` sections 1-2). It cannot recompute either percentage, and it is not meant to: the published ratio stays as it was, and the split is what lets a reader say how much of it is declared evidence. Counts are mentions (one per stream entry), not unique strings.

## 4. Measured Coverage (`raw/nombres.txt`)

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

## 5. Real Examples and Mandatory Payload Validation (`raw/nombres.txt` §1, §3)

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

## 6. Limitations

- **Encrypted TOC/Trailer ceiling**: Without the RPF9 AES key, the `91.17%` (`15,573/17,082`) of streams lacking inline strings (`PSIN` `LSNS` opaque bodies, `0DRP` page tables, `rsc50` geometry/textures, numeric tuning XMLs) cannot be mapped back to their original archive entry paths.
- **Referenced vs self-owning names**: XML manifests (`CDataFileMgr__ContentChangeSetDef`) list *referenced* child paths (`$(target)/data/credits/credits.rpf`) rather than the TOC path of the XML stream itself (`content.xml`), and `xml_chunk` continuation fragments only expose names inside the carved 64 KiB slice.
- **Sample window truncation**: 2 `SGD5` shader entries (`shaders.head.bin @0x3ff36c`, `shaders.q1.bin @0x1facd3`) and any zlib streams split across window boundaries are incomplete in the 2–4 MiB `.bin` windows.
- **Unencrypted non-zlib assets**: Raw `KB2n` Bink 2 streams and uncompressed `AWC` audio banks do not go through zlib inflation and are outside `name_recover.py`'s stream-inflation index.

## 7. Comparison vs Leonida's Offset-Based Naming

Per `ItsNotRexed/Leonida` (`docs/rpf.md`, `tools/rpf9_carve.py`, `tools/shader_carve.py`, GPL-3.0 reference):

| Dimension | Leonida (`rpf9_carve.py` / `rpf9dump`) | `rpf9-research` (`tools/name_recover.py`) |
|---|---|---|
| **Naming strategy** | Assigns synthetic offset-based paths (`recovered/...`, `off`) to every carved zlib stream (`docs/rpf.md`); `shader_carve.py` uses inline `<name>\0` before raw-deflate DXBC. | Extracts real paths/identifiers from inflated payloads with source provenance (`xml`, `psin`, `0drp`, `sgd5`, `rsc50`, `raw_stream`); marks the remaining 91.17% as `unnamed`. |
| **Coverage for extraction** | 100% of carved zlib streams get unique disk filenames for bulk export. | 8.83% overall (100% on `SGD5` shaders and small XML packs, 37.95% on `xml`, 0% on `script`). |
| **Semantic fidelity** | Offset names give physical location, not game resource identity (except shaders in `shader_carve.py`). | Every emitted name is verified inside the real payload; separates `full_paths` vs `identifiers` and never invents synthetic filenames. |
| **Complementarity** | Best for deterministic disk carving without TOC. | Best for indexing semantic asset references, verifying payload ground truth, and annotating offset-indexed streams. |
