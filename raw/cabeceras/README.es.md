# Cabeceras RPF9

[English](README.md) · **Español**

Los 64 bytes de cabecera de 22 archivos RPF9 retail, extraídos en solo lectura y publicados como
vectores de prueba. Es geometría del contenedor: magia, offsets, conteos y banderas. No contiene
nombres, ni payload, ni material de llave — aquí no hay nada que describa el contenido de un
archivo.

## Archivos

```
headers.bin        1,408 bytes: 22 x 64, mismo orden que headers.tsv
headers.tsv        una fila por archivo con los campos medidos
headers.json       lo anterior más el hex completo de cada cabecera
rpf9_headers.hpp   fixture de C++ (std::array<std::uint8_t, 64>), listo para un archivo de pruebas
rpf9_headers.py    fixture de Python, los mismos datos
```

## Mapa de campos usado para derivar la tabla

| offset | tipo | campo |
|---|---|---|
| `0x00` | 4 bytes | magia, en disco `39 46 50 52` (`RPF9` como u32 little-endian) |
| `0x04` | u32 | `toc_end_offset` |
| `0x08` | u32 | `toc_subtable_offset` |
| `0x0c` | u32 | `trailer_length` |
| `0x18` | u32 | constante `0x47a00` en los 22 |
| `0x1c` | u32 | constante `0x150` en los 22 |
| `0x20` | u32 | la mitad alta selecciona la forma de la tabla (ver salvedad) |
| `0x24` | u32 | número de entradas |
| `0x28` | u32 | etiqueta de perfil de llave |
| `0x2c` | u32 | el byte bajo vale 1 o 2 y selecciona el paso de entrada |

## La relación que este fixture existe para probar

La región de la tabla, desde `toc_subtable_offset` hasta `toc_end_offset`, equivale a

```
ceil(stride * w24 / 16) * 16        stride = 8 + (byte en 0x2c)
```

Se cumple en **22 de 22** archivos de este conjunto. El byte en `0x2c` vale 1 en 15 archivos
(paso 9) y 2 en los otros 7 (paso 10). `levels.rpf` como ejemplo: `w24 = 2078`,
`byte 0x2c = 2`, o sea paso 10; `10 * 2078 = 20780`, y `ceil(20780 / 16) * 16 = 20784`, que es
exactamente `toc_end_offset - toc_subtable_offset`.

Un parser que avance 16 bytes fijos por entrada lee `levels.rpf` como 1,299 registros que
contienen 2,078 entradas. Esa diferencia es para lo que sirve el fixture.

## Salvedad

Los 8 archivos cuya mitad alta de `0x20` es 2 usan una subtabla más ancha. Ninguno está en este
fixture: los 22 de aquí son todos mitad alta 1. El caso ancho está medido en `docs/NESTED.md` —es
una entrada de 12 bytes— y las 122 cabeceras detrás de esa conclusión están en `nested.tsv`.

## Procedencia

Extraídas con un script de solo lectura sobre un paquete en un entorno de laboratorio; los
archivos nunca se modificaron y su sha256 completo no se publica porque los archivos tampoco. Cada
valor de `headers.tsv` se deriva de los bytes de `headers.bin`, y `headers.bin` son los bytes en
disco: ambos se pueden verificar entre sí.
