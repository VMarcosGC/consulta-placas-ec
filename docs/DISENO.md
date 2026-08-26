# Sistema de diseño

> Resultado de dos revisiones cruzadas (§16.1). Lo que está aquí sobrevivió a
> ambas; lo que se descartó está al final, con el motivo, para que no se
> reintroduzca por olvido.

---

## 1. Concepto: dos registros

El producto muestra **dos clases de dato en la misma pantalla**: lo que el
vendedor declara y lo que dice un registro público. Hoy ambas se pintan igual,
así que la transparencia que da nombre al producto es invisible.

| Registro | Origen | Temperatura | Tipografía |
|---|---|---|---|
| **Oficial** | ANT, AMT, EPMTSD | fría | monoespaciada |
| **Declarado** | el vendedor | cálida | sans |

La distinción es **binaria y descriptiva**: dice *de dónde viene* el dato, no
cuánto vale. Nunca se mezclan.

Que la tipografía cargue la misma distinción que el color no es redundancia: es
lo que hace que el sistema sobreviva al daltonismo, a la escala de grises y a
una pantalla barata a pleno sol.

### Lo que este sistema NO afirma

No puntúa confianza. ANT y AMT respaldan hechos concretos —matrícula, multas—,
no la veracidad de un anuncio. Precio, fotos, estado mecánico e intención de
venta no los valida nadie. Cualquier indicador que agregue esos hechos en una
nota compuesta fabrica una calificación con apariencia oficial, y en un producto
cuyo diferenciador es la precisión, eso se autodestruye.

---

## 2. Paleta

Base: WGSN x Coloro, Key Colours S/S 27. Los hex son **aproximaciones derivadas
de las descripciones oficiales** — Coloro no publica equivalencias y sus
swatches son físicos y licenciados. Si el color importa a nivel marca, hay que
comprarlos.

| Token | Hex | Coloro | Único trabajo |
|---|---|---|---|
| `--marca` | `#2F3FC7` | 125-28-38 | acciones primarias y registro oficial |
| `--accion` | `#CB4A16` | 018-57-34 oscurecido | **solo** la acción de conversión |
| `--confirmado` | `#4B7A3E` | 050-61-19 | estado "al día". Nunca una acción |
| `--declarado` | `#C08D7C` | 014-60-13 | superficie de lo declarado |
| `--atencion` | `#B04A22` | derivado | "pendiente" del vehículo. Nunca una acción |
| `--critico` | `#8A2F43` | derivado | el peor estado del vehículo: "requiere atención" y **matrícula vencida**. Nunca una acción |
| `--error` | `#A8332B` | derivado | **fallo de la interfaz** y el estado "rechazado" de una decisión nuestra. Nunca un estado del vehículo, **nunca una acción** |
| `--destructivo` | `#7E2119` | derivado | **la acción de destruir**: borrar, rechazar, quitar. Nunca un estado, nunca un mensaje |
| `--lienzo` | `#FAF6F3` | — | fondo de página |
| `--tinta` | `#22201F` | — | texto primario |
| `--secundario` | `#706258` | — | texto secundario |
| `--superficie` | `#FFFFFF` | — | fondo de tarjeta. El lienzo es el fondo de *página* |
| `--superficie-tenue` | `#F2ECE8` | — | relleno sutil dentro de una superficie |
| `--borde` | `#E4DAD4` | — | filete de tarjeta (decorativo) |
| `--borde-suave` | `#EFE7E2` | — | divisor interno (decorativo) |
| `--borde-fuerte` | `#A0918A` | — | borde de **control de formulario** |

Las seis últimas filas —del `--secundario` para abajo— entraron a la tabla en
**TASK-017**. Nacieron en 1A como "neutros cálidos derivados", un anexo local de
`globals.css`, porque esta tabla definía texto y estados pero no bordes ni
superficies, y `slate` es azulado y pelea con el lienzo cálido. Estaban en uso
real en los cuatro primitivos compartidos, así que un anexo era exactamente el
lugar equivocado: un token que la mitad de la interfaz usa es parte del sistema,
no una nota al pie. Ahora si cambian acá, cambian allá.

