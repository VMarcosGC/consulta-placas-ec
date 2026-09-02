# Llevar el agendamiento (y CarStore) a producción para clientes reales

**Fecha:** 2026-09-02 · **Estado:** análisis para decisión de Marcos.
**Qué cubre:** datos, calendarización de datos (jobs programados), almacenamiento,
dominio web, y la decisión **web vs. app en Play Store / App Store vs. web + acceso
directo**. Todo lo que hay que contemplar para abrir a uso de clientes reales.

> Complementa a [`agendamiento_propuesta_servicio.md`](agendamiento_propuesta_servicio.md)
> (el modelo de negocio) y a [`plan_costos.md`](plan_costos.md) (el gasto de infra por
> fases). Aquí se mira lo operativo y lo legal.

---

## 0. Resumen de recomendaciones

| Tema | Recomendación |
|---|---|
| **Móvil** | **PWA primero** (web + "Agregar a pantalla de inicio"). Cuando haya tracción, **TWA en Google Play** (USD 25 único, 1–2 días de trabajo). **App Store: solo si un cliente lo exige**; es caro (USD 99/año), lento y Apple rechaza wrappers sin valor nativo. |
| **Dominio** | Comprar `carstore.ec` **y** `carstore.com.ec` (defensivo) + un `.com` o `.app` para correo/marketing. Frontend en la raíz, API en `api.` |
| **Datos** | Clasificar (público / PII / sensible), términos + política de privacidad publicados, base legal por finalidad, retención con borrado automático, export bajo pedido. Cumplir **LOPDP** (Ley Orgánica de Protección de Datos Personales, Ecuador). |
| **Jobs programados** | Un solo scheduler en `worker.py`: recordatorios de cita, expiración de presencias/anuncios, anonimización por retención, rollup de métricas, keep-alive. Todos idempotentes y con registro. |
| **Almacenamiento** | Neon (Launch, uso puro) para datos; Cloudinary→R2 para fotos cuando pese; backups/PITR activados; correo transaccional con dominio verificado (SPF/DKIM/DMARC). |
| **Antes de abrir** | Checklist §7: legal, seguridad, observabilidad, soporte, respaldo. |

---

## 1. Qué significa "producción para clientes reales"

Hoy el proyecto está en **validación**: cuentas del equipo, datos sembrados, un MVP en
Render free + Vercel Hobby. "Producción" agrega obligaciones que en validación se pueden
ignorar:

1. **Terceros de verdad** cargan datos personales (su nombre, su teléfono, el de sus
   clientes). Hay que tener base legal, consentimiento y forma de borrarlos.
2. **El servicio no se puede caer sin que alguien se entere** (observabilidad + alertas).
3. **Los datos no se pueden perder** (backups probados, no solo activados).
4. **Alguien tiene que poder pedir ayuda** (canal de soporte, aunque sea un WhatsApp).
5. **Vercel Hobby prohíbe uso comercial** — al cobrar el primer plan, se necesita Pro
   (ver `plan_costos.md` F1).

---

## 2. Datos: qué se guarda y cómo se gobierna

### 2.1 Inventario y clasificación

