# RESOLVER — from a manifest path to the asset bytes

Tool: `tools/resolve_path.py` (Python 3, standard library only).

**English** · [Español](RESOLVER.es.md)

## Scope

The resolver turns a path from the index into the bytes of the asset that lives inside an RPF9
container. It does **not** parse the encrypted TOC and it does **not** decrypt names: it works from
the index slice that the sweep already extracted, which says exactly which offset to read, how many
compressed bytes to read, and how many bytes the result must measure.

That is the point of the piece. The engine a port would run needs to answer "give me this asset",
and the encrypted table it would normally consult cannot be read without the key. The index is the
substitute: `rpf`, `abs_offset`, `compressed`, `inflated` per stream, and `path → (rpf, abs_offset)`
per mention.

```
paths-*.tsv     ruta, rpf, abs_offset          one row per mention
streams-*.tsv   rpf, abs_offset, compressed, inflated, type, ...
```

## Usage

```sh
# bytes to stdout
tools/resolve_path.py --index idx/ --containers rpf/ --path "path/from/the/manifest"

# to a file
tools/resolve_path.py --index idx/ --containers rpf/ --path "..." --out asset.bin

# metadata without reading the payload
tools/resolve_path.py --index idx/ --containers rpf/ --path "..." --info

# every mention, when the same path appears in more than one stream
tools/resolve_path.py --index idx/ --containers rpf/ --path "..." --all

# sample N paths and check every one of them
tools/resolve_path.py --index idx/ --containers rpf/ --verify 200 --rpf data --seed 7
```

## Rules the implementation follows

1. **Seek, never load.** The container is opened and read at the offset; a 481 MB archive is never
   held in memory.
2. **Compression is decided by the first byte**, not by a column: `0x78` means a zlib stream and it
   is inflated; anything else is treated as raw payload.
3. **The length is checked.** The result must measure exactly `inflated` bytes. A mismatch is a
   failure with its own reason, not a silent success.
4. **Errors carry a stable `reason`**: `path_not_found`, `container_missing`, `inflate_failed`,
   `size_mismatch`, so a caller can branch on the cause instead of parsing prose.
5. **`--verify` is reproducible.** The sample is seeded, so a differing result between two runs of
   the same version is a real difference and not sampling noise.

## Measured

Against a real container and its index slice (`data.rpf`, 481 MB, 28,509 streams, 4,639 paths):

```
--verify 200                    200 paths resolved, 0 failures
--verify 2295 (all mentions)    2,295 paths / 4,704 mentions, 0 failures
```

Every resolved path produced bytes that measured exactly the `inflated` value recorded in the
index. That is the acceptance criterion: not "it returned something", but "it returned exactly the
size the sweep measured".

## Limits, stated plainly

- It does not read the TOC. It depends on an index built by the sweep.
- It does not follow nested RPF9 containers; a stream that contains another container is returned as
  bytes and stops there.
- It does not decrypt anything, and it does not resolve names on its own.
- A path that appears in several streams resolves to the first mention unless `--all` is passed;
  which one is correct depends on the caller's context, and the tool does not guess.
- Offset conventions are per container: `abs_offset` is absolute inside the `.rpf`, which is what the
  index records, not relative to any slice.

## Reproduce

```sh
python3 -m unittest tests.test_resolve_path -v
python3 tools/resolve_path.py --index <idx> --containers <dir> --verify 200 --rpf data
```
