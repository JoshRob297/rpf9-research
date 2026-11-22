# rpf9-research

[English](README.md) · **Español**

Ingeniería inversa del contenedor **RPF9** usado por GTA VI (Xbox Series X|S), a partir de
un paquete de 209 GiB del que se tienen 22 archivos `.rpf` y 57 `.ttpf`.

## Qué sabemos antes de empezar

- La magia es `39 46 50 52` en los primeros cuatro bytes: `RPF9` leído como entero
  little-endian. GTA V usa `RPF7` (`37 46 50 52`).
- Los primeros bytes después de la magia no son texto ni una tabla legible: la región
  posterior parece cifrada (entropía alta, sin nombres en claro en los primeros 2 MB).
- En GTA V la tabla de contenidos de un RPF7 va cifrada con AES y las herramientas públicas
  (OpenIV, CodeWalker) conocen esa clave. Para RPF9 no hay herramienta pública.

## Objetivo

Determinar, con evidencia reproducible, **la estructura de la cabecera y de la tabla de
contenidos** de RPF9, y hasta dónde se puede llegar sin la clave. El resultado esperado es
un documento (`docs/RPF9.md`) más un prototipo (`tools/rpf9.py`) que:

1. lea la cabecera y explique cada campo con su medición,
2. diga si la TOC está cifrada y con qué evidencia (no por suposición),
3. liste entradas si logra descifrarla, o explique exactamente qué falta.

## Reglas del repositorio

- **Cada número que aparezca en la documentación debe tener su transcripción en `raw/`.**
  No se afirma nada que no esté medido.
- Lo que no se pueda determinar se escribe como **no determinado**, con la prueba que se
  intentó y falló.
- Los binarios de muestra **no se versionan** (ver `.gitignore`); solo su manifiesto con
  hashes.
- Documentación en pares: `docs/RPF9.md` (inglés) y `docs/RPF9.es.md` (español); igual con
  `docs/NAMES.md` y `docs/INDEX.md`.

Ver `METHODOLOGY.md`.
## Licencia

GPL-3.0-or-later.

El motivo es práctico: el trabajo de referencia más cercano, `ItsNotRexed/Leonida`, es
GPL-3.0 y publica hechos de formato medidos sobre este mismo paquete. Se pueden tomar los
hechos con atribución, pero si en algún momento se reutiliza código, esta licencia es la
única que lo permite sin conflicto. Los proyectos con GPL-2.0-only (`xcl`,
`americas-recomp`) y los de licencia no comercial (`PercyStar`) quedan como referencia de
lectura, nunca como fuente de código.

Ver también `docs/` para el estado medido del formato.
