# Asistente del vehículo en el garage — análisis (para construir más adelante)

**Fecha:** 2026-09-03 · **Estado:** SOLO ANÁLISIS. **No se construye ahora** (decisión de
Marcos). Este documento deja el diseño listo para retomarlo.

**Qué se pidió:** en la sección del auto del dueño (Mi Garage → mantenimientos), un módulo
donde "viva un agente" al que se le lanzan consultas **sobre ese auto**. Ejemplos:
cómo cambiar las pastillas de freno, cómo cambiar el limpiaparabrisas, qué pasa si no
cambio el aceite, qué mantenimientos son urgentes, cuánto dura un cambio de repuesto.
Siempre **enfocado al auto** → hace falta un modelo que pueda responder con ese contexto.

> Encaja con lo que AGENTS.md (Fase 3) ya anticipaba: *"más adelante con IA debemos poder
> hacer que nos genere un plan de mantenimientos según el modelo, año y estado del
> vehículo"*. El placeholder ya existe en el código: `plan_cuidado.py` devuelve
> `nota_ia = "Un plan a la medida del modelo, año y estado del auto llegará más adelante
> con IA."` Este asistente es el hogar natural de esa promesa.

---

## 1. Qué es

Un **asistente conversacional dentro del garage**, acotado a UN vehículo. No es un chatbot
general: cada conversación arranca ya sabiendo marca, modelo, año, motor, transmisión,
kilometraje actual, últimos mantenimientos registrados y el estado del plan de cuidado de
**ese** auto. El dueño escribe una pregunta y recibe una respuesta redactada para su auto,
no genérica.

Vive como una tarjeta más en `mi-garage/[id]` (`AsistenteVehiculoCard`), junto a
`PlanCuidadoCard`, `MantenimientosCard` y `GastosCard`. **Privado del dueño** (mismo gate
`vehiculo_propio` que el resto del garage).

---

## 2. Tipos de consulta que debe cubrir

Del pedido de Marcos, agrupados:

| Grupo | Ejemplos | Qué necesita el modelo |
|---|---|---|
| **Cómo se hace** (how-to) | "cómo cambio las pastillas de freno", "cómo cambio el limpiaparabrisas", "cómo reviso el nivel de aceite" | Procedimiento paso a paso + herramientas + nivel de dificultad + cuándo NO hacerlo uno mismo. Específico al tipo de freno/limpiaparabrisas del modelo cuando se sepa. |
| **Qué pasa si no** (consecuencias) | "qué pasa si no cambio el aceite", "qué pasa si sigo con las pastillas gastadas", "puedo manejar con el testigo de motor encendido" | Explicación del riesgo, en qué plazo se agrava, costo aproximado de dejarlo pasar vs. atenderlo. |
| **Qué es urgente** (priorización) | "qué mantenimientos son urgentes", "qué le hago primero", "de esta lista qué puede esperar" | Cruzar el **plan de cuidado** (vencidos/próximos) + kilometraje + historial → ordenar por seguridad y por costo de postergar. **Ya tenemos los datos** (`plan-cuidado` los calcula). |
| **Cuánto dura / cada cuánto** (intervalos y vida útil) | "cuánto dura un cambio de pastillas", "cada cuántos km se cambia el aceite en este auto", "cuánto vida le queda a la batería", "cuánto tarda un taller en hacer el ABC" | Intervalos por km/tiempo (los del `REGLAS` de `plan_cuidado.py` como base) + vida útil típica del repuesto + duración estimada del trabajo en taller. |
| **Diagnóstico ligero** (no pedido, pero llega solo) | "escucho un chirrido al frenar", "huele a quemado", "se prende una luz naranja" | Hipótesis probables + "esto sí/no es para seguir manejando" + recomendación de ir a un taller. **Con límites duros** (ver §6). |

**Fuera de alcance del asistente:** cotizar precios exactos (varían por taller y ciudad —
para eso está el directorio de `/servicios`), agendar (para eso está el agendamiento),
temas legales/de matrícula (para eso está `/verificar`).

---

## 3. Por qué necesita el contexto del auto (y qué contexto tenemos)