| Dato | Dónde | Clasificación | Notas |
|---|---|---|---|
| Anuncios (placa, marca, modelo, precio, fotos, ficha) | `publicaciones_internas`, `fotos_publicacion`, `fichas_publicacion` | **Público** (el usuario lo publica) | La placa es identificable pero el usuario decide publicarla. |
| Perfil de vendedor (nombre público, teléfono) | `vendedores` | **PII** | El teléfono NO viaja en feed/detalle; sale solo tras el chat (migración 0035). |
| Cuenta (email, hash de clave, nombre, id Google) | `usuarios` | **PII** | Hash bcrypt; nunca clave en claro. |
| Chat comprador↔vendedor | `conversaciones`, `mensajes` | **PII / contenido de terceros** | Texto libre entre dos personas. Retención §2.4. |
| Citas de servicio (nombre, teléfono, vehículo, motivo) | `citas_servicio` | **PII** (del cliente del negocio) | El negocio ve solo las suyas. |
| Presencias en puntos de encuentro | `presencias_punto` | **PII indirecta** (ubicación + fecha de una persona con un auto) | Futuro: cruzar con seguridad privada/policía → sube la sensibilidad. |
| Consultas a fuentes públicas (ANT/AMT) | `consultas` (caché) | **Público**, pero agregable | Anónimo por diseño (§9 AGENTS). No se ata a usuario. |
| Métricas de uso | `contactos_revelados`, `desbloqueos_consulta`, (futuro) `metricas_negocio_diarias` | **Agregado / anónimo** | Sin IP ni user-agent (§9). |
| Ledger de tokens | `transacciones_tokens` | **Financiero (dormido)** | Precios en 0 hoy; auditoría obligatoria igual (§10.3). |

### 2.2 Marco legal aplicable — Ecuador (LOPDP)

Ecuador tiene desde 2021 la **Ley Orgánica de Protección de Datos Personales**, con
régimen sancionatorio vigente y la **Superintendencia de Protección de Datos Personales**
como autoridad. Lo mínimo exigible para operar:

- **Política de privacidad** pública y en lenguaje claro: qué datos, para qué, por cuánto
  tiempo, con quién se comparten (Meta/WhatsApp, Cloudinary, Neon, Vercel), y cómo ejercer
  derechos (acceso, rectificación, eliminación, portabilidad, oposición).
- **Base legal por finalidad:**
  - Cuenta y publicación → *ejecución de la relación* que el usuario solicita.
  - Chat y citas → *ejecución de la solicitud* iniciada por el propio usuario.
  - Recordatorios por WhatsApp → *ejecución* (transaccional), **no marketing**.
  - Métricas agregadas → *interés legítimo*, siempre anonimizadas.
- **Consentimiento** explícito al registrarse (checkbox no premarcado, enlace a la
  política). Para el negocio que agenda: consentimiento adicional de que **él es
  responsable** de los datos de *sus* clientes y nos usa como *encargado del tratamiento*
  → hace falta una cláusula de encargo en los términos del negocio.
- **Registro de actividades de tratamiento**: una tabla/hoja simple con finalidad, datos,
  retención y destinatarios. Este documento es el borrador.
- **Notificación de brechas**: procedimiento escrito (a quién se avisa, en qué plazo).
- **Transferencia internacional**: Neon/Vercel/Cloudinary/Meta están fuera de Ecuador;
  declararlo en la política y apoyarse en cláusulas contractuales de esos proveedores.

> No se necesita abogado para arrancar el piloto, pero **sí** antes de escalar a decenas
> de negocios pagando. Presupuestar una revisión legal (~USD 150–400 puntual en Ecuador).

### 2.3 Derechos del titular — cómo se ejercen (mínimo viable)

- **Acceso / export:** endpoint `GET /mi-cuenta/export` que arma un JSON con la cuenta,
  publicaciones, favoritos, conversaciones y citas del usuario. (No existe hoy; ~1 día.)
- **Eliminación:** `DELETE /mi-cuenta` que hace *soft-delete* + anonimización (ver 2.4).
  Las conversaciones se conservan del lado de la contraparte con el nombre reemplazado por
  "Usuario eliminado" (no se puede borrar unilateralmente el chat de otra persona).
- **Rectificación:** ya cubierta por los PATCH de perfil.
- Canal de contacto para estos pedidos: correo `privacidad@<dominio>` (alias).

### 2.4 Retención y borrado (política propuesta)

