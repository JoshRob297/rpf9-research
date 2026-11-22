# rpf9-research

**English** · [Español](README.es.md)

Reverse engineering of the **RPF9** container used by GTA VI (Xbox Series X|S), from a 209 GiB
package holding 22 `.rpf` archives and 57 `.ttpf` files.

## What is known before starting

- The magic is `39 46 50 52` in the first four bytes: `RPF9` read as a little-endian integer.
  GTA V uses `RPF7` (`37 46 50 52`).
- The bytes right after the magic are neither text nor a readable table: the region behind them
  looks encrypted (high entropy, no plain-text names in the first 2 MB).
- In GTA V the RPF7 table of contents is AES-encrypted and public tools (OpenIV, CodeWalker)
  know that key. For RPF9 there is no public tool.

## Goal

Determine, with reproducible evidence, **the layout of the header and the table of contents** of
RPF9, and how far one can get without the key. The expected output is a document
(`docs/RPF9.md`) plus a prototype (`tools/rpf9.py`) that:

1. reads the header and explains each field with its measurement,
2. states whether the TOC is encrypted and on what evidence (not by assumption),
3. lists entries if it manages to decrypt it, or explains exactly what is missing.

## Repository rules

- **Every number in the documentation needs its transcript in `raw/`.** Nothing is claimed that
  has not been measured.
- Anything that cannot be determined is written as **undetermined**, together with the test that
  was attempted and failed.
- Sample binaries are **not versioned** (see `.gitignore`); only their manifest with hashes is.
- Documentation ships in pairs: `README.md` (English) and `README.es.md` (Spanish); likewise
  `docs/RPF9.md`, `docs/NAMES.md` and `docs/INDEX.md` with their `.es.md` counterparts.

See `METHODOLOGY.md`.

## What the scan produced

A full pass over the 22 archives (150.2 GiB, 71 chunks) recovered **177,087 named streams
(11.89%)**, **155,214 unique paths** and **200,184 unique identifiers**. Coverage is 100% for
shaders and 0.27% for `0DRP` containers. Details, method and the negative results are in
`docs/INDEX.md`.

The full path index is not published: it is the game's asset manifest, not the format. The repo
ships the tools, the counts and salted hashes so anyone can diff their own run against ours.

## License

GPL-3.0-or-later.

The reason is practical: the closest reference work, `ItsNotRexed/Leonida`, is GPL-3.0 and
publishes measured format facts about this same package. Facts can be taken with attribution,
but if code is ever reused, this is the only license that allows it without conflict. Projects
under GPL-2.0-only (`xcl`, `americas-recomp`) and non-commercial licenses (`PercyStar`) remain
reading references, never a source of code.

See also `docs/` for the measured state of the format.
