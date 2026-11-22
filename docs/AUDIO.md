# What an audio stream looks like at offset zero

**English** · [Español](AUDIO.es.md)

`open-vfs#18` asks for an `ADAT`/`AWC` header parser: magic validation, version, flags, stream
count, header size and the stream offset table. This measures where such a header actually is, and
reports a negative result that changes the parser's shape.

## Population

`audio.rpf` holds **838 streams, all of type `raw`**, 26.6 GiB compressed across 11 chunks of the
scan. Only 68 of them carry a name, and the names are clip identifiers rather than paths.

## What the first bytes show

Inflating the first 60 streams and reading their first four bytes:

```
0xffffffff   6   padding
0x00000000   5   silence with a 1.0f float nearby
0x0000803f   2   a float 1.0, i.e. audio data already
"AMB_"       1   ASCII: AMB_STREAM_ANIMALS_01\0AMB_STREAM_...
other        46  float and PCM patterns
```

**Not one of them starts with `ADAT` or `AWC`.** The payload begins directly with audio data — float
samples, silence, padding — and the only ASCII present are clip identifiers embedded in the body.

## What that means for the parser

The archive is not a stream of self-describing chunks the way `PSIN` is. A per-stream magic check
will reject 60 of 60 in this sample, so the header either lives at the archive level (before the
first stream, in the region the scan classifies as the index) or in a small number of dedicated
streams that this sample did not reach.

The practical consequence is the same one the texture measurement produced: **do not key the parser
on a magic per stream**. Locate the header by structure, and treat the rest as opaque payload.

## Limits

Sixty streams out of 838, sampled from the first offsets in the index, which are not randomly
distributed across the archive. A dedicated header stream, if it exists, may sit further in. This is
a negative result on the sample, not a proof that no `AWC` magic exists anywhere in `audio.rpf`.
