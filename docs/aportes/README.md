# Contributions prepared for VIctory

These four documents were written against VIctory at `1dd7afd` and describe what we can offer that
project, in the areas where its open blockers are: the world reaching the screen, the shaders that do
not translate, and the descriptor and page handling around them.

They are in Spanish; the issue that offers them summarises each one in English. Say the word and any of
them can be translated.

| File | What it is | Size |
|---|---|---|
| `01-mesh-gs-abi.md` | The mesh and geometry stage ABI a DXIL emitter must reproduce, with the corpus counts and the wave64 criterion | document |
| `02-wave64.md` | A wave64-on-32-wide-host design for compute and mesh, with the barrier placement and our test vectors | design |
| `04-typeless-86-115.md` | The typeless-resource recipe for `B5G5R5A1_UNORM` and `B4G4R4A4_UNORM` when the host refuses them as UAV or render target | recipe |
| `05-pipeline-library.md` | The pipeline library's layout as a warm-up source and a coverage metric | document |

A fifth contribution is code and lives as a pull request: the XMem physical-page change in
`crates/victory-hle/src/modules/xmem.rs`.

Nothing here contains game data: no asset paths, no container or archive names, no hashes of shipped
content. Only counts, offsets, structure sizes and code.
