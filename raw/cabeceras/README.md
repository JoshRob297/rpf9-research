# RPF9 header fixtures

**English** · [Español](README.es.md)

The 64 header bytes of 22 retail RPF9 archives, extracted read-only and published as test vectors.
This is container geometry: magic, offsets, counts and flags. It contains no names, no payload and
no key material — nothing here describes the contents of an archive.

## Files

```
headers.bin        1,408 bytes: 22 x 64, same order as headers.tsv
headers.tsv        one row per archive with the measured fields
headers.json       the same plus the full hex of each header
rpf9_headers.hpp   C++ fixture (std::array<std::uint8_t, 64>), drop-in for a test file
rpf9_headers.py    Python fixture, same data
```

## Field map used to derive the table

| offset | type | field |
|---|---|---|
| `0x00` | 4 bytes | magic, on disk `39 46 50 52` (`RPF9` as a little-endian u32) |
| `0x04` | u32 | `toc_end_offset` |
| `0x08` | u32 | `toc_subtable_offset` |
| `0x0c` | u32 | `trailer_length` |
| `0x18` | u32 | constant `0x47a00` in all 22 |
| `0x1c` | u32 | constant `0x150` in all 22 |
| `0x20` | u32 | high half selects the table shape (see caveat) |
| `0x24` | u32 | entry count |
| `0x28` | u32 | key profile tag |
| `0x2c` | u32 | low byte 1 or 2, selects the entry stride |

## The relation this fixture exists to test

The table region, from `toc_subtable_offset` to `toc_end_offset`, equals

```
ceil(stride * w24 / 16) * 16        stride = 8 + (byte at 0x2c)
```

It holds for **22 of 22** archives in this set. `levels.rpf` as an example: `w24 = 2078`,
`byte 0x2c = 2`, so stride 10, `10 * 2078 = 20780`, and `ceil(20780 / 16) * 16 = 20784`, which is
exactly `toc_end_offset - toc_subtable_offset`.

A parser that advances a fixed 16 bytes per entry reads `levels.rpf` as 1,299 records holding
2,078 entries. That mismatch is what the fixture is for.

## Caveat

The 8 archives whose `0x20` high half is 2 use a wider stride for the subtable, and this fixture
does not model that case. It is an open question, not a solved one.

## Provenance

Extracted with a read-only script over a package in a lab environment; the archives were never
modified and their full sha256 is not published because the files themselves are not. Every value
in `headers.tsv` is derived from the bytes in `headers.bin`, and `headers.bin` is the bytes on
disk — both can be checked against each other.
