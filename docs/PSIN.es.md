# La cadena de chunks PSIN, recorrida

[English](PSIN.md) · **Español**

`open-vfs` documenta la cadena como `PSIN → LSCH → LENM → LSNS → LGID → LRSC → CHKS` y tiene una
tarea abierta para implementar el parser. Esto la mide sobre un paquete retail para que la
implementación no arranque de una suposición.

## Población

Streams clasificados como `PSIN` en los 22 archivos: **15,380**, repartidos en diez archivos
(`levels`, `packs`, `anim`, `navmesh`, `story000`, `script` y cuatro menores).

## La regla de encuadre que hace que camine

Cada chunk es `magia (4 bytes) + longitud (u32 big-endian) + cuerpo`, y **la longitud incluye la
cabecera de 8 bytes**. Avanzar `8 + longitud` deja 8 bytes antes de la magia siguiente; avanzar
`longitud` cae exactamente sobre ella.

Esa sola regla es la diferencia entre un parser que lee un chunk y uno que lee la cadena. Medido
sobre 73 streams: la magia siguiente está en `offset + longitud` en 56 de 56 casos donde el stream
no está cortado a media estructura. Un barrido más amplio de 78 ventanas lo repite: 23,829 de
23,829 sucesores caen en `offset + longitud` y ninguno en `offset + 8 + longitud`
(`raw/comparativa/psin_census.txt`).

## Resultado

Recorriendo con esa regla 68 streams de diez archivos:

```
PSIN -> LSCH -> LENM -> LSNS -> LGID -> LRSC -> CHKS     67 streams
PSIN -> LSCH -> LENM                                      1 stream (muestra truncada)
```

El orden coincide exactamente con la cadena documentada, y arranca en el offset 0 sin relleno de
alineación entre chunks. Conteo en la muestra: `PSIN` 68, `LSCH` 68, `LENM` 68, `LSNS` 67, `LGID`
67, `LRSC` 67, `CHKS` 67.

## Formas

Los tamaños varían por archivo pero se repiten dentro de él. Tres ejemplos:

```
anim@24576        PSIN(2,048) -> LSCH(440) -> LENM(8) -> LSNS(196) -> LGID(8) -> LRSC(88) -> CHKS(20)
anim@450162688    PSIN(9,168) -> LSCH(648) -> LENM(8) -> LSNS(68)  -> LGID(8) -> LRSC(88) -> CHKS(20)
anim@450179072    PSIN(22,608) -> LSCH(648) -> LENM(8) -> LSNS(68) -> LGID(8) -> LRSC(88) -> CHKS(20)
```

`LENM` y `LGID` son siempre 8 bytes: cabecera sin cuerpo. `CHKS` son 20. Las partes variables son
`LSCH` y `LRSC`, que es donde vive la metadata del recurso.

## Dentro de los cuerpos

Los cuerpos son tablas de dos fases, no bloques opacos. `LSCH` contiene `N` cabeceras de struct de
32 bytes consecutivas, cada una con la marca `[0xAA;8]` en `+0x10`, y luego un registro de campo de
16 bytes por cada cuenta guardada en `+0x1C` (mitad alta). `32*N + 16*sum(cuenta)` es igual al
largo del cuerpo en los 3,983 chunks `LSCH` que caben en su stream. `LENM` es el mismo patrón con
cabeceras de 24 bytes (marca `[0xEE;8]` en `+0x08`) y registros de valor de 16 bytes: 3,980 de
3,980 cuerpos son `24*N + 16*sum(cuenta)`. Los conteos están en `raw/comparativa/psin_census.txt`.

## Lo que esto no dice

No dice nada del significado de los bytes dentro de cada chunk; solo que la cadena, su orden y su
encuadre son lo que la documentación afirma. Los cuerpos no se decodifican aquí.

## Límites

- 68 streams recorridos de 15,380. Se muestrearon diez archivos, uno de ellos (`anim`) más a fondo
  que el resto.
- Un stream cuya longitud declarada se pasa de su tamaño inflado se descartó como truncado; esos
  existen de verdad y hay que manejarlos, no son error de medición. En el barrido de 78 ventanas
  hay 107, todos inflando exactamente 65,536 bytes; sus cuerpos quedan fuera de los conteos de
  layout de arriba.

`docs/COMPARATIVA.es.md` pone este framing al lado del único lector público de PSIN que lo recorre
(`PercyStar/src/psin.rs:188-201`, con sus propios lectores de tabla en `vehicle_data.rs`) y de las dos
herramientas que solo etiquetan el stream.
