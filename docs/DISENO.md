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
| `--atencion` | `#B04A22` | derivado | "pendiente". Nunca una acción |
| `--error` | `#A8332B` | derivado | **fallo de la interfaz**. Nunca un estado del vehículo |
| `--lienzo` | `#FAF6F3` | — | fondo de página |
| `--tinta` | `#22201F` | — | texto primario |

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

### El gradiente de marca CONVIVE con `--marca` (agregado 2026-08-11)

No se reemplaza uno por otro; tienen trabajos distintos:

- **`--marca` (plano)** — acciones primarias y registro oficial. Es el que se usa
  al migrar utilidades.
- **Gradiente `brand-from/via/to`** — **identidad**, y solo en dos lugares: el
  **logo** y el **chip Premium**.

**No se expande a ningún lugar nuevo.** §6 ya descartó los gradientes amplios por
rendimiento en Android de gama baja; conservarlo en dos elementos puntuales no
contradice eso, expandirlo sí. Si aparece un tercer uso, es una decisión nueva y
hay que justificarla aquí.

### Contraste verificado

| Par | Ratio | Veredicto |
|---|---|---|
| `--marca` sobre blanco | 7.90:1 | AA texto normal |
| `--accion` sobre blanco | 4.64:1 | AA texto normal |
| `--confirmado` sobre blanco | 5.06:1 | AA texto normal |
| tinta sobre lienzo | 15.10:1 | AA texto normal |
| secundario `#77695F` sobre lienzo | 4.92:1 | AA texto normal |

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
