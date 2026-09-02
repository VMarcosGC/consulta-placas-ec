# Agendamiento de citas — propuesta de servicio y modelo de negocio

**Fecha:** 2026-09-02 · **Estado:** análisis para decisión de Marcos.
**Qué pide este documento:** simular un escenario real, levantar costos y herramientas,
definir el grupo de clientes inicial, la dinámica, el esfuerzo, dónde se aloja, qué datos
se guardan y qué se ofrece — para poder poner un **precio por servicio**.

> Este documento es de **negocio/producto**, no de código. Lo que ya está construido:
> migración `0034` (`servicios.acepta_agendamiento` + `citas_servicio`), router
> `agendamiento.py`, pantalla `/servicios/agenda`, seed `seed_agendamiento.py`. Falta
> todo el "otro lado": ir a negocios reales, recordatorios, panel del negocio, cobro.

---

## 1. Idea en una frase

CarStore ya tiene un **directorio de servicios automotrices** (talleres, mecánicas,
lavaderos, luces, accesorios). El agendamiento convierte ese directorio en una
**herramienta de trabajo para el negocio**: el cliente pide una cita en línea (fecha +
franja + motivo + contacto), el negocio la confirma/reprograma/rechaza/marca cumplida, y
las dos partes tienen el historial en un solo lugar. Para el negocio chico —que hoy
coordina todo por WhatsApp y una libreta— es dejar de perder citas y dejar de contestar
"¿a qué hora abren?" cincuenta veces al día.

**El agendamiento es el primer producto de CarStore que le cobra a un negocio, no a un
particular.** Encaja con §1.0.3 (monetización de particulares suspendida): esto es un
canal de ingresos distinto, B2B, que no toca la promesa de gratuidad al comprador/vendedor.

---

## 2. Grupo de clientes a atacar primero (ICP)

**Perfil exacto del primer cliente:**

| Rasgo | Valor objetivo |
|---|---|
| Tipo | Mecánica de barrio, lavadero, taller de frenos/suspensión, cambio de aceite express |
| Tamaño | 1–4 bahías, 2–6 empleados, **dueño-operador** |
| Ciudad | **Quito** (norte: La Y, El Inca, Carcelén; sur: Villaflora, Solanda). Es donde ya sembramos puntos de encuentro y presencias. |
| Dolor | Agenda en cuaderno o en la cabeza; el celular del negocio es un WhatsApp saturado; se les cae 1–3 citas/semana por descoordinación |
| Tecnología | Tienen smartphone y datos; **no** tienen software de agenda; quizá una página de Facebook |
| Ticket promedio del negocio | USD 15–80 por servicio |
| Volumen | 5–25 vehículos/día |

**Por qué este perfil y no otro:**

- **No los patios ni las concesionarias**: tienen sistemas propios y procesos de compra
  largos. Están en la etapa 2 del roadmap.
- **No los talleres grandes multimarca**: ya usan software de taller (con OT, inventario,
  facturación). Competir ahí es otro producto.
- El negocio chico es el que **más gana con lo mínimo** y el que **decide en una
  conversación** (el dueño está en el mostrador).

**Tamaño del mercado inicial realista:** Quito tiene del orden de 2.000–3.000
establecimientos de servicio automotriz informal/semiformal. Un piloto no necesita más
de **10–15 negocios activos** para validar. Meta de 12 meses: **80–150 negocios pagando**.

---

## 3. Escenario simulado — piloto de 3 meses en Quito

**Supuestos del piloto:**

- Reclutamos **12 negocios** puerta a puerta (visita del propio equipo; ver §7 esfuerzo).
- Cada negocio recibe en promedio **18 solicitudes de cita/mes** por la plataforma una vez
  que su ficha tiene tráfico (arranca en ~4 y sube).
- **65 %** de las solicitudes se confirman; **12 %** se reprograman; **10 %** las rechaza
  el negocio; **13 %** las cancela el cliente.
- **No-show** de citas confirmadas: **~18 %** sin recordatorio → baja a **~8 %** con
  recordatorio automático (este es el número que vende el plan pago).
- Recordatorio por WhatsApp: 1 al confirmar + 1 el día previo = **2 mensajes/cita
  confirmada**.

**Mes 3 del piloto (régimen):**

