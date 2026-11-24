# Aporte 04 — Recurso tipeless para los formatos 86 y 115 (#16)

Contra VIctory en `97c78d1` (rama `JoshRob297/aporte-typeless`). Comparativo:
`docs/VICTORY-VS-OURS.md:100-124`. Medida propia: `docs/d3d12_vulkan.md:388-400`.

Sin datos de juego: ni rutas, ni contenedores, ni hashes. Solo conteos, tamaños y líneas.
**Hecho** = leído en código o cabecera de Windows. **Inferencia** = deducido, paso intermedio
a la vista. **Sin medir** = hace falta una máquina NVIDIA.

---

## 0. Qué propone, y qué no

#16 dice, con esas palabras: `CreateCommittedResource` con `ALLOW_UNORDERED_ACCESS` sobre
`B5G5R5A1_UNORM` y con `ALLOW_RENDER_TARGET` sobre `B4G4R4A4_UNORM` fallan, y de ahí salen dos
«no host texture» de 2560×1440 (formatos 86 y 115). VIctory ya tiene un parche en el hilo
(*parche FIocker*): reintenta sin los usos que el driver rechaza. **No está** en `97c78d1` —
no hay `unsupported_uses` ni RTV nulo en el árbol. Este aporte es la otra mitad: en vez de
tirar el uso, **enseñar al host un formato que sí lo soporta** y guardar el del título para
las vistas. No toca el tope de un millón de descriptores (§3).

---

## 1. La receta

**Hecho.** La creación es `crates/victory-gpu/src/resource.rs:800-874` (`host_texture`), no
`host.rs:1205-1214`: eso es `swap_format`, la tabla de presentación, sin entrada para 86 ni
115 (`host.rs:1210-1218`).

1. **Formato de almacenamiento.** Si el título pide `UNORDERED` (bit `4` de `desc.flags`) o
   `RENDER_TARGET` (bit `1`) sobre 86/115, se crea con un formato de 16 bits que el host
   acepte para ese uso — `R16_UINT` (**57**) — y no con 86/115. El tamaño por texel no cambia:
   `element()` da `(2, 1)` para 85, 86 y 115 (`resource.rs:126`), así que pies y offsets
   siguen valiendo.
2. **Lista de formatos casteables.** `CreateCommittedResource3`/`CreatePlacedResource2` toman
   `NumCastableFormats` + `pCastableFormats` (`d3d12.h:23495-23506`). Lista: `{57, 86}` o
   `{57, 115}`. VIctory ya llama a esa puerta y **tira la lista**: `create_committed3` recibe
   `_castable_count`/`_castable` y reenvía a `create_committed` (`resource.rs:1034-1049`). Ese
   es el enganche.
   - **Hecho:** `D3D12_OPTIONS12.RelaxedFormatCastingSupported` existe (`d3d12.h:2861`) y es
     lo que permite castear dentro de la lista.
   - **Inferencia:** 86 y 115 **no tienen hermano `_TYPELESS`** (`dxgiformat.h:98-115`: 85, 86,
     87 y 115 van seguidos; no hay `B5G5R5A1_TYPELESS` ni `B4G4R4A4_TYPELESS`). El recurso no
     puede ser «typeless» literal: es *tipado con lista casteable*. Esto corrige la inferencia
     del comparativo (`VICTORY-VS-OURS.md:121`).
3. **Vistas con el formato del título.** `descriptor/host.rs:556-597` (`fits`) ya hace lo
   correcto para un recurso typeless: si el recurso no lo es, **fuerza** su formato en la
   vista (`:594-596`); si lo es, respeta el de la vista dentro de la familia (`:589-592`).
   Falta que la detección de typeless (`:576`, `family(own) == own && family(own+1) == own`)
   reconozca una lista casteable. `view_format()` (`resource.rs:282-288`) devuelve el formato
   propio cuando difiere del host: con almacenamiento 57 y título 86 devuelve 86.
4. **Clear y copia.** Es lo que el parche FIocker no hace:
   - **Copia:** `texture.rs:103-169` arma las localizaciones desde los `footprint` del host y
     llama `CopyTextureRegion` (`:166`); se guía por tamaños, no por formato, así que sobre
     `R16_UINT` los 16 bits se mantienen. `list.rs:439-465` (`copy_resource`) tampoco compara
     formatos.
   - **Clear de UAV: no existe.** No hay `ClearUnorderedAccessViewFloat/Uint` en el árbol; la
     tabla de métodos solo trae `clear_dsv` (51) y `clear_rtv` (52) (`list.rs:1313-1314`). Hay
     que implementarlo con empaquetado 5-5-5-1 (86) y 4-4-4-4 (115), redondeo al más cercano y
     clamp: la regla que medimos en `docs/d3d12_vulkan.md:322-323`. Sin esto el título limpia a
     un valor que nunca llega al recurso.
   - **Clear de RTV:** `list.rs:670-714` sí existe; el RTV lleva
     `Format: DXGI_FORMAT(v.format)` (`draw.rs:380`), así que los bits se reescriben igual.
   - **Trampa:** `legal_for` prohíbe combinaciones por flags (`host.rs:1494-1507`, tabla
     `FORBIDDEN`, 4 entradas) y `host_texture` ya lo consulta al crear (`resource.rs:858`). El
     formato sustituto debe pasar esa tabla, no solo `CheckFeatureSupport`.