La misma pregunta ("¿cómo cambio las pastillas?") tiene respuestas distintas para un
Sail 2016 y una Sportage 2019 diésel. El valor del módulo es que **no** contesta genérico.

Contexto que el garage **ya guarda** y que se inyecta en cada consulta:

| Dato | De dónde sale | Tabla / endpoint |
|---|---|---|
| Marca, modelo, año, color, clase | alta del vehículo | `vehiculos` |
| Motor / tipo de motor, transmisión, ciudad de registro | perfil del vehículo (migración 0004) | `vehiculos.tipo_motor`, `.transmision` |
| Kilometraje actual | última lectura o último mantenimiento | `kilometraje_lecturas`, `mantenimientos` |
| Historial de mantenimientos | lo que el dueño registró | `mantenimientos` (tipo libre + fecha + km) |
| Estado del plan de cuidado (vencidos / próximos / al día) | reglas genéricas × historial | `GET /vehiculos/{id}/plan-cuidado` |
| Gastos por rubro (combustible, mantenimiento, …) | lo que el dueño registró | `gastos_vehiculo` (migración 0032) |
| VIN / motor / chasis | **solo del dueño** | `vehiculos` (nunca sale ofuscado acá; es su propio auto) |

Lo que **no** tenemos y haría falta conseguir para respuestas de fábrica precisas:

- **Intervalos de servicio del fabricante** por modelo/año/motor (hoy usamos intervalos
  genéricos de uso común en Ecuador). Opciones: (a) una base propia curada de los modelos
  más comunes en Ecuador (Chevrolet, Kia, Hyundai, Toyota, Nissan, Renault — cubren la
  mayoría del parque), (b) dejar que el modelo lo estime y marcarlo como estimación,
  (c) `web_search` acotado a sitios del fabricante (más caro y más lento; ver §5).
- **Especificaciones de repuestos** (tipo de pastilla, medida de limpiaparabrisas, tipo de
  aceite) por modelo. Mismo criterio: base propia de los modelos top, o estimación
  marcada.

---

## 4. Qué modelo usar

El modelo tiene que: entender es-EC, seguir el contexto del auto, razonar sobre
prioridades, y ser **barato** (es un chat de alto volumen para clase media-baja en
celulares de gama baja). Precios API de Anthropic (por 1M de tokens, jun-2026):

| Modelo | ID | Entrada / Salida | Cuándo |
|---|---|---|---|
| Claude Opus 5 | `claude-opus-5` | $5 / $25 | Solo si la calidad de razonamiento no alcanza con Sonnet en pruebas. |
| **Claude Sonnet 5** | `claude-sonnet-5` | **$2 / $10** | **Recomendado para arrancar.** Es el equilibrio calidad/precio para un producto de alto volumen. |
| Claude Haiku 4.5 | `claude-haiku-4-5` | $1 / $5 | Para las consultas más simples (intervalos, "cada cuántos km") si el volumen crece mucho. Se puede rutear por tipo de pregunta. |

**Recomendación:** empezar con **Sonnet 5**, medir calidad con preguntas reales, y solo
subir a Opus 5 si hace falta. La decisión final de modelo es de Marcos.

**Palancas de costo (bajan la factura ~5–10×):**

- **Prompt caching del contexto del auto.** La ficha + historial + plan es un prefijo
  estable dentro de una sesión → se cachea (`cache_control: {type: "ephemeral"}`). Las
  preguntas siguientes de esa sesión pagan ~10% por ese prefijo.
- **Respuestas cortas.** `max_tokens` acotado (p. ej. 800–1200) + instrucción de responder
  breve y accionable. La salida es lo caro.
- **Ruteo por dificultad.** "cada cuántos km se cambia el aceite" → Haiku; "de esta lista
  qué le hago primero y por qué" → Sonnet.
- **Sin historial largo.** El garage no necesita memoria entre sesiones al principio; cada
  consulta puede ser 1–2 turnos. Menos tokens de entrada.

**Estimación gruesa por consulta** (Sonnet 5, con caché del contexto tras el 1er turno):
~2.5k tokens entrada efectivos + ~700 salida ≈ **USD 0,012**. 1.000 consultas/mes ≈
**USD 12/mes**. Con Haiku para la mitad, baja a ~USD 8.