`--borde-fuerte` **no se mide con el criterio de los otros dos bordes.** Es el
límite de un control de formulario, así que le aplica WCAG 1.4.11 (3:1 contra el
fondo adyacente), no el criterio de texto. Da **3.04:1 sobre blanco**, que es el
fondo real del `<input>` (`bg-superficie`). Los otros dos son decorativos y no
tienen piso: si un borde decorativo tuviera que pasar 3:1 dejaría de ser un
filete y sería un marco.

> **Margen de 0.04, y el criterio no es el mismo que arriba.** Sobre `--lienzo`
> ese borde da **2.83:1** y no pasaría; se salva porque el input es blanco. Y a
> cuatro párrafos de acá este documento fija el piso del texto secundario en
> 4.8:1 —por encima del 4.5:1 de la norma— con el argumento de que el mínimo
> exacto no deja margen para el próximo retoque. Aceptar 3.04:1 acá usa el
> criterio contrario. Se deja anotado, no resuelto: subir el borde a ~3.3:1
> costaría oscurecerlo y pesa distinto en un control que en un texto. **Quien
> retoque este hex tiene que decidir el criterio primero.**

**Regla dura:** un color, un trabajo. Si `--accion` aparece dos veces en una
pantalla, deja de significar "esto es lo que vas a tocar".

### `--error` y `--atencion` no son el mismo color (agregado 2026-08-11)

Se agregó `--error` al inventariar la migración: hay **96 usos de `rose`** para
mensajes de fallo y la tabla no tenía token para ellos.

**No se reutiliza `--atencion`.** Significan cosas distintas y de dominios
distintos: `--atencion` es *"el vehículo tiene una multa"* —un estado del auto,
un hecho del mundo— y `--error` es *"algo falló en la interfaz"* —no pudimos
cargar, el formulario está mal—. Pintarlos igual haría que un problema nuestro se
lea como un problema del auto, que es justo lo contrario de repartir bien la
responsabilidad (§7). Reutilizarlo además violaría la regla dura de arriba.

Contraste verificado: **6.62:1 sobre blanco** y **6.16:1 sobre lienzo**. Pasa AA
para texto normal en ambos fondos sin necesidad de oscurecerlo.

### `--destructivo`: la acción, separada del mensaje (agregado 2026-08-26)

`--error` estaba cargando **dos** trabajos y la fase 3 lo destapó: el mensaje
*"no pudimos cargar"* y el botón *"Eliminar"*. Uno es algo que **nos pasó**; el
otro es algo que **el usuario va a hacer**. Todos los demás tokens de estado
llevan escrito "nunca una acción" —`--confirmado`, `--atencion`, `--critico`—;
`--error` era el único sin esa línea, y por eso se le fue acumulando la acción
encima. Ahora también la lleva, y la acción tiene token propio.

**Qué es cada uno, para no volver a mezclarlos:**

| | `--error` | `--destructivo` |
|---|---|---|
| Qué es | un hecho consumado nuestro | un control que el usuario toca |
| Forma | relleno de tinte + texto | **contorno, nunca relleno** |
| Ejemplos | "No pudimos cargar", "✕ Rechazada" | "Eliminar", "Rechazar", "Quitar" |

**La separación es por PESO, no por tono, y hay que decirlo de frente.** La
paleta ya tiene **cinco** tokens cálidos dentro de ~20° de hue (`--error` 3.8°,
`--critico` 346.8°, `--atencion` 16.9°, `--accion` 17.2°). Un sexto rojo separado
por 1–5° sería invisible, y repetiría exactamente el problema que este documento
ya admite entre `--critico` y `--error`. Lo que separa a `--destructivo` es que
es **más oscuro** —9.91:1 contra 6.62:1 sobre blanco— y que su forma es siempre
la misma. Peso y forma cargan la distinción, igual que la tipografía en §1 y el
anillo más arriba.