| Dato | Retención | Acción al vencer |
|---|---|---|
| Cuenta inactiva (sin login) | 24 meses | Aviso por correo; +1 mes → anonimizar |
| Anuncio no renovado | Ya expira por `SEMANAS_VIGENCIA`; borrar del todo a los 12 meses de expirado | Hard-delete de fotos en Cloudinary + fila |
| Conversaciones de un anuncio borrado | 6 meses tras el borrado del anuncio | Anonimizar y luego purgar |
| Citas cerradas (cumplida/rechazada/cancelada/no_show) | 12 meses | Borrar nombre + teléfono; conservar fecha/franja/motivo/estado para métricas |
| Presencias pasadas | 3 meses | Purgar |
| Caché de consultas | TTL ya definido (12 h / 90 d) | — |
| Logs de aplicación | 30–90 días | Rotación automática |
| Ledger de tokens | Indefinido (financiero) | Nunca se borra (§10.3) |

Todo esto lo ejecutan **jobs programados** (§3), no borrado manual.

---

## 3. Calendarización de datos (jobs programados)

### 3.1 Dónde corren

Hoy existe `worker.py` para el scraping híbrido (AMT/FGE desde IP residencial). Se suma a
ese proceso un **scheduler** (APScheduler ya disponible, o el Task Scheduler de Windows
que se usa para el worker). **Un solo lugar** para todos los jobs, cada uno:

- **idempotente** (si corre dos veces no duplica ni rompe),
- deja **registro** (tabla `jobs_ejecutados` o log estructurado: job, inicio, fin, filas
  afectadas, error),
- **acotado** (LIMIT por corrida para no barrer toda la tabla en un pico).

### 3.2 Catálogo de jobs

| Job | Frecuencia | Qué hace | Fuente/Destino |
|---|---|---|---|
| **Recordatorio T-1 día** | cada 15 min | Busca `citas_servicio` `confirmada` con `fecha = mañana` sin recordatorio enviado → encola en `recordatorios_cita` | WhatsApp Cloud API |
| **Aviso de confirmación** | cada 5 min | Citas que pasaron a `confirmada`/`reprogramada`/`rechazada` desde el último corte → notifica al cliente | in-app + WhatsApp (plan pago) |
| **Resumen diario al negocio** | 1×/día 07:00 | Por negocio con plan Pro: lista de citas del día | WhatsApp |
| **Cierre de cita** | cada 30 min | Citas `confirmada` cuya franja terminó hace > 2 h → pide al negocio marcar `cumplida`/`no_show`; si en 48 h no responde, `cumplida` por defecto | in-app |
| **Expirar presencias** | 1×/día 03:00 | `presencias_punto` con `fecha < hoy` → `estado = finalizada`; y purga las > 3 meses | BD propia |
| **Expirar / degradar anuncios** | 1×/día 03:10 | Aplica `SEMANAS_VIGENCIA`; hard-delete de anuncios expirados > 12 meses (+ fotos en Cloudinary) | BD + Cloudinary |
| **Anonimización por retención** | 1×/día 03:20 | Aplica la tabla de §2.4 (citas > 12 m, convos huérfanas > 6 m, cuentas inactivas) | BD + Cloudinary |
| **Rollup de métricas** | 1×/día 02:00 | Agrega `citas_servicio` → `metricas_negocio_diarias`; agrega contactos/desbloqueos del día | BD propia |
| **Keep-alive** | cada 10 min | Ping a `/health` (ya lo hace UptimeRobot; mantenerlo hasta pasar a Render Starter) | — |
| **Verificación de backups** | 1×/semana | Comprueba que Neon tenga un snapshot reciente; avisa si no | alerta |
| **Limpieza de `recordatorios_cita`** | 1×/día | Borra enviados > 90 días; reintenta fallidos < 3 intentos | BD |

### 3.3 Reglas transversales

- **Zona horaria:** todo en UTC en la BD; convertir a `America/Guayaquil` (UTC−5, sin
  horario de verano) solo al mostrar y al decidir "mañana"/"hoy" de un recordatorio.
- **Ventana de envío:** recordatorios y avisos solo entre **07:00 y 21:00** hora local; lo
  que caiga fuera se acumula para las 07:00.
- **Rate limit de WhatsApp:** encolar, no enviar en ráfaga; respetar límites de Meta.
- **Fallo de un job no tumba a los demás:** cada job en su try/except, con alerta.

