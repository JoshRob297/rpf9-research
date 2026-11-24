# Dossier de ABI: etapas de malla y geometría

Para el emisor DXIL de VIctory (Rust, GPL-3.0), fijado en `1dd7afd`. Todo lo
`hecho` está medido o contado sobre el corpus; lo `sin medir` se dice.

Premisa (comparativa §2.1): de las dos etapas que les faltan, la **malla** está
a medias —traducen 8.191 de 8.506 pipelines— y la **geometría** falta entera:
no traducen ni uno. Las dos tablas siguientes son lo que un emisor debe
reproducir; no incluyen código de emisor, sólo contratos y fixtures descritos.

**Corrección a la comparativa (§4.1).** Atribuye el parseo de firmas a
`crates/victory-shader/src/structure.rs`; es falso: ese fichero estructura el
flujo de control. La ABI vive en `crates/victory-shader/src/emit/mod.rs`
(partes `ISG1`/`OSG1`/`PSG1`, filas de 32 bytes), `emit/container.rs` (PSV0,
runtime info) y `native.rs` (datos de etapa del FSSM).

## 1. Tabla de malla

Fuente nuestra: `docs/design.md:325`, `:326`, `:505`; su lado:
`emit/mod.rs:180-260`, `io.rs:237`, `native.rs:632`, `emit/lower.rs:384-430`.

| Campo | Valor en el corpus | Dónde se declara |
|---|---|---|
| Hilos (`NumThreads`) | 128 × 1 × 1 en 9.282/9.282 | PSV0 `u32_at(d, 4+36)`, `emit/mod.rs:217` |
| Vértices máx. / primitivas máx. | 128 / 128 en 9.282/9.282 | PSV0 `[12..16]`, `[14..16]`, `container.rs:164` |
| Topología | triángulos (2) en 9.282/9.282 | PSV0 `[27]`, `native.rs:632` |
| Tamaño de wave | 64, declarado en el FSSM | `native.rs:19`, bit 5 de `flags` |
| Payload v5 (`MeshGroup`) | `groupIndex * NumThreads + índice local` | `lower.rs:941`, stride en `emit/mod.rs:217` |
| s3 (`MergedWaveInfo`) | `id de wave << 24` (sólo bits 24-27) | `lower.rs:948` |
| Recuento (`GS_ALLOC_REQ`) | `m0 = primitivas<<12 \| vértices`, por el hilo 0 a una variable de workgroup, con barrera | `io.rs:31`, `lower.rs:408` |
| Export de vértice | hilo t → vértice t (`pos0`, `paramN`), todo-`off` no escribe | `lower.rs:6074` |
| Export de primitiva | índices empaquetados `[8:0]`, `[18:10]`, `[28:20]`; cull en el bit 31 | `emit_indices`, `lower.rs:6285` |
| Clip/cull por vértice | `pos1..pos3` como Block por vértice cuando se usan (1.906 programas) | `half_outputs`, `lower.rs:288` |
| Máscaras de lane | las del hardware: no hay `WaveSize` para malla | `MaskData::None`, `lower.rs:228` |

Lo que ya tienen y coincide: hilos/vértices/primitivas/topología desde PSV0,
`OSG1`/`PSG1` (descartan los tipos 10 y 30, `emit/mod.rs:207`), `v5` por
`MeshGroup`, `s3` por `MergedWaveInfo`, índices y cull empaquetados, y la
supresión de barrera tras `GS_ALLOC_REQ` (`lower.rs:408`).

Lo que **no** pueden reproducir hoy, en su propio código: no pueden declarar
tamaño de wave en malla —`shader.rs:70` documenta `wave_size` como propiedad de
compute y sólo se escribe en esa rama (`shader.rs:377`, `:509`)—; se niegan a
las operaciones de cruce de lane (`lower.rs:1786`), a las reducciones de wave
(`:729`) y a las máscaras leídas como dato (`:1144`, `const LANE_MASK`); y su
`v_mbcnt_lo/hi` (`:4846-4895`) numera lanes a la consola con desplazamiento
`& 31`, de modo que para lanes ≥ 32 no da el id de lane. Aciertan `v5 >> 7` y
`s3[27:24]` porque 32 divide a 128, no por construcción.

*Fixture descrito* (`ms_w64x_ballot.asm`, nuestro): lanes con `(lane & 7) == 5`
—5, 13, 21, 29, 37, 45, 53, 61—; `s_bcnt1` del ballot debe dar 8, no 4;
`v_mbcnt_lo(-1,0) + v_mbcnt_hi(-1,lo)` debe dar `lane` para las 64 lanes. Es la
prueba mínima de que el id de lane de malla es `índice local & 63` y sólo sale
de la cadena de dos mitades.

## 2. Tabla de geometría

Fuente nuestra: `docs/design.md:327`; su lado: `native.rs:64` («Merged stages
keep their stage data in another layout (not read)»), `native.rs:532`
(`_ => StageIo::None`), `io.rs` (`_ => Err(unsupported(0, "I/O of this stage"))`),
y README:43, que nombra «merged geometry stages» como límite.

