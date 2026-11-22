# Where the textures live and how they are shaped

**English** · [Español](TEXTURES.es.md)

Before offering anything about BCPack, this measures the population it would apply to: how many
texture-bearing streams exist, how big they are, and whether their sizes are consistent with
16-byte blocks. Counts and geometry only — no texture data and no names are published.

## Method

`textures.rpf` holds two kinds of stream: 1,365 `rsc50` records averaging 0.1 KiB, and 1,384 `raw`
streams averaging 132.7 KiB. The `rsc50` ones are indexes; the data lives in the `raw` ones.

Every `raw` stream of that archive was inflated and measured: real inflated size, its remainder
modulo 16, how many 4×4 blocks of 16 bytes fit, and which texture dimensions imply that block
count.

## Result

```
streams raw           1,384
inflated without error 1,384 (0 failures)
inflated bytes         464.6 MiB
size mod 16            0 in 1,384 of 1,384
```

Every stream is an exact multiple of 16 bytes, which is what a block-compressed texture looks like
when it carries no header: blocks of 4×4 texels, 16 bytes each.

Blocks per stream:

| range | streams |
|---|---:|
| ≤ 512 | 4 |
| 513 – 2,048 | 1,317 |
| 2,049 – 8,192 | 22 |
| 8,193 – 32,768 | 7 |
| 32,769 – 131,072 | 6 |
| > 131,072 | 28 |

Median: **2,048 blocks**, which is 32,768 texels — a 128×256 surface, or any rotation of it.

The dominant case is striking: **1,313 of 1,384 streams carry exactly 2,048 blocks**. Sixteen more
carry 4,096 (256×256). The remaining 55 are the outliers above.

## The negative result that matters

Inflating the first forty streams and reading their first bytes showed **no container header**:
no `DDS `, no `RSC5`, no `RSC7`. The streams start directly with block data — zeros, flat colours
with alpha, and pixel patterns.

That means a BCPack detector cannot work by matching a magic. It has to work per 16-byte block,
which is exactly the shape of the problem the decoder projects describe.

## What this does not say

It does not classify a single stream as BCPack or BC7. Both formats use 16-byte blocks, so the
size tells you the population, not the format of each element. Deciding that needs the decoder
that `ItsNotRexed/Leonida` and `R0Y00/Xbox2Windows` are building.

What it does give them is the population size and the shape: 1,384 blobs, one dominant size class,
no headers, block-aligned. If a decoder handles the 2,048-block case, it covers 95% of the data in
this archive.

## Reproduce

The measurement reads the public index columns (`rpf`, `offset`, `compressed`, `inflated`, `type`)
and inflates each `raw` stream of the archive. It needs the package, which is not distributed; the
counts above are what it produced on one retail copy.