---

## 4. Almacenamiento

### 4.1 Base de datos

- **Hoy:** Neon free (0.5 GB, 100 CU-h/mes). Alcanza para el piloto — las tablas de chat y
  citas son texto, pesan poco.
- **Trigger de upgrade a Neon Launch** (uso puro, ~USD 5–15/mes): storage acercándose a
  0.4 GB **o** cómputo > 80 CU-h/mes. Casi siempre lo dispara el crecimiento de fotos-URLs
  y consultas, no el chat.
- **Backups:** activar **PITR** (point-in-time recovery) de Neon — en Launch da 7 días de
  historial. En free solo hay snapshots limitados: **razón de peso para pasar a Launch
  antes de abrir a clientes reales**.
- **Índices ya creados** en 0035 cubren las consultas del chat (por publicación, por
  comprador, por vendedor, por `ultimo_mensaje_en`).

### 4.2 Archivos (fotos)

- **Hoy:** Cloudinary free (25 créditos/mes). Ver `plan_costos.md §5`.
- **Camino:** cuando el techo sea *storage/costo* → mover originales a **Cloudflare R2**
  (10 GB gratis, egress $0) y dejar Cloudinary solo para transformaciones; cuando el techo
  sea *bandwidth* → apoyarse en el CDN de Vercel para las variantes.
- El chat **no** maneja archivos (decisión de diseño): no agrega presión de storage.

### 4.3 Correo transaccional

Para recuperación de clave, avisos de cuenta y pedidos de privacidad hace falta enviar
correo **desde el dominio propio** (si no, va a spam):

- Proveedor: **Resend** (3.000/mes gratis, luego USD 20/mes) o **Amazon SES** (más barato
  a volumen, más configuración). Recomendación: Resend para arrancar.
- Configurar **SPF + DKIM + DMARC** en el DNS del dominio.
- Remitentes: `no-responder@`, alias `privacidad@`, `soporte@`.

---

## 5. Dominio web

### 5.1 Qué comprar

| Dominio | Para qué | Costo aprox. |
|---|---|---|
| `carstore.ec` | Marca principal (mercado ecuatoriano) | ~USD 35–55/año vía NIC.ec |
| `carstore.com.ec` | Defensivo (evita que otro lo tome) | ~USD 25–35/año |
| `carstore.com` **o** `carstore.app` | Correo, marketing, respaldo internacional | ~USD 12–20/año |

`.app` obliga a HTTPS (HSTS preload) — no es problema, ya se sirve todo por HTTPS.

### 5.2 Estructura DNS

| Host | Apunta a | Servicio |
|---|---|---|
| `carstore.ec` / `www` | Vercel | Frontend Next.js |
| `api.carstore.ec` | Render | Backend FastAPI |
| `app.carstore.ec` | Vercel (mismo frontend) | Origen para la PWA / TWA (ver §6) |
| MX + TXT (SPF/DKIM/DMARC) | Resend/SES | Correo |
| CAA | Let's Encrypt / proveedores | Restringe quién emite certificados |

- **CORS** del backend: pasar de `*.vercel.app` a la lista exacta de dominios propios +
  `localhost` (variable `CORS_ORIGINS`, ya soportada).
- **SSL:** automático en Vercel y Render con dominio propio; no hay que gestionar certs.

### 5.3 Migración sin downtime

1. Comprar dominios, configurar DNS con TTL bajo (300 s).
2. Agregar dominios en Vercel y Render, esperar verificación.
3. Cambiar `NEXT_PUBLIC_API_URL` → `https://api.carstore.ec` y `CORS_ORIGINS`.
4. Redeploy frontend; probar; subir TTL a 3600 s.
5. Dejar los `.vercel.app` / `.onrender.com` como redirección 301 por un tiempo.

---

## 6. Móvil: web, Play Store, App Store, o acceso directo

### 6.1 Las tres opciones

