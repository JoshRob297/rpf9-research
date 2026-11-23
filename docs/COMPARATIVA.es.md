# Cómo se comparan nuestras mediciones con rpf9-extract y PercyStar

[English](COMPARATIVA.md) · **Español**

Tres cosas de este repositorio salen de medir y no de una implementación existente: el framing de los
chunks `PSIN`, la forma de encontrar contenedores anidados y el ancho de una entrada de TOC. Esta
página pone cada una al lado de tres herramientas públicas de RPF9 y dice dónde coinciden los
números, dónde no, y qué lado conviene para qué.

| herramienta | commit leído | qué es |
|---|---|---|
| [offs/rpf9-extract](https://github.com/offs/rpf9-extract/tree/46ca608975b749fc3e77a62435d46fdc115a97e0) | `46ca6089` | extractor + reporte en Rust, descubrimiento por sectores de 4 KiB |
| [rpatty-dev/PercyStar](https://github.com/rpatty-dev/PercyStar/tree/6a64e53f6d1c48aae250109232eebb02a2a68e36) | `6a64e53f` | navegador de datos del juego en Rust, el único de los tres con un decodificador de cuerpos `PSIN` |
| [zeozeozeo/rpf9](https://github.com/zeozeozeo/rpf9/tree/3d8d4fbbf49fe54cb3e91a8a6dee01ff41858c7b) | `3d8d4fbb` | librería de lectura y escritura en Rust, misma forma de descubrimiento que rpf9-extract |

## Método

Los tres repositorios se clonaron en un directorio de trabajo y se **leyeron**, con `nl -ba` para los
números de línea; no se compiló ni se ejecutó ningún binario suyo, así que todo lo que se afirma aquí
sobre su comportamiento es una afirmación sobre su código, no sobre una corrida [verified]. Nuestro
lado de cada comparación sale de las comprobaciones registradas en `docs/PSIN.md`, `docs/NESTED.md`,
`docs/RPF9.md` y de las transcripciones de `raw/comparativa/` [verified].

Los enlaces del cuadro abren cada proyecto en el commit leído; las referencias `ruta:línea` son
relativas a ese commit.

Cada afirmación va etiquetada: `[verified]` significa que se leyó en el `ruta:línea` citado o que
salió de una corrida cuya transcripción está en este repositorio; `[hypothesis]` significa que es una
interpretación que la evidencia sostiene pero no cierra.

## 1. PSIN

### Qué hacen

`rpf9-extract` trata `PSIN` como una etiqueta de payload, no como una estructura: cuando un stream
inflado empieza con `PSIN`, el barrido registra el archivo como `pso`/`PSO`
(`rpf9-extract/src/scan.rs:116-117`) y el bucle de inflado salta el miembro comprimido en un paso
(`rpf9-extract/src/scan.rs:99-107`) [verified]. Nunca recorre los chunks. Su reporte `-v` imprime los
ocho campos de cabecera y los rangos de cuerpo y trailer (`rpf9-extract/src/report.rs:125-142`) y su
README anuncia una tabla de `PSIN` bajo `-v` (`rpf9-extract/README.md:7`); en el código leído aquí el
contenido `PSIN` se clasifica solo por prefijo [verified]. `zeozeozeo/rpf9` hace lo mismo en una línea
(`rpf9/src/scan.rs:285`) [verified].

`PercyStar` es distinto: tiene un lector completo. `parse_iff_chunks` lee una etiqueta de 4 bytes y un
largo `u32` big-endian, toma el cuerpo como `[pos+8 .. pos+sz]` y avanza `pos += sz`
(`PercyStar/src/psin.rs:188-201`) [verified]. `parse_lsch` lee cabeceras de struct de 32 bytes
mientras los 8 bytes en `+16` sean `0xAA`, toma la cuenta de campos de la mitad alta de `+28` y luego
lee registros de campo de 16 bytes (`PercyStar/src/psin.rs:203-232`) [verified]. `parse_lenm` lee una
cabecera de enum de 24 bytes y después los valores de 16 bytes de ese enum antes de buscar la
siguiente cabecera (`PercyStar/src/psin.rs:235-255`) [verified]. Un segundo lector independiente en
`PercyStar/src/vehicle_data.rs:288-340` lee ambas tablas **con todas las cabeceras primero**, que es
lo que medimos abajo [verified]. Los dos lectores se usan: `PercyStar/src/psin.rs:418-419` y
`PercyStar/src/psin_xml.rs:45,80-81` llaman al primer par [verified].

### Qué medimos

`raw/comparativa/psin_census.py` recorre todos los streams `PSIN` de 78 ventanas de muestra y escribe
`raw/comparativa/psin_census.txt`: **4,066** streams, el mismo conteo que la línea de inventario de
payload `raw/payload.txt:62` da para esas ventanas [verified]. El recorrido llega al final exacto del
cuerpo inflado en 3,959 streams: 3,958 cadenas completas de siete chunks y la única variante PMAP;
los otros 107 se detienen en un chunk cuyo largo declarado cruza el final, los prefijos de 64 KiB que
se discuten abajo [verified]. Ningún chunk del barrido declaró un largo menor que 8 [verified]. Los
finales exactos y las ecuaciones de cuerpo de dos fases de abajo son lo que corrobora el framing: unos
límites desplazados 8 bytes cortarían los cuerpos a mitad de registro y no satisfarían esas
ecuaciones [hypothesis]. Los layouts de cuerpo son exactos, no aproximados: `32*N + 16*sum(campos)`
es igual al largo del cuerpo en 3,983 de 3,983 chunks `LSCH` (48,475 cabeceras de struct, 344,446
registros de campo), y `24*N + 16*sum(valores)` lo es en 3,980 de 3,980 chunks `LENM` (11,806
cabeceras de enum, 72,455 valores) [verified]. Los conteos de marcas son por construcción — el
recorrido avanza solo mientras esté `[0xAA;8]` en `+0x10` o `[0xEE;8]` en `+0x08`
(`raw/comparativa/psin_census.py`) —, así que lo que se mide de forma independiente es que la
ecuación de dos fases caiga exactamente en el final del cuerpo, no que las marcas existan [verified].
Esos números son nuevos en esta tarea y también están escritos en `docs/PSIN.md:52-59` [verified].

### Dónde coincidimos

1. **El largo incluye la cabecera de 8 bytes.** Su `pos += sz` con cuerpo `[pos+8..pos+sz]`
   (`PercyStar/src/psin.rs:193-198`) es la misma regla que usa nuestro recorrido de censo, y la que
   produce las 3,958 cadenas completas de arriba [verified].
2. **La magia `PSIN` vive en el cuerpo inflado.** Las tres herramientas clasifican después de
   inflar, no en el contenedor (`rpf9-extract/src/scan.rs:99-107`, `PercyStar/src/psin.rs:388`,
   nuestro `raw/payload.txt`) [verified].
3. **`LSCH` es cabeceras primero, con la puerta `0xAA`.** `PercyStar/src/vehicle_data.rs:287-320`
   enuncia la regla en un comentario y la implementa; nuestro censo halla la lectura cabeceras
   primero exacta en 3,983 de 3,983 cuerpos `LSCH` [verified]. Ambas implementaciones coinciden, que
   es lo útil.
4. **Un chunk corto o que se pasa termina la cadena.** `PercyStar/src/psin.rs:194` corta con
   `sz < 8 || pos + sz > len`; nuestro censo se detiene en el mismo exceso y descarta el stream
   completo, la política que describe `docs/PSIN.md:70-72` [verified]. La rama `sz < 8` nunca se
   activó en el barrido, así que es una guarda que ambos lados mantienen por la misma razón, no una
   diferencia [verified].

### Dónde diferimos

**Profundidad, y la dirección les favorece.** `PercyStar` decodifica instancias, structs, campos,
enums y hashes de nombre, y arma con eso una base de datos de vehículos
(`PercyStar/src/vehicle_data.rs:270-361`), además de poder exportar `PSIN` a XML
(`PercyStar/src/psin_xml.rs`) [verified]. Nuestra herramienta no recorre los cuerpos `PSIN`: se detiene
en `head.startswith(b"PSIN")` y etiqueta el archivo (`tools/rpf9.py:481-482`) [verified]. Todo lo que
sabemos del layout de los cuerpos está en el script de censo y en los documentos, no en la
herramienta. Para extraer contenido `PSIN` su enfoque es el mejor; el nuestro es una medición del
contenedor y hay que leerlo así.

**Una tabla se lee en la dirección contraria.** `PercyStar/src/psin.rs:235-255` lee `LENM` como
cabecera, valores, cabecera, valores. Los cuerpos dicen lo contrario: todas las cabeceras van primero.
La lectura de dos fases llega al final exacto del cuerpo en 3,980 de 3,980 chunks, mientras que la
lectura intercalada lo logra solo en 2,929 — exactamente los chunks con un solo enum; 1,051 chunks
tienen dos o más, y ahí es donde se queda corta [verified]. El mismo repositorio ya contiene la
lectura correcta en `PercyStar/src/vehicle_data.rs:322-340`, así que es una función en desacuerdo con
la otra, y la medición le da razón a `vehicle_data.rs` [verified]. Eso cambia a qué se decodifica un
cuerpo multi-enum, que es un error real para quien use el camino de `psin.rs`; no afecta a los
recursos de un solo enum, y por eso puede sobrevivir [hypothesis].

**Ellos recortan, nosotros saltamos.** Sus bucles de campos se detienen cuando el cuerpo se acaba en
lugar de leer más allá (`PercyStar/src/psin.rs:217-220`, `PercyStar/src/vehicle_data.rs:300-306`)
[verified]. Es la forma mejor para un parser que encuentra un cuerpo truncado. Nuestra primera versión
del censo tenía el defecto contrario — cortaba cuerpos que se pasaban del miembro inflado y producía
falsos desajustes de layout — y el arreglo fue saltar esos chunks por completo
(`raw/comparativa/psin_census.py`) [verified]. Su recorte y nuestro salto llegan al mismo sitio por
razones distintas; el nuestro mantiene limpios los conteos, el suyo sigue devolviendo datos parciales.

### Lo que ninguno de los dos ha medido

Un stream de 4,066 recorre otra cadena: `PSIN → PMAP → PSCH → PSIG → STNS → CHKS`
(`anim.tail.bin @0x3ed8b0`, tamaños 260/56/144/20/1,352/20) [verified]. Ningún repositorio leído aquí
menciona `PMAP`, `PSCH`, `PSIG` ni `STNS` (un grep sobre las tres fuentes no devuelve nada) [verified],
y nuestros propios documentos describen solo la cadena principal (`docs/PSIN.md:38-49`). Un stream de
4,066 no es un segundo formato, pero tampoco está explicado [hypothesis: una variante que usa otro
tipo de recurso]. Es lo primero que hay que muestrear cuando se escriba un parser `PSIN` contra estos
números.

Los 107 streams cuyo largo declarado se pasa del cuerpo inflado inflan exactamente 65,536 bytes
[verified]. Son ventanas de miembros más grandes cortadas por nuestras ventanas de muestra,
no datos malformados [hypothesis], y por eso quedan fuera de los conteos de layout en lugar de
tratarse como rasgo del formato (`docs/PSIN.md:70-72`) [verified].

## 2. RPF9 anidado

### Qué hacen

`rpf9-extract` busca contenedores anidados mientras dispone el archivo. `layout` recorre los huecos
entre archivos conocidos en pasos de 4 KiB (`rpf9-extract/src/container.rs:74`), valida cada candidato
con `Header::parse`, toma el primer acierto como archivo externo y el resto como anidados
(`rpf9-extract/src/container.rs:71-89`) [verified]. El paso es solo la mitad del filtro: `parse`
rechaza cualquier cabecera cuyo largo declarado se pase del búfer (`.../container.rs:32`), así que una
cabecera que valida describe un contenedor completo que está presente en los datos [verified].
`zeozeozeo/rpf9` tiene la misma forma en `discover` (`rpf9/src/archive.rs:65-97`), arrancando en 0 y
saltando rangos ya tallados, con una validación de cabecera más laxa que igual exige las reglas de
tamaño y alineación a 16 bytes (`rpf9/src/header.rs:56-97`) [verified]. `PercyStar` no busca
contenedores anidados: su lector de archivos lee una cabecera de 64 bytes en el offset 0
(`PercyStar/src/main.rs:4833-4841`), y la única búsqueda de `9FPR` en todo el código es un diagnóstico
que cuenta coincidencias de texto en un ejecutable de arranque, con tope de 16 y sin validar nada
(`PercyStar/src/boot.rs:99-113`) [verified].

### Qué medimos

Nuestro barrido busca los bytes de magia en **todos** los offsets, no cada 4 KiB, y acepta una
cabecera solo cuando pasa las comprobaciones de constantes: `+0x18 == 0x47A00`, `+0x1c == 0x150`,
`+0x30 == 16` y tres palabras en cero — unos 28 bytes restringidos (`tools/rpf9.py:54-64`)
[verified]. Cada acierto se censa después: el tamaño se reconstruye desde un trailer block conocido o
desde el hueco de ceros antes de la cabecera siguiente (`tools/rpf9.py:260-299`) [verified], que es
lo que `docs/RPF9.md:48` reporta como 29 tamaños exactos de 55 ocurrencias [verified].

El resultado medido es más estrecho que el argumento: las 122 cabeceras del censo están en múltiplos
de 4,096 (`raw/cabeceras/nested.tsv`), y sobre las seis ventanas de 4 MiB que cubre el censo (`data`,
`packs`, `script`, `common`, `shaders`, `textures`) el barrido byte a byte encuentra las mismas 15
cabeceras que el barrido por pasos, sin extras (`raw/comparativa/nested_scan.txt:125-129`)
[verified]. La diferencia aparece en un archivo: `core_restofworld.head.bin` tiene un contenedor
anidado en `0xaa0` que el barrido por pasos no puede ver, porque arranca en `0x1000`; el barrido byte
a byte lo encuentra y su cabecera coincide con el inventario independiente de `raw/payload.txt:171`
(`w04=0x2c0`, `w24=2`, id `0x162b7cc3d164fea3`, 912 B) [verified]. Así que el paso por sectores perdió
exactamente un contenedor conocido en las diez ventanas muestreadas, y no ganó nada en las seis
ventanas del censo [verified].

### Dónde son mejores

1. **La completitud forma parte de su prueba de validez.** Exigir `at + largo <= búfer` significa que
   un contenedor anidado reportado es un contenedor que se puede leer. Nuestras 26 cabeceras sin
   límite de 55 (`docs/RPF9.md:48`) no serían reportadas por ellos, y esa es la respuesta correcta
   para un extractor: nunca entrega un archivo truncado [verified]. Es el diseño más fuerte para
   extraer, y si nuestro barrido se usa alguna vez para extraer en lugar de medir, esa comprobación
   debería importarse [hypothesis: se puede añadir sin cambiar los conteos del censo].
2. **Su paso es además un filtro de falsos positivos, y gratis.** Un candidato tiene que parsear y
   describir un contenedor completo; el nuestro confía en la magia y seis palabras constantes
   (`tools/rpf9.py:54-64`), con una comprobación de orden (`w08 < w04`) solo en el script de censo
   (`raw/comparativa/nested_scan.py:32`), y sin ninguna coherencia de tamaño [verified]. Sobre
   archivos completos su puerta es estrictamente más fuerte.
3. **Costo.** Un paso de 4 KiB es 1/4096 de los offsets; nuestro barrido paga una búsqueda de magia
   más una comprobación de constantes por acierto, y el barrido byte a byte de las diez ventanas de
   `raw/comparativa/nested_scan.txt` se completa en una pasada [verified]. El suyo es más barato; el
   nuestro es pagable, y por eso se pudo soltar la suposición de alineación.

### Dónde aportamos

La suposición de 4 KiB es una apuesta a la alineación del escritor, y es una apuesta que puede perder:
`0xaa0` es evidencia de que el conjunto de muestras contiene al menos una cabecera anidada que un
barrido por pasos pierde [verified]. También significa que su censo de contenedores anidados es una
cota inferior, mientras que el nuestro — tras la reconstrucción — puede dar un conteo por ventana y un
tamaño por contenedor [verified]. Ninguna de las dos herramientas descifra la TOC, así que ambas
adivinan la extensión del contenedor desde el trailer; la nuestra usa una tabla de valores observados
de block 0 indexada por `w24` más una comprobación de entropía (`tools/rpf9.py:282-299`), la suya usa
el último byte distinto de cero antes del archivo siguiente
(`rpf9-extract/src/container.rs:95-105`) [verified]. La nuestra es exacta cuando la tabla de block 0
tiene el `w24`; si no, cae al hueco de ceros antes de la cabecera siguiente y reporta `unbounded`
cuando no hay cabecera siguiente en la ventana. La suya es general pero heurística. Es un intercambio
real, no una victoria clara.

## 3. Geometría de la tabla

### Su modelo: 16 bytes por registro

Los dos lectores en Rust fijan el ancho de registro en 16 bytes — `RECORD` en
`rpf9-extract/src/container.rs:11` y `RECORD_SIZE` en `rpf9/src/lib.rs:14` — y derivan la cuenta de
registros dividiendo el largo de la tabla (`rpf9-extract/src/container.rs:50-52`) [verified]. Ambos
rechazan una cabecera cuyas tablas no sean múltiplos de 16 (`rpf9-extract/src/container.rs:32`,
`rpf9/src/header.rs:86-97`) [verified]. Ninguno tiene código para un paso de 9, 10 o 12 bytes: un grep
de `stride` sobre los dos árboles de fuentes no devuelve nada [verified]. Sí leen los campos que
seleccionan el paso — `0x2c` se parsea como `u32` (`rpf9/src/header.rs:111`) y se imprime como
desconocido (`rpf9-extract/src/report.rs:138`) — pero nada actúa sobre su byte bajo [verified]. `0x20`
se parte en dos `u16` y se llama `version`/`platform` en `rpf9/src/header.rs:107-108`; la mitad alta
que selecciona la sub-tabla ancha se guarda, no se interpreta [verified].

La consecuencia se ve en un archivo real: `levels.rpf` tiene `w24 = 2,078` y una región `[w08..w04)`
de 20,784 B, que su aritmética lee como 1,299 registros para 2,078 entradas
(`raw/cabeceras/README.md:47-48`) [verified].

### Nuestro modelo: la cabecera predice la tabla

`w04 - w08 == ceil(paso * w24 / 16) * 16` con `paso = 9` o `10` según el byte bajo de `+0x2c`, y
`12` en los casos limpios de mitad alta 2 (`docs/RPF9.md:30`, `docs/NESTED.md:26-33`) [verified]. Se
cumple 54/54 para 9, 15/15 para 10 (69/69 en el conjunto de mitad alta 1) y 22/22 en los 22 fixtures
externos (`raw/cabeceras/README.md:42`); para mitad alta 2 encaja 12 en 13 casos limpios más 2 que
necesitan `w24 + 1`, con una cabecera que sigue usando paso 10 (`docs/NESTED.md:29-33`) [verified].
Eso es lo que permite que una cabecera prediga el tamaño de su propia sub-tabla y que el censo
anidado informe cuentas de entradas sin descifrar nada [verified].

### Qué es mejor, y para qué

Para **tallar**, el modelo de 16 bytes alcanza y es más simple. Las dos herramientas se saltan la TOC
cifrada por completo, encuentran miembros de payload buscando zlib o formatos conocidos
(`rpf9-extract/src/scan.rs:95-107`, `rpf9/src/scan.rs:282-291`) y reconstruyen la extensión del
archivo desde el trailer [verified]. La cuenta de registros nunca alimenta un offset de archivo, así
que 1,299 en lugar de 2,078 les cuesta un número impreso, no una extracción [verified]. La
comprobación de alineación que sí aplican es además un filtro útil de falsos positivos que nuestro
validador de cabecera no tiene [verified].

Para **describir el contenedor**, el modelo de paso es el que coincide con el formato: explica el
ancho de `[w08..w04)`, por qué esa región se rellena a 16, y da el ancho para las 18 cabeceras de
mitad alta 2 [verified]. Sin él, la única salida honesta es "la región mide N bytes", que es a lo
que equivale su `records()`.

Dos puntos flojos nuestros, dichos sin adornos. Nuestra herramienta calcula la fórmula pero no la
exige: `tools/rpf9.py:86-92` anota si la predicción coincide y acepta la cabecera en cualquier caso
[verified]. Su puerta de alineación rechazaría una tabla malformada; la nuestra la reportaría. Y
nuestra tabla de pasos es una regla medida con dos excepciones explicadas (`docs/NESTED.md:31-33`)
sobre 22 fixtures de cabecera (`raw/cabeceras/README.md:42`) y 122 cabeceras anidadas de seis archivos
(`docs/NESTED.md:16`), no una ley [verified].

## Qué tomar de cada lado

- De `PercyStar`: un decodificador de cuerpos `PSIN` (structs, enums, instancias, fixups) y la
  costumbre de recortar al final de un cuerpo corto; nuestro censo es la medición, su código es el
  lector [verified].
- De `rpf9-extract` / `zeozeozeo/rpf9`: la comprobación de completitud `at + largo <= búfer` antes de
  aceptar una cabecera anidada, y el paso de 4 KiB como prefiltro barato; ambas encajan en el barrido
  actual sin cambiar los conteos del censo [hypothesis].
- De este repositorio: la fórmula de paso 9/10/12, los layouts de dos fases `LSCH`/`LENM`, y la
  cabecera anidada `0xaa0` como vector de prueba para cualquier bucle de descubrimiento que asuma
  alineación a 4 KiB [verified].

## Qué no cubre esta comparación

- **No se ejecutó ningún binario de terceros.** Lo que se afirma de su comportamiento sobre archivos
  reales es una inferencia desde su código, no desde una corrida [verified]; una compilación podría
  comportarse distinto [hypothesis].
- **Solo se leyeron los módulos de parser, descubrimiento y reporte.** Cada repositorio tiene más
  código (PercyStar por sí solo es un navegador grande); una función podría estar en otra parte
  [verified].
- **Nuestro censo `PSIN` es una muestra de 78 ventanas**, no la población de 22 archivos con 15,380
  streams (`docs/PSIN.md:9-12`); los conteos de arriba describen las ventanas y lo dicen [verified].
- **Los 107 streams truncados y los 26 tamaños anidados sin límite** son límites del muestreo por
  ventanas, no propiedades medidas del formato [hypothesis].
- **`open-vfs`**, que nuestro documento de `PSIN` cita para el orden de la cadena, no se clonó ni se
  revisó aquí [verified].