| Métrica | Valor |
|---|---|
| Negocios activos | 12 |
| Solicitudes de cita/mes (total) | ~216 |
| Citas confirmadas/mes | ~140 |
| Mensajes WhatsApp salientes/mes | ~280 recordatorios + ~216 avisos de estado ≈ **500** |
| Valor recuperado para el negocio (no-shows evitados) | 12 negocios × ~4 citas rescatadas/mes × USD 35 ticket ≈ **USD 1.680/mes** repartido entre los 12 |
| Lo que le ahorramos en tiempo | ~3–5 h/semana de "coordinar por WhatsApp" por negocio |

**La cuenta que le hacemos al negocio:** "Pagas USD 12–20 al mes. Con evitar **una sola**
cita perdida al mes ya lo pagaste; el resto es tiempo que recuperas."

---

## 4. Dinámica del servicio (cómo opera, día a día)

### 4.1 Alta y configuración del negocio

1. El negocio entra por el CTA "Súmate" de `/servicios` (hoy es un `wa.me`; en producción
   es un formulario) o lo damos de alta nosotros en la visita.
2. Se crea un `Servicio` (`estado_moderacion = pendiente`). Un admin lo aprueba (evita
   spam y datos falsos).
3. El negocio activa `acepta_agendamiento` y define: **horario** (texto libre hoy;
   estructurado en la v2), **franjas** que ofrece (mañana/tarde/noche/todo el día — ya
   modeladas), y opcionalmente el/los **motivos** que atiende.

### 4.2 El cliente pide

- Desde la ficha del servicio (`/servicios`), botón "Agendar cita" → formulario:
  nombre, teléfono, vehículo (texto), motivo (catálogo cerrado), fecha, franja, nota.
- Se crea una `CitaServicio` en estado `solicitada`. El cliente la ve en
  `/servicios/agenda` ("Mis citas").

### 4.3 El negocio responde

- El negocio ve la solicitud en `/servicios/agenda` ("Solicitudes a mi negocio") o —en el
  plan pago— en un **panel/bandeja con calendario**.
- Acciones: **confirmar**, **reprogramar** (propone otra fecha/franja; el cliente acepta o
  cancela), **rechazar**, **marcar cumplida** (cuando el auto ya pasó).
- Cada transición puede disparar una **notificación** al cliente (in-app siempre; WhatsApp
  en el plan pago).

### 4.4 Recordatorios y cierre

- **T-1 día** de una cita `confirmada`: recordatorio automático al cliente (y resumen del
  día al negocio).
- **T+2 h** de la franja: si sigue `confirmada`, el negocio recibe "¿se cumplió?" para
  marcarla `cumplida` o `no_show` (nuevo estado a agregar — hoy no existe; ver §10).
- Métricas que el negocio ve: solicitudes, tasa de confirmación, no-shows, franjas más
  pedidas.

### 4.5 Lo que el cliente nunca ve

- El teléfono del negocio no es un secreto (está en el directorio), pero el flujo empuja a
  coordinar **dentro** de la plataforma para que quede el registro y las métricas.

---

## 5. Qué información almacenamos

### 5.1 Del negocio (`servicios`, ya existe)

nombre, categoría, provincia/ciudad, dirección, teléfono/WhatsApp, horario, `certificado`
(hoy sin uso), `acepta_agendamiento`, `aportado_por_usuario_id` (quién lo gestiona),
estado de moderación.

### 5.2 De cada cita (`citas_servicio`, ya existe)

`servicio_id`, `solicitante_usuario_id`, **nombre_contacto**, **telefono_contacto**,
vehiculo (texto), motivo, fecha, franja, nota, estado, `respuesta_negocio`,
`fecha_propuesta`/`franja_propuesta`, timestamps.

### 5.3 Qué es dato personal aquí

- **PII del cliente:** nombre + teléfono + (indirectamente) el vehículo y el motivo
  (un "cambio de frenos" es dato de salud del auto, no de la persona; bajo riesgo).
- **Base para tratarlo:** ejecución de la solicitud que el propio cliente inició. Se pide
  consentimiento de términos al crear la cuenta.
- **Retención propuesta:** citas cerradas (cumplida/rechazada/cancelada) se **anonimizan a
  los 12 meses** (se borra nombre y teléfono, se conservan fecha/franja/motivo/estado para
  métricas agregadas). Citas activas, hasta que se cierren.