**No lo aclares para "diferenciarlo" de `--error`**: perdería lo único que hoy lo
distingue. Si alguna vez hace falta más separación, el camino es la forma o un
paso de confirmación, no el hue.

Contraste verificado: **9.91:1 sobre blanco**, **9.22:1 sobre lienzo**, **8.47:1
sobre `--superficie-tenue`**. Como borde de control cumple WCAG 1.4.11 (3:1) con
margen de sobra.

### El tercer estado del vehículo tiene token propio (agregado 2026-08-26)

El vehículo se describe con una escala de **tres** pasos —`tonoEstadoComponente()`
devuelve `bueno → regular → requiere_atencion`— pero la tabla solo daba dos
colores: `--confirmado` y `--atencion`. El tercero **prestaba** la familia de
`--atencion` y se distinguía por un anillo.

Prestar es lo que rompe la regla dura: `--atencion` significaba "pendiente" y
"requiere atención" a la vez, o sea que había dejado de significar una cosa. Por
eso el token propio, no por gusto estético.

**Es vino, no rojo, y eso no es negociable.** El rojo ya es `--error`, que es un
fallo *nuestro*. Un auto que requiere atención pintado del mismo rojo con el que
decimos "no pudimos cargar" invierte exactamente el reparto de responsabilidad
de §7.

**La regla "un color, un trabajo" NO queda saldada con este token.** Sería cómodo
escribirlo y seguir, así que se anota lo contrario:

- ~~`--atencion` sigue cargando **tres** trabajos~~ **Saldado en la fase 3
  (2026-08-26).** Las tandas 1B/1C pasaron *"Ficha incompleta"* y *"Sin
  verificar"* al tono `neutro`, así que `--atencion` hoy solo pinta el estado
  "pendiente" del vehículo. Verificado por grep: ninguna utilidad `atencion`
  aparece fuera de `DatosOficialesMini`, `PerfilVehiculo` y `ResumenPlaca`, y en
  las tres es una multa o un pendiente del auto.
- `--critico` cubre dos casos, no uno: el tercer estado de un componente
  (`tonoEstadoComponente()`) y **la matrícula vencida** (`ResumenPlaca`). Son
  coherentes entre sí —los dos son "lo peor que le pasa a este auto"— y por eso
  comparten token, pero la celda de la tabla lo dice explícitamente en vez de
  dejar que el lector lo descubra en el código.

**Lo que este token NO resuelve, dicho de frente:** la separación con `--error`
es de **17° de hue**. En una pantalla barata a pleno sol eso no alcanza, y sería
deshonesto anotar el token y seguir. Lo que de verdad separa a los dos es el
**anillo** del tono `peligro` y el lugar donde aparece cada uno — el mismo
argumento de §1, donde la tipografía carga la distinción para que el sistema
sobreviva al daltonismo y a la escala de grises. **No quitar el anillo** creyendo
que el color nuevo ya alcanza.

### El gradiente de marca CONVIVE con `--marca` (agregado 2026-08-11, corregido 2026-08-26)

No se reemplaza uno por otro; tienen trabajos distintos:

- **`--marca` (plano)** — acciones primarias y registro oficial. Es el que se usa
  al migrar utilidades.
- **Gradiente `brand-from/via/to`** — **identidad**, y **solo en el logo**.

**Corrección de TASK-017.** Eran dos lugares: el logo y el chip Premium. El chip
pasó a `--marca` plano. Un chip Premium es **metadato de una publicación**, no la
identidad del producto, y mientras el gradiente estuviera en los dos no había
forma de responder qué comunicaba: ¿marca o estado? Con un solo uso la respuesta
es siempre la misma.

**No se expande a ningún lugar nuevo.** §6 ya descartó los gradientes amplios por
rendimiento en Android de gama baja. Un **segundo** uso vuelve a ser decisión
nueva y hay que justificarla aquí.