---

## 2. Qué sustituye a cuál, sin tabla por vendor

**Hecho.** El parche del hilo consulta `CheckFeatureSupport(D3D12_FEATURE_FORMAT_SUPPORT)` y
mira `Support1 & D3D12_FORMAT_SUPPORT1_RENDER_TARGET` (`d3d12.h:2439`) y
`..._TYPED_UNORDERED_ACCESS_VIEW` (`d3d12.h:2449`): preguntar por **uso**, no por nombre de
GPU. Es el criterio correcto, pero en `97c78d1` esa consulta no sirve: `device.rs:305-313`
contesta `q[1] = 0x7fff_ffff; q[2] = 0xffff;` («todo uso de todo formato», con el comentario
«shortcut: … once there is one»). Hay que reenviarla al dispositivo real:

```rust
// device.rs, rama FORMAT_SUPPORT de check_feature_support
let q = unsafe { &mut *data.cast::<[u32; 3]>() };
let mut s = D3D12_FEATURE_DATA_FORMAT_SUPPORT {
    Format: DXGI_FORMAT(q[0] as i32), ..Default::default() };
unsafe { host_device.CheckFeatureSupport(D3D12_FEATURE_FORMAT_SUPPORT,
    (&raw mut s).cast(), size_of_val(&s) as u32)? };
q[1] = s.Support1.0;
q[2] = s.Support2.0;
```

Con eso la elección queda así (todo **inferencia** hasta medirlo en NVIDIA; el «no soporta» de
partida es **hecho**, está en #16):

| título | uso | almacenamiento | vista RTV/SRV | vista UAV | clear |
|---|---|---|---|---|---|
| 86 | UAV | `R16_UINT` (57) | 86 | 57, mismos bits | empaquetar 5-5-5-1 |
| 86 | RTV | 86 o 57 | 86 | — | `ClearRenderTargetView` (ya existe) |
| 115 | RTV | **sin sustituto honesto** (§3) | 115 (el driver lo rechaza) | — | — |
| 115 | SRV/copia | `R16_UINT` | 115 | — | — |

El «mismos bits» del UAV de 86 es **hecho** en tamaño (2 bytes) y **sin medir** en uso: si el
shader hace `as_float` sobre el UAV hay que decodificar 5-5-5-1 en el shader, y eso no lo
podemos afirmar sin ver ese shader.

**Lo que hay que medir en hardware** (no lo tenemos): (a) que `R16_UINT` responda
`TYPED_UNORDERED_ACCESS_VIEW` donde 86 no; (b) que `CreateCommittedResource3` con `{57, 86}`
acepte el recurso de 2560×1440; (c) si el shader indexa el UAV como entero o como float.

---

## 3. Efecto esperado y lo que no arregla

Los dos «no host texture» de 2560×1440 desaparecen. Para **86** el efecto puede ser exacto:
los bits son los mismos y solo cambia el formato declarado en las vistas. Para **115** como
render target **no**: el formato que el driver rechaza *es* el de la vista, así que castear no
lo devuelve; solo queda el RTV nulo del parche FIocker o que el pase escriba 4-4-4-4
empaquetado en un `R16_UINT`. Decirlo de otra forma sería vender de más.

**No arregla** el tope de un millón de descriptores
(`host view heap capped at 1000000 … count=1245184`), que el reportero señala como causa
probable del cuelgue: eso es PR #21, ya fusionado. Tampoco el TDR ni los fotogramas negros que
los probadores siguen viendo con el parche FIocker.

---

## 4. Verificarlo sin GPU NVIDIA

1. **Que elige tipeless.** Con un `desc` sintético de formato 86 con `flags |= 4`, afirmar que
   la decisión devuelve 57 + lista `{57, 86}`. Prueba de unidad pura: inyectar la respuesta de
   `CheckFeatureSupport` como parámetro. Hoy no se puede porque `host_texture` llama a
   `crate::host::host()` (`resource.rs:811`) y a `CreateCommittedResource` (`:853`) dentro;
   separar decisión de creación es el cambio mínimo que lo hace testeable.
2. **Que las vistas salen bien.** `fits` (`descriptor/host.rs:556`) es pura salvo `GetDesc`:
   con un recurso de formato 57 y una vista pedida en 86, afirmar que la deja en 86; con una
   pedida en 87, que la rechaza con «view format of another family» (`:589-592`). Hoy la lista
   casteable no entra en la detección de typeless (`:576`), así que la prueba **falla** antes
   del parche y pasa después: es la que hay que escribir.
3. **Que el empaquetado del clear es el de WARP.** El clear de UAV hay que implementarlo
   (§1.4) y se prueba sin GPU contra la tabla ya medida: 5-5-5-1 y 4-4-4-4 con redondeo al más
   cercano y clamp (`docs/d3d12_vulkan.md:322-323`), con casos límite 0.5, 1.0, negativo y NaN.

Solo el punto (b) de §2 exige hardware, y lo puede correr cualquiera de los tres probadores
del hilo.