| Opción | Qué es | Costo | Esfuerzo | Cuándo |
|---|---|---|---|---|
| **A. PWA + "Agregar a inicio"** | La web con `manifest.json` + service worker. El usuario la "instala" desde el navegador; queda un ícono como una app. | USD 0 | 1–2 días (manifest, íconos, SW básico, offline shell) | **Ahora** |
| **B. TWA en Google Play** | *Trusted Web Activity*: un contenedor Android mínimo que abre la PWA a pantalla completa. Se publica en Play Store como app real. | **USD 25** (cuenta Play, único) | 1–2 días con Bubblewrap + assetlinks | Cuando haya tracción / lo pidan usuarios |
| **C. App en App Store (iOS)** | Wrapper (Capacitor) o nativa. Apple **no** acepta TWA; exige un wrapper con algo de valor nativo (push, cámara, biometría) o rechaza por "web view sin funcionalidad suficiente" (guideline 4.2). | **USD 99/año** + Mac para compilar | 1–2 semanas (wrapper Capacitor + push nativo + revisión) | Solo con tracción real y demanda de usuarios iOS |
| **D. App nativa (React Native/Flutter)** | App de verdad, código aparte. | USD 25 + USD 99/año | Meses | Fuera de alcance (roadmap Fase 6) |

### 6.2 Recomendación y razones

**Ir A → B, y postergar C.**

- **A (PWA) primero** porque el público objetivo (clase media-baja, Quito, gama baja) es
  **mayoritariamente Android** y el 90 % del beneficio de "tener app" (ícono en el
  teléfono, pantalla completa, arranque rápido, algo de offline) se consigue sin tienda,
  sin costo y sin proceso de revisión. Además Next.js hace PWA con poco trabajo.
- **B (TWA) cuando haya tracción**: USD 25 una vez, la misma PWA, aparece en Play Store
  (señal de seriedad, y muchos usuarios "buscan la app" ahí). Bajo riesgo: Google acepta
  TWA sin fricción si la PWA cumple Lighthouse.
- **C (App Store) solo si un segmento real lo exige.** Es el camino más caro (USD 99/año
  recurrente), más lento (revisión de días, rechazos frecuentes de wrappers), necesita
  Mac, y el retorno es bajo mientras el público sea Android. Cuando llegue: Capacitor
  envolviendo la misma web + push nativo para justificar la guideline 4.2.

### 6.3 Qué hace falta para la PWA (opción A, accionable ya)

- [ ] `manifest.webmanifest`: nombre, `short_name` "CarStore", `theme_color`/`background_color`
      del sistema "Grafito", `display: standalone`, `start_url: /marketplace`.
- [ ] Íconos: 192, 512, y `maskable` 512 (fondo sólido, sin el wordmark recortado).
- [ ] Service worker mínimo: *app shell* cacheado + estrategia *network-first* para la API
      (nada de cachear respuestas de la API con PII). Con `next-pwa` o SW a mano.
- [ ] `apple-touch-icon` y `<meta name="apple-mobile-web-app-*">` para el "Agregar a inicio"
      de iOS (aunque no haya app en la store, el ícono queda decente).
- [ ] Prompt "Instalar app" discreto (evento `beforeinstallprompt`), no intrusivo.
- [ ] Probar con Lighthouse PWA ≥ 90 (es también el requisito para el TWA de la opción B).

### 6.4 Qué NO hace falta

- No hace falta reescribir nada en React Native/Flutter.
- No hace falta pagar Apple para "tener presencia móvil".
- El chat (0035) con polling cada 12 s es suficiente para la PWA; **push** (Web Push con
  VAPID) es una mejora para B/C, no un bloqueante.

---

## 7. Checklist "listo para abrir a clientes reales"

### Legal / datos
- [ ] Política de privacidad + Términos publicados (`/privacidad`, `/terminos`) y enlazados
      en registro y pie.