> **Cerrado en la fase 3 (2026-08-26).** El gradiente aparece hoy en **3 lugares
> y los 3 son el logo**: el monograma "RC" en `Header.tsx:68` y `Footer.tsx:21`,
> y el wordmark "Carro" en `Header.tsx:79`. Los 60 restantes se migraron; el
> "Crear cuenta" de la barra quedó en `--accion`, como correspondía a un CTA.
> Si vuelve a aparecer un cuarto uso, es una decisión nueva y se justifica acá.

### Contraste verificado

| Par | Ratio | Veredicto |
|---|---|---|
| `--marca` sobre blanco | 7.90:1 | AA texto normal |
| `--accion` sobre blanco | 4.64:1 | AA texto normal |
| `--confirmado` sobre blanco | 5.06:1 | AA texto normal |
| tinta sobre lienzo | 15.10:1 | AA texto normal |
| `--critico` sobre blanco | 8.18:1 | AA texto normal |
| `--destructivo` sobre blanco | 9.91:1 | AA texto normal |
| `--destructivo` sobre lienzo | 9.22:1 | AA texto normal |
| secundario `#706258` sobre lienzo | 5.46:1 | AA texto normal |
| secundario sobre blanco | 5.87:1 | AA texto normal |
| secundario sobre `--superficie-tenue` | 5.02:1 | AA texto normal |
| `--borde-fuerte` sobre blanco | 3.04:1 | AA **1.4.11**, no texto |

El secundario era `#77695F` hasta TASK-017. Pasaba sobre lienzo (4.92:1) pero
sobre `--superficie-tenue` daba **4.52:1**, y ahí es justo donde vive el tono
`neutro` de las insignias. Se oscureció hasta que pasara **5:1 en las tres
superficies** donde aparece. El piso de este sistema para texto secundario es
4.8:1, no 4.5:1: 4.5 es el mínimo de la norma y no deja margen para que el
siguiente ajuste de un tinte lo rompa en silencio.

El Energy Orange original (`#F0562A`) da **3.46:1** con texto blanco y **no
pasa AA** para texto normal. Por eso el token es la variante oscurecida. No se
revierte "porque se ve más vivo".

### Tintes y su texto

Todo texto sobre un tinte usa el tono oscuro de su propia familia, nunca negro
ni gris genérico.

| Tinte | Texto | Ratio |
|---|---|---|
| `#E8F0E4` | `#2E4A26` | 8.48:1 |
| `#FBE9E2` | `#7A3316` | 7.72:1 |
| `#E9EBF8` | `#2A3170` | 9.99:1 |
| `#F3E9E4` | `#6B4A3D` | 6.58:1 |
| `#F7E7EA` | `#7A2A3B` | 7.91:1 |
| `#F9E7E5` | `#A8332B` | 5.54:1 |
| `#F7E7E4` | `#7E2119` | 8.26:1 |

Las dos últimas filas entraron en TASK-017. La de `#F9E7E5` es el tinte de
`--error`, que existía en el código desde que se agregó el token pero nunca llegó
a esta tabla; su texto es el propio `--error` porque §2 nunca definió un segundo
hex de esa familia y **inventarlo sería peor que reutilizarlo**.

---

## 3. Tipografía

Dos roles, y la distinción entre ellos es semántica, no estética.

- **Sans** — todo lo declarado, la interfaz y el precio.
- **Monoespaciada** — placa y datos que vienen de un registro oficial. Ya se usa
  para la placa; ese instinto era correcto y se formaliza.

La monoespaciada **no** se usa para etiquetas de procedencia repetidas en el
listado: añade densidad sin aportar. Se reserva para el identificador y para el
dato oficial en el detalle.

Escala: precio 26px/500 · título 15px/500 · cuerpo 12–14px/400 · placa 11px con
`letter-spacing` amplio.

---