---

## 5. Estrategia de fundamentación (grounding)

Tres capas, de más simple a más completa:

1. **Contexto en el system prompt (MVP).** Se arma un bloque con la ficha del auto + los
   últimos N mantenimientos + el JSON del plan de cuidado y va como `system`. El modelo ya
   sabe de mecánica general; el contexto lo aterriza al auto. **Alcanza para el 80% de las
   preguntas** y es lo que se construye primero.
2. **Base propia de conocimiento (Fase 2).** Un set curado (Markdown/JSON versionado en el
   repo) de: intervalos de servicio y specs de repuestos de los ~15 modelos más comunes en
   Ecuador. Se inyecta el fragmento del modelo del auto en el prompt (no hace falta un
   vector store para 15 modelos). Sube la precisión de "cada cuánto" y "qué repuesto".
3. **`web_search` acotado (Fase 3, opcional).** Herramienta de servidor
   (`web_search_20260209`) con `allowed_domains` = sitios de fabricantes / manuales, para
   preguntas de modelos raros. Más caro (~+$0.01/consulta) y más lento; solo si las
   Fases 1–2 dejan huecos que molestan.

No se necesita RAG con embeddings al principio: el corpus es chico y el contexto del auto
es estructurado.

---

## 6. Seguridad y límites (no negociable)

Es asesoría sobre **sistemas críticos de seguridad** (frenos, dirección, suspensión). El
diseño tiene que:

- **Marco de responsabilidad claro.** Cada respuesta de how-to sobre algo crítico
  (frenos, dirección, airbags, combustible) cierra con: "esto es una guía; si no tienes
  experiencia y herramientas, hazlo en un taller — un freno mal armado es un riesgo".
  El sistema lo enuncia, no como si el auto tuviera algo raro (mismo criterio que
  `DISENO.md §7`).
- **No dar instrucciones peligrosas.** Nada de "puentea el sensor", "quita el testigo",
  "maneja igual". Si la pregunta pide algo así, se explica el riesgo y se deriva a un
  taller.
- **"¿Es seguro seguir manejando?" siempre se responde con criterio conservador.** Ante
  la duda: "no sigas manejando, revísalo". Un falso positivo cuesta un taxi; un falso
  negativo cuesta un choque.
- **Acotado al dominio.** El asistente responde SOLO sobre este auto / mecánica
  automotriz. Preguntas fuera de tema → "solo puedo ayudarte con tu [modelo]". Se logra
  con el system prompt + `output_config` / instrucción, no hace falta un clasificador
  aparte.
- **Nada de datos de terceros ni PII.** Es el auto del propio dueño; no se cruzan otras
  fuentes.
- **Disclaimer visible en la UI**, una vez, no en cada burbuja: "Respuestas generadas por
  IA. Orientativas, no reemplazan a un mecánico."
- **`stop_reason: "refusal"`** del modelo se maneja con un mensaje amable, no un error.

---

## 7. Arquitectura (esbozo, para cuando se construya)

**Backend** — módulo `vehiculos` (es dato del dueño), NO el módulo `consulta`:

- `POST /vehiculos/{vehiculo_id}/asistente` — `{ pregunta: str, conversacion_id?: int }`.
  - `Depends(vehiculo_propio)` (privado del dueño).
  - Arma el contexto (ficha + últimos mantenimientos + `generar_plan(...)` reusando
    `plan_cuidado.py` + resumen de gastos).
  - Llama al SDK de Anthropic (`anthropic` en Python; ver `claude-api`): `client.messages
    .create(model="claude-sonnet-5", system=<contexto+reglas>, messages=[...],
    max_tokens≈1000, cache_control={"type":"ephemeral"})`.
  - Devuelve `{ respuesta, disclaimer, conversacion_id }`. Un servicio externo **nunca
    propaga excepción** (§5 AGENTS): captura y devuelve un mensaje de "no pude responder,
    intenta de nuevo".
- Nueva env var `ANTHROPIC_API_KEY` (secreta, solo backend). Sin ella, la tarjeta del
  asistente no se muestra (feature flag natural).
