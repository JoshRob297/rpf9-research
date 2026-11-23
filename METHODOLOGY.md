# Methodology

**English** · [Español](METHODOLOGY.es.md)

## The evidence rule

Every numeric or structural claim needs:

1. the command or script that produced it,
2. its raw output in `raw/<topic>.txt`,
3. the reference in the document (`docs/RPF9.md`) pointing at the file that holds the proof.

If an experiment fails it is kept anyway: `raw/` preserves attempts, not only successes.

## Forbidden

- Inferring a layout "because that is how GTA V did it" without measuring it on RPF9.
- Filling fields with zeros because the size "adds up".
- Presenting as fact anything that depends on a key we do not have.
- Writing to the binaries in `samples/`: they are read-only and their sha256 is in the manifest.

## Hypotheses and falsation

Each hypothesis lives as a row with what it predicts, how it is tested and the result
(`confirmed`, `refuted`, `undetermined`). A refuted hypothesis is worth as much as a confirmed one
and is documented the same way.

## Comparison with RPF7

The GTA V format is a reference for contrast, not a template. The public tool can be used to
*verify our method* against a known RPF7, but no RPF9 field is inherited without measurement on
the samples.

## Multi-source merger

`tools/merge_index.py` is the only tool that crosses sources. Every source declares its type
on the command line; an input that does not match that type is written to `unrecognized` and
the run continues. The conflict order is fixed in the code and copied verbatim into
`report.json`:

1. a path recovered literally from the payload (mount XML) beats any pattern;
2. same container, path, offset and size merge without a mark;
3. same path with a different offset or size is a `conflict`; every version is kept;
4. two different paths with the same hash are a `collision`;
5. no path but an identifier is an `orphan`.

`hashes` sources are reference-only: they compare the salted SHA-256 of the merged paths and
never add an entry. The historical two-positional invocation and `--skip` are unchanged.

### Design decisions

- `streams.tsv`, `paths.tsv` and `ids.tsv` were left as mention logs instead of being
  redefined. The published reproduction counts stay byte-identical; the normalized view goes
  to `index.tsv`.
- The container (`rpf`) is part of the identity because offsets are absolute inside a
  container. The same path in another container is a different location, not a conflict.
- Rule (a) resolves offset disagreements only. A size disagreement at the same offset stays a
  conflict: provenance says where a name came from, not which size is right.
- Hash collisions are detected by re-hashing the merged paths with the published salt; they
  are reported, never used to merge two names.

## Deliverables

- `tools/rpf9.py` — header plus a TOC attempt, with `--json`.
- `tools/name_recover.py` — name recovery from the payload, with provenance.
- `tools/merge_index.py` — merges chunk JSONs and heterogeneous sources; writes `index.tsv`
  and `report.json` alongside the historical mention logs.
- `docs/RPF9.md` / `docs/RPF9.es.md` — layout, fields, hypotheses, limits.
- `docs/INDEX.md` / `docs/INDEX.es.md` — full-scan coverage.
- `raw/` — transcripts.