- **El negocio ve** el nombre y teléfono del cliente **solo de las citas de su propio
  negocio** (ya está filtrado en `citas/recibidas`).

### 5.4 Lo que agregamos para el producto pago (nuevas tablas, v2)

- `configuracion_agenda` (1:1 con servicio): capacidad por franja, días no laborables,
  duración estimada por motivo, política de anticipación mínima.
- `recordatorios_cita`: cola de mensajes a enviar (canal, plantilla, estado, proveedor,
  id externo, error). Necesaria para idempotencia y auditoría del gasto en WhatsApp.
- `metricas_negocio_diarias`: rollup por negocio y día (solicitudes, confirmadas,
  no-shows). Evita recalcular sobre `citas_servicio` en cada carga del panel.

---

## 6. Qué ofrecemos — planes

| | **Directorio** (gratis) | **Agenda** (pago) | **Agenda Pro** (pago) |
|---|---|---|---|
| Ficha en `/servicios` con horario y contacto | ✅ | ✅ | ✅ |
| Recibir solicitudes de cita en línea | ✅ | ✅ | ✅ |
| Confirmar / reprogramar / rechazar | ✅ (lista simple) | ✅ | ✅ |
| Notificación al cliente **in-app** | ✅ | ✅ | ✅ |
| **Recordatorio al cliente por WhatsApp** | — | ✅ (T-1d + confirmación) | ✅ + a medida |
| Vista **calendario** + capacidad por franja | — | ✅ | ✅ |
| Métricas (confirmación, no-show, franjas top) | — | básicas | completas + export |
| Página propia del negocio (`/servicios/n/<slug>`) con reseñas | — | — | ✅ |
| Varios usuarios operando la agenda | — | — | ✅ |
| Recordatorio también al **negocio** (resumen del día) | — | — | ✅ |
| Precio sugerido | USD 0 | **USD 12 /mes** | **USD 25 /mes** |

**Por qué freemium y no todo pago:** el directorio gratis es el anzuelo y el inventario que
hace útil a `/servicios` para el comprador. El negocio prueba gratis, ve llegar solicitudes,
y el salto a pago se lo vende **el no-show evitado** y el recordatorio, no una demo.

**Alternativa de cobro por uso** (si el mensual asusta al negocio muy chico):
**USD 0,25 por cita confirmada** con tope de USD 15/mes. Más difícil de facturar, pero
baja la barrera. Recomendación: empezar con **mensual simple**, ofrecer el por-uso solo si
el mensual traba la venta.

---

## 7. Herramientas a considerar (build vs. buy) y su costo

