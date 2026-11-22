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

## Deliverables

- `tools/rpf9.py` — header plus a TOC attempt, with `--json`.
- `tools/name_recover.py` — name recovery from the payload, with provenance.
- `tools/merge_index.py` — merges the chunk JSONs into an index with absolute offsets.
- `docs/RPF9.md` / `docs/RPF9.es.md` — layout, fields, hypotheses, limits.
- `docs/INDEX.md` / `docs/INDEX.es.md` — full-scan coverage.
- `raw/` — transcripts.
