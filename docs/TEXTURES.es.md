# Dónde viven las texturas y qué forma tienen

[English](TEXTURES.md) · **Español**

Antes de ofrecer cualquier cosa sobre BCPack, esto mide la población a la que aplicaría: cuántos
streams con textura hay, de qué tamaño son, y si sus tamaños encajan con bloques de 16 bytes. Solo
conteos y geometría; no se publica ni un dato de textura ni un nombre.

## Método

`textures.rpf` tiene dos clases de stream: 1,365 registros `rsc50` de 0.1 KiB de media, y 1,384
streams `raw` de 132.7 KiB de media. Los `rsc50` son índices; los datos viven en los `raw`.

Se inflaron todos los streams `raw` de ese archivo y se midió: tamaño inflado real, su resto
módulo 16, cuántos bloques de 4×4 de 16 bytes caben, y qué dimensiones de textura implican ese
número de bloques.

## Resultado

```
streams raw             1,384
inflados sin error      1,384 (0 fallos)
bytes inflados          464.6 MiB
tamaño módulo 16        0 en 1,384 de 1,384
```

Cada stream es múltiplo exacto de 16 bytes, que es la forma de una textura comprimida en bloques
cuando no lleva cabecera: bloques de 4×4 texeles, 16 bytes cada uno.

Bloques por stream:

| rango | streams |
|---|---:|
| ≤ 512 | 4 |
| 513 – 2,048 | 1,317 |
| 2,049 – 8,192 | 22 |
| 8,193 – 32,768 | 7 |
| 32,769 – 131,072 | 6 |
| > 131,072 | 28 |

Mediana: **2,048 bloques**, o sea 32,768 texeles — una superficie de 128×256, o cualquier rotación.

El caso dominante es llamativo: **1,313 de 1,384 streams llevan exactamente 2,048 bloques**. Otros
dieciséis llevan 4,096 (256×256). Los 55 restantes son los atípicos de arriba.

## El resultado negativo que importa

Al inflar los primeros cuarenta streams y leer sus primeros bytes no aparece **ninguna cabecera de
contenedor**: ni `DDS `, ni `RSC5`, ni `RSC7`. Los streams empiezan directamente con datos de
bloque: ceros, colores planos con alfa y patrones de píxel.

Eso significa que un detector de BCPack no puede funcionar por magia. Tiene que trabajar bloque a
bloque de 16 bytes, que es exactamente la forma del problema que describen los proyectos de
decodificación.

## Lo que esto no dice

No clasifica ni un solo stream como BCPack o BC7. Los dos formatos usan bloques de 16 bytes, así
que el tamaño te da la población, no el formato de cada elemento. Decidirlo requiere el
decodificador que están construyendo `ItsNotRexed/Leonida` y `R0Y00/Xbox2Windows`.

Lo que sí les da es el tamaño y la forma de la población: 1,384 blobs, una clase de tamaño
dominante, sin cabeceras, alineados a bloque. Si un decodificador resuelve el caso de 2,048
bloques, cubre el 95% de los datos de este archivo.

## Reproducir

La medición lee las columnas públicas del índice (`rpf`, `offset`, `compressed`, `inflated`,
`type`) e infla cada stream `raw` del archivo. Necesita el paquete, que no se distribuye; los
conteos de arriba son los que produjo sobre una copia retail.