- **Rate limit por usuario** (p. ej. 20 consultas/día) para acotar costo y abuso.
- Solo BD propia + la API de Anthropic. No toca scraping ni el marketplace (§10.2).

**Datos que se almacenan** (nueva migración, cuando toque):

- `conversaciones_asistente` (id, vehiculo_id, usuario_id, creado_en) — opcional; se puede
  arrancar **sin persistir** nada y sumar historial después.
- `mensajes_asistente` (id, conversacion_id, rol, cuerpo, tokens_entrada, tokens_salida,
  modelo, creado_en) — sirve de historial para el usuario y de **auditoría de costo**.
- Retención: 12 meses y se purga (mismo criterio que el resto; ver
  `agendamiento_a_produccion.md §2.4`).

**Frontend** — `consulta-placas-web`:

- `AsistenteVehiculoCard` en `mi-garage/[id]` (otra tarjeta junto a las tres actuales).
- Chips de preguntas sugeridas ("¿Qué es urgente?", "¿Cómo cambio el aceite?",
  "¿Cuánto dura la batería?") que prellenan el input — bajan la fricción y encauzan hacia
  las consultas que sabemos responder bien.
- Reusa el patrón de `PanelChat` (burbujas + input) pero más simple (sin polling, sin
  otro participante).
- Disclaimer fijo arriba de la tarjeta.

---

## 8. Fases

| Fase | Alcance | Esfuerzo aprox. |
|---|---|---|
| **1 — MVP** | Endpoint + tarjeta + contexto en el system prompt + Sonnet 5 + disclaimers + rate limit. Sin persistencia (cada consulta es fresca) o con persistencia mínima. Chips sugeridos. | ~4–6 días |
| **2 — Base de conocimiento** | Set curado de intervalos/specs de los ~15 modelos comunes en Ecuador; se inyecta el fragmento del modelo. Historial de conversación por vehículo. | ~4–5 días + curaduría de datos |
| **3 — Plan de mantenimiento con IA** | Reemplazar `generar_plan` (o complementarlo) con un plan generado por el modelo según modelo/año/estado real — cierra la promesa del `nota_ia`. `web_search` acotado para modelos raros si hace falta. | ~5–7 días |
| **4 — Proactivo** | El asistente sugiere solo ("tu aceite está vencido hace 2.000 km; esto es lo que conviene") cruzando el plan + kilometraje al abrir el garage. Notificación cuando algo entra en "vencido". | por definir |

---

## 9. Preguntas abiertas (a resolver al retomar)

- **¿Modelo?** Sonnet 5 recomendado; decisión de Marcos según pruebas de calidad y
  presupuesto.
- **¿Se persiste el historial desde la Fase 1** o se arranca sin memoria? (Sin memoria es
  más barato y más simple; el historial se puede sumar después sin migrar nada.)
- **¿Rate limit?** Propuesta 20/día por usuario; ajustar con datos de uso.
- **¿La base de conocimiento propia** (Fase 2) se cura a mano o se genera con el modelo y
  se revisa? (Generar + revisar es más rápido; hay que revisar por seguridad.)
- **¿Entra en el presupuesto de infra?** Ver `plan_costos.md` — es un costo variable nuevo
  (~USD 8–15/mes a 1.000 consultas), sube con el uso. Cubierto por diseño si se cobra
  algo alguna vez; hoy es gasto puro (§1.0.3), así que quizá conviene la Fase 1 detrás de
  un límite bajo hasta ver uso real.
- **¿Idioma del prompt del sistema?** es-EC, tuteo (§5 AGENTS), igual que el resto.

---

## 10. Qué NO hacer

- No convertirlo en un chatbot general (se va de tema y de costo).
- No dar instrucciones que, mal hechas, sean peligrosas (frenos, airbags, combustible).
- No prometer precios exactos de repuestos/trabajos (varían por taller; para eso está
  `/servicios`).
- No mezclarlo con el chat comprador↔vendedor (`conversaciones`/`mensajes`) — es otro
  dominio (garage privado) y otra tabla.
- No hardcodear la API key ni exponerla al frontend.
- No construirlo ahora: **este documento es el análisis; la implementación va después.**
