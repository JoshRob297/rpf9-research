# Cómo se ve un stream de audio en el offset cero

[English](AUDIO.md) · **Español**

`open-vfs#18` pide un parser de cabecera `ADAT`/`AWC`: validación de magia, versión, flags, número de
streams, tamaño de cabecera y tabla de offsets. Esto mide dónde está realmente esa cabecera, y
reporta un resultado negativo que cambia la forma del parser.

## Población

`audio.rpf` tiene **838 streams, todos de tipo `raw`**, 26.6 GiB comprimidos en 11 tramos del
escaneo. Solo 68 llevan nombre, y los nombres son identificadores de clip, no rutas.

## Qué muestran los primeros bytes

Inflando los primeros 60 streams y leyendo sus primeros cuatro bytes:

```
0xffffffff   6   relleno
0x00000000   5   silencio con un float 1.0 cerca
0x0000803f   2   un float 1.0, o sea ya datos de audio
"AMB_"       1   ASCII: AMB_STREAM_ANIMALS_01\0AMB_STREAM_...
otros       46   patrones de float y PCM
```

**Ninguno empieza con `ADAT` ni `AWC`.** El payload arranca directo con datos de audio —muestras
float, silencio, relleno— y el único ASCII presente son identificadores de clip embebidos en el
cuerpo.

## Qué significa para el parser

El archivo no es una sucesión de chunks autodescriptivos como `PSIN`. Una comprobación de magia por
stream rechazaría 60 de 60 en esta muestra, así que la cabecera o vive a nivel de archivo (antes del
primer stream, en la región que el escaneo clasifica como índice) o en un número pequeño de streams
dedicados que esta muestra no alcanzó.

La consecuencia práctica es la misma que produjo la medición de texturas: **no encuadres el parser
en una magia por stream**. Localiza la cabecera por estructura y trata el resto como payload opaco.

## Límites

Sesenta streams de 838, tomados de los primeros offsets del índice, que no están distribuidos al
azar por el archivo. Un stream de cabecera dedicado, si existe, puede estar más adentro. Esto es un
resultado negativo sobre la muestra, no una prueba de que no exista ninguna magia `AWC` en
`audio.rpf`.