| Campo | Valor en el corpus | Dónde se declara |
|---|---|---|
| Programas | 195 `$GS_VoxelizeGeneric`, 195/195 | índice del traductor, `f847748c` |
| Etapas | ES + GS fusionadas en una, stream 0 | FSSM, etapas 2 y 3 |
| Tamaño de wave | 64 en 195/195; prólogo EXEC compara con 64 y arma EXEC de 64 bits (`s_bfe_i32 s0, s3, 0x80008`, `s_bfm_b64`, `s_cselect_b64`) | `tools/rdna2spirv.py:15221` |
| Entrada | vértice i en v0 lo / v0 hi / v1 lo; LDS en base + `4·(4·reg+comp)` = registro/componente de la firma (SV_Position xyz dwords 0-2, TEXCOORD0.xy dwords 4-5) | `:13766` |
| Salida | vértice k = dwords `[k·4·nreg, (k+1)·4·nreg)` del área GSVS del lane; dword = `4·reg+comp`; 20 dwords = 5 registros `OSG1` | `:13818` |
| Emisión | `MSG_GS EMIT` → copia + `OpEmitVertex`; `CUT` → `OpEndPrimitive`; `GS_DONE` → nada | `:13818` |
| LDS | anillos; `v_mbcnt_hi` presente en los 195 | `design.md:299` |

La traducción es de offsets sintéticos `64·i`, lecturas LDS → `gl_in[i]`,
escrituras LDS → slots escalonados. GPU: `gs_tri.asm` 0 errores, seis vértices
→ dos triángulos; respaldo a compute `tools/spirv_gs_to_compute.py` 195/195
exactos, 4096/4096 píxeles en A18 Pro. Sin hacer: cablear el draw, GS con cruce
de lane, más de una invocación.

*Fixture descrito* (`gs_tri.asm`): `s_bfe 0x80008`, `s_bfm_b64`, `s_cselect`,
dos lecturas y dos escrituras LDS, slots de salida de 2 registros (8 dwords),
tres `EMIT`, un `CUT`, un `DONE`.

Para el emisor, la malla y la geometría se separan así: en malla el contrato es
«un hilo = un vértice y una primitiva, recuento por variable de workgroup y
barrera»; en geometría es «un lane = una invocación que escribe su área GSVS y
la emite copiando». Ninguna de las dos es una firma de etapa gráfica normal.

## 3. Criterio de wave64 y por qué la partición gráfica es invariante

Compute y malla: exacto en cualquier tamaño de subgroup con `--wave64-emulate`
(`design.md:385`, 4096/4096 píxeles). Rondas con scratch `%x_buf` de workgroup,
una `OpControlBarrier(Workgroup, AcquireRelease, workgroup|uniform|image)` en
flujo uniforme, doble buffer por paridad de ronda, dos palabras de máscara por
wave en tres slots por `ronda mod 3`; lanes ausentes de la wave parcial leen 0.

Gráficas: no hay scratch de workgroup ni barrera que dé pareja a la mitad, así
que la emulación es por shader (`design.md:481`): la wave64 es exacta **si y
sólo si** sus resultados observables no cambian al cortar la wave en dos mitades
de 32. `tools/wave64_halves.py` lo decide (taint hacia delante sobre bloques,
más dependencia de control sobre votos de wave) y el traductor lo anota en
`index.json` como `wave64_graphics` (`A`/`B`/`C`), con
`wave64_graphics_reasons` y `wave64_graphics_idioms`.

Su código hace lo mismo por otra vía y con menos alcance: `MaskData::Host` para
PS/VS, `Console` para CS y `None` para el resto (`lower.rs:462-472`), y en Host
sólo admite los usos que significan lo mismo en cualquier wave —recuentos,
primer lane, cuenta por debajo de un lane, igualdad—, que es el criterio del
tier A dicho en voz alta. Lo que no tienen es la maquinaria de rondas: sus
tiers no existen y por eso 9.287 de sus 13.405 shaders gráficos wave64 no
pueden ser exactos en un host de 32.

## 4. Corpus que sostiene cada tabla

Malla: 9.282 programas, todos 128×1×1, 128/128, wave64, 0-18 parámetros,
1.906 con distancias de clip, ninguno con cull por primitiva, ningún task.
Todos leen v5 una vez por `v_readfirstlane_b32` y lo usan sólo con
`s_lshr_b32 D, sX, 7`. GPU `ms_v5_workgroup.asm` 24/24 (RTX 4060 Ti, RTX 3080,
RTX 4050 Laptop, AMD 740M RADV), `ms_tri.asm` 0 errores, `ms_wave_info_s3`
4096/4096, `ms_clip` 2048/4096.

Geometría: 195 programas, 195/195 wave64, 195 GS con `s_sendmsg` + `v_mbcnt` y
sin export de posición, 195 ES sin `exp` y con escrituras LDS.

Reparto de wave del corpus entero: 23.841 de 26.503 wave64
(10.974/12.101 PS, 9.282/9.282 MS, 2.236/2.236 VS, 1.154/2.689 CS, 195/195 GS).

## 5. Lo que este dossier no cubre

Los **315 programas de malla** que fallan (8.506 − 8.191). Su causa no se ve en
el corpus ni en la ABI: necesita sus logs de fallo, que no tenemos. En su código
hay hipótesis candidatas, no pruebas: la numeración de lanes de `v_mbcnt` para
lanes ≥ 32, la heurística `mesh_stride = max(threads, maxv, maxp)`
(`emit/mod.rs:217`) frente al `NumThreads` real —coinciden en 128/128/128, que
es todo el corpus, y divergen en cuanto `maxv`/`maxp` superen los hilos—, los
rechazos de `cross_lane`, y la ausencia de emulación de wave64 en malla.

Tampoco cubre: la variante malla-como-compute (`design.md:326`) más allá de lo
citado, el cableado del draw, el GS con cruce de lane, ni los pipelines de
geometría fuera de los 195 `$GS_VoxelizeGeneric`.