- [ ] Checkbox de consentimiento no premarcado en el registro.
- [ ] Cláusula de *encargo del tratamiento* en los términos del negocio que agenda.
- [ ] Endpoints de export y eliminación de cuenta (§2.3).
- [ ] Alias `privacidad@` y procedimiento escrito de brechas.
- [ ] Registro de actividades de tratamiento (este doc como base).

### Seguridad
- [ ] `JWT_SECRET_KEY` y credenciales solo por env var (ya); rotación documentada.
- [ ] Rate limiting en auth (`/auth/login`, `/auth/registro`) y en el chat
      (`POST .../mensajes`) — por IP y por usuario.
- [ ] CORS restringido a dominios propios.
- [ ] Backups Neon con PITR **probados** (restaurar a un entorno de prueba una vez).
- [ ] Headers de seguridad en el frontend (CSP básica, HSTS, `X-Content-Type-Options`).
- [ ] Revisión de que ningún endpoint público filtre PII (auditoría §9 AGENTS ya hecha;
      re-correr sobre el diff del chat).

### Observabilidad / operación
- [ ] **Sentry** (o similar) en backend y frontend — free tier alcanza.
- [ ] UptimeRobot sobre `/health` y sobre el frontend, con alerta a WhatsApp/correo.
- [ ] Logs estructurados con retención 30–90 días.
- [ ] Panel simple de métricas de negocio (citas/día, usuarios activos, errores).
- [ ] Runbook de "qué hacer si se cae Render / Neon / Cloudinary".

### Soporte
- [ ] Canal de soporte visible (WhatsApp del negocio o `soporte@`).
- [ ] FAQ para negocios (cómo activar agenda, cómo confirmar, cómo se cobra).
- [ ] SLA informal declarado ("respondemos en 24 h hábiles").

### Infra (ver `plan_costos.md`)
- [ ] Render Starter (USD 7) — sin cold start.
- [ ] Vercel Pro (USD 20) — obligatorio al cobrar.
- [ ] Neon Launch — antes de abrir, por los backups.
- [ ] Dominios comprados y DNS configurado.
- [ ] Correo transaccional con dominio verificado.

### Producto (del otro doc)
- [ ] Recordatorios WhatsApp + jobs del worker (§3).
- [ ] Estado `no_show`, `configuracion_agenda`, `metricas_negocio_diarias`.
- [ ] Formulario de alta real (reemplazar `wa.me`).

---

## 8. Costo mensual a producción (con agendamiento activo)

| Fase | Infra | + Agendamiento | Total/mes |
|---|---|---|---|
| Abrir piloto (10–15 negocios, sin cobro aún) | Render Starter 7 + dominios ~2 | WhatsApp en tramo gratis (~USD 0) + Resend gratis | **~USD 9** |
| Cobro activo (primer plan vendido) | + Vercel Pro 20 + Neon Launch ~8 | WhatsApp ~USD 5,6/negocio pasado el tramo gratis | **~USD 40 + USD 5,6 × (negocios − 7)** |
| Tracción (50 negocios pagando) | ~USD 45 infra | ~USD 240 WhatsApp | **~USD 285**, contra ~USD 600–900 de ingresos → margen sano |

El gasto sube **con los ingresos** (WhatsApp por negocio), no como costo fijo hundido.

---

## 9. Orden de trabajo sugerido

1. **PWA (opción A)** — 1–2 días. Gana "app en el teléfono" sin costo ni tiendas.
2. **Dominio + correo** — 1 día. Sube confianza del feed y desbloquea correo transaccional.
3. **Neon Launch + backups probados** — 0,5 día. Prerrequisito para abrir a terceros.
4. **Legal mínimo** — política + términos + consentimiento + export/borrado (~2 días).
5. **Recordatorios WhatsApp + jobs del worker** (del otro doc) — 3–4 días. Es lo que hace
   vendible el plan pago.
6. **Sentry + alertas** — 0,5 día.
7. **Piloto de 12 negocios** (§ del otro doc). Medir 3 meses.
8. Con tracción: **TWA en Google Play** (opción B, 1–2 días). App Store solo si se pide.
