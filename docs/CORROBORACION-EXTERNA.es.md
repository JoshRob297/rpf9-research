# Corroboración externa desde una copia de trabajo distinta

[English](CORROBORACION-EXTERNA.md) · **Español**

Reproducción independiente de dos resultados medidos en este repositorio, hecha sobre una
copia de trabajo *distinta* de v1.0.2.1 y con una implementación propia (sin código
compartido con `tools/`). Se ofrece únicamente como corroboración — reubicar, fusionar o
descartar como prefieras; sin problema en convertirlo en un issue si encaja mejor en el
flujo del proyecto.

## Qué se reprodujo

1. **H8 — fórmula de tamaño de la rejilla `[w08..w04)`** (`docs/RPF9.md` §3, fila `0x08`):
   `w04 − w08 == ceil(9·w24/16)·16` (o `ceil(10·w24/16)·16`), verificada sobre **seis
   cabeceras** de una copia distinta, incluida una hija anidada (`script.rpf` @0x1000)
   analizada sin usar en ningún momento la TOC cifrada.
2. **H13 — estructura del trailer** (`docs/RPF9.md` §5): el trailer cifrado
   `[EOF−w0c..EOF)` de `story000_bvh4` y `core_licenses_data` (mismos `w24=4`,
   `w20_hi=1`, `w0c=144`) comparte **exactamente sus primeros 32 bytes**, divergiendo
   desde el byte 32 (la zona donde empiezan los nombres específicos del archivo). El
   bloque 0 medido del par — `5a178c51e7b96189237e72453084db8a` — reproduce el
   valor publicado byte a byte.

Transcripción (comandos y salida cruda, en español dentro del archivo), dentro de las
clases de evidencia del repositorio (solo trozos de cabecera, sin nombres de payloads,
sin binarios):

- [`raw/corrobora_externa_w08_trailer_v1021.txt`](../raw/corrobora_externa_w08_trailer_v1021.txt)

## Método y límites

- Copia de trabajo: instalación v1.0.2.1 distinta, en otra máquina; solo se leyó la
  cabecera (64 B) y los `w0c` bytes finales de cada contenedor.
- Seis contenedores medidos: los cuatro archivos pequeños completos citados en la tabla
  de coherencia de `docs/RPF9.md` §3 más dos cabeceras anidadas. Los seis cumplen la
  fórmula H8 exactamente.
- Nada de esto afirma algo nuevo sobre el cifrado, la clave o el contenido de payloads.
- No se incluye ningún dato de juego; la transcripción solo contiene valores de campos
  de cabecera y los primeros 32 bytes de los trailers.