| Necesidad | Opción build | Opción buy | Recomendación |
|---|---|---|---|
| **Recordatorios WhatsApp** | — (WhatsApp no permite envío sin API oficial) | **WhatsApp Cloud API** (Meta) directo, o vía **Twilio**/**360dialog** | **Cloud API directo.** Costo por conversación de *utilidad* en Ecuador ≈ **USD 0,015–0,04**; las primeras 1.000 conversaciones de servicio/mes son gratis. Requiere número dedicado + verificación de negocio (Meta Business). |
| **Plantillas de mensaje** | propias en `recordatorios_cita` | — | Build. Meta exige aprobar cada plantilla (24–48 h). Tener 4: confirmación, recordatorio T-1d, reprogramación, cancelación. |
| **Calendario / disponibilidad** | tabla `configuracion_agenda` + lógica de slots | **Cal.com** self-host, Calendly API | **Build.** El modelo de franjas gruesas ya evita la complejidad de slots exactos; meter Cal.com es una dependencia pesada para lo que damos. |
| **Cron / jobs programados** | `worker.py` ya existe (APScheduler/Task Scheduler) | Render Cron, Upstash QStash | **Build sobre el worker actual.** Ya corre para scraping; sumar los jobs de agenda (§ doc de producción). |
| **Notificaciones push (móvil/web)** | Web Push (VAPID) propio | OneSignal (free ≤ 10k) | Diferir. In-app + WhatsApp cubren el piloto. |
| **SMS de respaldo** | — | Twilio (~USD 0,04–0,08/SMS a EC) | Diferir. Solo si WhatsApp falla mucho. |
| **Panel del negocio** | Next.js, mismas rutas | Retool/Appsmith | **Build.** Es la cara del producto pago; no se terceriza. |
| **Facturación/cobro del plan** | — | Se decide con el tema pagos (§1.0.3, fuera de alcance hoy) | **Manual al inicio**: transferencia/efectivo mensual, nosotros marcamos el negocio como `plan_pago` a mano. 12 negocios se facturan a mano sin problema. |

---

## 8. Costos

### 8.1 Costos fijos incrementales (sobre lo que ya se paga hoy)

| Concepto | Costo/mes | Cuándo aparece |
|---|---|---|
| Número WhatsApp Business + verificación Meta | ~USD 0 (número) + tiempo de verificación | Antes del primer recordatorio |
| WhatsApp Cloud API — conversaciones | **USD 0** hasta 1.000/mes; luego ~USD 0,02 c/u | Piloto entra en el tramo gratis (500/mes) |
| Worker con más jobs | USD 0 si sigue en el equipo/Render free; +USD 7 si pasa a Render Starter dedicado | F1–F2 |
| Neon (más filas: citas, recordatorios, métricas) | USD 0 en free tier un buen tiempo (son filas chicas) | F2 cuando el proyecto crezca por fotos, no por esto |
| **Total incremental piloto** | **≈ USD 0–7 / mes** | |

El agendamiento es **barato de operar**: son filas de texto, no fotos ni scraping. El
costo real del piloto es **tiempo de personas** (ventas + soporte), no infraestructura.

### 8.2 Costo variable por negocio (a escala, plan pago)

- WhatsApp: ~140 citas confirmadas/mes × 2 mensajes × USD 0,02 = **~USD 5,6/negocio/mes**
  cuando se pasa el tramo gratis de 1.000/mes (≈ a partir de ~7 negocios activos).
- Todo lo demás (BD, cómputo) es ruido a esta escala.

### 8.3 Unit economics del plan "Agenda" (USD 12/mes)

| | Valor |
|---|---|
| Ingreso/negocio/mes | USD 12,00 |
| Costo WhatsApp/negocio/mes | −USD 5,60 |
| Costo infra prorrateado | −USD 0,40 |
| **Margen bruto/negocio/mes** | **≈ USD 6,00 (50 %)** |
| CAC (visita + onboarding, ~2 h a USD 8/h + traslados) | ~USD 25 una vez |
| **Recuperación del CAC** | ~4–5 meses |

Con **Agenda Pro (USD 25)** el margen sube a ~70 % porque el costo de WhatsApp casi no
cambia. La palanca de rentabilidad es **subir a los negocios de Agenda a Pro**, no sumar
negocios en el plan básico.

---

## 9. Cuánto tiempo invertimos (esfuerzo)

### 9.1 Ingeniería (para dejar el producto pago listo)

| Bloque | Estimado |
|---|---|
| Estado `no_show` + job "¿se cumplió?" | 0,5 día |
| `configuracion_agenda` + vista calendario del negocio | 3–4 días |
| `recordatorios_cita` + integración WhatsApp Cloud API + 4 plantillas | 3–4 días |
| Jobs en el worker (recordatorio T-1d, resumen del día, cierre) | 1–2 días |
| `metricas_negocio_diarias` + panel de métricas | 2 días |
| Formulario de alta real (reemplazar el `wa.me`) + moderación | 1 día |
| Marca "plan_pago" manual + gate de features | 0,5 día |
| **Total** | **~12–16 días de desarrollo** (2–3 semanas de calendario) |

### 9.2 Operación / comercial (mensual, durante el piloto)

- Reclutamiento: ~2 h/negocio (visita + alta + explicación) → 12 negocios ≈ **24 h** una vez.
- Soporte + acompañamiento: ~30 min/negocio/semana el primer mes, luego ~10 min → **~10
  h/mes** en régimen para 12 negocios.
- Moderación de altas + revisión de métricas: ~2 h/semana.

**Conclusión:** el cuello de botella no es el código (2–3 semanas) sino **la venta y el
acompañamiento puerta a puerta**. El piloto se dimensiona por cuántas visitas se pueden
hacer, no por servidores.

---

## 10. Dónde se aloja y qué falta ("dónde lo depositamos")

- **Datos:** misma BD Neon (PostgreSQL 16) del resto del proyecto. Son tablas nuevas del
  módulo `marketplace`. Nada sale a un tercero salvo el **texto del recordatorio** que va a
  la API de WhatsApp de Meta en el momento del envío.
- **Cómputo:** backend FastAPI en Render; los envíos programados los dispara `worker.py`.
- **Esfuerzo (roadmap):** ver §9.1. El orden sugerido: (1) `no_show`, (2) recordatorios
  WhatsApp + jobs — **es lo que convierte el plan en vendible**, (3) calendario, (4)
  métricas, (5) página propia del negocio (Pro).

### Checklist de lo que falta para cobrar

- [ ] Estado `no_show` en `EstadoCita` + transición desde el negocio.
- [ ] Tabla `configuracion_agenda` (capacidad/franja, días no laborables, anticipación mínima).
- [ ] Tabla `recordatorios_cita` (cola idempotente, auditoría de gasto).
- [ ] Alta de número WhatsApp Business + verificación Meta Business + 4 plantillas aprobadas.
- [ ] Integración WhatsApp Cloud API en un servicio del backend (`services/whatsapp.py`).
- [ ] Jobs en el worker: recordatorio T-1d, resumen diario al negocio, cierre T+2h.
- [ ] `metricas_negocio_diarias` + panel.
- [ ] Formulario de alta real + flujo de moderación (hoy es `wa.me`).
- [ ] Flag `plan` en `servicios` (`directorio` | `agenda` | `agenda_pro`) + gate de features.
- [ ] Términos específicos del negocio (tratamiento de datos de sus clientes; ver doc de producción).

---

## 11. Riesgos y cómo se mitigan

| Riesgo | Mitigación |
|---|---|
| El negocio no entra a la plataforma a confirmar | Recordatorio al negocio por WhatsApp también (Pro); si en 2 h no responde, la cita queda "solicitada" y el cliente ve "sin confirmar aún" — nunca un falso "confirmada". |
| WhatsApp bloquea el número por reportes | Usar plantillas aprobadas, solo mensajes transaccionales, nunca marketing; número dedicado y verificado; volumen bajo y creciente. |
| Meta cambia precios de conversaciones | El margen aguanta hasta ~USD 0,06/conversación; por encima, se sube el plan o se pasa a recordatorio in-app + push. |
| Pocos clientes usan la ficha → pocas solicitudes | El piloto arranca con negocios de zonas donde ya hay tráfico (puntos de encuentro, presencias); si `/servicios` no trae demanda, el problema es de tráfico del marketplace, no del agendamiento. |
| Cobro manual no escala | A 12–30 negocios se factura a mano; pasar a débito automático se resuelve con el tema pagos (hoy fuera de alcance, §1.0.3). |

---

## 12. Métricas de éxito del piloto (3 meses)

- **≥ 10** negocios activos (con ≥ 5 citas recibidas/mes).
- **≥ 60 %** de tasa de confirmación.
- No-show **< 10 %** en citas con recordatorio.
- **≥ 4** negocios dispuestos a pagar USD 12/mes al terminar el piloto (conversión ≥ 33 %).
- NPS informal del dueño: "¿se lo recomendarías a otro taller?" → sí ≥ 8/10.

Si se cumplen 3 de 5 → se escala. Si no → el problema casi siempre es tráfico del
directorio; se ataca eso antes de insistir con el agendamiento.

---

## 13. Propuesta comercial lista para ofrecer (resumen de una página)

> **CarStore Agenda** — para tu taller, lavadero o mecánica.
>
> Tus clientes piden cita desde tu ficha en CarStore. Tú confirmas con un toque. El
> sistema le recuerda al cliente el día antes por WhatsApp. Menos citas perdidas, menos
> tiempo en el teléfono.
>
> - **Gratis:** apareces en el directorio y recibes solicitudes.
> - **Agenda – USD 12/mes:** recordatorios por WhatsApp + vista calendario + métricas.
> - **Agenda Pro – USD 25/mes:** página propia con reseñas, varios usuarios, resúmenes
>   diarios.
>
> Sin permanencia. Si en el primer mes no te sirve, no pagas.
>
> *La cuenta: con evitar una sola cita perdida al mes ya lo pagaste.*