## 4. Jerarquía de la tarjeta

El orden sigue la secuencia de la decisión: cada bloque responde la pregunta que
el anterior deja abierta.

```
FOTO 4:3            ¿me gusta?
PRECIO              ¿me alcanza?
título              qué es
ciudad · km         ¿me sirve?
placa               identidad
chips               metadato
```

**El precio va debajo de la foto, no sobrepuesto.** Con fotos heterogéneas y uso
a pleno sol en Android económico, un precio sobre imagen pierde contraste y
consistencia. La versión actual es más robusta.

**Sin botón dentro de la tarjeta.** La tarjeta completa ya es un `<Link>`; meter
un control dentro produce anidación inválida o destino duplicado. La acción vive
en el detalle.

**Los chips van al final.** Ficha, Premium y verificado son metadato, no criterio
de decisión.

---

## 5. Implementación

El proyecto usa Tailwind 4 **sin `tailwind.config`**: los tokens de marca viven
en `@theme inline` de `src/app/globals.css`.

Cambiar la paleta **no es intercambiar seis variables**. Hay `slate`, `blue`,
`emerald` y `amber` aplicados directamente en componentes, así que requiere una
migración semántica: reemplazar utilidades de color literales por tokens con
significado. Esa migración es el grueso del trabajo y debe presupuestarse como
tal, no como un ajuste de CSS.

### Fase 1 — sin dependencias

Aplicable hoy: tokens, tipografía, jerarquía de la tarjeta, lienzo cálido y la
migración semántica de utilidades. No requiere ningún dato nuevo.

### Fase 2 — bloqueada

El registro oficial en la tarjeta **no se puede implementar todavía**, por dos
razones independientes que apuntan al mismo hueco:

1. **El feed no entrega procedencia por campo.** Hay `verificado`,
   `completitud_ficha` y estados de fuente en el perfil consolidado, pero no un
   mapa "este dato viene de ANT". Calcularlo en cliente sería inventar un
   contrato; pedir el perfil por tarjeta sería un N+1 que viola §1.0.1.
2. **El cache está vacío.** El worker no drena la cola desde el 20 de julio, y
   publicar ya no precalienta. Sin datos, el registro oficial no aparecería en
   ningún anuncio nuevo.

Orden real: arreglar el worker → llevar el estado oficial al schema del feed →
implementar el registro oficial en la tarjeta.

---

## 6. Descartado, con motivo

No reintroducir sin resolver el motivo.

| Descartado | Motivo |
|---|---|
| Barra segmentada de "respaldo" | Fabrica una calificación compuesta con apariencia oficial sobre hechos que nadie agregó. Y no hay contrato de datos que la sostenga |
| Precio sobre la foto | Pierde contraste con fotos heterogéneas a pleno sol en gama baja |
| Botón dentro de la tarjeta | La tarjeta ya es un `<Link>`: anidación inválida o destino duplicado |
| Etiquetas de procedencia en mono, repetidas en el listado | Densidad sin aporte. La mono se reserva para placa y detalle |
| `#F0562A` como fondo de texto blanco | 3.46:1, falla AA |
| Contadores de demanda ("X personas vieron esto") | Con volumen bajo señalan mercado vacío |
| Testimonios | Leen como fabricados y contradicen la propuesta de transparencia |
| Animaciones de scroll y gradientes amplios | Público en Android de gama baja (§4) |

---

## 7. Lo que queda sin resolver

**El lienzo cálido es una decisión estética, no una consecuencia de
"confianza".** Se propone porque diferencia del blanco-azulado de todos los
clasificados ecuatorianos, no porque comunique algo. Es legítimo, pero debe
etiquetarse como preferencia y validarse con usuarios reales, no defenderse como
criterio.

**El copy de ausencia de datos reparte mal la responsabilidad.** "Sin datos
oficiales" se lee como falta del vendedor cuando es de la plataforma. Formularlo
desde el sistema: "todavía no consultamos esta placa".
