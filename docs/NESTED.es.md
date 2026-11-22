# Cabeceras RPF9 anidadas y la subtabla ancha

[English](NESTED.md) · **Español**

Los 22 archivos de nivel superior comparten la misma forma de cabecera: la mitad alta de `+0x20`
vale 1 y el paso de la tabla es de 9 o 10 bytes. Las muestras anteriores mostraban además
cabeceras donde esa mitad vale 2 y la tabla no cuadra con ese paso. Aquí se cierra esa pregunta
con medición.

## Método

Un recorrido en streaming sobre seis archivos (5.6 GiB: `data`, `textures`, `packs`, `script`,
`common`, `shaders`) busca la magia en los dos órdenes y conserva un hallazgo solo si la cabecera
valida: `+0x18` igual a `0x47a00`, `+0x1c` en `0x150`/`0x154`/`0x158`, `w24` distinto de cero, y
`toc_end_offset` mayor que `toc_subtable_offset` y menor a 64 MiB. Solo lectura; no se extrae nada.

Resultado: **122 cabeceras válidas**, 104 con la mitad alta de `+0x20` en 1 y **18 en 2**.

## El paso, por grupo

Para cada cabecera se prueba qué paso `s` cumple

```
toc_end_offset - toc_subtable_offset == ceil(s * w24 / 16) * 16
```

| grupo | cabeceras | paso que cuadra |
|---|---:|---|
| mitad alta 1 | 104 | 9 o 10, según el byte bajo de `+0x2c` |
| mitad alta 2 | 18 | **12** en 13 de ellas; 2 más cuadran con 12 solo si el conteo es `w24 + 1`; 1 cuadra con 10 y byte bajo de `+0x2c` en 1 |

O sea: la subtabla ancha no es un misterio, es una **entrada de 12 bytes**. Los dos residuales son
16 bytes más grandes de lo que predice la fórmula, que es exactamente un registro de 16 bytes, y
la tercera es una cabecera con mitad alta 2 que sigue usando el paso de 10.

Los 13 casos limpios se repiten en `data.rpf`: trece cabeceras con `w24 = 1115`, byte bajo de
`+0x2c` en 2 y región 13,392. `12 * 1115 = 13,380`, y `ceil(13380/16)*16 = 13,392`.

## Qué cambia esto

La salvedad de `raw/cabeceras/README.md` decía que el caso de mitad alta 2 "es una pregunta
abierta, no un problema resuelto". Ahora es una regla medida con dos excepciones contabilizadas, y
la tabla está en `raw/cabeceras/nested.tsv` con una fila por cabecera.

## Límites del método

- Solo son visibles las cabeceras anidadas **sin comprimir**. Una dentro de un stream zlib no
  muestra su magia y no se cuenta.
- Se recorrieron seis archivos, no los 22. Los 5.6 GiB cubren los tipos de contenedor que anidan
  otros; `levels` y `audio` no entraron.
- Seis de las 18 cabeceras con mitad alta 2 tienen `w24` entre 3 y 76, donde cualquier paso entre
  8 y 16 redondea a la misma región. Son compatibles con 12 pero no lo prueban; los trece casos de
  `w24 = 1115` son los que sostienen el argumento.
