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
no está cortado a media estructura.

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

## Lo que esto no dice

No dice nada del significado de los bytes dentro de cada chunk; solo que la cadena, su orden y su
encuadre son lo que la documentación afirma. Los cuerpos no se decodifican aquí.

## Límites

- 68 streams recorridos de 15,380. Se muestrearon diez archivos, uno de ellos (`anim`) más a fondo
  que el resto.
- Un stream cuya longitud declarada se pasa de su tamaño inflado se descartó como truncado; esos
  existen de verdad y hay que manejarlos, no son error de medición.
