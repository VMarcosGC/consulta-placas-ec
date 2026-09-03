# Bitácora de trabajo — `consulta_placas_ec`

Registro cronológico de **lo que se hace en cada sesión** (decisiones, cambios, pendientes).
Complementa, no reemplaza:
- [AGENTS.md](../AGENTS.md) — fuente de verdad (reglas, fases, convenciones).
- [proyecto-snapshot.md](../proyecto-snapshot.md) — foto del estado AS-IS completo.

Entradas nuevas arriba (más reciente primero). Formato por entrada:
fecha · rama · qué se hizo · verificación · pendientes.

> **Nota de corrección (2026-08-05) — sobre los "Commit sin push" de julio.**
> Las entradas del 2026-07-18 al 2026-07-25 llevan marcas de *"Commit sin push"*,
> *"Push pendiente de ambos repos"* o *"Push acumulado"*. **Ninguna sigue vigente:** el
> backend ya estaba sincronizado y los 3 commits del frontend (M2.10, MC2 y el fix de
> `solo_cache`) se pushearon el 2026-08-05, con el build desplegado verificado. Ver la
> entrada *"Frontend pusheado: la deuda de M2.6/M2.7 queda cerrada en producción"*.
> Se dejan tal cual porque son el registro de lo que pasó ese día; esta nota es el
> puntero para no volver a leerlas como estado actual. La lección de fondo: un pendiente
> arrastrado entrada tras entrada deja de leerse, y por eso conviene comprobar el estado
> real antes de escribirlo (es lo que persigue TASK-007).

---

## 2026-09-03 — Consulta de datos como sección aislada (`/verificar`) + hub de dos puertas

**Repos:** backend `consulta_placas_ec` (`main`, migración 0036, commit `09ec154`) ·
frontend `consulta-placas-web` (`main`, commit `766db40`).

**1. Análisis de fuentes y fases** —
[`docs/producto/consulta_datos_fases.md`](producto/consulta_datos_fases.md): inventario
de lo que ya teníamos (ANT/AMT/EPMTSD activas; SRI/FGE dormidas por captcha; capa de
proveedores API con `consultas_ec` como POC), evaluación de nuevas webs (ANT "valores de
matrícula", más GADs municipales — EMOV Cuenca, ATM Guayaquil —, Función Judicial eSATJE
para "temas judiciales", Registro Civil / Policía / aseguradoras como aspiracionales por
requerir convenio), y agrupación en **3 fases**: básico gratis sin cuenta → ampliado con
login → compra segura con consentimiento.

**2. Backend (migración 0036 + `consultar_perfil`).** Se retoma "el tema de la consulta
por placa" que AGENTS.md §1.0.3 dejó anotado:
- `productos_consulta` con **todos los precios en 0** (deuda anotada saldada). El cobro
  queda cableado pero inalcanzable.
- `GET /consultar/{placa}/perfil`: **con sesión se revelan todos los bloques activos** sin
  `POST /desbloquear` por bloque; sin sesión, teaser. El gate pasa a ser **login**, no
  tokens. Reversible cuando vuelva la monetización.

**3. Frontend — `/verificar` aislado + hub.**
- `/verificar` es una **superficie propia**: sin Header/Footer/barra móvil/chat
  (`lib/rutas.ts` + `ChromeSlot` en `layout.tsx`). Barra mínima propia con wordmark +
  volver + tema. `/verificar` = landing con el campo de placa; `/verificar/{placa}` =
  resultado **en bloques** (reusa `PerfilVehiculo`, que al montar re-consulta con token
  si hay sesión).
- **`/` pasa a ser un hub** de dos puertas: "Verificar un vehículo" → `/verificar` ·
  "Marketplace y servicios" → `/marketplace`, sobre los accesos directos y el mapa que ya
  estaban.
- `/consultar` y `/consultar/{placa}` → `permanentRedirect` a `/verificar` (SEO). Enlace
  "Verificar placa" en la nav del Header.

**Pendientes (siguiente iteración, en el doc):** probar ANT "valores de matrícula" desde
el worker; sumar EMOV Cuenca / ATM Guayaquil; bloque "temas judiciales" con eSATJE;
bloque "n.º de dueños" al confirmar el contrato del proveedor; consentimiento explícito
para Fase 3. Migración 0036 la aplica Render en el próximo deploy.

---

## 2026-09-02 — Chat interno comprador↔vendedor, sello de mecánica flotante, análisis de agendamiento

**Repos:** backend `consulta_placas_ec` (`main`, migración 0035, commits `d9b9b9d`,
`e94a45e`) · frontend `consulta-placas-web` (`main`, commits `a2858fb`, `01c2e85`).

**1. "Mecánica certificada" fuera de `/servicios`.** No hay un proceso real de
certificación de talleres; la categoría prometía algo que no se cumple. Se quitó de
`CATEGORIAS_SERVICIO`, `PLANTILLAS`, el chip "✓ Certificado", el alta y el copy. Los
negocios que el backend traiga con `categoria = "mecanica_certificada"` se muestran
bajo "Mecánica general" (`desdeApi` colapsa el valor; el contrato de la API no cambia).

**2. El sello "revisado por mecánica" pasa a flotar sobre la foto del auto.** Antes era
un chip en la cabecera del anuncio, lejos de la imagen. Ahora: `GaleriaAnuncio` →
`SelloFlotante` (esquina sup-izq del detalle) y un overlay en `ListingCard` (esquina
inf-der del feed). Es un aval del vehículo y se lee mejor pegado a su imagen.

**3. Chat interno comprador↔vendedor + barrera del WhatsApp (migración 0035).**
"Termina el chat en la web sin dar paso a WhatsApp si antes no se cumplió algún
requisito de seguridad relacionado con verificación."
- Tablas `conversaciones` (un hilo por publicación+comprador, contadores de no leídos
  por lado, `contacto_habilitado_en`) + `mensajes` (texto plano, `rol_autor`
  desnormalizado). Router `chat.py` bajo `/marketplace`.
- **La barrera:** `POST /publicaciones/{id}/contacto` deja de ser público. Para ver el
  WhatsApp del vendedor hace falta (a) sesión y (b) un hilo donde el vendedor ya
  respondió (o tocó "Compartir mi WhatsApp"). Sin eso → 422 `chat_requerido` con el
  `conversacion_id`. El dueño del anuncio se saltea la barrera. 422 `chat_bloqueado`
  si el vendedor cerró el hilo.
- Frontend: `PanelChat` (hilo reutilizable, polling 12 s), `/mensajes` (bandeja
  maestro-detalle para ambos roles), `ContactoVendedor` reescrito (chat primero, botón
  WhatsApp 🔒 hasta la respuesta), `ChatWidget` deja de ser "en preparación" (enlaza a
  `/mensajes`, contador de no leídos).
- Tests: 25 nuevos (`tests/test_chat.py`); `test_contacto_vendedor.py` actualizado a la
  barrera. Suite backend **278 OK** (skipped=6). tsc + eslint + build frontend en verde.

**4. Análisis de agendamiento (no es código).** Dos documentos en `docs/producto/`:
- [`agendamiento_propuesta_servicio.md`](producto/agendamiento_propuesta_servicio.md):
  ICP (talleres chicos de Quito), escenario simulado a 3 meses, dinámica, qué datos se
  guardan, planes (Directorio gratis / Agenda USD 12 / Agenda Pro USD 25), herramientas
  (WhatsApp Cloud API para recordatorios), costos y unit economics, esfuerzo (~12–16
  días de dev + venta puerta a puerta), checklist de lo que falta para cobrar.
- [`agendamiento_a_produccion.md`](producto/agendamiento_a_produccion.md): datos y
  LOPDP, jobs programados (recordatorios, expiración, anonimización, rollups) en el
  worker, almacenamiento (Neon Launch + PITR antes de abrir), dominio (`carstore.ec` +
  `api.`), y la decisión móvil → **PWA primero, luego TWA en Google Play (USD 25),
  App Store solo con tracción**. Checklist "listo para abrir a clientes reales".

**Pendientes:** construir lo del doc de agendamiento (recordatorios WhatsApp + jobs,
`no_show`, `configuracion_agenda`, métricas, alta real) cuando Marcos lo priorice.
Migración 0035 la aplica Render en el próximo deploy.

---

## 2026-08-30 (4) — Datos demo en puntos, agendamiento de servicios, widget de chat

**Repos:** backend `consulta_placas_ec` (`main`, migración 0034, commits `b1803d7`,
`fd58501`) · frontend `consulta-placas-web` (`main`, commits `16f6fa1`, `b20fced`).

**1. Presencias demo en los puntos de encuentro.** `scripts/seed_puntos_encuentro.py`
anuncia 22 publicaciones activas de la cuenta demo repartidas entre los 6 puntos de
Quito (fechas próximas, franjas variadas). Corrido contra Neon; 3–5 autos por punto,
verificado en el feed.

**2. Agendamiento de citas para servicios (migración 0034).** "La plataforma
disponibiliza el agendamiento; el otro lado es ir con los negocios y ofrecérselo."
- `servicios.acepta_agendamiento` (lo declara el propio negocio en el alta) + tabla
  `citas_servicio`. Flujo: cliente pide (`POST /servicios/{id}/citas`, 422 si el
  negocio no acepta) → negocio confirma / reprograma (propone fecha/franja) / rechaza
  / marca cumplida (`POST /citas/{id}/responder`, dueño del servicio o admin, 404 a
  terceros) → cliente ve todo en `GET /citas/mias`, acepta la reprogramación o
  cancela (`PATCH /citas/{id}`). Bandeja del negocio: `GET /citas/recibidas`.
- Frontend: el bloque "Agenda tu cita" del detalle de `/servicios` es real (form
  inline si el negocio acepta; copy honesto si no). Página `/servicios/agenda` con
  los dos lados. Alta de negocio con checkbox `acepta_agendamiento` + copy del pitch.
- `scripts/seed_agendamiento.py`: 8 negocios `aprobada` con agendamiento atribuidos
  a `--dueno` (default mrkitov@gmail.com) + 4 citas demo. Corrido contra Neon;
  verificado en `/marketplace/servicios`.
- 15 tests nuevos (252 OK). Bug atrapado: agregar `acepta_agendamiento` a
  `ServicioSalida` rompía 2 tests que arman `Servicio(...)` sin ese campo → validator
  `mode="before"` que normaliza `None → False` (la columna es NOT NULL DEFAULT false;
  solo un objeto ORM pre-flush llega con None).

**3. Widget flotante de chat interno.** `ChatWidget` — botón abajo-derecha con punto
verde "online" (comunica "plataforma activa", no presencia real). Al abrirlo: "Chat
interno · En preparación" + las vías que sí funcionan hoy (teléfono del anuncio,
puntos de encuentro, agendar una cita). Se oculta en el reel.

**Verificación.**
- Backend: `python -m unittest discover tests` → **252 OK** (skipped=6).
- Frontend: `tsc --noEmit` + `eslint "src/**/*"` + `next build` limpios.
- Navegador: `/servicios` (detalle con "Agenda tu cita"), `/puntos-encuentro`, el
  widget de chat abierto — revisados en el dev server contra el backend de Render.
- Migraciones 0033 y 0034 ya desplegadas en Render (auto-deploy); seeds corridos
  contra Neon.

---

## 2026-08-30 (3) — Pasada visual + Puntos de encuentro seguros + fix de hidratación

**Repos:** backend `consulta_placas_ec` (`main`, migración 0033, commit `6f7855d`) ·
frontend `consulta-placas-web` (`main`, commit `7ae0987`).

**Pasada visual (frontend).** Marcos pidió que la web se sienta "calmada y con
atracción" y que "los colores hagan juego en cada zona". El sistema "Grafito" ya es
casi monocromo por diseño; el ruido venía de los **emoji de color** (🔧🛡️💡✨🫧🏭🔍🚗
📢🛠️) usados como iconos de sección/categoría. Se creó `Iconos.tsx` (15 SVG
monocromos, `currentColor`, mismo trazo que la barra móvil) y se reemplazaron en:
tarjetas del inicio, categorías de `/servicios` (+ su eco en `/intereses`) y el
buscador del marketplace. Resultado revisado en navegador (claro + oscuro): la
página lee como un solo sistema. Además `DistribucionGeografica` reintenta el fetch
2× con backoff — antes un cold start de Render ocultaba el mapa de la portada hasta
recargar.

**Puntos de encuentro seguros (feature nueva, migración 0033).** Ver entrada
detallada del commit `6f7855d`: catálogo curado (6 puntos de Quito, sembrados),
`presencias_punto` (el vendedor anuncia que lleva una publicación suya a un punto en
una fecha/franja), matriz pública de "qué autos van a estar acá". `tiene_seguridad`
queda declarado (hoy `false`) para sumar seguridad privada/policial sin migración.
Endpoints públicos + del dueño + admin; 18 tests (237 OK). Frontend:
`/puntos-encuentro` (lista + "tus anuncios"), `/puntos-encuentro/[id]` (detalle +
form "voy a llevar mi auto"); accesos desde nav, footer y un banner en
`/marketplace`.

**Fix de hidratación del feed (regresión).** La restauración de scroll del
`2026-08-28` leía el snapshot de `sessionStorage` en un inicializador de `useState`
→ server lo veía `null`, cliente un objeto → mismatch de hidratación (reventaba la
línea de stats del marketplace en dev, y en prod regeneraba el árbol). Ahora el
snapshot se lee/aplica en un efecto post-montaje con los fetch iniciales esperando a
`restauracionLista`; el render de hidratación vuelve a coincidir server/cliente.

**Verificación.**
- Backend: `python -m unittest discover tests` → **237 OK** (skipped=6).
- Frontend: `tsc --noEmit` + `eslint "src/**/*"` + `next build` limpios.
- Navegador (dev server contra el backend de Render): inicio, `/servicios`,
  `/marketplace`, `/puntos-encuentro` y `/puntos-encuentro/1` revisados en claro y
  oscuro.

**Pendientes / notas.**
- Aviso de dev de Next 16 "`<script>` cannot be a child of `<html>`" por el script
  no-flash del tema: **pre-existente**, no es regresión. `suppressHydrationWarning`
  está puesto y la app renderiza bien; `next/script beforeInteractive` y un `<head>`
  literal no lo evitan en el root layout de App Router. Se deja como está.
- La consulta por placa sigue en stand-by; los avisos de `getServerSnapshot should
  be cached` del `Header` son pre-existentes.

---

## 2026-08-30 (2) — Bug de prod: sello de mecánica nunca aparecía + 81 fantasma en el seed

**Repo:** backend `consulta_placas_ec` (`main`, commit `c35a5ca`).

**Qué pasó.** Marcos reportó "algo no está bien" con el sello de mecánica: revisando
el feed en vivo, **ninguna** de las 103 publicaciones traía `sello_mecanica` (se
verificó con `curl` contra `/marketplace/feed`). Causa: la corrida de `seed_demo.py`
del cierre anterior nunca se había ejecutado contra Neon (quedó pendiente en la
bitácora del 2026-08-28). Al correrla ahora para aplicar el top-up de sellos, el
script reportó "81 creadas / 19 ya existían" en vez de "0 creadas / 100 ya
existían" — **bug real**: `sello_idx`, `rng.choice(MECANICAS_SELLO)` y el jitter de
`certificado_mecanica_en` tomaban números del MISMO `random.Random(SEMILLA)` que ya
definía marca/modelo/año/precio/km/placa de las 100 specs; insertar esos draws
corrió toda la secuencia y cada spec terminó con una placa distinta a la sembrada →
el script dejó de reconocer lo existente y creó **81 publicaciones fantasma
duplicadas** en prod (100 → 181 en la cuenta demo).

**Remediación (misma sesión).**
1. Fix en `scripts/seed_demo.py`: `rng_sello = random.Random(SEMILLA + 1)`,
   independiente de `rng`, para todo el sello de mecánica.
2. `python -m scripts.seed_demo --borrar` → limpió las 181 publicaciones fantasma
   (+ 121 fichas, 398 fotos) de la cuenta `demo-seed@carstore.local`.
3. `python -m scripts.seed_demo` (ya con el fix) → resembró limpio: **100
   publicaciones, 65 fichas, 12 con sello de mecánica**. Segunda corrida confirma
   idempotencia real: "creadas: 0 / ya existían: 100 / sellos aplicados: 0".
4. Verificado en vivo: `GET /marketplace/feed` devuelve 12 publicaciones con
   `sello_mecanica`, y `/marketplace/461` en el navegador muestra el pill verde
   "🔧 Revisado por Tecnicentro Andrade" arriba del precio, tal como se diseñó
   (aval de una mecánica sobre la ficha del vehículo, no sobre el vendedor ni el
   servicio).

**Lección.** Cuando un seed determinista identifica filas por un valor que él mismo
genera con RNG (acá la placa), CUALQUIER campo nuevo que agregue randomness debe
usar un `Random` separado — nunca el mismo stream, así se inserte "después" en el
código: el orden de ejecución en el loop es lo que importa, no el orden en el
archivo.

---

## 2026-08-30 — Carga de 20 referencias externas (SUV Facebook Marketplace, Quito)

**Repo:** backend `consulta_placas_ec` (`main`, commit `ba39647`).

**Qué se hizo.** Marcos pasó `matriz_20_suv_marketplace_quito.xlsx` (20 SUV de FB
Marketplace, Quito, USD 13.300–17.900, armada por Codex el 2026-08-30) para cargarlos
"como externos". Se creó `scripts/importar_referencias_fb.py`: importador idempotente
(clave `url_externa`) que inserta a `publicaciones_referenciadas` por SQLAlchemy Core,
con los 20 registros horneados. Cada uno pasa la misma validación
`PublicacionReferenciadaCrear` que el endpoint. Flags: `--aprobar` (feed directo) /
`--aportante EMAIL` (default `mrkitov@gmail.com`) / `--borrar`.

**Ejecución (prod Neon).** `python -m scripts.importar_referencias_fb --aprobar` →
**20 creadas**, `estado_moderacion=aprobada`, `activa=True`, `usuario_id=5`
(mrkitov@gmail.com). Ya visibles en el feed y en "Mis referencias" de esa cuenta.

**Notas.**
- Las URLs de foto de `fbcdn.net` vienen firmadas y caducan en pocos días; al expirar
  la tarjeta cae al placeholder "Sin fotos". Para fotos permanentes habría que
  resubirlas a Cloudinary.
- Deshacer: `python -m scripts.importar_referencias_fb --borrar` (borra exactamente
  esas 20 por URL).
- `openpyxl` se instaló en la venv solo para extraer el xlsx; NO es dependencia del
  proyecto ni del script (los datos van horneados).

---

## 2026-08-28 — Servicios por bloques, "vendido" con resumen, y garaje con cuidado + gastos

**Repos:** backend `consulta_placas_ec` (`main`, migraciones 0030–0032) ·
frontend `consulta-placas-web` (`main`, varios commits).

**Qué se hizo**

1. **Directorio de servicios, iteración 2.** `/servicios` pasa a DOS niveles: bloques
   por categoría (con conteo) → al tocar uno, la lista de esa categoría. Cada servicio
   es un acordeón: resumen + dirección, horario y teléfono + apartado **"Agenda tu
   cita"** (servicio de la plataforma, aún no disponible). Mezcla los negocios
   aprobados del backend (`GET /marketplace/servicios`) con la demo (~84) y, si el
   backend falla, queda la demo. Alta de negocio: **formulario propio** (requiere
   sesión) → `crearServicio()` entra `pendiente`; el wa.me pasa a vía secundaria.
   Backend: campo `horario` (texto libre) en `servicios` — **migración 0030**.
2. **Inicio compacto + favoritos fuera del market + Servicios en la barra móvil.**
   "¿Qué quieres hacer?" pasa a grilla **2×2** en celular (era 1 columna a pantalla
   completa). Se quitó el bloque "♥ Tus favoritos" del feed de `/marketplace`: los
   guardados viven **solo** en `/intereses`. `BarraNavegacionMovil` gana una cuarta
   entrada, **Servicios** (antes solo Inicio / Marketplace / Publicar).
3. **"Vendido": dónde va + resumen.** Marcar un anuncio como `vendida` ya existía;
   faltaba la fecha y la ubicación en la UI. **Migración 0031**: `vendido_en` en
   `publicaciones_internas`, sellada al entrar a `vendida` y limpiada al salir
   (`_aplicar_transicion_estado`). `mis-publicaciones`: fila de resumen por estado,
   botón "Marcar como vendido" en cada anuncio activo/pausado, y **panel "🎉
   Vendidos"** aparte con la fecha de venta y "Volver a publicar". El seed demo
   (`seed_demo.py`) aplica el **sello "revisado por mecánica"** a 12 publicaciones
   con ficha (nombre + ciudad de una mecánica ficticia + fecha), con top-up
   idempotente.
4. **Garaje: control del vehículo (`/mi-garage/[id]`).** Página nueva por vehículo:
   - **Plan de cuidado** — `GET /vehiculos/{id}/plan-cuidado`: 13 reglas genéricas
     (aceite 5.000 km/6 meses, frenos, líquido de frenos, distribución, matrícula
     anual…) cruzadas con los `mantenimientos` registrados → estado por ítem (al día
     / pronto / vencido / sin datos). Km de referencia = mayor dato conocido (última
     lectura o último mantenimiento). `fuente: "reglas"` + `nota_ia` dejan lugar al
     plan con IA. Función pura en `services/plan_cuidado.py`.
   - **Últimos mantenimientos** — se surface el listado (antes el garaje no lo
     mostraba) + alta inline; al guardar se recalcula el plan.
   - **Control de gastos** — **migración 0032**, tabla `gastos_vehiculo`
     (combustible, mantenimiento, seguro, matrícula, peajes, multas, repuestos,
     lavado, otro). `POST/GET/DELETE /vehiculos/{id}/gastos`; el GET devuelve
     listado + `resumen` derivado (total, promedio mensual, desglose por tipo) y la
     suma de `costo` de los mantenimientos (total combinado, sin doble registro).
5. **Feed estilo FB Marketplace (solo frontend, commit `52eda62`).**
   - **Leyenda de tiempo flotante** (`LeyendaTiempoScroll`): "Hoy / Ayer / Esta
     semana / Este mes / <Mes Año>" mientras te desplazas, se desvanece al parar. Lee
     `[data-fecha]` que ahora emiten las `ListingCard` (por `creado_en`); en
     `/marketplace` escucha window, en `/marketplace/reel` su contenedor.
   - **El scroll del feed ya no se pierde al volver del detalle**
     (`lib/feedScroll.ts`): foto en `sessionStorage` (1 ranura, TTL 30 min, clave =
     querystring) del feed curado + estado de búsqueda paginado + scrollY. Al
     remontar `/marketplace` con la misma clave se rehidrata, se saltan los refetch
     iniciales y se restaura el scroll.
   - **Servicios ordenados por cercanía**: `/servicios` pide la ubicación del
     navegador (con caída a elegir ciudad); con un origen, la lista de la categoría
     se ordena por distancia y cada negocio muestra "📍 ~N km · ~M min". Sin
     coordenadas por negocio todavía: centroide de la ciudad / capital de provincia
     (`lib/geolocalizacion.ts`, haversine + 12 ciudades). Marcado como aproximado.

**Verificación**
- Backend: `python -m unittest discover tests` → **219 OK** (+20: `test_servicios`
  ampliado, `test_publicacion_vendido_en`, `test_gastos_vehiculo`, `test_plan_cuidado`).
- Frontend: `tsc --noEmit` + `eslint "src/**/*"` + `next build` → limpio (dos rondas:
  garaje/vendido y feed FB).
- Sin comprobación visual en navegador (el navegador embebido sigue sin responder).

**Pendientes / notas**
- Migraciones 0030–0032 **sin aplicar a Neon desde acá** (el clasificador bloquea
  `alembic upgrade head`): las aplica Render en el deploy (`CMD` del Dockerfile) o
  Marcos en local.
- `seed_demo.py` con el sello **no se corrió** (toca Neon): correrlo tras desplegar.
- Item 6 (rates de servicios) sigue diferido: reusar el patrón de `calificaciones`
  cuando los servicios tengan uso real.
- Plan de cuidado con IA (según modelo/año/estado): pendiente; el contrato
  (`fuente`, `nota_ia`) ya lo contempla.
- Servicios por cercanía usa centroide de ciudad. Para distancias reales haría falta
  `latitud`/`longitud` por negocio (migración + campo en el form de alta): pendiente,
  no urgente.

---

## 2026-08-27 — Distribución geográfica, detalle del anuncio, reel y zona de publicidad

**Repos:** backend `consulta_placas_ec` (`main`, merge `feat/distribucion-geografica`) ·
frontend `consulta-placas-web` (`main`, varios commits).

**Qué se hizo**

1. **Distribución por provincia/región + filtro geográfico.** `geografia.py` mapea las
   12 ciudades del catálogo a (provincia, región). `GET /marketplace/distribucion`
   cuenta publicaciones activas por región/provincia (derivado de `ciudad`).
   `/marketplace/buscar` gana `provincia` y `region` (se intersecan; 422 fuera de
   catálogo). Portada: bloque **"¿Dónde están los autos?"** con enlaces al marketplace
   filtrado; `<select>` de provincia + pills removibles. Sin mapa SVG (peso en gama
   baja). +10 tests (169 OK).
2. **Detalle del anuncio: galería nueva + ficha plana.** `GaleriaAnuncio.tsx`: foto
   principal + miniaturas, **panel por foto** (según `foto.bloque` muestra el resumen
   de ese bloque de la ficha al lado), y **visor a pantalla completa con zoom** (tap
   1x↔2.5x, rueda 1x–4x, arrastre, swipe/flechas, Esc). `FichaTecnica` pasa a PLANA
   (encabezado por bloque + lista a dos columnas, sin `BentoCard`); mismos campos,
   menos "recuadro". Helpers `filas*` + `BLOQUES_FICHA` en `lib/ficha.ts` como fuente
   única.
3. **Marketplace en modo REEL** (`/marketplace/reel`). Un auto por pantalla, scroll
   vertical con snap, estilo feed. Reusa `GET /marketplace/buscar` con cursor
   (IntersectionObserver para paginar). ♡ favorito, "Ver detalle" despliega un
   vistazo + enlace al anuncio completo. Entrada "▶ Ver como reel" en `/marketplace`.
   **Revierte `AGENTS.md §1.0.2`** ("Feed tipo reels — fuera"): Marcos lo repuso; el
   doc quedó actualizado. No agrega backend.
4. **Zona de publicidad de la portada.** `PublicidadHome.tsx` + `config/publicidad.ts`.
   Si `PUBLICIDAD_HOME === null` no se renderiza (no invasiva). Cuando hay pauta: una
   tarjeta etiquetada "Publicidad", enlace `sponsored` en pestaña nueva.

**Verificación**
- Backend: `python -m unittest discover tests` → 169 OK.
- Frontend: `tsc` + `next build` OK en cada commit. Archivos fuente tocados lintean
  limpio (el `npm run lint` global sigue con ruido de `.claude/worktrees/*/.next`).
- Sin comprobación visual en navegador (el navegador embebido no respondió).

**Pendientes**
- Ver en pantalla: "Grafito" claro/oscuro, el bloque de distribución, el visor con
  zoom, el reel.
- Reel v2: traer la ficha completa al expandir (hoy el "detalle ampliado" es el
  enlace al anuncio); dedupe de premium destacadas si molesta.

---

## 2026-08-27 — "Grafito": paleta casi monocroma + modo oscuro, y antigüedad de publicaciones

**Repos:** frontend `consulta-placas-web` (rama `main`, varios commits) · backend
`consulta_placas_ec` (rama `main`: merges `feat/publicacion-renovacion` +
`chore/seed-demo`).

**Qué se hizo**

1. **Inicio sin dobles CTA + consulta de placa fuera de la UI** (`e09ff9a`). El hero
   del inicio ya no lleva botones; la navegación son 3 tarjetas de resumen, una por
   destino, sin repetirse. Se retiró `CtaSection` y `DestacadosMarket`. "Consulta de
   placa" salió de Header, Footer y barra móvil (stand-by; rutas `/consultar*` y
   backend intactos); "Inicio" ocupa el hueco en la barra móvil. Footer a 2 columnas
   (sin "Fuentes oficiales").
2. **Antigüedad + renovación de publicaciones** (backend `be2a42d` + frontend
   `8fd2b6e`). Migración `0026`: `publicaciones_internas.renovada_en` (columna propia,
   sin `onupdate` — solo la mueve el endpoint de renovación, así una edición de precio
   no "renueva" solo). Feed y `/buscar` mandan **al final** las publicaciones con 3+
   semanas sin renovar (`vigente` es la clave keyset de más peso; el cursor gana la
   clave `v`, con back-compat). `POST /marketplace/publicaciones/{id}/renovar` — dueño
   (404), solo activa (422), solo si ya venció (422), no cobra. Frontend: "Publicado
   hace N semanas" en tarjetas y detalle; botón "Renovar anuncio" en
   `mis-publicaciones` cuando `puede_renovar`. `SEMANAS_VIGENCIA_PUBLICACION` = 3
   (env `PUBLICACION_SEMANAS_VIGENCIA`). `tests/test_renovacion_publicacion.py` (15
   casos). Suite: 159 OK.
3. **Seed demo** (`scripts/seed_demo.py`, `4a2fc7d`). 100 publicaciones internas
   (80 light / 20 premium), 65 fichas, 218 fotos, cuenta `demo-seed@carstore.local`,
   sembradas contra Neon. Idempotente y reversible (`--borrar`). SQLAlchemy Core (no
   ORM) para no depender de que modelo y migraciones estén sincronizados.
4. **Sistema visual "Grafito"** (`2bffea9`). Marcos rechazó naranja → esmeralda →
   azul → teal→verde. Paleta **casi monocroma en grafito**: sin color de marca
   cromático, la acción es un sólido que **invierte con el tema** (`--accion` =
   `--oscuro`), `--marca` = gris templado. `@theme` (no `inline`) + tres bloques de
   override para los tres estados de tema. **Modo oscuro con toggle**
   (`ThemeToggle.tsx` + no-flash en `layout.tsx`, `localStorage.tema`,
   `useSyncExternalStore`). Barrido `text-white → text-superficie`. Gradiente de marca
   retirado. Detalle en `DISENO.md §0` (reescrito). `AGENTS.md §4` actualizado.

**Verificación**
- Frontend: `tsc` + `next build` OK en cada commit. `npm run lint` limpio salvo ruido
  de `.claude/worktrees/*/.next` (build generado de una tarea en background; los
  archivos fuente tocados lintean limpio).
- Backend: `python -m unittest discover tests` → 159 OK. `import main` OK, ruta
  `/marketplace/publicaciones/{id}/renovar` registrada.
- **Migración 0026 en Neon:** aplicada por el `CMD` de Render en el deploy
  (`alembic upgrade head && python run.py`). En local: `alembic upgrade head`.

**Pendientes**
- Verificar "Grafito" en pantalla (claro + oscuro) — el navegador embebido no
  respondió esta sesión; queda pendiente el visual real.
- Legibilidad del detalle del anuncio ("resulta pesada de leer") — no abordada aún.
- `precio_usd.toLocaleString` sobre string en `mis-publicaciones` (tarea en background).

---

## 2026-08-27 — Dirección C: nuevo sistema visual "App limpia"

**Repo:** frontend `consulta-placas-web`, rama `feat/diseno-c` (sobre `main`, que ya tiene
las secciones 1–4a mergeadas). Backend: solo `docs/DISENO.md` y esta bitácora.

**Decisión.** Tras el artefacto de 3 direcciones, Marcos eligió la **Dirección C** ("App
limpia": casi blanco, denso, píldoras oscuras, cercano a la referencia ESTORE) **pero pidió
cambiar el naranja por un verde en tendencia**. Se reemplazó `--accion` naranja `#CB4A16`
por **verde esmeralda `#047857`** (AA con texto blanco; el acento de conversión que usan
marketplaces y fintech; distinto del azul de marca que lleva enlaces/favoritos y del verde
de estado "al día").

**Cómo se aplicó — clave:** se reescribió `globals.css` conservando los **nombres** de los
tokens y cambiando los **valores**, así que toda la app heredó el look sin tocar
componentes uno por uno. Solo se hicieron a mano las piezas **estructurales**.

- **`globals.css`** (`c4cd460`): lienzo `#FBFBFC` frío, neutros fríos (adiós cálidos),
  `--accion` esmeralda, tokens nuevos **`--oscuro` / `--oscuro-suave`** (píldora oscura para
  lo secundario), `--confirmado` más apagado, tintes recalculados, sombra de tarjeta más
  nítida. Sobrevive: dos registros (mono para lo oficial), un-color-un-trabajo, gradiente
  solo en el logo.
- **Portada** (`/marketplace`, home): **línea de estadística** en mono ("N autos · M marcas
  · K verificados o con ficha", derivada del feed en cliente, sin endpoint); chips de
  filtro/precio activos y "Cargar más" / "Buscar" en **píldora oscura** (no `--accion`);
  grillas más densas (hasta 5 col en desktop, 2 en móvil). Recuadros de ícono de la home y
  avatar del menú de cuenta salidos de `--accion` (eran verdes decorativos / de identidad).
- **Login / registro**: tarjeta mínima centrada (`max-w-sm`, radio 2xl, borde + sombra),
  título centrado, enlace de cambio debajo.
- **Header + detalle**: en curso (segunda pasada del agente `dev-frontend`) — cluster de
  íconos en el Header, `bg-accion` del detalle auditado (esmeralda solo para "Ver teléfono"
  / contacto; "Verificar esta placa" a píldora oscura).
- **`DISENO.md`**: nueva **§0** con la paleta vigente y qué de §1–§7 sigue aplicando. §7
  queda saldada (el lienzo cálido "sin resolver" se reemplazó a conciencia por un frío).

**Verificación:** computed styles en la app viva (`bg-accion` = `rgb(4,120,87)`, `bg-oscuro`
= `rgb(28,29,34)`, `body` = `rgb(251,251,252)`); `tsc --noEmit` limpio; `lint` 0; `build` OK
(17 rutas). El dev server hay que **reiniciarlo** para que Turbopack recompile `@theme`.

**Pendiente:** cerrar la pasada de Header + detalle; merge de `feat/diseno-c`.

---

## 2026-08-27 — Iteración de diseño del frontend (secciones 1–4a)

**Repo:** frontend `consulta-placas-web`, rama `feat/diseno-portada` (5 commits sobre
`main`, **sin merge**). Backend **no se tocó**. Marcos pidió iterar el diseño del frontend
en orden de impacto: 1) portada, 2) tarjetas, 3) detalle, 4) sistema base. Se probó con la
app corriendo (`npm run dev`, `.env.local` → backend de Render) en móvil 375 y desktop.

**Marco de trabajo.** El sistema visual (`docs/DISENO.md` + `globals.css`) es el resultado
de TASK-017 (3 fases, doble revisión cruzada) y cada token lleva su "no tocar sin
evidencia". Por eso las secciones 1–3 son **corrección y robustez DENTRO del sistema** — no
un cambio de *look*. Ninguna toca `globals.css`, la paleta ni las familias tipográficas.

### Sección 1 — portada (`29e4d85`)
- **Bug de precio**: el backend serializa `precio_usd` como string (`"22000.00"`);
  `String.toLocaleString()` ignora las opciones → se veía `$22000.00`. Helper `precioNum()`
  en el borde (`src/lib/precio.ts`), aplicado en `precioFmt`, `enBanda` y `bajaDePrecio`.
  Ahora `$22.000`.
- **Portada con poco stock**: con ~6 autos reales los 7 bloques MC1 se colapsaban a "★
  Destacados" con 1 tarjeta + 400px de vacío. Bajo `UMBRAL_PORTADA_CURADA = 8`, una sola
  grilla unificada (internas + referenciadas). Los bloques curados vuelven a partir del
  umbral. El carrusel solo con ≥2 premium.
- CTAs de vendedor bajan a después de la primera grilla ("¿Vendes tu auto?").
- `.espacio-barra-movil` en `/marketplace` y `/`; hero de la home más bajo en móvil (asoma
  "Autos en venta" sin scroll); placeholder del buscador acortado.

### Sección 2 — tarjetas del feed (`c2325d8`)
- **Una fila de chips** (§4): de hasta 3 `<Insignia>` que envolvían a máx. 2, prioridad
  Verificado > Premium > Ficha, `flex-nowrap`.
- **Paridad de altura** interna↔referenciada: de +45–73px a **+6px** (la grilla unificada
  ya no baila). El chip "Referencia externa · datos no verificados" pasó de recuadro a
  línea de texto (copy M2.5 intacto, tono `declarado` cálido).
- Botón favorito: 36→40px, `ring-borde`→`ring-borde-fuerte` (se leía como un cuadrado
  hasta que componía el blur), estado lleno `bg-error`→`bg-marca` (el rojo es para fallos
  de interfaz, no para "guardado"), `focus-visible` agregado.
- Padding `p-4`→`p-3 sm:p-4`.

### Sección 3 — detalle + "dos registros" (`354d154`)
- **Skeleton de carga** con la forma real del detalle, en vez de "Cargando publicación…".
- Encabezado con ritmo vertical parejo; la meta pierde las etiquetas redundantes
  ("Marca:", "Año:") — el título ya lo dice; queda "km · ciudad".
- **`DISENO.md §1` materializado**: `DatosOficialesMini` se lee como **registro oficial** —
  los valores de dato duro (veredicto de multas, monto, "Consultado el…") en `font-mono`;
  la ficha declarada sigue sans/cálida con "declarado por el vendedor".
- **`DISENO.md §7` (pendiente anotado)**: "Aún no hay datos oficiales… Consulta la placa"
  (sonaba a falta del vendedor) → **"Todavía no consultamos las fuentes oficiales de esta
  placa"** + acción "Consultar ahora" aparte. Enunciado desde el sistema.
- "Total a pagar" con separador de miles; ficha vacía con copy más cálido.

### Sección 4a — esqueletos de carga (`b24fa1a`)
Parte **segura** de la sección 4 (sin tocar paleta/tipos). Componente `EsqueletoTarjetas`
(N tarjetas fantasma con la forma de `ListingCard`), aplicado en `/marketplace` (grilla
curada y de búsqueda) y en la home (`DestacadosMarket`). Sin salto de layout al llegar los
datos.

### Sección 4b — evolución estética del sistema base: **NO hecha, requiere dirección**
Cambiar la paleta / el lienzo cálido / la tipografía es reabrir `DISENO.md` a propósito
(su propio §7 admite que el lienzo cálido "es una preferencia, no un criterio"). No es una
decisión que se tome sin un rumbo: queda a la espera de que Marcos diga qué sensación
busca (referencia, más sobrio / más "app" / más cálido).

**Verificación (cada commit):** `npx tsc --noEmit` limpio · `npm run lint` **0 errores** ·
`npm run build` OK (17 rutas). Revisado visualmente en la app.

**Pendiente:** merge de `feat/diseno-portada` (aprueba Marcos); decidir la sección 4b.
Seguimiento menor: combos de chip `✓ Verificado` + `★ Premium` a la vez exceden el ancho a
166px y quedan recortados por `overflow-hidden` — hoy ninguna publicación está verificada,
así que no se ve; revisar cuando exista.

---

## 2026-08-27 — Cierre, ola 2 (vendedor): editar y vaciar los datos de una publicación

**Repo:** backend `consulta_placas_ec`, rama `chore/cierre-ola2`. Ola 1 ya mergeada a
`main` en ambos repos (fast-forward). Frontend en curso (agente `dev-frontend`).

**El hueco.** `PATCH /marketplace/publicaciones/{id}` usaba `if datos.X is not None` para
todos los campos, así que un `null` explícito **no vaciaba nada**: se podía cambiar el
kilometraje 87 500 → 91 200 pero no dejarlo en blanco tras teclearlo mal. Dos entradas de
bitácora (TASK-012 y TASK-013 frontend) ya lo anotaron como deuda: *"ya van dos campos con
la misma limitación; cuando se resuelva, conviene hacerlo para todo el schema de una vez"*.

**Qué se hizo (M2.11).** `actualizar_publicacion` ahora mira `datos.model_fields_set` para
los cuatro campos opcionales del auto (`titulo`, `descripcion`, `ciudad`, `kilometraje`) —
**el mismo patrón que `actualizar_ficha` ya usaba**:

| Cliente envía | Efecto |
|---|---|
| omite el campo | no lo toca |
| `"campo": null` | lo **vacía** |
| `"campo": valor` | lo reemplaza (validado: ciudad del catálogo, km 0…2 000 000 → 422) |

`precio_usd` sigue con `is not None`: no es opcional (`gt=0`), solo se reemplaza. `plan` y
`estado` igual. Docstrings de `PublicacionInternaCrear`/`Actualizar` corregidos (ya no
dicen "el plan premium se cobra": monetización suspendida, §1.0.3).

**Verificación:** `import main` → 69 rutas; `python -m unittest discover tests` → **144
tests OK** (142 + 2: `test_enviar_ciudad_null_la_vacia`, `test_enviar_kilometraje_null_lo_vacia`,
ambos comprueban que el `null` explícito vacía **y** hace `commit`, distinto de omitir).
Sin migración (`alembic heads` = `0025`).

**Frontend (agente `dev-frontend`, commit `09cac9a` en `consulta-placas-web`):** wrapper
`actualizarPublicacion` en `api.ts` (`publicarBorrador` pasa a delegar en él, body
byte-idéntico); tipo `PublicacionActualizar` en el mirror (los 4 opcionales `?: T | null`,
`precio_usd` `?: number` sin null); formulario inline "Editar datos" por publicación en
`mis-publicaciones`, mismo contenedor y `inputCls` que `FichaEditor`, envía solo los
campos que cambiaron respecto del snapshot ("campos sucios"), vaciar un opcional viaja
como `null`. Validación suave en cliente para dar copy es-EC en vez del 422 crudo.
`tsc`/`lint`/`build` verdes.

**Pendiente de la ola:** el carril del comprador (abajo).

---

## 2026-08-27 — Cierre, ola 2: `scripts/estado.py` (TASK-007)

**Repo:** backend `consulta_placas_ec`, rama `chore/cierre-ola2`. Spec:
[`specs/TASK-007-scripts-estado.md`](specs/TASK-007-scripts-estado.md). Se ejecutó en Claude
Code (no Codex) porque el usuario pidió avanzar el cierre completo en una sola sesión; la
spec es autocontenida y no toca dominio.

**Qué es.** `python -m scripts.estado` imprime **cinco bloques** mirando el sistema real, no
la documentación. Su salida es **precondición de cada entrada de bitácora**.

1. Migraciones — head del repo (leído de los archivos, sin conectar) vs `alembic_version`
   de Neon; dice si faltan migraciones **o si la base va por delante del código**.
2. Git — commits sin pushear y ramas sin mergear a `main`, en **ambos** repos (`git fetch`
   sin `--prune` primero).
3. Proveedor vehicular — capacidades observadas en `GET /consultar/{placa}/perfil?solo_cache=true`
   **anónimo** (sin gastar tokens, sin nombrar cuál es): `identificadores_tecnicos` /
   `titular_validado` en `disponible: true` → hay proveedor con capacidades (alerta: puede
   ser `mock`); ambos `false` → estado correcto.
4. Fuentes — consultas de los últimos 7 días por `fuente`, **incluidas las que no tienen**
   (la ausencia es la señal).
5. Cola del worker — `pendiente` y `en_proceso` con su antigüedad; un `en_proceso` de horas
   es un lock colgado.

**Restricciones (cumplidas):** solo lectura, nunca escribe; lee `DATABASE_URL` **directo de
`.env`** con `dotenv_values` (no `src.core.database`, que resolvería la BD local); si una
fuente no responde, ese bloque lo dice y los otros se imprimen igual; exit 0 siempre; sin
dependencias nuevas. `stdout` se fuerza a UTF-8 para la consola legacy de Windows.

**Verificación — los seis criterios de la spec, ejecutados:**

- Corrida real contra Neon + producción: 5 bloques, exit 0. Detectó estado vivo — **AMT,
  EPMTSD y FGE sin consultas hace 32/32/90 días; 12 trabajos `pendiente` (el más viejo de
  38 d) y 1 `en_proceso` colgado hace 28 d** (esto es TASK-008, ahora con evidencia).
- **Neon inalcanzable** (host inexistente en `.env`, restaurado con `trap`): bloques 1/4/5
  reportan el fallo, 2 y 3 se imprimen completos, exit 0.
- **Backend caído** (`ESTADO_BACKEND=http://127.0.0.1:59999`): bloque 3 reporta
  `ConnectError`, el resto sigue.
- **Repo hermano ausente** (renombrado y restaurado): bloque 2 dice "el repositorio no está
  en esta máquina", el resto sigue.
- **Prueba de no-escritura:** `alembic_version` de Neon (`0025` → `0025`) y `git rev-parse
  main` de ambos repos, idénticos antes y después. Demostrado, no afirmado.
- Copy es-EC, 72 columnas.

**Archivos:** `scripts/estado.py` (nuevo) · `docs/ORDEN-DE-TRABAJO.md` (TASK-007 marcada +
filas 001/003/005/008 actualizadas contra el estado real).

---

## 2026-08-27 — Cierre, ola 2 (comprador): el ciclo no muere sin contacto

**Repo:** frontend `consulta-placas-web`, rama `chore/cierre-ola2`, commits `abbbdea` y
`3dddb13`. Backend **no se tocó**: el carril del comprador ya estaba construido (MC1
portada curada, MC2 búsqueda por cursor, TASK-011 contacto). El trabajo fue cerrar dos
puntas sueltas y aplicar dos decisiones de producto de Marcos.

### Decisiones de Marcos (2026-08-27)

1. **Contacto: se queda en 1 paso.** El botón "Ver teléfono" → número + WhatsApp sigue
   igual. El "primer contacto interno → luego teléfono" de la visión es una funcionalidad
   nueva (tabla + bandeja del vendedor), no una limpieza de cierre: se retoma en un ciclo
   posterior con datos de uso reales (era la decisión M5 original — "chat interno queda
   para después de validar demanda").
2. **En el detalle, el contacto va DESPUÉS de la evidencia.** El bloque de revelación del
   teléfono baja al final, tras ficha técnica + datos oficiales. Arriba, en la fila de
   CTAs del encabezado, un botón compacto **"Contactar al vendedor"** que ancla
   (`#contacto-vendedor`, scroll suave nativo, `scroll-mt-24` por el header sticky) a esa
   sección. Reemplaza en parte la decisión M2.7 ("acciones sin scroll en celular"): la
   acción **sigue** visible sin scroll, pero como ancla, no como el bloque completo. El
   dueño (`esMia`) no ve el ancla; abajo tiene su preview "Así lo verán los compradores".
   `ContactoVendedor.tsx` no se tocó. Commit `3dddb13`.

### El hueco que rompía el final del ciclo (commit `abbbdea`)

Un vendedor podía completar todo el flujo de publicar y dejar su anuncio **activo** sin
que nada le dijera que necesita cargar un teléfono. Resultado: el comprador pulsa "Ver
teléfono" → **409** → el ciclo comprador↔vendedor muere ahí. `mi-perfil-vendedor` solo se
alcanzaba desde el menú de la cuenta.

- **`mis-publicaciones`** resuelve el perfil de vendedor junto al listado (`Promise.all`,
  patrón lint-safe intacto) y muestra un aviso **solo** cuando hay ≥ 1 anuncio `activa` y
  el perfil no tiene `telefono`. Fallo de red / sesión vencida → no se avisa (no molestar
  sobre algo no verificado). El aviso se deriva de `pubs`, así que aparece en vivo al
  publicar un borrador.
- **Wizard de publicar:** tras publicar con éxito, si falta el teléfono, un paso de cierre
  corto ("Tu anuncio ya está publicado / agrega tu número") con dos salidas; **no
  bloquea** — el anuncio ya está activo. El chequeo vive en el handler, no en un efecto.
- **`AvisoContactoVendedor`** pasó de auto-fetch con 4 estados a presentacional; la página
  decide si se monta. Se perdieron el banner de confirmación ("los compradores te ven
  como X") y el de reintento — esa info sigue en `mi-perfil-vendedor` y `MenuCuenta`.
  Token `--marca` (invitación, no error; `DISENO.md §2` reserva `--atencion` para estado
  del vehículo).

**Verificación (frontend):** `npx tsc --noEmit` limpio · `npm run lint` **0 errores** ·
`npm run build` OK (17 rutas, `/marketplace/[id]` sigue dinámica).

**Pendiente de la ola:** `scripts/estado.py` (TASK-007), y el merge de `chore/cierre-ola2`
en ambos repos.

**Repos:** backend `consulta_placas_ec` (rama `chore/cierre-market-sin-precios`) +
frontend `consulta-placas-web` (agente `dev-frontend`). Primera tanda del plan de cierre
que salió de la auditoría del 2026-08-27. **Sin merge todavía.**

**Decisión de Marcos.** La monetización se suspende **en la superficie del producto**, no
solo en la documentación: nada de precios, costos, tokens ni "paga para…" visible. El
foco es el market; la consulta por placa y "dónde colocar costos" se retoman más adelante.
Origen: `AGENTS.md §1.0.3` decía "todos los precios están en 0" mientras el código de
market cobraba 3–100 tokens y `/precios` vendía paquetes — contradicción doc ↔ código.

### Backend (hecho, verificado)

- `TOKENS_PUBLICACION_PREMIUM`, `TOKENS_VERIFICACION_MARKETPLACE` (`publicaciones.py`) y
  `COSTO_COMPARTIR_TOKENS` (`compartidos.py`) → **0**, env-overridables. Con
  `debitar_tokens(0)` como no-op, publicar premium / solicitar verificación / compartir
  quedan gratis sin tocar la lógica: el débito sigue cableado y atómico, subir el valor
  reactiva el cobro. Docstrings corregidos (ya no afirman "cobra N tokens").
- `compartidos.py`: `SaldoInsuficiente` → **402** (era 422). Cierra **TASK-005**: es un
  flujo de pago, va con la excepción de contrato de §10.2. Latente mientras el costo sea 0.
- **Se retiró el endpoint legacy `GET /marketplace`** (`routers/marketplace.py`, sobre
  `Vehiculo.en_venta`/`precio_venta_usd`). Estaba huérfano: el frontend usa
  `/marketplace/feed` y `/marketplace/buscar` (`PublicacionInterna`/`Referenciada`).
  También se quitó `VehiculoSalidaMarketplace` (su único consumidor). Las columnas
  `en_venta`/`precio_venta_usd`/`url_externa` de `Vehiculo` quedan en el modelo (sin
  migración de borrado); ya no alimentan ningún listado.
- **Sin migración** (`alembic heads` = `0025`, cabeza única). La tabla `productos_consulta`
  **no se tocó**: sigue con tokens > 0 en BD, dormida y sin UI que la alcance. Se pondrá
  en 0 (migración) cuando se retome la consulta por placa. Anotado en `AGENTS.md §1.0.3`.

**Verificación:** `import main` → **69 rutas** (antes 70; −1 por el endpoint retirado);
`GET /marketplace` exacto ya no existe (comprobado sobre `app.routes`); `alembic heads` →
`0025`; `python -m unittest discover tests` → **142 tests OK**.

### Frontend (hecho — agente `dev-frontend`, rama `chore/cierre-market-sin-precios`, commit `0271c46`)

19 archivos, +184 −736. Se eliminaron `precios/page.tsx`, `TokenBadge`, `UnlockCard`,
`ProductoConsultaCard`, `ReporteCompraSeguraCard` y `desbloquearProducto`. `/precios` fuera
del `Header`, `Footer` y la barra móvil. `PerfilVehiculo` pierde la sección "Completa tu
revisión del vehículo" y el re-fetch con token; la consulta por placa queda como
herramienta gratuita que pinta lo que el backend entrega. Wizard de publicar y
`mis-publicaciones`: el plan `light`/`premium` se sigue eligiendo y enviando, presentado
como gratis; fuera todo copy de "N tokens" y todo manejo de 402. `types/api.ts` conserva
`saldo_tokens` y `ProductoEstado` en el mirror (el backend los sigue enviando) con nota de
que la UI ya no los pinta. De paso se limpiaron los **4 errores de lint
`react-hooks/set-state-in-effect`** preexistentes (`Header`, `mis-publicaciones`,
`admin/moderacion`, `admin/verificaciones`) con el patrón nonce + setState-tras-await, sin
`eslint-disable`.

**Revisión:** diffs leídos uno por uno. Sin `eslint-disable`, sin referencias colgantes,
los fixes de lint son reales. `npx tsc --noEmit` limpio · `npm run lint` → **0 errores**
(antes 4) · `npm run build` OK (17 rutas, `/precios` ya no aparece).

### Cierre de la ola

- `proyecto-snapshot.md` **regenerado** (estaba de 2026-06-01, hablaba de 16 migraciones y
  de "subir a Gemini"). Ahora es autocontenido: qué hay (verificado), qué se decidió y por
  qué, qué está bloqueado vs pospuesto, qué sigue. No se movió a `docs/` — ese cambio es de
  TASK-016.
- `AGENTS.md §1.0.3` refleja el estado aplicado.

**Pendientes de esta ola**
- **Merge** de `chore/cierre-market-sin-precios` en ambos repos (aprueba Marcos). Sin
  migración.
- La deuda del catálogo `productos_consulta` (tokens > 0 en BD) queda anotada, no urgente
  (se pone en 0 al retomar la consulta por placa).

---

## 2026-08-26 — TASK-017 fase 2: dos rutas que solo existían si sabías la URL

**Repo:** frontend `consulta-placas-web`, commits `d7d5f6d`, `dc421c4`, `eef7498`.
Recorrido funcional de las 18 rutas. **Parcial y declarado como tal.**

### Navegación: la regla dura se estaba incumpliendo

`/marketplace/mis-referencias` y `/marketplace/referenciar` **no tenían entrada en
ninguna** de las cuatro navegaciones (Header, Footer, barra móvil, menú de cuenta). Solo
se llegaba desde dentro del feed o escribiendo la URL. Van al **menú de cuenta** y no a
la barra pública por dos razones concretas: las dos exigen sesión (redirigen a
`/login?next=…`), y la barra ya tiene cinco entradas — una sexta para una acción
secundaria le quita claridad a las primarias.

Aparecieron además dos afirmaciones falsas en el propio menú:

- *"Mis publicaciones — Tus anuncios y referencias"*: llevaba a una página **sin**
  referencias y sin enlace hacia ellas.
- *"Se mudaron acá enteras (no duplicadas)"* sobre las tareas de admin: siguen también
  en `Header.tsx:103-112`, que sí lo documenta bien.

Estado final: **15 rutas estáticas con entrada**; las 3 dinámicas son detalles y su
entrada correcta es el clic en un ítem del listado.

### La portada vendía lo que no se cobra

El home tenía una sección *"Precios claros"* con un plan de **"$0.04 / token"**, y
`/precios` ofrece paquetes comprables (`$1.00 → 25 tokens`, con etiqueta *"Más
popular"*). Pero la monetización está **suspendida** (§1.0.3): los precios del catálogo
están en 0 y no hay proveedor de pago activo. Eso constaba **solo en un comentario del
código**; el usuario veía un catálogo de compra.

Se consultó porque toca qué cree el usuario que puede hacer, y se decidió: **fuera el
bloque del home** —además rompía la secuencia, porque después del hero la pregunta
abierta es "muéstrame los autos", no "cuánto cuesta un token"— y **aviso visible en
`/precios`** ("Todavía no cobramos nada"), con la palabra *referencial* pegada a cada
paquete para quien llegue scrolleando sin leer la cabecera. `/precios` sigue en el menú:
no se pierde ninguna capacidad.

En un producto cuya propuesta es la transparencia, un catálogo de compra que no cobra se
autodestruye solo.

### `/consultar/[placa]`: sin encabezado y sin salida

Era la **única de las 18 rutas sin `<h1>`** — y es la que se indexa por placa, según su
propio `generateMetadata`. Para un lector de pantalla empezaba directo en un formulario.

Y su copy de error le hablaba al usuario de *"la API"*, *"el backend"* y el *"cold start
~30s"*. El público navega en gama baja; el detalle además no le sirve, porque la acción
es la misma pase lo que pase. Reescrito desde el sistema —*"es un problema nuestro, no
de la placa"*—, que es el pendiente que §7 de `DISENO.md` marca sobre repartir bien la
responsabilidad. Se agregó salida al market: §1.0.1 dice que si una consulta falla el
flujo del marketplace continúa, y sin ese enlace era un callejón sin salida.

### Lo que se decidió NO tocar, y por qué

En `/marketplace/[id]` el **contacto va antes** de la ficha técnica y de los datos
oficiales. Por secuencia de decisión debería ir después: contactar es el paso final, no
el primero, y ponerlo antes de la evidencia pide la decisión antes de dar la
información. **No se movió**: el archivo documenta esa posición como decisión tomada en
M2.7 (*"bloque de precio + título + acciones visible sin scroll en un celular"*).
Revertir una decisión documentada sin evidencia nueva es exactamente el error que la
revisión cruzada existe para atrapar. Queda para decidir con datos de uso.

### Lo que la fase 2 NO alcanzó

El recorrido de las cuatro preguntas —qué pregunta responde el usuario, qué sobra, qué
falta, si el orden sigue la secuencia— se aplicó a fondo en `/`, `/precios`,
`/consultar`, `/consultar/[placa]`, `/marketplace/[id]` y las cuatro navegaciones. Las
demás rutas se auditaron **solo por estructura** (encabezados, orden de secciones,
alcanzabilidad), no leyendo su copy completo. Está declarado acá para que nadie lo lea
como un recorrido completo.

---

## 2026-08-26 — TASK-017 fase 1: el mismo texto pasó a significar otra cosa

**Repo:** frontend `consulta-placas-web` (código) + backend (`docs/DISENO.md`, esta
bitácora). Cierra la fase 1A del sistema de diseño "dos registros".

### La etiqueta de referencia externa cambió de significado sin cambiar una letra

El copy es **exacto y obligatorio desde M2.5** y sigue siendo idéntico:

> Referencia externa · datos no verificados

Lo que cambió es el tono de la insignia: de `alerta` (ámbar) a `declarado` (cálido).
Parece cosmético y no lo es, porque el color era la mitad del mensaje.

| | Antes (ámbar) | Ahora (cálido) |
|---|---|---|
| Qué comunicaba | *cuidado con este auto* | *este dato lo aporta un usuario* |
| De qué habla | un estado del vehículo | la **procedencia** del dato |
| A quién señala | al auto anunciado | a nuestra propia cadena de datos |

El ámbar es el color de "el vehículo tiene algo pendiente". Puesto en esta etiqueta
decía que el problema era del auto, cuando lo que la etiqueta declara es que
**nosotros no verificamos ese dato** — no lo raspamos, lo pegó un usuario. Es
exactamente el reparto de responsabilidad que §7 de `DISENO.md` marca como pendiente
("el copy de ausencia de datos reparte mal la responsabilidad") y es la distinción
declarado/oficial de §1, que hasta 1A era invisible porque los dos registros se
pintaban igual.

**Por qué se anota.** Un cambio de significado que no toca el texto **no aparece en un
diff de copy**. Alguien que audite las cadenas visibles del producto va a ver la
etiqueta idéntica en M2.5 y hoy, y va a concluir que no pasó nada. Pasó: cambió qué
afirma la plataforma sobre un anuncio ajeno. Si mañana se revierte el tono a ámbar
"porque se ve más visible", se revierte también la afirmación.

**Queda una inconsistencia viva y es honesto decirlo.** La misma etiqueta aparece en
tres lugares y solo uno se migró:

| Lugar | Tono hoy |
|---|---|
| Feed (`ListingCard`) | `declarado` — cálido |
| Detalle (`/marketplace/referencias/[id]`) | ámbar literal (`amber-50/200/900`) |
| `mis-referencias` (vista del aportante) | ámbar literal |

O sea que hoy el producto dice una cosa en el feed y otra al abrir el anuncio. Los dos
ámbar son de páginas que se migran en la fase 3 (tandas 1B y 1C); hasta entonces la
inconsistencia existe y **es deuda de esta fase, no un descuido de las otras**.

### Lo demás de la fase 1

- **Chip Premium a `--marca` plano.** El gradiente de marca queda **solo en el logo**.
  Eran dos lugares permitidos; con el chip adentro no se podía responder si ese
  gradiente decía "marca" o decía "estado". Se migraron los **cinco** chips Premium
  (feed, detalle, mis-publicaciones, publicar, admin/verificaciones), no solo el del
  feed: dejar cuatro con gradiente habría pintado el mismo chip distinto según la
  pantalla.
- **Token propio para el tercer estado del vehículo**, `--critico` `#8A2F43`. La escala
  es de tres pasos (`bueno → regular → requiere_atencion`) y el tercero **prestaba** la
  familia de `--atencion`, así que `--atencion` significaba dos cosas — contra la regla
  dura de §2. Es vino y no rojo porque el rojo es `--error`, que es un fallo *nuestro*.
  **Lo que el token no resuelve:** la separación con `--error` es de 17° de hue, que en
  una pantalla barata a pleno sol no alcanza. Lo que separa de verdad es el anillo del
  tono `peligro`, que por eso se queda.
- **`--secundario` de `#77695F` a `#706258`.** Sobre lienzo pasaba (4.92:1) pero sobre
  `--superficie-tenue` daba **4.52:1**, y ahí vive el tono `neutro` de las insignias.
  Ahora pasa 5:1 en las tres superficies donde aparece. El piso se fija en 4.8:1 y no en
  el 4.5:1 de la norma justamente para que el próximo ajuste de un tinte no lo rompa en
  silencio.
- **Los neutros cálidos entraron a la tabla de §2**: `--secundario`, `--superficie`,
  `--superficie-tenue`, `--borde`, `--borde-suave`, `--borde-fuerte`. Nacieron en 1A
  como anexo local de `globals.css` y ya estaban en uso en los cuatro primitivos
  compartidos: un token que la mitad de la interfaz usa es parte del sistema, no una
  nota al pie.

**Verificación, y una afirmación mía que el revisor tumbó.** La primera versión de esta
entrada decía *"los 16 ratios que 1A afirmaba se recalcularon uno por uno y los 16 daban
exacto — el trabajo previo era honesto"*. **Era falso por alcance.** Lo que recalculé
fueron las **tablas de `DISENO.md`**, y esas sí dan exacto. Los ratios también viven
sueltos en comentarios —de tokens en `globals.css` y de componentes— y ahí no miré.
Cuatro números estaban mal:

| Dónde | Decía | Real |
|---|---|---|
| `BentoCard.tsx:25` — `slate-400` sobre blanco | 2.83:1 | **2.63:1** (Tailwind 4; 2.56:1 en la v3) |
| `globals.css:42` — `--declarado` sobre blanco | 2.6:1 | **2.86:1** |
| `ListingCard.tsx:86` — secundario sobre tarjeta | 5.29:1 | **5.87:1** |
| `ListingCard.tsx:105` — secundario sobre relleno | 4.52:1 | **5.02:1** |

Los dos primeros venían de 1A. **Los dos últimos los rompí yo en esta misma fase**: al
oscurecer `--secundario` invalidé dos comentarios que lo citaban, y el peor de los dos
—4.52:1— quedaba afirmando en presente justo el valor por debajo del piso de 4.8:1 que
esta fase acababa de establecer. Un lector que auditara el código habría encontrado la
violación viva en un comentario en vez del arreglo.

Los cuatro están corregidos. Los ratios nuevos (`--critico` 8.18:1 sobre blanco, su par
tinte/texto 7.91:1, el secundario en las tres superficies) se midieron, no se estimaron,
y además se comprobaron **sobre el CSS compilado** —`.text-secundario{color:#706258}`,
`.bg-critico-tinte{background-color:#f7e7ea}`— porque una clase de Tailwind que no se
genera no rompe el build: simplemente no existe.

**La lección, que es la misma de TASK-015 con otro disfraz:** cambiar el valor de un
token invalida en silencio cada comentario que lo cita, y un comentario con un número
viejo es documentación falsa igual que un `0021` que no existe. Al mover un token hay que
hacer `grep` del número, no solo del nombre.

### Nota de proceso: esta revisión NO fue independiente

`AGENTS.md` §16.1 exige que `revisor-calidad` corra en la herramienta que **no** ejecutó
el trabajo. Acá corrió en la misma sesión que lo implementó, y queda anotado porque una
desviación de proceso sin registro es indistinguible de no haber tenido el proceso.

**Por qué se aceptó:** el trabajo es una migración de tokens contra un documento de
diseño ya cerrado por dos revisiones cruzadas, así que el criterio de aceptación es
externo y verificable —los hex y los ratios están escritos en `DISENO.md`— y no depende
de la interpretación de quien lo implementó. Además el ciclo es cerrado: cada fase se
revisa hasta veredicto APTO, y al revisor se le entrega **el pedido original**, no solo
el diff.

**Qué NO mitiga, que es lo que importa:** §16.1 no existe para atrapar fallos de estilo
—esos los atrapa cualquiera— sino para atrapar que se haya implementado algo
**adyacente** a lo pedido. Ese error es invisible desde adentro por construcción: quien
escribió el diff lo revisa con la misma lectura del requisito con la que lo escribió.
Un contraste mal calculado se detecta en la misma sesión; haber resuelto el problema
equivocado, no. Ese riesgo **queda abierto** en esta tarea y la forma de cerrarlo es
pasar el diff por Codex.

---

## 2026-08-25 — TASK-015 (3): un guard que compara subcadenas de una URL no es un guard

**Repo:** backend, rama `feat/TASK-015-login-google`. **Sin commit.** Cierra el hallazgo
de Codex sobre la barrera de `TEST_DATABASE_URL` que introdujo la entrada anterior.

**El hallazgo.** La barrera decía esto:

```python
if "127.0.0.1:5433" not in URL_PG_DEV and "localhost:5433" not in URL_PG_DEV:
    raise RuntimeError(...)
```

Busca una **subcadena en el texto completo de la URL**. Una URL a producción que lleve
ese texto en cualquier parte que no sea el host —un parámetro
(`?options=-c search_path=127.0.0.1:5433`), la contraseña— la pasa entera. Y lo que hay
al otro lado del guard es `TRUNCATE usuarios RESTART IDENTITY CASCADE` en cada `setUp`.
Es decir: la barrera que la entrada anterior presentó como la razón de que "Neon no se
tocó" **no protegía Neon**.

**Es el mismo error que el nonce de la revisión 3**: algo que *parece* una protección y
tiene la forma de una protección, sin la propiedad que se le atribuye. Ahí era un nonce
que no se verificaba contra nada; acá, una comparación de texto donde hacía falta una de
identidad. Las dos pasaban su propia lectura porque el nombre de la variable ya afirmaba
lo que el código no hacía.

**Qué se hizo.** La comprobación se extrajo a `exigir_pg_dev(url)` en
[tests/test_login_google_carreras.py](../tests/test_login_google_carreras.py), que parsea
con `make_url` de SQLAlchemy y exige por separado, **sobre los componentes parseados y
nunca sobre el texto**:

| Componente | Valor exigido |
|---|---|
| `url.host` | exactamente `127.0.0.1` o `localhost` |
| `url.port` | exactamente `5433` (sin puerto → `None` → aborta; el default sería 5432) |
| `url.database` | exactamente `task015_carreras` |

Los tres, o no se corre. Antes bastaba con el host+puerto: se agrega la base porque
`pg-dev` hospeda varias (TASK-010) y solo la desechable puede truncarse. El mensaje de
error se arma con `render_as_string(hide_password=True)` para no filtrar la clave al log.

**7 pruebas nuevas, y son lo único del archivo que corre siempre** — no están bajo el
`skipIf` de pg-dev, a propósito: el día que alguien "simplifique" el guard de vuelta a un
`in` sobre el texto, fallan en CI sin necesidad de un Postgres levantado. La central es
la negativa: una URL a `…aws.neon.tech` con el literal `127.0.0.1:5433` en `options`
—verificado con `assertIn` dentro del propio test, para que se vea que el guard viejo la
dejaba pasar— debe abortar. Las demás cubren la misma trampa en la contraseña, host bueno
con puerto 5432, host y puerto buenos con otra base, sin puerto, y URL malformada.

**Verificación.** Con `pg-dev` levantado, el archivo corre **13 pruebas, `OK`, sin un solo
skip**: las 7 del guard más las 6 de carrera contra Postgres real. Sin Docker da
`OK (skipped=6)` — las del guard corren igual, que es el punto. **Suite completa:**
`python -m unittest discover tests` → **142 pruebas, OK** (135 + 7). Y se comprobó que las
dos URL de la prueba negativa **pasaban el guard viejo**: `'127.0.0.1:5433' in url` da
`True` en ambas.

**Lección, que es la que importa más que el parche.** Un guard que compara subcadenas de
una URL no es un guard: una URL es una estructura, y el único chequeo que vale es el que
se hace sobre sus componentes parseados. Vale igual para hosts, orígenes de CORS,
`redirect_uri` y cualquier allowlist — `"midominio.com" in origen` acepta
`midominio.com.evil.tld`. Y en general: cuando una protección es lo único que separa un
test de una tabla de producción, hay que escribirle la prueba negativa. Sin ella, el guard
se degrada en el primer refactor que lo "limpie".

**Documentación falsa, cerrada.** §2 de la spec decía que el `if not
context.is_offline_mode():` del `downgrade` era *"el mismo cuidado que tomó `0021`"*.
`grep is_offline_mode alembic/` da sólo `env.py` y la propia `0025`: **el precedente no
existe**. `0021_vendedor.py` usa `op.execute`, que en modo `--sql` se emite como texto y
nunca abre conexión, así que nunca tuvo el problema; `0025` es la primera migración del
repo que necesita *leer* estado dentro de un `downgrade`. Corregido en la spec con la nota
del porqué: una cita a un precedente inexistente hace que la próxima revisión dé por
verificado algo que nadie verificó — el mismo mecanismo que el nonce y que el guard.

**Commit.** `feat(auth): TASK-015 login con Google`. `ORDEN-DE-TRABAJO.md` marca el backend
hecho y el frontend pendiente.

**`0025` aplicada en Neon.** `alembic current` decía `0024`, `upgrade head` la llevó a
`0025 (head)`. Verificado sobre `information_schema` en la base real: `password_hash`
**nullable**, las tres columnas nuevas (`proveedor_autenticacion` NOT NULL, `id_google`
nullable, `email_verificado` NOT NULL), el índice **único** `ix_usuarios_id_google` y el
CHECK `ck_usuarios_proveedor_autenticacion`. Neon no estaba suspendida y no hubo timeout.

> **Cuidado del procedimiento.** `.env.local` apunta a `pg-dev` y **gana sobre `.env`**
> (TASK-010), así que apuntar a Neon exige moverlo a un lado y volver a ponerlo después.
> Se comprobó el host resuelto **antes** de migrar y **después** de restaurarlo: sale
> `…aws.neon.tech` durante la migración y `127.0.0.1:5433` al terminar. Sin esa
> comprobación, `alembic upgrade head` corre contra la base que uno cree, no contra la
> que está configurada.

**Pendiente:** el frontend (botón en login y registro, con salida visible para el 409), y
volver a pasar el diff por Codex.

---

## 2026-08-25 — TASK-015 (2): carreras de BD y verificación contra Postgres real

**Repo:** backend, rama `feat/TASK-015-login-google`. **Sin commit.** Cierra el único
hallazgo (severidad media) de la auditoría de Codex sobre el diff de la entrada anterior.

**El hallazgo.** Las comprobaciones previas de `/auth/google` y `/auth/google/vincular`
son `SELECT`, y entre el `SELECT` y el `COMMIT` cabe otra petición. Dos altas simultáneas
—un **doble clic** en "Entrar con Google" basta— o dos vinculaciones concurrentes del
mismo `sub` pasaban las dos comprobaciones y chocaban contra `ix_usuarios_email` /
`ix_usuarios_id_google` recién al commitear. Eso escapaba como **500**, contra §10.2.

**Qué se hizo.** Mismo patrón que `obtener_o_crear_vendedor` (TASK-001): capturar
`IntegrityError`, `rollback`, releer la fila que ganó y responder según ella; **si la
violación no es la esperada, se relanza** en vez de tragarla. Cubre las tres rutas: alta
nueva, enlace autoritativo del paso 2, y el commit de `/auth/google/vincular`. La rama de
alta distingue dos ganadores posibles: si ganó una petición con los mismos claims,
responde 200 con la fila del rival; si en la carrera se registró ese correo **por
contraseña**, aplica §0.1 igual que si la cuenta hubiera existido desde el principio
(enlace si es autoritativa, 409 si no).

**Verificación contra Postgres real — `pg-dev`, no simulada.** Una `SesionFalsa` no
ejerce restricciones: un test con `Mock` afirmaría que el `except IntegrityError`
funciona sin que ningún `IntegrityError` llegue a levantarse. Por eso las pruebas de
carrera viven aparte, en `tests/test_login_google_carreras.py`, contra el contenedor
`pg-dev` (base desechable `task015_carreras`). **Neon no se tocó**: la URL resuelta se
verificó antes de migrar y el archivo aborta si `TEST_DATABASE_URL` no apunta a `5433`.

- **La cadena completa `0001` → `0025` corre limpia** contra Postgres real. `\d usuarios`
  confirma `password_hash` **nullable**, las tres columnas nuevas, el CHECK del proveedor
  y el índice **único** `ix_usuarios_id_google`. Esto cierra criterios de aceptación que
  la entrada anterior había declarado no verificables.
- **6 pruebas nuevas**, y se comprobó que **fallan sin el fix**: neutralizando los dos
  `except IntegrityError`, 5 de 6 dan error (la sexta es el control sin carrera). Una
  prueba de concurrencia que no se ve fallar no prueba nada.
- El rival se inserta en `before_flush`, no en `after_flush`: escribiendo después, se
  bloquearía contra el índice único esperando nuestro `COMMIT` y la prueba se colgaría.
- Sin `pg-dev` levantado las 6 se **saltan con motivo explícito** — la suite queda verde
  (135 pruebas, `OK (skipped=6)`) sin silenciar nada.

**Suite completa:** `python -m unittest discover tests` → **135 pruebas, OK** (129 + 6).

**Pendiente:** volver a pasar el diff por Codex. Y la corrección de la spec pendiente de
la entrada anterior (§2 cita un precedente de `0021` que no existe).

---

## 2026-08-25 — TASK-015: login con Google (sin contraseña)

**Repo:** backend, rama `feat/TASK-015-login-google`. **Sin commit:** el diff queda para
la revisión cruzada (§16.1 — revisa Codex, que no lo escribió).

**Qué se hizo.** `POST /auth/google` canjea un ID token de Google Identity Services por
el JWT propio del proyecto, y `POST /auth/google/vincular` enlaza una cuenta de Google
desde una sesión ya autenticada. La verificación vive en
[src/modules/auth/google.py](../src/modules/auth/google.py); el ID token se valida y **se
descarta**: no se guarda, no se reenvía y no se refresca. Migración
[0025](../alembic/versions/0025_login_google.py): `password_hash` pasa a NULL y
`usuarios` suma `proveedor_autenticacion`, `id_google` (índice ÚNICO) y
`email_verificado`. **La migración NO se aplicó a ninguna base.**

**Las tres decisiones que no son obvias.**

1. **Auto-enlace solo con identidad autoritativa.** `email_verified: true` NO alcanza
   para tomar posesión de una cuenta existente: el claim dice que en *algún momento*
   Google comprobó el buzón, no que hoy lo controle la misma persona — los correos
   corporativos se reasignan, los dominios caducan. Solo enlazan automáticamente
   `gmail.com`/`googlemail.com` (Google opera el buzón) y las cuentas con `hd` de
   Workspace. Un `juan@hotmail.com` que ya existe recibe **409** y la salida es
   `/auth/google/vincular` — autenticarse es la prueba de posesión que el claim no da.
   Es fricción deliberada; el copy dice qué hacer.
2. **`proveedor_autenticacion` es el origen de la cuenta, no una exclusividad.** Quién
   puede entrar por dónde lo dicen las columnas de hecho (`password_hash IS NOT NULL` /
   `id_google IS NOT NULL`) y una cuenta puede tener las dos. Como bandera exclusiva,
   vincular Google le apagaría al usuario su propia contraseña en silencio.
3. **`/auth/login` trata `password_hash IS NULL` como credencial inválida (401).** Con la
   columna nullable, un usuario de Google que probara el formulario llegaba a `passlib`
   con `None` → `TypeError` → 500 por una condición de negocio esperable. El mensaje es
   el mismo que el de una contraseña equivocada: decir "esa cuenta usa Google" revelaría
   qué correos están registrados y con qué proveedor.

**Lo que jose NO hace y hubo que escribir.** `_validate_aud` valida **pertenencia, no
igualdad** (`aud: [nuestro_id, otro_id]` pasa), `require_aud`/`require_exp` vienen en
`False` (un token sin `aud` o sin `exp` pasa en silencio), `_validate_iss` no valida nada
si no se le pasa `issuer=`, `azp` no lo mira en absoluto y `_get_keys` devuelve el JWK Set
entero: `jose` prueba **todas** las claves hasta que alguna valide, ignorando el `kid`.
Cada una tiene su prueba negativa, porque ninguna falla ruidosamente: un agujero de
autenticación sigue devolviendo 200. Por eso `python-jose` queda **pineado a `==3.5.0`**
(único cambio en `requirements.txt`, cero dependencias nuevas): todo esto está escrito
contra el comportamiento interno de esa versión.

**El refresco del JWKS es single-flight.** `kid` ausente → 401 **sin tocar el JWKS** (si
no, mandar tokens basura sin `kid` sería un DoS contra el endpoint de claves de Google).
`kid` presente y desconocido → **un** refresco con piso de 5 minutos, y el lock, la doble
comprobación y la lectura del piso van **dentro** del `threading.Lock`: leer, decidir y
escribir fuera de él es una carrera que convierte una ráfaga de N tokens inventados en N
golpes a Google. El límite es **por proceso** y eso es sabido y aceptado; hoy Render free
corre una instancia.

**Riesgo residual declarado, no mitigado:** no hay antirreplay. El ID token vale ~1 h y
`/auth/google` lo acepta cuantas veces se lo manden; con `JWT_EXPIRA_MINUTOS=1440`, cada
canje rinde 24 h de sesión propia y los canjes repetidos emiten **sesiones concurrentes**
que hoy no se pueden revocar. Exposición total: hasta ~25 h desde la filtración. El cierre
correcto es un guard por `jti` en Redis y espera a que haya Redis. Queda anotada la
recomendación de bajar `JWT_EXPIRA_MINUTOS` a 4-8 h — **no se tocó acá**, afecta a todos
los logins y se decide aparte.

**Verificación.** `import main` limpio; el OpenAPI pasa de 51/64 a **53/66** con
`/auth/google` y `/auth/google/vincular` presentes. `alembic heads` → una sola cabeza,
`0025`; el DDL se revisó con `--sql` (offline, sin conectar). `python -m unittest discover
tests -v` → **129 pruebas OK** (59 previas + **70 nuevas**). La **ráfaga paralela** (20 peticiones
simultáneas, mismo `kid` desconocido) deja el contador del doble del JWKS en **1**; se
comprobó que **falla con 20 != 1 al quitar el lock**, que es lo que la hace útil.

**Pendientes.** Aplicar la `0025` contra Postgres real y comprobar `\d usuarios`, el
`downgrade` limpio y su aborto con cuentas de Google vivas (acá solo se probó la decisión
del guard, con `op` y `context` mockeados). Crear el proyecto en Google Cloud Console
—separado del de Vision— y cargar `GOOGLE_CLIENT_ID`; **publicar la pantalla de
consentimiento pronto: la verificación de Google demora y es tiempo de espera de un
tercero**. Frontend del botón GIS: tarea aparte, sin acoplamientos (solo manda `id_token`).

---

## 2026-08-05 — TASK-010: entorno local anclado a la raíz del proyecto

**Repo:** backend. **Sin commit:** el diff queda para la revisión cruzada.

**Qué se hizo.** `src/core/database.py` carga `.env.local` y `.env` desde la raíz
derivada de `Path(__file__).resolve().parents[2]`, no desde el CWD. La precedencia se
mantiene: variable real del entorno > `.env.local` > `.env`, sin `override=True`.
`.env.local` también queda fuera del contexto de Docker para que una URL local nunca se
hornee en la imagen.

**Verificación.** Los tres casos de precedencia (local, variable exportada y fallback a
`.env`) se probaron desde la raíz y desde un subdirectorio. `import main` conserva 68
rutas y la suite completa pasó. La spec suma explícitamente la prueba desde subdirectorio.

---

## 2026-08-10 — TASK-013 (frontend): mostrar y capturar el kilometraje

**Repo:** `consulta-placas-web` (el backend solo recibe esta entrada). Ejecutó el agente
**dev-frontend**. **La migración `0024` ya está aplicada en Neon** y el backend está
mergeado en `main` (`066c9cd`): código y base alineados.

**Qué se hizo.** `kilometraje?: number | null` en el mirror —siguiendo la convención
`?: X | null`, que fue un hallazgo de la auditoría de TASK-012—, campo numérico opcional en
el wizard, el kilometraje en el detalle junto a marca/modelo/año/ciudad, y en la tarjeta
del feed **una sola prop**: `LineaExtras` ya lo formateaba para la referenciada, así que
`ListingInternaCard` solo tuvo que pasarle el campo. Queda `Quito · 85.000 km`, igual que
en los portales conocidos.

**El retorno de haber unificado en TASK-012.** Las dos tarjetas ahora hacen la llamada
**idéntica** `<LineaExtras ciudad={pub.ciudad} kilometraje={pub.kilometraje} />`. Agregar
el kilometraje fue una prop, sin markup ni formateo nuevo: eso es lo que se compró al
extraer el helper en vez de duplicar la línea.

### Por qué NO se hizo el prefill

No es "hoy hay 0 filas y mañana se llena": es un **no-op estructural**. Se revisó todo
`src/` y **no existe una sola llamada** a `GET /vehiculos/{id}/kilometraje` ni a
`kilometros` — **mi-garage no registra lecturas de kilometraje**. La tabla no se puede
llenar desde esta web, así que el prefill no tendría de dónde sugerir nada hasta que el
garage gane esa función.

Y no salía gratis: a diferencia de la ciudad —que viajaba en el `listarVehiculos()` que la
página ya pedía—, esto exigía una función nueva en `api.ts`, un tipo nuevo en el mirror y
una llamada **autenticada por vehículo**, re-disparada en cada cambio del `<select>`, con
sus respuestas potencialmente fuera de orden y su flag de interacción. Todo eso para
proponer `undefined`. Cuando el garage registre kilometraje, el prefill se hace ahí y
**con `max(kilometros)`**, por la discrepancia registrada en la entrada del 2026-08-09
(el endpoint ordena por `fecha_lectura desc` pero la validación monotónica usa el máximo).

### `line-clamp-2` en la línea de extras, y solo ahí

Con una ciudad larga, el `truncate` heredado partía la cifra a media: *"Santo Domingo ·
1.25…"* donde el dato dice **1.250.000 km**. **Una cifra cortada cambia lo que dice**; un
título cortado no — sigue significando lo mismo aunque se lea a medias. Por eso la regla de
M2.7 (*una línea, truncada*) **se conserva para el título** y cambia solo para esta línea.
En un producto cuya propuesta es la transparencia, un kilometraje mal leído es peor que
ocupar un renglón más.

**Medido a 360px** con el peor caso inyectado en el feed: el texto se ve **completo** en 2
líneas, sin desborde horizontal (`scrollWidth` 360 = `innerWidth`), y **la grilla no
baila** — en la fila que mezcla una tarjeta de 2 líneas con una de 1, **ambas miden 289px**
porque el grid las estira a la más alta. La diferencia de 16px se da *entre* filas, que es
lo esperado. (Nota de la medición: se capturaron 3 de las 5 tarjetas inyectadas; las dos
que faltan son los casos triviales —solo ciudad y sin extras— que el selector no tomó.)

**Verificación:** `npx tsc --noEmit` limpio · `npm run lint` → 4 errores, los 4
preexistentes, 0 nuevos · `npm run build` OK.

**Pendientes**
- **No se puede editar el kilometraje de una publicación ya creada**, igual que la ciudad:
  `mis-publicaciones` no tiene formulario de campos básicos y `api.ts` no expone el
  `PATCH /marketplace/publicaciones/{id}`. Ya van **dos** campos que solo se pueden fijar
  al crear; el tercero heredará el problema. Es su propia tarea.
- `/marketplace/buscar` no filtra ni ordena por kilometraje (tocaría el keyset).
- El prefill queda para cuando **mi-garage registre lecturas** — con `max(kilometros)`.

---

## 2026-08-09 — TASK-013: kilometraje declarado en las publicaciones internas

**Rama:** `feat/TASK-013-kilometraje-publicacion`. Ejecutó el agente **dev-backend**.
**Migración `0024` escrita pero NO aplicada** — Neon sigue en `0023` y sin la columna.
> **Actualización 2026-08-10:** la `0024` **ya está aplicada** en Neon (`alembic_version`
> = `0024`, columna `kilometraje bigint` nullable presente) y la rama está **mergeada en
> `main`** (`066c9cd`, pusheado). Código y base quedaron alineados. Ver la entrada
> *"TASK-013 (frontend)"*, arriba.

**El problema.** `PublicacionInternaSalida` no traía kilometraje y `PublicacionReferenciada`
sí, y la tarjeta ya lo pintaba vía `LineaExtras`. La misma asimetría que cerró TASK-012 con
la ciudad: el comprador veía el kilometraje de un auto copiado de OLX pero no el de uno
publicado aquí. Después del precio, es el dato que más decide.

**Qué se hizo.** Columna `kilometraje` (BigInteger, nullable) en `publicaciones_internas`,
con **el mismo nombre y tipo** que en la referenciada para que `LineaExtras` siga leyendo
un solo campo sin ramificar. Entra en alta y edición con `ge=0, le=2_000_000` (los mismos
límites de la hermana) y sale en feed, `/buscar`, `mias` y detalle. **No es obligatorio
para publicar**: no entra al umbral de activación ni a ninguna validación del alta. La
salida va `int | None` **sin** los límites, mismo precedente que la ciudad: el rango se
impone al escribir, y si mañana se baja el tope las filas viejas tienen que poder leerse
en vez de convertir un GET público en 500.

### Por qué NO se derivó del garage — y por qué este caso es distinto al de la ciudad

El argumento fuerte no es semántico, es de **consentimiento**: `SCOPE_PERMITIDO =
{"kilometraje", "mantenimientos", "duenos_historico"}`. El dominio **ya modela el
kilometraje como opt-in**: es uno de los tres bloques que el dueño elige compartir, y solo
a través del token de compra-venta con scope explícito. Derivarlo automáticamente a un
anuncio **público** saltaría un consentimiento que el modelo ya tiene construido, y lo
haría en silencio.

Eso lo separa del caso de `ciudad_registro` en TASK-012, que era **solo semántico** —dónde
se matriculó no es dónde está en venta, pero nadie había declarado la ciudad como privada—.
Aquí el problema no es que el dato signifique otra cosa: es que **su exposición ya estaba
decidida, y decidida en contra**.

Se suman dos razones prácticas: la última lectura del garage es el odómetro de un momento
cualquiera, no el que el vendedor quiere publicar; y **ambas fuentes están vacías en
producción** (`kilometraje_lecturas` 0 filas, `mantenimientos` 0 filas), así que derivar
habría dado `NULL` para el 100% de los anuncios. Por lo mismo, **no hay backfill**.

### Discrepancia del endpoint de lecturas — importante para el prefill

`GET /vehiculos/{vehiculo_id}/kilometraje` ordena por **`fecha_lectura desc`**, pero la
validación monotónica del POST compara contra **`max(kilometros)`**. No son lo mismo: se
puede insertar una lectura con fecha vieja y kilometraje más alto, y esa lectura sería la
mayor sin ser la primera de la lista.

**Consecuencia para quien haga el prefill del formulario: tomar `max(kilometros)`, no
`lecturas[0]`.** Usar el primero devolvería un valor menor al real y propondría al vendedor
un odómetro que su propio garage contradice. Otros dos avisos: es una **llamada extra**
(`VehiculoSalidaCompleta` no expone kilometraje, a diferencia de la ciudad, que venía en el
garage ya cargado), y hoy el prefill será un **no-op** porque no hay lecturas — el
formulario tiene que verse bien sin sugerencia.

### Los dos kilometrajes conviven, y está escrito por qué

`PublicacionInternaSalida` ya exponía uno escondido: `ResumenMantenimientos.ultimo_kilometraje`,
`max(kilometraje_relacionado)` de los mantenimientos, solo premium y hoy siempre `NULL`.
**Conviven a propósito**, con la nota en ambos schemas apuntándose mutuamente para que
nadie borre uno sin leer el otro: `kilometraje` es *"el odómetro **hoy**, según el
vendedor"* (declarado, cualquier plan) y `ultimo_kilometraje` es *"el odómetro en el
**último service**"* (derivado, verificable, solo premium). La redundancia **es** el valor:
si el service de hace tres meses marcaba 78.000 y el anuncio dice 42.000, hay algo que
explicar — borrar uno pierde justo esa comparación. Tres tests fijan la decisión.

**Seguimiento:** hoy `ultimo_kilometraje` es siempre `NULL`. El día que deje de serlo, hay
que revisar **cómo se presentan juntos en el detalle**: dos cifras de kilometraje sin
explicación se leen como contradicción, no como información.

**Verificación** (ejecutada de forma independiente al reporte del agente): `import main` →
**68 rutas** (sin cambio) · `alembic heads` → **`0024`, cabeza única**, cadena `0023→0024`
con `downgrade` · **59 tests OK** (40 previos + 19 nuevos) · SQL offline en ambos sentidos
(`ADD COLUMN kilometraje BIGINT` / `DROP COLUMN`) sin conectar a ninguna BD · **Neon
intacta**: `alembic_version` = `0023`, columna ausente.

**Pendientes**
- ~~**Marcos: `alembic upgrade head`** (0024) contra Neon.~~ **HECHO el 2026-08-10**, junto
  con el merge a `main`. Se aplicó con la guarda habitual: apartar `.env.local`, verificar
  que el destino fuera Neon, exigir que la versión de partida fuera `0023`, y restaurar
  `.env.local` con `trap` pasara lo que pasara.
- **Frontend**: el kilometraje en el formulario (con el prefill por `max(kilometros)`) y en
  la tarjeta — `LineaExtras` ya lo pinta para la referenciada, así que debería ser pasarle
  el campo.
- **Nada valida el kilometraje declarado contra el garage.** Se puede publicar 42.000 con
  un service de 78.000. Es coherente con "son hechos distintos", pero esa contradicción es
  justo la señal que el sello premium debería mirar. Candidato a regla, no implementado.
- **No se puede vaciar el kilometraje desde la edición** (`is not None` en el PATCH), igual
  que la ciudad. Ya van **dos** campos con la misma limitación: cuando se resuelva, conviene
  hacerlo para todo el schema de una vez y no campo por campo.
- `/marketplace/buscar` no filtra ni ordena por kilometraje: tocaría el keyset y no estaba
  pedido.

---

## 2026-08-08 — TASK-012 (frontend): mostrar y capturar la ciudad

**Repo:** `consulta-placas-web` (el backend solo recibe esta entrada). Ejecutó el agente
**dev-frontend**; corregido tras la auditoría de **Codex**. **Migración `0023` ya aplicada
en Neon** (verificado: columna `ciudad VARCHAR(80)` nullable, 3 filas en `null`).

**Qué se hizo.** `ciudad` en el mirror de types; selector con el catálogo cerrado de 12 en
el wizard; la ciudad en el detalle del anuncio junto a marca/modelo/año; y la línea de
extras de la tarjeta **unificada**: se extrajo `LineaExtras` con ambos campos opcionales,
que ahora usan tanto `ListingInternaCard` como `ListingReferenciadaCard`. Antes esa línea
existía solo en la referenciada; como ambas entidades comparten el nombre `ciudad`, la
tarjeta lee una sola forma y no dos ramas. Sin ciudad no se pinta nada: no deja hueco.

**Prefill: se propone, no se hereda.** El wizard llega del garage con `?vehiculo=<id>`
pero sin ciudad, así que se resuelve del vehículo ya cargado (la página ya pedía el
garage) en vez de sumar un query param con texto libre — y así también funciona al elegir
el auto en el `<select>`. El valor se **propone** con un aviso que dice de dónde salió y
que es **dónde se matriculó**, no dónde está en venta. Si `ciudad_registro` no calza con
el catálogo tras normalizar (sin tildes, minúsculas, espacios colapsados), el selector
queda vacío: un prefill que adivina es peor que ninguno. Publicar sin ciudad sigue siendo
válido; no se agregó ninguna validación que bloquee el alta.

**Tres correcciones de la auditoría de Codex**

1. **El prefill pisaba "Sin especificar" (la de fondo).** `setCiudad(actual => actual ||
   sugerida)` usaba el VALOR para inferir intención, y `""` significa dos cosas distintas:
   "todavía no eligió" y "eligió *Sin especificar*". Quien elegía "Sin especificar"
   mientras `listarVehiculos()` seguía en vuelo se encontraba la ciudad del garage
   impuesta — exactamente lo contrario de la intención declarada. Se corrigió con un
   **flag de interacción** (`useRef`, no estado: solo se consulta, no debe re-renderizar
   ni entrar en dependencias) que se marca en el `onChange` del selector. La misma regla
   se aplicó a `elegirVehiculo`, que tenía el mismo patrón.
   **Verificado simulando la carrera** con Playwright, retrasando `/vehiculos` 3 s y
   tocando el selector durante la ventana: elegir "Sin especificar" queda en `""`, elegir
   "Ambato" queda en `"Ambato"`, y no tocar nada sigue prellenando `"Quito"` (sin
   regresión del caso feliz).
2. **El mirror no reflejaba la opcionalidad real.** El OpenAPI declara `ciudad` nullable
   **y no requerida** en la salida, y el input admite `null` (`anyOf: [enum, null]`).
   Quedó `ciudad?: string | null` en la salida y `ciudad?: CiudadPublicacion | null` en el
   input. Nota: la convención del archivo ya era `?: X | null` —y el hermano
   `PublicacionReferenciada.ciudad` ya la seguía—, así que el interno era el desalineado.
3. **Faltaba esta entrada de bitácora** (§5 del checklist).

**Verificación:** `npx tsc --noEmit` limpio · `npm run lint` → 4 errores, los 4
preexistentes, 0 nuevos · `npm run build` OK · a 360px la línea de extras no desborda
(tarjeta `scrollWidth == clientWidth`; el `truncate` recorta con elipsis en el peor caso
`"Santo Domingo · 128.450 km"`) y sin ciudad simplemente no se renderiza (−18 px de alto).

**Pendientes**
- **No se puede corregir la ciudad de una publicación ya creada.** El backend acepta
  `ciudad` en el PATCH, pero el frontend no tiene formulario de edición de datos básicos
  en `mis-publicaciones` (solo ficha, fotos y estado). Si el vendedor se equivoca, hoy no
  tiene cómo arreglarlo desde la web. Se suma al detalle heredado del backend: `ciudad:
  null` en el PATCH significa "no la toques", no "bórrala".
- El **filtro por ciudad** sigue fuera de alcance, por decisión: se construye cuando haya
  publicaciones suficientes para que filtrar tenga sentido.

---

## 2026-08-08 — TASK-012: ciudad en las publicaciones internas

**Repo:** backend. Ejecutó el agente **dev-backend**. **Migración `0023` escrita pero NO
aplicada** — Neon sigue en `0022` y sin la columna; aplicarla es tarea de Marcos.

**El problema.** `PublicacionInterna` no tenía ciudad y `PublicacionReferenciada` sí, así
que un comprador podía ver dónde está un auto **copiado de OLX** pero no uno publicado en
la plataforma. En un market de autos la ciudad decide si vale la pena abrir el anuncio.

**Qué se hizo.** Columna `ciudad` (String(80), nullable) en `publicaciones_internas`;
catálogo cerrado `CiudadPublicacion` como `Literal` **en código** con 12 ciudades (Quito,
Guayaquil, Cuenca, Ambato, Manta, Loja, Machala, Santo Domingo, Portoviejo, Ibarra,
Riobamba, Esmeraldas); el campo entra en alta y edición y sale en feed, `/buscar`, `mias`
y detalle. **El filtro por ciudad NO entra**: se construye cuando haya publicaciones
suficientes para que filtrar tenga sentido.

*Por qué el catálogo va en código y no en BD:* el repo tiene los dos precedentes. Los
catálogos de la ficha son `Literal`; el de productos vive en BD porque §10.3 lo declara
fuente de verdad de precios — ahí un cambio es decisión comercial, necesita auditoría y
debe ocurrir sin desplegar. La lista de ciudades no cumple ninguna de las tres.

**Tres decisiones de diseño, con su motivo**

1. **No se hizo backfill; la ciudad queda NULL en las 3 publicaciones existentes.** El
   dato del garage era mapeable —el único valor, `'QUITO'`, cae sin ambigüedad en el
   catálogo—, pero **`ciudad_registro` es dónde se MATRICULÓ el auto, no dónde está en
   venta**. Derivar una de otra es una inferencia disfrazada de dato: alguien que compró
   en Quito y vive en Ambato habría aparecido en Quito sin haberlo dicho nunca. Además
   cubría 1 de 3 filas. El formulario prellenará ese valor para que el vendedor lo
   **confirme**, y un humano confirmando es estrictamente mejor que una migración
   afirmando.
2. **Los valores del catálogo van capitalizados** (`"Quito"`, `"Santo Domingo"`), no en
   `snake_case` como `Combustible` o `Transmision`. `PublicacionReferenciada.ciudad` es
   texto libre que el aportante copia tal cual del anuncio original; con un
   `"santo_domingo"` interno, la tarjeta tendría que embellecer una rama y la otra no —
   exactamente las dos ramas que el campo compartido existe para evitar.
3. **La salida se tipa `str | None`, no `CiudadPublicacion`.** El catálogo se impone al
   **escribir** (422 en alta y edición). Si mañana se retira una ciudad de la lista, las
   filas viejas tienen que poder **leerse**: tipar la salida con el `Literal` convertiría
   un GET público en **500** por un cambio de catálogo. Hay una prueba que fija la
   decisión.

**Dos decisiones aplazadas, deliberadamente**

- **La ciudad no es requisito para publicar.** No entró al umbral de activación, así que
  un anuncio sin ciudad llega al feed con `null`. Sumar fricción al alta reduce oferta, y
  la oferta es lo que menos sobra hoy. Se revisa cuando haya volumen.
- **Las referencias externas siguen con ciudad de texto libre**, sin catálogo. Una
  referencia puede decir `"tulcán"` y una interna no. La asimetría no molesta hasta que
  exista el filtro por ciudad; recién ahí habrá que decidir si se normalizan o si el
  filtro simplemente no las alcanza (son "datos no verificados" por definición).

**Verificación** (ejecutada de forma independiente al reporte del agente): `import main`
→ **68 rutas** (sin cambio) · `alembic heads` → **`0023`, cabeza única**, cadena
`0022→0023` con `downgrade` · **40 tests OK** (26 previos + 14 nuevos) · SQL offline en
ambos sentidos (`ADD COLUMN ciudad VARCHAR(80)` / `DROP COLUMN`) sin conectar a ninguna
BD · **Neon intacta**: `alembic_version` = `0022` y la columna no existe.

**Pendientes**
- **Marcos: `alembic upgrade head`** (0023) contra Neon.
- **Frontend**: selector de ciudad en el wizard, prellenado desde `ciudad_registro` del
  vehículo del garage (el backend ya lo entrega en `VehiculoSalida`; no hizo falta
  agregarle nada), y mostrar la ciudad en la tarjeta.
- Menor: `ciudad: null` en el PATCH significa "no la toques", no "bórrala" — el endpoint
  usa `is not None` igual que `titulo`, `descripcion` y `precio_usd`. El vendedor puede
  corregir Quito→Manta pero no volver a "sin ciudad". Si hace falta, conviene cambiarlo
  para todo el schema a la vez, no solo para este campo.

---

## 2026-08-06 — Publicar deja de disparar scraping de la placa

**Repos:** frontend (el cambio) y backend (solo `AGENTS.md` y esta bitácora).

**Qué se quitó.** El wizard de publicación disparaba `GET /consultar/{placa}` en
*fire & forget* al crear el anuncio (M2.6, "enriquecimiento oficial automático"), para
dejar la caché caliente y que el detalle mostrara datos oficiales sin espera. Se eliminó
esa llamada y, con ella, `consultarPlaca()` de `lib/api.ts`, que se quedaba sin ningún
llamador en todo `src/`.

**El motivo NO es §1.0.1, y conviene que quede escrito bien.** §1.0.1 exige que un fallo
de consulta no bloquee el flujo del market, y **eso ya se cumplía**: era
`void consultarPlaca(...).catch(() => {})`, sin `await`, sin spinner y con los errores
tragados, así que una fuente caída jamás impidió publicar. El motivo real es que
**`GET /consultar/{placa}` dispara scraping**: Playwright contra ANT más encolado de
AMT/EPMTSD. Cada publicación generaba trabajo contra las fuentes oficiales. Es la misma
familia que la deuda de M2.6/M2.7 —el detalle público scrapeando en *cache miss*— vista
desde el lado del vendedor, y choca igual con el skill `scraping-respetuoso`.

**Efecto que hay que asumir a conciencia.** Los anuncios nuevos **ya no traen datos
oficiales precargados**. `DatosOficialesMini` lee con `solo_cache=true`, así que ante una
caché vacía muestra *"Aún no hay datos oficiales disponibles para esta placa"* y ofrece
"Ver detalle completo →". Es decir: los datos oficiales pasan a depender de que **un
visitante los pida**. No se rompe nada y el camino de recuperación existe, pero la
propuesta de valor del producto (§1) es la ficha del vendedor **junto a** datos oficiales,
y ahora esa segunda mitad ya no aparece sola. **Si se quiere recuperar, la salida es
precalentar la caché desde el worker o un proceso propio — no volver a acoplar una acción
del market al pipeline de scraping.**

**Invariante registrado en AGENTS §1.0.1.** Con esto queda completo: *ningún flujo del
marketplace dispara scraping*. El detalle lee con `solo_cache`; las llamadas que sí
consultan viven solo en `/consultar/[placa]` y `PerfilVehiculo`, donde el usuario lo pidió
explícitamente. Se anotó con la tabla de consumidores y con qué buscar al revisar un diff,
porque los dos incidentes fueron **silenciosos**: cumplían "no bloquea" y aun así
generaban carga desde páginas públicas e indexables.

**Verificación.** Diff de un solo archivo funcional; se comprobó contra `HEAD` que **no se
tocaron** los CTA del detalle, `DatosOficialesMini`, `Header`, `MenuCuenta` ni
`BarraNavegacionMovil`. `tsc --noEmit` limpio, lint 4 preexistentes, sin llamadores
huérfanos (se quitó también el import de `ConsultaPlacaRespuesta`, que quedaba sin uso).
Revisión: **APTO**, sin bloqueantes; los tres hallazgos fueron observaciones y los tres
se aplicaron.

---

## 2026-08-05 — Un solo planificador: el eje M pasa a historia y la serie TASK se unifica

**Solo documentación.** Ningún archivo de `src/`, `alembic/` ni `tests/`.

**El problema.** Había **dos ejes planificando a la vez**. El plan tenía M0→M5 y el orden
de trabajo tenía TASK-001→007, y describían el mismo trabajo con nombres distintos: el
contacto comprador-vendedor era **a la vez "M5" y "TASK-001"**. Consecuencia visible: el
plan seguía listando M5 como etapa futura cuando su backend ya estaba implementado,
auditado y pusheado. Además circulaban **dos series TASK incompatibles**: en el orden de
trabajo TASK-002 era "frontend del contacto"; en el backlog, "coherencia del bundle".

**Qué se decidió**
- **`ORDEN-DE-TRABAJO.md` es el único planificador**; la unidad de trabajo es la spec
  `TASK-NNN` de `docs/specs/`.
- **`plan_market_autos.md` pasa a historia de lo construido.** Se conserva entero —es buen
  registro de decisiones por etapa— pero deja de decir qué viene. Su checklist §5 y su
  ritual §3 siguen vigentes: son proceso, no planificación.
- **M5** queda marcada con el **backend hecho** y apunta a TASK-001; su frontend es
  TASK-011. **M4 (patios)** se marca **etapa 2** por AGENTS §1.0.2, y se anota que el orden
  original del plan (M4 antes de M5) ya no aplica.

**Renumeración TASK.** Se conserva la serie del backlog (003–009 ya coincidían, y
008/009/010 solo existían ahí) y el **frontend del contacto pasa de TASK-002 a TASK-011**.
Queda constancia en `ORDEN-DE-TRABAJO.md` §2 para que nadie busque el número viejo.

**Estado registrado con evidencia** (P0 proveedor `mock` cortado y verificado en el
catálogo público · P1 frontend `b953710..98372e4` pusheado y verificado en el build
desplegado · P2 `e9c969e` · TASK-001 `99e1fbf`, auditada por Codex y con migraciones
probadas contra Postgres real, pendiente solo el merge), más el orden de lo que sigue y el
backlog por riesgo.

**Corrección menor:** el archivo decía "siete compuertas abiertas" y enumeraba **ocho**
(M2, M2.5, M2.6, M2.7, M2.8, M2.10, MC1, MC2). Se buscó en todo el repo: el error **no se
había propagado** a ningún otro documento.

**Nota:** se evaluó crear un `ESTADO-CICLO.md` nuevo y se descartó — habría sido un tercer
documento de estado compitiendo con los dos que ya existían, que es justo el problema que
esta entrada resuelve.

---

## 2026-08-05 — Frontend pusheado: la deuda de M2.6/M2.7 queda cerrada en producción

**Repo:** `consulta-placas-web`. Se pushearon los **3 commits** que estaban solo en local
desde el 20-25 de julio: `ad46440` (M2.10), `a4cb76d` (MC2) y `98372e4` (fix de
`solo_cache`). `origin/main` quedó sincronizado con el local.

**Lo importante no es el push, es lo que destraba.** La entrada del 2026-07-25 declaraba
cerrada la deuda de M2.6/M2.7 —el detalle público de un anuncio disparaba scraping en
*cache miss* sobre una página indexable— pero el arreglo vivía **solo en local**. Estuvo
documentado como resuelto y sin resolver durante once días. Ahora sí está en producción.

**Verificado sobre el sitio desplegado, no sobre el push.** Un push no es un deploy, así
que se descargaron los bundles de `/marketplace` en Vercel y se buscaron marcadores del
código nuevo: **`solo_cache` está presente**, junto con `Cargar más`, `combustible`,
`transmision`, `precio_min` y `anio_max` (MC2). Como `solo_cache` solo existe en `98372e4`,
que es el HEAD de `origin/main`, los otros dos commits son ancestros suyos y están
necesariamente incluidos en ese build. (`"Vive en tu garage"`, de M2.10, no aparece en
esos bundles porque vive en el chunk del detalle, no en el de `/marketplace`.)

**Consecuencia:** de las cinco discrepancias que abrieron este ciclo, esta era la única con
impacto sobre usuarios reales. Queda cerrada **y comprobada**, que no es lo mismo.

---

## 2026-08-05 — Ciclo real de migraciones contra BD desechable (desbloquea TASK-001)

**Rama:** `feat/TASK-001-contacto-vendedor` · **Solo verificación**: ningún archivo de
`src/` ni `alembic/` cambió. Cierra el criterio de aceptación de TASK-001 que había
quedado **BLOCKED por falta de una BD desechable**.

**Entorno.** Contenedor `pg-dev` (PostgreSQL 16.14) en `localhost:5433`, con tres bases
creadas al efecto: `task001_head`, `task001_backfill` y `task001_ref`. **Neon no se tocó
en ningún momento**: cada invocación llevó `DATABASE_URL` sobrescrita en el entorno y se
verificó la URL resuelta antes de la primera migración. Control al cerrar: Neon sigue en
`0020` y sin las tablas nuevas.

**Lo que se ejerció, y su resultado**
- **Cadena completa desde cero:** las **22 migraciones** corren de `0001` a `0022` sin un
  solo error. Es la primera vez que la cadena entera se aplica contra una base real; hasta
  hoy solo se había renderizado SQL offline.
- **Esquema:** `vendedores` y `contactos_revelados` con las columnas exactas de la spec;
  `uq_vendedores_usuario_id`; el `CheckConstraint` de exactamente-un-FK; FK a `usuarios`
  con `CASCADE` y las dos a `vendedores` con `SET NULL`.
- **Backfill con el escenario acordado** (2 usuarios: uno con 2 publicaciones internas,
  otro con 1 referencia externa; cargados en `0020` **antes** de aplicar `0021`). Las cinco
  aserciones pasan: se creó **un solo** vendedor —el del usuario con internas—, el
  **aportante no recibió perfil**, las 2 internas quedaron con `vendedor_id`, la
  **referencia quedó en NULL** y **`nombre_publico` quedó NULL**. La reentrancia que
  promete el docstring también se comprobó: correr el backfill por segunda vez no duplica.
- **Downgrade sin residuos:** tras `0022→0021→0020`, se comparó el catálogo completo contra
  una base migrada limpia a `0020`. **Idénticos en los cinco conjuntos**: 18 tablas, 157
  columnas, 39 constraints, 53 índices y 17 secuencias, sin sobrantes ni faltantes.
- **Re-upgrade limpio:** volver a `head` después del downgrade corre sin error, así que el
  downgrade no deja la base en un estado no re-migrable.

**El hueco de restricciones de BD quedó PARCIALMENTE CUBIERTO.** No basta con que las
restricciones existan: se comprobó que **muerden**. Un segundo vendedor para la misma
cuenta da `UniqueViolation`; `contactos_revelados` rechaza tanto la fila sin ninguna
publicación como la que trae las dos, y acepta ambas formas válidas; un `vendedor_id`
inexistente da `ForeignKeyViolation`; borrar la publicación arrastra sus contactos por
`CASCADE`; borrar el vendedor deja `vendedor_id` en NULL sin llevarse la publicación.

Consecuencia para los tests: **el test de carrera que estaba simulado queda validado** —
la UK sí produce el `IntegrityError` que `obtener_o_crear_vendedor` captura, así que el
`Mock` no estaba fingiendo un comportamiento inexistente.

**TASK-009 sigue vigente**, con el alcance ahora acotado a lo que de verdad falta: los
**tests de parser de los scrapers** contra fixtures HTML (§14.5 y §16.2), que siguen sin
existir — `tests/fixtures/` no está creado y cada scraper es un parser sin red de
seguridad ante un cambio de DOM. La decisión sobre el runner (pytest vs `unittest`) sigue
ahí también.

**Hallazgo de entorno que originó TASK-010.** `alembic/env.py` toma la URL de
`src/core/database.py`, que hace `load_dotenv()` — y eso lee **`.env`**, que apunta a
**Neon de producción**. `.env.local` no lo lee nadie. Hoy el default local ES producción y
lo único que lo evita es exportar `DATABASE_URL` a mano en cada comando. Un olvido corre
migraciones contra Neon. Abierta **[TASK-010](specs/TASK-010-entorno-local.md)** (ruteo
Codex) para invertirlo. Se agregó `.env.local` al `.gitignore`, que solo tenía `.env`
exacto.

**Limpieza:** se eliminó `zip/` de la raíz (carpeta de traspaso con copias ya versionadas
en `docs/`, una de ellas una versión **vieja** de la spec de TASK-001) y se agregó al
`.gitignore` para que no vuelva a entrar.

---

## 2026-08-04 — TASK-001: capa Vendedor + contacto comprador-vendedor (backend)

**Rama:** `feat/TASK-001-contacto-vendedor` · **Ejecutó:** agente `dev-backend` ·
**Revisa:** Codex (§16.1 — revisa quien no ejecutó). **Sin commitear**: el diff queda en
el árbol para la auditoría cruzada.

**Qué se hizo.** Cierra el circuito del marketplace: hasta hoy un comprador veía el
anuncio y no tenía cómo llegar al vendedor.
- **`Vendedor`** (migración `0021`): `usuario_id` FK CASCADE **UNIQUE** (la UK impone el
  1:1 de etapa 1 y se levanta en etapa 2), `tipo` (`particular`|`patio`), `nombre_publico`,
  `telefono` E.164 sin `+`, `telefono_verificado` reservado. `vendedor_id` agregado a
  `publicaciones_internas` y `publicaciones_referenciadas`; **`usuario_id` se conserva** en
  ambas (en referenciadas documenta al aportante, que no siempre es el vendedor).
  Backfill en SQL plano y reentrante (`ON CONFLICT DO NOTHING` + `WHERE vendedor_id IS NULL`).
- **`ContactoRevelado`** (migración `0022`): métrica anónima de cada revelación. Sin IP,
  sin user-agent, sin usuario (§9: es métrica de producto, no vigilancia). CheckConstraint
  de exactamente un FK presente.
- **Endpoints:** `GET`/`PATCH /marketplace/vendedor/mi-perfil` (dueño) en un router nuevo
  `routers/vendedor.py`, y `POST /marketplace/publicaciones/{id}/contacto` **público y sin
  cobro** (§1.0.3: el contacto es libre), que devuelve teléfono, nombre público y
  `whatsapp_url`. Teléfono inválido → 422 · vendedor sin teléfono → 409 · publicación
  inexistente o no pública → 404 indistinto.
- **Privacidad:** el teléfono **no aparece** en feed, `/buscar` ni detalle. Solo lo entrega
  el endpoint de contacto, bajo acción explícita del comprador. La acción explícita es la
  barrera contra cosecha automatizada, y de paso produce la métrica.

**Verificación ejecutada** (la corrí yo, independiente del reporte del agente):
`import main` → **68 rutas** (eran 65) · las 2 rutas nuevas presentes en
`app.openapi()["paths"]` · `alembic heads` → **`0022`, cabeza única**, cadena
`0020→0021→0022` consecutiva · ambas migraciones con `upgrade` **y** `downgrade` ·
`unittest discover -s tests` → **19 tests OK** (15 nuevos + los 4 previos, sin regresión) ·
`telefono` ausente de todo schema de listado/detalle, comprobado recorriendo el OpenAPI real
con `$ref` resueltos · orden de rutas verificado sobre las registradas.

**⚠️ DOS LÍMITES DELIBERADOS — para el auditor de T4: esto NO es una omisión del agente.**
> **Actualización 2026-08-05:** el límite 1 (ciclo `upgrade`/`downgrade`) **ya no aplica**:
> se ejerció contra una BD desechable y pasó completo, incluidas las restricciones reales.
> Ver la entrada del 2026-08-05, arriba. El límite 2 (`unittest` en vez de pytest) sigue
> vigente y se decide en TASK-009.
1. **El ciclo `alembic upgrade` / `downgrade` real queda BLOCKED.** `DATABASE_URL` apunta a
   **Neon de producción con datos reales** y aplicar migraciones es tarea de Marcos (modelo
   de trabajo de `plan_market_autos.md`). En su lugar se verificó **offline** con
   `alembic upgrade 0020:0021 --sql`, `0021:0022 --sql` y los `downgrade --sql`, confirmando
   simetría, más el contraste del DDL de `Base.metadata` contra el de las migraciones. Se
   desbloquea cuando exista una **BD desechable**. Confirmado que producción quedó intacta:
   `alembic_version` sigue en `0020` y ni `vendedores` ni `contactos_revelados` existen.
2. **El test es `unittest`, no `pytest`.** El criterio de aceptación de la spec pedía
   `pytest tests/test_contacto_vendedor.py -q`, pero **pytest no está instalado ni en
   `requirements.txt`**, y agregarlo sería una dependencia nueva (§4). Se siguió el estilo
   del único test previo (`tests/test_consulta_solo_cache.py`: `unittest` + `Mock`, sin BD —
   necesario además porque los modelos usan JSONB y SQLite no sirve). Corre con
   `python -m unittest tests.test_contacto_vendedor -v`. La decisión sobre pytest es **TASK-009**.

**Auditoría cruzada y correcciones aplicadas (misma sesión).** La revisión encontró un
**bloqueante** y cuatro puntos menores; los cinco se corrigieron con el alcance ampliado a
`publicaciones.py`, `referencias.py`, `vendedor.py` y `0021_vendedor.py`:

1. **La invariante de `vendedor_id` nacía rota (bloqueante).** `crear_publicacion` no
   poblaba el vínculo, así que toda publicación creada tras la `0021` habría quedado en
   NULL para siempre: un backfill corre una vez y el dato se degradaba con cada anuncio.
   Ahora el alta llama a `obtener_o_crear_vendedor` y asigna `vendedor_id`.
2. **Fallback eliminado.** `_vendedor_de` resolvía por `usuario_id` cuando el vínculo
   faltaba. Se quitó por completo (no se cambió a `.first()`: eso dejaba una segunda vía
   que en etapa 2 devuelve un vendedor **arbitrario en silencio**, que es peor que fallar).
   Un `vendedor_id` NULL sale como 409 honesto. De paso desaparece el
   `MultipleResultsFound` → 500 que la etapa 2 habría destapado.
3. **Upsert a prueba de carreras.** `obtener_o_crear_vendedor` captura `IntegrityError`
   sobre `uq_vendedores_usuario_id`, hace `rollback` y relee el perfil que ganó. Si la
   violación no fue esa UK, se relanza en vez de tragarla. Nunca 500.
4. **Referencias: `vendedor_id` queda NULL a propósito.** Se quitó del backfill de la
   `0021` el UPDATE sobre `publicaciones_referenciadas` y el INSERT de vendedores ya no
   incluye a los aportantes. En una referencia, `usuario_id` es **quien copió un anuncio
   ajeno**, no quien vende: derivar un `Vendedor` de ahí publicaría su nombre y su teléfono
   por un auto que no vende. Documentado en el docstring de la migración y en el alta de
   `referencias.py`, para que nadie lo "arregle" después.
5. **Opt-in explícito del nombre (compuerta M5).** Un `PATCH` que solo mandaba teléfono
   heredaba el nombre de la CUENTA y lo publicaba sin que nadie lo eligiera. Ahora cargar
   teléfono exige `nombre_publico` explícito → **422**. La regla se evalúa sobre el estado
   resultante, así que tampoco se puede borrar el nombre dejando el teléfono publicado.
   El perfil que crea el alta nace con `nombre_publico` NULL por el mismo motivo.

**Spec actualizada:** se fijó que `GET /mi-perfil` devuelve **404 cuando no hay perfil** y
que **T5 debe tratarlo como estado de onboarding, no como fallo** (es la única ruta donde
404 no significa "no existe o no es tuyo"); y se corrigió la contradicción sobre
referencias, que a la vez decía que `usuario_id` es el aportante y mandaba backfillear
`vendedor_id` desde él.

**Verificación tras las correcciones:** `import main` → **68 rutas** · `alembic heads` →
`0022` · **23 tests OK** (eran 19; +4 de las reglas nuevas) · SQL offline de la `0021`
confirma **cero** sentencias sobre `publicaciones_referenciadas` en el backfill ·
`telefono` sigue ausente de feed, `/buscar`, detalle y `mias`, comprobado sobre el OpenAPI
con `$ref` resueltos · orden de rutas intacto · Neon sigue en `0020`, sin tablas nuevas.

**⚠️ Limitación de la suite — insumo para TASK-009.** Los tests aíslan la sesión con
`Mock`, así que **no ejercen ninguna restricción real de la base**: ni la UK
`uq_vendedores_usuario_id`, ni el `CheckConstraint` de `contactos_revelados`, ni las FK,
ni el `ON DELETE`. El test de carrera **simula** el `IntegrityError`; no demuestra que la
UK lo produzca. El backfill de la `0021` no se ejerce en absoluto. Lo que sí cubren es la
lógica de router y schema. Cerrar esto pide una **BD desechable** (contenedor Postgres o
base de pruebas en Neon) y decidir el runner en TASK-009 — es el mismo bloqueo que dejó
sin correr el ciclo `upgrade`/`downgrade`.

**Pendientes / deuda anotada**
- `ContactoRevelado.publicacion_referenciada_id` queda **sin escritor** (la spec solo pidió
  el endpoint de publicaciones internas). No es código muerto: es la etapa siguiente.
- **TAREA DE SEGUIMIENTO — mover el helper a `services/vendedor.py`.**
  `publicaciones.py` importa `obtener_o_crear_vendedor` desde `routers/vendedor.py`, o sea
  un router importando a otro router. Funciona y no hay ciclo, pero su lugar natural es un
  servicio del módulo, junto a `services/cloudinary.py`. **Se deja donde está a propósito:**
  mover un helper es un refactor de estructura y no pertenece a esta tarea, que ya se
  amplió tres veces. Hacerlo aparte, con su propio diff revisable.

**Cierre de los dos residuos del opt-in (ajuste final, alcance ampliado a `schemas.py`)**
- El docstring de `VendedorActualizar` decía que `nombre_publico: null` "restaura el nombre
  de la cuenta". Corregido: ahora lo **borra**, y el docstring explica por qué el nombre no
  se hereda.
- El backfill de la `0021` ya **no copia** `usuarios.nombre` a `nombre_publico`: lo deja
  NULL, igual que el teléfono. El criterio: **un backfill no puede dejar filas en un estado
  que la regla vigente prohíbe crear por la API.** Copiar el nombre de la cuenta habría
  dejado 3 vendedores con un nombre que su dueño nunca eligió, y al cargar el teléfono ese
  nombre habría pasado sin opt-in fresco. Con NULL, el primer PATCH que publique un número
  obliga a elegirlo. Se actualizó también la fila de `nombre_publico` en la tabla de modelo
  de la spec, que seguía diciendo "por defecto el nombre del usuario".
- El detalle público no expone si hay teléfono cargado, así que el frontend no puede decidir
  si mostrar el botón sin arriesgar un 409. Un booleano `tiene_contacto` lo resolvería sin
  exponer el número; no se agregó por estar fuera de lo pedido. Decisión de producto.
- **Marcos debe correr `alembic upgrade head` (0021 + 0022)** contra Neon tras la auditoría.
- La entrada de esta bitácora está fuera del alcance de archivos de la spec; se agrega por
  el ritual §3 y por pedido explícito, y es el único archivo tocado fuera de esa lista.

---

## 2026-08-04 — Reorientación de AGENTS.md §1 al marketplace + corrección de la spec TASK-001

**Repo:** solo backend, **solo documentación** (ningún archivo de `src/` ni `alembic/`).
Abre el ciclo marketplace definido en `docs/ORDEN-DE-TRABAJO.md`. **Commit en `main`, sin push.**

**Qué se hizo**
- **`AGENTS.md` §1 reemplazada.** La decisión M2.6 (2026-07-19) giró el producto a
  marketplace y §1 se quedó describiendo el producto anterior ("consulta por placa,
  cuatro pilares"). Los tres agentes leen este archivo como fuente única, así que
  decidían con una definición obsoleta. Nueva §1 con §1.0.1 (jerarquía: el marketplace
  es el producto, la consulta es complemento y **su fallo nunca bloquea el flujo**),
  §1.0.2 (alcance del ciclo, con tabla de lo que queda fuera y su criterio de
  reactivación), §1.0.3 (**monetización suspendida, no eliminada**: precios en 0, `mock`
  prohibido en producción) y §1.0.4 (etapas 1 particulares / 2 patios, con la capa
  `Vendedor` incorporada desde ya para no pagar una migración cara después).
  **§1.1 y el resto de la numeración no se tocaron.**
- **`.claude/agents/revisor-calidad.md`**: el checklist suma que un fallo de consulta
  externa nunca bloquea publicar, buscar, ver un anuncio ni contactar (§1.0.1).
- **`docs/specs/TASK-001-contacto-vendedor.md` corregida antes de ejecutarla.** Su
  "Alcance de archivos" permitía tocar `src/modules/marketplace/router.py`, que **no
  existe**: el módulo tiene varios grupos y sus routers están en `routers/` (cuatro
  archivos), que es lo que manda §5. Se disparó la condición de BLOCKED de la propia
  spec ("si los routers están repartidos de otra forma, reportar antes de crear
  archivos"). Alcance corregido a `routers/vendedor.py` (nuevo, prefijo
  `/marketplace/vendedor`), `routers/publicaciones.py` (solo el endpoint de contacto) y
  una línea de `include_router` en `main.py`. **La spec estaba mal escrita, no el repo.**

**Verificación — estado real, no declarado**
Contra el sistema, no contra la documentación (es la causa común de las discrepancias
que motivaron este ciclo: la bitácora venía registrando intención):
- **Neon está en `0020`**, igual que el head del código. Las cinco entradas previas que
  arrastraban "⚠️ Marcos debe correr `alembic upgrade head` (0019 + 0020)" describían un
  pendiente **ya resuelto**.
- **Backend en Render al día** (expone `solo_cache` en el perfil). Arranque en frío ~19 s.
- **P0 confirmado en producción:** `identificadores_tecnicos`, `titular_validado` y
  `reporte_compra_segura` responden `disponible: false`. El proveedor `mock` —que
  fabricaba VIN y titular y aun así cobraba— está efectivamente cortado.
- **Frontend con 3 commits sin pushear** (M2.10, MC2 y el fix de `solo_cache`), verificado
  con `git fetch`. Por eso la deuda de M2.6/M2.7 que la entrada del 2026-07-25 declara
  cerrada **sigue viva para los usuarios**: el fix existe solo en local. Es la tarea T1.
  > **RESUELTO el 2026-08-05:** los 3 commits se pushearon y el build desplegado se
  > verificó marcador a marcador. La deuda está cerrada en producción. Ver la entrada
  > "Frontend pusheado", arriba.
- **Pre-flight del backfill de TASK-001 (limpio):** 0 publicaciones con `usuario_id`
  huérfano en `publicaciones_internas` y `publicaciones_referenciadas`; 3 vendedores a
  crear; 2 internas y 3 referenciadas; ningún usuario con `nombre` vacío, así que el
  default de `nombre_publico` aplica a todos.

**Contradicciones detectadas dentro de AGENTS.md, reportadas y NO corregidas**
La reorientación de §1 dejó dos choques con secciones que no entraban en el alcance:
- **§3 "Próximas fases"** sigue prometiendo Fase 6 = app móvil + gateway de pago
  (PlaceToPay/MercadoPago), justo lo que §1.0.2 acaba de poner **fuera de alcance**.
- **§10.3** lista el catálogo con precios vivos (3/5/8/10/12/40/100 tokens) mientras
  §1.0.3 declara que **todos los precios están en 0**. Hoy el código le da la razón a
  §10.3. Es TASK-003 del backlog.
- Menores: §1.1 rotula los módulos como "Pilar 1+2/3/4" y la `description` de
  `dev-backend.md` cita "los pilares existentes" — pilares que §1 ya no define. Y §1.0.4
  introduce el vocabulario "Etapa 1/2" mientras §3 sigue en "Fase 1…6".

**Pendientes**
- **T1: pushear el frontend** (3 commits). Hasta entonces la deuda de M2.6/M2.7 sigue
  abierta en producción pese a estar documentada como cerrada.
- **T3: ejecutar TASK-001** en `feat/TASK-001-contacto-vendedor`, con auditoría cruzada
  de Codex (§16.1) antes de commitear.
- Resolver las dos contradicciones de arriba (§3 y §10.3) para que la fuente de verdad
  deje de contradecirse.
- `zip/` en la raíz quedó con copias de los tres documentos ya ubicados en `docs/`; no
  está en `.gitignore`.

---

## 2026-07-25 — Market: detalle público solo lee datos oficiales en caché

**Repos:** ambos. Cierre de la deuda de M2.6/M2.7: una visita al detalle público de
un anuncio ya no inicia scraping ni encola trabajo para una placa fría.

**Backend:** `GET /consultar/{placa}/perfil` acepta `solo_cache=true` (retrocompatible;
sin el parámetro conserva el flujo normal). En este modo lee únicamente resultados vigentes
de `consultas`; en un cache miss devuelve el nuevo estado consolidado `no_consultada`.
No llama Playwright, servicios externos ni `encolar_scraping`.

**Frontend:** `DatosOficialesMini` del detalle de marketplace usa `solo_cache=true`.
Una placa sin datos muestra “Aún no hay datos oficiales disponibles” y enlaza a la consulta
completa; solo muestra “Consultando” cuando una consulta normal realmente dejó una fuente
en `en_proceso`. Se actualizó el tipo espejo `EstadoFuenteConsolidada`.

**Verificación:** 4 pruebas unitarias backend (placa fría, ANT cacheado, selección
cache-only y flujo normal) OK; `import main` = 65 rutas; `alembic heads` = `0020`;
`npx tsc --noEmit --incremental false` OK; `git diff --check` OK. Revisión
`revisor-calidad`: **APTO PARA COMMIT**, sin bloqueantes.

**Pendiente:** prueba manual contra una placa fría y otra precargada, después de aplicar
las migraciones `0019` y `0020` en Neon.

## 2026-07-21 — Market MC2: búsqueda y filtros del feed (carril comprador)

**Repos:** ambos. Segunda etapa del carril C. Revisado por **revisor-calidad** (**APTO**,
sin bloqueantes). **Commit sin push.**

**Decisión de arquitectura (Marcos): endpoint nuevo, no reemplazar el feed.** El feed de 3
cubos (`GET /marketplace/feed`) alimenta la portada curada MC1 y **queda intacto**. La
búsqueda vive en un endpoint NUEVO de **lista plana** — un feed filtrable y paginado por
cursor quiere ser una lista ordenada, no tres cubos (en la página 2 ya no puedes "volver a
poner premium arriba"). Cada endpoint con un trabajo claro; MC1 no se re-verifica. La
alternativa (reescribir el feed y re-derivar los bloques de MC1) se descartó por riesgo de
regresión sobre lo recién hecho.

**Backend — `GET /marketplace/buscar`** (público, sin auth):
- Filtros: `q` (título/marca/modelo, ILIKE), `tipo`/`combustible`/`transmision` (validados
  contra los `Literal` de la ficha → 422 gratis), `precio_min/max`, `anio_min/max`. Los de
  ficha salen del JSONB (`motor_suspension->>'combustible'` etc.); el año de la interna sale
  del vehículo vinculado (interna sin vehículo se excluye si hay filtro de año).
- **Paginación por cursor keyset** (no offset — el reel de la app MC3 lo reutiliza tal cual).
  Orden `destacado DESC · creado_en DESC · fuente ASC (internas=0, referenciadas=1) · id
  DESC`. Cursor opaco (base64 de `{d,c,f,i}`); corrupto → **400**. La condición keyset se
  arma **por niveles** (no row-value ingenuo) porque `fuente` ordena ASC mientras el resto
  DESC — una comparación de tupla con direcciones mixtas se saltaría/repetiría filas. Detalle
  SQLAlchemy: `destacado` es Boolean y no admite `<`, se compara con `cast(..., Integer)`.
- **Referencias externas**: participan como `destacado=false` (se intercalan con las light
  por fecha), pero con **cualquier filtro de ficha activo se omiten por completo** (no tienen
  ficha, no pueden cumplirlo; el join a `FichaPublicacion` es INNER).
- **Dos queries, sin N+1**: keyset sobre una proyección liviana (4 columnas) para obtener los
  `(fuente,id)` de la página en orden, luego hidratación en lote con `selectinload`
  (vehículo+mantenimientos+ficha+fotos). El keyset filtra en BD, no en Python.
- Privacidad: reusa `PublicacionInternaSalida`/`PublicacionReferenciadaSalida` (sin VIN, sin
  nombre del dueño, sin `vehiculo_id`); solo internas `activa` y referenciadas
  `activa+aprobada`. **Sin migración** (`alembic heads` = `0020`); índices GIN/btree anotados
  como deuda para cuando haya volumen (decenas de filas hoy).

**Frontend:** `/marketplace` sin filtros = bloques curados MC1 intactos; con filtro o
búsqueda = grilla plana server-side + **"Cargar más autos"** (cursor). **Estado de filtros
en la URL** (`?q=&tipo=&combustible=&transmision=&precio_min=&precio_max=&anio_min=&anio_max=`,
compartible); `leerFiltros` valida contra los catálogos, así un `?tipo=zzz` manipulado se
descarta sin pegarle al backend. Los chips de marca y las bandas de presupuesto de MC1 ahora
alimentan los filtros reales; se **eliminó el filtro de texto en cliente**. Nuevo
`src/lib/busqueda.ts`. Para no repintar stock viejo sin `setState` síncrono en el efecto
(lint), los resultados se atan a `busqueda.clave`: si no coincide con el filtro actual, la
grilla dice "Buscando…". ♡ favorito y badge de baja conservados en las tarjetas de resultado.

**Verificación:** `import main` → 65 rutas · `alembic heads` = `0020` · `tsc --noEmit`
limpio · lint **4 preexistentes, 0 nuevos** · `build` OK. La **simulación del cursor** (7
publicaciones mezcladas, `limite=2`, 4 páginas sin repetir ni saltar, `siguiente_cursor` →
null) la corrió el agente; el revisor **verificó a mano el contraejemplo interna-vs-
referenciada con fecha igual** (la fila-cursor siempre queda excluida en los 4 niveles).

**Pendientes**
- Correr el **guión MC2** ([guion_prueba_market.md](guion_prueba_market.md) §3-octies,
  secciones Y–Z).
- **MC1.1** (feedback de Marcos, ya en el plan) sigue **sin implementar**: reordenar el feed
  en secciones autocontenidas y reescribir la narrativa de las referencias externas ("autos
  de otros markets" + disclaimer según completitud de la ficha del referido).
- Deuda arrastrada: `alembic upgrade head` (0019 + 0020) contra Neon; plegado de acentos en
  `q`; índices cuando haya volumen. Push acumulado en ambos repos.

---

## 2026-07-20 — Market M2.10: aclarar Garage vs Publicar + editar referencias

**Repo:** solo frontend (`consulta-placas-web`); **backend intacto** (el PATCH de
referencias ya existía desde M2.8). Feedback de Marcos. Revisado por **revisor-calidad**
(**APTO**, sin bloqueantes). **Commit sin push.**

**El problema (tarea 1):** el garage y publicar se sentían idénticos porque el wizard
recapturaba placa/marca/modelo que el garage ya tiene. **No se fusionaron** —garage es
historial **privado**, la publicación es un anuncio **público** de venta— sino que se
**conectaron y diferenciaron**:
- `mi-garage`: "Publicar este auto" ahora pasa **marca/modelo/año** además de placa y
  `vehiculo_id` (`?placa=…&vehiculo=…&marca=…&modelo=…&anio=…`). Un vehículo que ya tiene
  publicación vinculada muestra **"Ya publicado →"** (borrador → mis-publicaciones;
  activa/pausada/vendida → `/marketplace/{id}`), sin perder los CTA de ficha de M2.8. Copy
  breve que explica la diferencia: *"Tu garage es privado (tu historial). Publicar crea un
  anuncio público de venta."*
- Wizard paso 1: cuando llega prellenado desde el garage, **no vuelve a pedir** esos datos
  —bloque de confirmación "Publicando desde tu garage → {marca} {modelo} {año}" con título
  propuesto editable y un "Ajustar o publicar otra placa" que devuelve al modo manual.
  marca/modelo/año son **solo contexto**: no son campos de la publicación interna, así que
  **no se envían** al POST (el flujo por placa suelta queda intacto).
- Detalle `/marketplace/{id}`: chip **"Vive en tu garage"** — **solo para el dueño**.

**Privacidad del chip.** `vehiculo_id` **no** viaja en ninguna salida pública
(`PublicacionInternaSalida`/`PublicacionDetalleSalida` no lo exponen; solo está en el input
`...Crear`). El chip se infiere en el cliente cruzando la **placa** contra el garage propio
y solo si `esMia`; el fetch del garage **falla cerrado** (si no carga, no hay chip) y no se
dispara para anónimos (retorno temprano sin sesión). Un comprador nunca ve el chip ni el id.

**Editar referencias externas (tarea 2).** El backend ya lo soportaba
(`PATCH /marketplace/referencias/{id}`, devuelve a `pendiente` al cambiar contenido). Faltaba
la UI: en `mis-referencias`, botón **"Editar"** → formulario inline con los campos ricos
(marca, modelo, año, precio, ciudad, kilometraje, descripción) + uploader de fotos, todo
prellenado, con aviso **"Al editar, tu referencia vuelve a revisión."** El uploader
`FotosReferencia` se **extrajo** de la página de referenciar a un componente reutilizable
(crear y editar comparten UI). Se agregaron `actualizarReferencia()` en `lib/api.ts` y el
tipo `ReferenciaActualizar` (mirror del schema). Dejar un campo en blanco **conserva** el
dato previo (`exclude_unset`); `fotos` es la excepción (viaja completa, así que se puede
vaciar).

**Verificación:** `tsc --noEmit` limpio · lint **4 preexistentes, 0 nuevos** · `build` OK ·
backend `git status` sin cambios de código. Revisor **APTO**; su único hallazgo (un
comentario que decía "null" cuando el código manda `undefined`) se corrigió.

**Pendientes**
- Correr el **guión M2.10** ([guion_prueba_market.md](guion_prueba_market.md) §3-septies,
  secciones V–X).
- Siguen pendientes de M2.8/MC1: `alembic upgrade head` (0019 + 0020) contra Neon.

---

## 2026-07-20 — Market MC1: portada del market para el comprador

**Repos:** ambos (frontend el grueso; backend **una migración mínima**). Primera etapa del
**carril C (comprador)** — hasta aquí todo el market era carril V (vendedor). Diseño en
[producto/experiencia_comprador.md](producto/experiencia_comprador.md) §2. Revisado por
**revisor-calidad** (**APTO**, sin bloqueantes). **Commit sin push.**

**Qué se hizo — `/marketplace` deja de ser un feed plano y pasa a portada curada**
Los 7 bloques del doc §2, móvil primero: buscador protagonista · **Tus favoritos** (arriba
del todo, solo logueado) · Destacados premium en carrusel · **Verificados y transparentes**
(`verificado` o ficha ≥ 80 %) · **Explora por marca** · Recién publicados · **Por
presupuesto** (< $10k · $10-20k · > $20k) · Referencias externas al pie.
**Regla dura respetada: un bloque sin contenido no se renderiza** — nada de encabezados
sobre grillas vacías, incluidas las bandas de presupuesto sin stock.

**♡ favorito con un toque en toda tarjeta.** Reutiliza el módulo `favoritos` existente,
que estaba subutilizado desde la Fase 3. Va sobre la foto, es un `<button>` accesible
(`aria-pressed`) con `preventDefault + stopPropagation` para no disparar el `Link` de la
tarjeta. Optimista con rollback; 409 = éxito idempotente. **Anónimo:** invitación amable
("Guarda este auto para verlo después"), nunca un 401 crudo ni una redirección de golpe.

**Decisiones de diseño**
- **Sin endpoints de agregados.** `GET /marketplace/feed` ya devuelve todas las activas sin
  límite, así que las **marcas con stock** y los conteos se derivan en el cliente. Un
  endpoint habría duplicado la fuente de verdad a cambio de nada. Las marcas **nunca** se
  hardcodean (compuerta MC1): si no hay ningún Kia publicado, no existe el chip "Kia".
- **El buscador filtra en cliente** sobre el feed ya cargado. Los filtros reales con query
  params y paginación por cursor son **MC2**; adelantarlos aquí habría sido trabajo tirado.
- **Favoritos sigue siendo por PLACA, no por `publicacion_id`** (§10.4). El cruce en "Tus
  favoritos" no asume unicidad: si dos publicaciones comparten placa aparecen las dos, y una
  placa favorita sin publicación simplemente no aparece.

**Backend (mínimo, una migración): `0020_favorito_precio`**
`precio_al_guardar` Numeric(12,2) **nullable** en `vehiculos_favoritos`. Es la única pieza
que faltaba para el **badge de baja de precio**: sin persistir el precio al momento de
guardar no hay contra qué comparar. Nullable a propósito y sin backfill — los favoritos
previos y las placas sin publicación no tienen referencia, y un `0` fingido se leería como
"bajó de precio", que es peor que no saber. El badge solo se muestra en **bajada**; una
subida no se anuncia. La comparación la hace el frontend con el precio que ya trae del feed.

**Correcciones aplicadas tras la revisión**
1. **Bug de favoritos:** al recuperar de un 409, si la relectura de `/favoritos` fallaba, el
   `?? []` **vaciaba el mapa entero** — se apagaban todos los ♡ y desaparecía "Tus
   favoritos" aunque en BD siguieran guardados. Ahora ante fallo se conserva el estado.
2. **Rendimiento móvil:** "Recién publicados" y "Verificados" se renderizaban **completos**.
   Con el feed sin límite, un auto premium+verificado+favorito se pintaba 4 veces y con ~300
   activas la portada montaba cientos de tarjetas con sus imágenes — en celulares de gama
   baja, que son nuestro público. Limitados a 12, con aviso de cuántas hay en total.
3. Badge de baja visible en **todos** los bloques, no solo en "Tus favoritos".
4. `haySesion` unificado con `tieneSesion()`: antes confundía "sin sesión" con "backend
   caído" y quedaba divergente del `alternar`.

**Verificación:** `import main` OK · `alembic heads` → **`0020`, cabeza única** ·
`tsc --noEmit` limpio · lint **4 errores preexistentes, 0 nuevos** · `build` OK.
Privacidad confirmada por el revisor: los **borradores son estructuralmente inalcanzables**
desde la portada (el feed filtra `estado == ACTIVA`), y no se agregó ni un campo al feed.

**Pendientes**
- ⚠️ **Marcos debe correr `alembic upgrade head`** (0020) antes de probar: sin ella el ♡
  falla al guardar. Sigue pendiente también la **0019** de M2.8.
- Correr el **guión v6** ([guion_prueba_market.md](guion_prueba_market.md) §3-sexies,
  secciones R–U), **en celular**.
- Deuda anotada para MC2: el corte a 12 se resuelve naturalmente con la paginación por
  cursor; falta la barra sticky de búsqueda al scrollear (transversal del doc §2).
- Deuda transversal (preexistente, no de MC1): los `Decimal` de dinero no tienen cota
  superior (`le=`/`decimal_places`), así que un desbordamiento de `Numeric(12,2)` daría
  `DataError` → 500. Afecta a todos los precios del proyecto, no solo a este campo.
- Sigue abierta la deuda de M2.6: `DatosOficialesMini` dispara scraping en cache miss.

---

## 2026-07-20 — Market M2.9: detalle local de las referencias externas

**Repos:** ambos (frontend el grueso; backend **un endpoint nuevo**, sin migración).
Ajuste de UX pedido por Marcos sobre M2.8. Revisado por **revisor-calidad** (**APTO**, sin
bloqueantes). **Commit sin push**.

**El problema:** la tarjeta de referencia era un `<a>` directo al portal externo. Un clic
te expulsaba del sitio **sin haber visto nada** — ni las fotos ni el detalle que el
aportante se había tomado el trabajo de copiar en M2.8.

**Qué se hizo — dos interacciones separadas**
1. **Clic en la tarjeta → detalle LOCAL** `/marketplace/referencias/{id}`: aviso ámbar con
   el copy exacto "Referencia externa · datos no verificados" **arriba del todo** (antes de
   la galería y del precio: el visitante sabe qué mira antes de leer los datos), galería
   con swipe en móvil, precio, descripción, ciudad, kilometraje y portal de origen. Si la
   referencia trae placa, también "Verificar esta placa".
2. **Botón explícito "Ver anuncio original en {fuente} ↗"** — la única salida al portal
   externo, en pestaña nueva (`rel="noopener noreferrer"`), avisando que abre otro sitio.
   En la tarjeta del feed el texto pasó de "Ver en {fuente} ↗" a "Ver detalle · {fuente}"
   (sin flecha: ese clic ya no sale del sitio).

**Backend (no estaba pedido, pero era necesario):** `GET /marketplace/referencias/{id}`
público. No existía forma de traer UNA referencia, y resolverlo desde el feed no servía
porque está capado a 30 (`LIMITE_REFERENCIADAS_FEED`): una referencia más antigua habría
dado 404. Sirve **solo aprobadas y activas** (mismo filtro que el feed, en el `WHERE`), con
404 indistinto — una `pendiente` o `rechazada` **no se puede ver por URL directa**, que era
el punto crítico de abrir una superficie pública nueva. Declarado **al final** del router
para no capturar las literales `GET /mias` y `GET /pendientes`.

**Verificación**
- Backend: `import main` → **64 rutas**; orden de rutas confirmado sobre las registradas
  (`/mias` y `/pendientes` siguen antes del dinámico); `alembic heads` → `0019` (sin
  migración nueva).
- Frontend: `tsc --noEmit` limpio; lint **4 errores, los 4 preexistentes**; `build` OK con
  la ruta `/marketplace/referencias/[id]` registrada.
- Revisor: sin bloqueantes. Confirmó el filtro aprobada+activa, el orden de rutas, el
  `rel="noopener noreferrer"` y que `PublicacionReferenciadaSalida` no expone `usuario_id`
  ni datos del aportante (no se amplía la superficie de datos, solo el alcance).
- Menores del revisor, **corregidos**: comentario de cabecera de `ListingCard` que seguía
  diciendo "link vivo al portal", y las dos menciones desactualizadas en **AGENTS.md §10.6**
  y `proyecto-snapshot.md`. (`docs/diagramas/modelo_datos.mermaid` dice "enlace vivo" sobre
  la columna `url_externa`, donde **sigue siendo cierto** — no se tocó.)

**Pendientes**
- Guión de prueba: nueva **sección Q** en [guion_prueba_market.md](guion_prueba_market.md)
  (§3-quinquies) y corregido el paso de la sección E que describía el comportamiento viejo.
- Sigue pendiente ⚠️ **`alembic upgrade head` (0019)** de M2.8 y el push de ambos repos.
- Anotado por el revisor (no es deuda nueva, es el patrón del proyecto): la página es
  client-only, así que los detalles de referencia no tienen SEO ni preview al compartirse.

---

## 2026-07-19 — Market M2.8: borrador con umbral, ficha para todos, garage y referencias ricas

**Repos:** ambos. Backend con **migración `0019`** (⚠️ **pendiente de aplicar en Neon: la
corre Marcos con `alembic upgrade head`**). Implementado por el **controller**, revisado por
**revisor-calidad**. **Commit sin push** — Marcos prueba primero.

**Qué se hizo**

1. **BUG "el plan light no deja llenar la ficha" — la causa no era la que parecía.**
   Busqué el gate por plan en el frontend y **no existe**: ni en el wizard, ni en
   mis-publicaciones, ni en el detalle; el `PATCH .../ficha` del backend tampoco restringe.
   La causa real es que `FichaEditor` y `GaleriaFotosEditor` prellenaban con
   `obtenerPublicacionDetalle` = el endpoint **público**, que solo sirve publicaciones
   `activa` (deuda ya anotada en M1). Fix: **`GET /marketplace/publicaciones/{id}/mia`**
   (dueño, cualquier estado) y los dos editores lo usan. Esto era además **requisito** del
   borrador: por definición no es `activa`, así que sin este endpoint el paso 2 del wizard
   no habría cargado nunca.
2. **Borrador + umbral de publicación.** `EstadoPublicacion.BORRADOR` (String en BD, sin
   migración de tipo). `POST /publicaciones` crea en borrador y **ya no cobra**. Publicar es
   `PATCH {estado: activa}`: valida `UMBRAL_FICHA_PUBLICACION` (env, default 30) → **422**
   *"Completa al menos el 30% de la ficha para publicar. Vas en N%."*, y **ahí** se debita
   el premium. Verificado que `borrador` no se expone: feed y detalle público ya filtraban
   por `activa` (el revisor auditó todos los consumidores). Las activas existentes **no se
   retro-validan**.
3. **Mi garage.** Cada vehículo cruza con las publicaciones propias **por placa** — no por
   `vehiculo_id`, porque exponerlo obligaría a sacar un id interno del garage en
   `PublicacionInternaSalida`, que también sirve el feed anónimo (el revisor validó la
   decisión). CTA "Publicar este auto" (wizard prellenado por query params, con `Suspense`
   por `useSearchParams`), "Completa tu ficha (N %)", "Borrador sin publicar" o
   "✓ Ficha completa".
4. **Referencias ricas.** Migración `0019`: `descripcion` (2000), `ciudad` (80),
   `kilometraje` (BigInteger) y `fotos` (JSONB NOT NULL default `'[]'`, **máx 5** validado
   en Pydantic con dedup). Endpoint `POST /marketplace/referencias/firma-foto` con carpeta
   propia. Formulario con los campos nuevos + uploader. Los campos ricos entran a
   `_CAMPOS_CONTENIDO`: editarlos devuelve la referencia a moderación `pendiente`.

**Verificación**
- Backend: `import main` → **63 rutas**; `alembic heads` → **`0019`** único; validación de
  fotos (dedup + rechazo de 6) y del umbral (0 % → 422 con el copy exacto; 35 % → pasa).
- Frontend: `tsc --noEmit` limpio; lint **4 errores, los 4 preexistentes**; `build` OK.

**Hallazgos del revisor — 2 BLOQUEANTES y 1 mayor, los tres corregidos**
- **Doble cobro del premium.** Mi idempotencia "por construcción" (prohibir volver a
  borrador) **no se sostenía**: `light → PATCH plan=premium (en borrador) → PATCH
  estado=activa` cobraba **6 tokens** en vez de 3, porque `asciende_a_premium` y
  `publica_borrador` eran flags independientes.
- **Activación saltándose el umbral Y sin pagar.** `borrador → pausada → activa` dejaba el
  anuncio **activo, premium, destacado, con ficha al 0 % y costo 0 tokens**.
- **Corrección de ambos:** máquina de estados explícita (`_aplicar_transicion_estado`: desde
  `borrador` **solo** se sale a `activa`, validando umbral; a `borrador` no se vuelve) +
  cobro derivado de **un solo predicado sobre el estado resultante** ("queda premium Y
  activa Y `premium_cobrado_en is None`"), con la marca persistida nueva
  **`premium_cobrado_en`** (agregada a la misma migración `0019`, que aún no se aplicó).
  Re-verificado simulando los caminos exactos del revisor: 1 cobro en vez de 2, y 422 en el
  atajo por `pausada`.
- **Mayor:** `PATCH /referencias/{id}` con `{"fotos": null}` reventaba en 500 (columna NOT
  NULL). Ahora un `null` explícito se normaliza a lista vacía ("quitar todas").
- Menores corregidos: docstrings que citaban un endpoint `activar` inexistente, `descripcion`
  de referencias ahora sí se renderiza en la tarjeta, `carpeta_referencia` muerta eliminada,
  el garage distingue borrador/vendida, y el wizard avisa del cobro premium **antes** de
  pulsar publicar (antes se enteraba con un 402).

**Pendientes**
- ⚠️ **`alembic upgrade head` (0019) en Neon** — sin eso, las referencias y el cobro
  idempotente no funcionan.
- **Correr el guión v5** ([guion_prueba_market.md](guion_prueba_market.md) §3-quinquies,
  secciones M–P), incluidos los dos casos de abuso que encontró el revisor.
- **Push pendiente** de ambos repos.
- Sigue abierta la deuda de M2.6/M2.7: `DatosOficialesMini` dispara scraping en cache miss
  desde una página pública e indexable (resolver en M3 con `solo_cache=true`).

---

## 2026-07-19 — Market M2.7: pulido UX (consulta compacta, tarjetas, entradas)

**Repo:** `consulta-placas-web` (**el backend no se tocó** — verificado por el revisor: sin
cambios en `src/` ni `alembic/`). Responde a los 3 hallazgos de la prueba de Marcos sobre
M2.5/M2.6. Implementado por el **controller**, revisado por **revisor-calidad** (**APTO**,
sin bloqueantes). **Commit sin push** — Marcos prueba primero.

**Qué se hizo**

1. **Consulta de placa compacta** (hallazgo 1: "muy extensa").
   - Nuevo `ResumenPlaca.tsx`: tarjeta "de un vistazo" con **máximo 6 datos** en tipografía
     grande (marca/modelo, año/color, matrícula, multas, total, fecha de consulta) y el
     veredicto. Exporta `derivarResumen`/`fechaLegible`, que reusa el anuncio (sin duplicar).
   - Nuevo `Acordeon.tsx` sobre **`<details>/<summary>` nativo**: sin estado, sin JS,
     accesible por teclado y sin sumar efectos de React (ni errores de lint).
   - `PerfilVehiculo.tsx` **reescrito**: todo el detalle (desglose por fuente, matriculación,
     identificación/titular, portales oficiales, tablero de fuentes) pasó a acordeones
     **cerrados por default**. La sección de desbloqueos con tokens queda **visible**: es
     acción, no detalle. El revisor confirmó que no hubo regresiones (polling, re-consulta
     con sesión, reintento de AMT, gating por `fuenteInactiva`, enlaces oficiales).
2. **Objetos del marketplace** (hallazgo 2: "presentación").
   - `ListingCard.tsx` reescrito, mobile-first: portada con **ratio fijo 4:3** (+ placeholder
     🚗 del mismo tamaño, para que la grilla no baile), **precio grande primero**, título en
     una línea truncada, **una sola fila de chips**, y **toda la tarjeta clickeable**. Se
     eliminaron la descripción y el bloque de mantenimientos que la estiraban, y la prop
     `onEliminar` (código muerto: ningún caller la pasaba).
   - Detalle reescrito con jerarquía **foto → precio/título/CTA → ficha → oficial → extras**.
     Galería con **swipe** en móvil (scroll-snap nativo, sin librerías) y miniaturas en
     escritorio. Ficha en tarjetas por bloque con íconos (⚙️ 🚙 🪑 ✨).
   - Nuevo `DatosOficialesMini.tsx`: la sección oficial en el anuncio baja a **3-4 líneas**
     con "Ver detalle completo →" hacia `/consultar/{placa}`.
3. **Puntos de entrada que faltaban** (hallazgo 3: "no se descubren").
   - `/marketplace`: bloque visible **"🔗 ¿Viste un auto en Facebook u OLX?"** con
     "Referenciar anuncio externo" (el flujo ya existía, pero estaba escondido entre botones
     iguales) + "Mis referencias". Enlace equivalente en la home.
   - `mis-publicaciones`: las acciones pasaron de enlaces de texto a **botones visibles
     📷 Fotos y 📋 Ficha técnica**, con estado activo. El vendedor llega a subir fotos **sin
     rehacer el wizard**.

**Verificación**
- `tsc --noEmit` limpio; `npm run lint` → **4 errores, los 4 preexistentes**; `build` OK.
- **Hallazgo mayor del revisor, corregido en la sesión:** con AMT en **`error_fuente`** el
  resumen decía **"Al día"** en verde y el botón de reintentar quedaba enterrado en un
  acordeón cerrado. Es la misma familia del bug que M2.6 arregló para `en_proceso`, ahora
  expuesta para la fuente caída. Ahora `derivarResumen` expone `municipalesCaidas`, el
  veredicto muestra **"Sin dato municipal"**, el chip del acordeón dice lo mismo y ese
  acordeón **se abre solo** cuando hay que reintentar.
- Menores corregidos: guarda explícita de `detalleBloqueado` antes de pintar cualquier monto
  (antes la privacidad dependía de que el consolidador vaciara `multas_detalle`), y
  `tabIndex`/`aria-label` en el carrusel móvil.

**Pendientes**
- **Correr el guión v4** ([guion_prueba_market.md](guion_prueba_market.md) §3-quater,
  secciones I–L) — **en celular**, que es donde se nota el rediseño.
- **Push pendiente** de ambos repos.
- **Deuda de M2.6 que M2.7 NO resolvió** (el revisor insistió en registrarla):
  `DatosOficialesMini` llama al perfil en el primer render de una página pública e indexable,
  y ese endpoint dispara scraping en cache miss. Las dos mitigaciones ya acordadas
  (`solo_cache=true` o disparo bajo interacción) siguen sin aplicarse. Resolver en M3, antes
  de que el market reciba tráfico real.

---

## 2026-07-19 — Market M2.6: market-first + datos oficiales automáticos en el anuncio

**Repos:** ambos (frontend el grueso; backend un cambio mínimo aditivo, **sin migración**).
Decisión de producto de Marcos (plan_market_autos.md §M2.6). Implementado por el
**controller**, revisado por **revisor-calidad** (**APTO**, sin bloqueantes).
**Commit sin push** — Marcos prueba primero.

**Qué se hizo**

1. **Reposicionamiento market-first.** El producto ES el market de autos; la consulta por
   placa pasa a herramienta de apoyo mientras las fuentes estatales sigan bloqueadas.
   - Home: hero **"Compra y vende autos con transparencia"** con CTA primario "Ver autos en
     venta" y secundario "Publica tu auto" (antes el hero era el buscador de placa). Nueva
     sección de destacados del feed (`DestacadosMarket.tsx`, premium primero, degrada a CTA
     si el feed está vacío). La consulta baja a una sección **"Herramientas"**.
   - Navegación: **Marketplace · Publicar · Consulta de placa · Precios** ("Consultar" se
     renombró). Pie, títulos, metadescripciones y copy de `/marketplace` girados a market.
   - **Ninguna ruta de consulta se eliminó** (verificado por el revisor): `/consultar` y
     `/consultar/{placa}` siguen intactas, solo pierden protagonismo.
2. **Enriquecimiento oficial automático (fire & forget).** Al crear la publicación en el
   paso 1 del wizard, el **cliente** dispara `GET /consultar/{placa}` sin `await`, sin
   spinner y tragando errores: el pipeline deja los datos cacheados en `consultas` y el
   vendedor no espera ni se entera si una fuente está caída. Usa `pub.placa` (la que
   normalizó el backend) para que la caché quede bajo la misma clave que lee el anuncio.
   **§10.2 intacta**: el CRUD del backend nunca invoca scraping — el revisor lo verificó con
   grep sobre `src/modules/marketplace/` y `src/modules/vehiculos/` (0 resultados).
3. **Sección "Datos oficiales" en `/marketplace/{id}`.** Consume el perfil consolidado de la
   placa, filtra por `fuenteInactiva` (SRI/FGE fuera) y muestra matrícula (ANT) e
   infracciones con **"Consultado el {fecha}"** en es-EC. Si no hay nada cacheado, degrada a
   **"Datos oficiales en proceso"** sin romper la página. **No filtra lo que se cobra**: con
   `multas_bloqueado` (el caso anónimo) solo se muestra el veredicto gratis, nunca los
   montos; el enlace lleva a `/consultar` para el detalle pagado.
4. **Backend (mínimo, aditivo, sin migración).** Campo `consultado_en: str | None` en
   `EstadoFuenteItem`. Lo inyecta la caché al leer (desde `creado_en`, **sobre una copia**
   para no ensuciar el objeto ORM) y `consultar_con_cache` para el dato recién scrapeado.
   Solo se sella lo que trajo datos (`ESTADOS_CACHEABLES`): sellar un error afirmaría una
   consulta exitosa que no ocurrió.

**Verificación**
- Backend: `import main` → **61 rutas (sin cambio)**; `alembic heads` → único `0018`;
  prueba directa de `consolidar_placa` → ANT cacheada propaga `consultado_en`, AMT
  `en_proceso` lo deja en `None`.
- Frontend: `tsc --noEmit` limpio; `npm run lint` → **4 errores, los 4 preexistentes**;
  `npm run build` OK.
- **Hallazgo mayor del revisor, corregido en la sesión:** la tarjeta de multas afirmaba
  **"Al día"** cuando AMT seguía `en_proceso` — el veredicto estaba incompleto y en un
  anuncio de venta ese falso negativo favorece al vendedor. Ahora, con el municipio en
  camino, muestra un estado neutro **"Consultando…"** y **no estampa fecha** (sellar con la
  hora de la ANT daba una sensación de completitud inexistente). Reproducido y verificado
  con `consolidar_placa` (ANT completada + AMT en_proceso → `tiene_pendientes: False`).
- Menores corregidos: docstring/sellado de `consultado_en` por estado cacheable, copy
  "(ANT y AMT)" → incluye municipios (podía listar EPMTSD), condición de "en proceso" ya no
  se queda pegada, y el fire & forget usa `pub.placa`.

**Pendientes**
- **Correr el guión de prueba v3** ([guion_prueba_market.md](guion_prueba_market.md) §3-ter,
  secciones F–H). Con eso se cierra M2.6.
- **Push pendiente** de ambos repos (Marcos prueba antes).
- **Deuda que entra a M3** (hallazgo mayor diferido): el detalle público llama al perfil, que
  en *cache miss* **dispara scraping**. Como el anuncio es público e indexable, varias
  visitas sobre una placa fría podrían generar scrapes concurrentes contra la misma fuente
  (choca con `scraping-respetuoso`). Propuesta: `solo_cache=true` en el endpoint de perfil.

---

## 2026-07-19 — Market M2.5: stand-by de fuentes + wizard de publicación + referencias

**Repos:** el grueso en `consulta-placas-web` (frontend); en este repo **solo documentación**.
Decisión de producto de Marcos (plan_market_autos.md §M2.5). Implementado por el
**controller**; revisado por **revisor-calidad**. **Commit sin push** — Marcos prueba primero.

**El backend NO se tocó.** Verificado: sin cambios en `src/` ni en `alembic/`. Los servicios
de SRI y FGE quedan vivos y **dormidos**; el ocultamiento es de presentación y reversible.

**Qué se hizo**

1. **Stand-by de fuentes.** Nuevo `src/lib/fuentes.ts` con `fuenteInactiva(clave)`, manejado
   por la env var **`NEXT_PUBLIC_FUENTES_INACTIVAS`** (default `sri,fge`; `""` reactiva todo).
   SRI y FGE salen de **toda** la UI: tarjeta "Valores SRI", enlace passthrough al portal del
   SRI, chips del tablero "Fuentes consultadas", lista del pie de página, filas de `/precios`
   (SRI y alertas legales) y metadatos SEO. El total "A pagar" del encabezado ya no suma
   valores del SRI (mostrar un monto sin su fuente era inexplicable). Documentado en
   **AGENTS.md §8**. ⚠️ **EPMTSD vuelve a mostrarse**: la lista vieja estaba hardcodeada como
   `["FGE","EPMTSD"]` y EPMTSD sí es una fuente activa vía worker residencial. Su enlace
   oficial pasó a `destacado` al quedar como acción principal de la sección.
2. **Wizard de publicación (3 pasos).** `/marketplace/publicar` pasó de formulario suelto a
   **datos básicos → ficha técnica → fotos**, con barra de pasos. Al crear la publicación
   **navega automático al paso 2** (antes el usuario caía en el feed y la ficha nacía vacía —
   ese era el problema que motivó la etapa). "Completar después" siempre disponible. Se
   conservan vinculación con el garage, selector de plan y manejo de 401/402.
   `FichaEditor` acepta un `onCompletitud` opcional (patrón latest-ref) para que el
   contenedor refresque el % en vivo.
3. **Transparencia de la ficha.** Umbrales en `src/lib/ficha.ts`
   (`UMBRAL_FICHA_INCOMPLETA = 30`, `FICHA_COMPLETA = 100`). CTA persistente
   **"Completa tu ficha (N %)"** en mis-publicaciones (abre el editor, el % baja en vivo) y
   en `/marketplace/{id}` **solo si el visitante es el dueño**. Bajo 30 %, feed y detalle
   público muestran **"Ficha incompleta"** en lugar del chip de porcentaje (`null` cuenta
   como incompleta).
4. **Referencias externas.** Copy exacto **"Referencia externa · datos no verificados"** en
   el feed (`ListingCard`) y en `mis-referencias`. El formulario de referenciar no se tocó.
   De paso, corregido un voseo preexistente ("Podés" → "Puedes") en mis-referencias.

**Verificación**
- `npx tsc --noEmit` limpio; `npm run lint` → **4 errores, los 4 preexistentes** (ninguno
  nuevo); `npm run build` OK (16 rutas).
- Sobre el **HTML renderizado** del build: el pie lista solo ANT y AMT; `/precios` ya no
  muestra las filas de SRI ni de alertas legales.
- **revisor-calidad**: 2 hallazgos MAYORES, **ambos corregidos en la sesión** —
  (a) `.env.example` quedaba fuera del repo por el patrón `.env*` del `.gitignore`
  (se agregó `!.env.example`, si no la variable nueva quedaba sin documentar);
  (b) `hayFuentesEnProceso` no filtraba fuentes ocultas, así que una FGE `en_proceso` dejaba
  el perfil repollando cada 4 s con el encabezado en "Consultando…" para siempre.
  Sin hallazgos de privacidad: el CTA del dueño no dispara nada sin sesión y falla en silencio.

**Pendientes**
- **Correr el guión de prueba v2** ([guion_prueba_market.md](guion_prueba_market.md) §3-bis,
  secciones A–E) en local. Con eso se cierran **M2.5 y M2** juntas.
- **Push pendiente** de ambos repos (Marcos prueba antes).
- Menor (anotado por el revisor, diferido a M3): el detalle público descarga
  `listarMisPublicaciones()` completo solo para saber si el anuncio es propio; un campo
  `es_mia` en el detalle lo resolvería.
- Menor: el botón del paso 1 ya no dice "Publicar Premium/gratis"; el aviso de que Premium
  cobra tokens vive solo en el selector de plan.

---

## 2026-07-19 — Market M2 (frontend): uploader + galería de fotos

**Repo:** `consulta-placas-web`. Implementado por el **controller** (el subagente dev-frontend se
cortó por límite de sesión a mitad); revisado por **revisor-calidad** (APTO, sin bloqueantes).

**Qué se hizo**
- **`types/api.ts` + `lib/api.ts`**: tipos `BloqueFoto`/`FirmaSubida`/`FotoRegistrar`/`FotoSalida`,
  `fotos` en `PublicacionDetalle`, `foto_portada` en `PublicacionInterna`. Funciones
  `firmarSubidaFoto`, `subirACloudinary` (fetch **directo** a Cloudinary, no al backend),
  `registrarFoto`, `reordenarFotos`, `eliminarFoto`. Nueva clase `CloudinaryError` para no
  confundir los códigos HTTP de Cloudinary con los del backend propio.
- **Galería pública** en `marketplace/[id]/page.tsx`: portada grande + miniaturas (solo lectura).
- **`GaleriaFotosEditor.tsx`** (dueño, en `mis-publicaciones`): subir (flujo firma→Cloudinary→
  registrar), borrar y reordenar (optimista con reversión). **Límite 12** (botón deshabilitado +
  corte del bucle + 409). Degrada con gracia ante **503** (Cloudinary no configurado). Carga con
  el patrón IIFE-async-en-useEffect (como FichaEditor) → sin error de lint nuevo.
- **`ListingCard.tsx`**: usa `foto_portada` como portada del feed (publicaciones internas).

**Verificación:** `tsc --noEmit` limpio; `npm run lint` → **4 errores (los preexistentes**;
`GaleriaFotosEditor` no agrega ninguno). Revisor: contrato fiel al backend, flujo de subida
correcto, manejo 503/409, privacidad (galería pública solo lectura, mutaciones con Bearer),
sin deps nuevas. Menor detectado y **corregido en la sesión**: errores de Cloudinary ahora se
distinguen de los del backend (`CloudinaryError`).

**Pendientes**
- **E2E real de fotos** requiere cargar `CLOUDINARY_*` en el backend (dev responde 503) y la
  **migración `0018` aplicada en Neon** (la corre Marcos). Sin eso, subir/registrar no opera.
- Compuerta M2: código listo en ambos repos; falta la verificación E2E con Cloudinary configurado
  (subir/borrar/reordenar + portada en el feed).

---

## 2026-07-19 — Market M2 (backend): fotos de la publicación (Cloudinary firmado)

**Rama:** `main`. Ejecutado por **dev-backend**, revisado por **revisor-calidad** (APTO).
Decisión de infra (Marcos, plan_costos.md): **Cloudinary free tier**, el navegador sube directo
con firma del backend; la BD solo guarda URLs. **Migración 0018 aún NO aplicada en Neon** (la
corre Marcos).

**Qué se hizo**
- **`fotos_publicacion`** (migración `0018`): `publicacion_id` FK→`publicaciones_internas`
  (CASCADE, index), `url` String(**2048**), `bloque` String(20) nullable
  (`motor_suspension|carroceria|interiores|general`, validado en Pydantic), `orden` Integer,
  `creado_en`. Modelo `FotoPublicacion` + relación `PublicacionInterna.fotos`
  (`delete-orphan`, `order_by orden`). Registrado en `registry.py`.
- **Firma Cloudinary** (`marketplace/services/cloudinary.py`): SHA-1 **manual** (sin SDK →
  cero deps nuevas); credenciales solo por env (`CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET/
  UPLOAD_FOLDER`). El `api_secret` **nunca** sale al cliente. Sin config → **503** (patrón vision.py).
- **Endpoints del dueño** (orden de rutas: literales antes que dinámicas): `POST .../fotos/firma`
  (503 si no hay config), `POST .../fotos` (valida URL de nuestro cloud → 400; **límite 12 → 409**;
  `orden` al final), `PATCH .../fotos/orden` (reorden; **422** si la lista no calza), `DELETE
  .../fotos/{foto_id}` (204; borra registro, no el binario). 404 indistinto de propiedad.
- **Salida**: `PublicacionDetalleSalida.fotos` (ordenadas) y `PublicacionInternaSalida.foto_portada`
  (primera por orden) en el feed. `selectinload(fotos)` en feed/mias/detalle/helpers → sin N+1.
- `.env.example` con las 4 vars (aviso de no commitear valores; 503 sin credenciales).

**Verificación:** `import main` → 61 rutas (las 4 `/fotos*` presentes; literales siguen
resolviendo); `Base.metadata` → 17 tablas con `fotos_publicacion`; `alembic heads` → único `0018`;
`alembic upgrade 0017:0018 --sql` (offline) genera tabla+índice y `downgrade` simétrico; firma
determinista y api_secret no expuesto; validación de URL rechaza http/host ajeno/spoofing de
subdominio. **Sin SDK cloudinary en requirements.**

**Pendientes / deuda menor (del revisor)**
- **`alembic upgrade head` contra Neon** (0018) — lo corre Marcos; cierra la parte backend de M2.
- `registrar_foto` con `orden` explícito no deduplica contra órdenes existentes (empate resoluble;
  `reordenar` lo normaliza). `FotoReordenar.orden` es lista de `foto_id` (nombre podría confundir).
- **DELETE no destruye el binario en Cloudinary** (barrido posterior, decisión acordada).
- **Frontend M2** (uploader por bloque + galería en el detalle): segunda sesión con dev-frontend.

---

## 2026-07-18 — Market M1: ficha técnica en el frontend (detalle + editor)

**Repo:** `consulta-placas-web` (commit `1c0bd95`). **Backend M0** cerrado antes: migración
`0017` aplicada en Neon (`alembic current` = `0017`), commits `45c7da9` (ficha) + `5855abb`
(agentes + plan). Ejecutado por el agente **dev-frontend**, revisado por **revisor-calidad**.

**Qué se hizo**
- **Detalle público** `app/marketplace/[id]/page.tsx`: consume `GET /marketplace/publicaciones/{id}`;
  pinta el anuncio + la ficha en 4 tarjetas (Motor y suspensión / Carrocería / Interiores /
  Extras), **barra de completitud** y etiqueta **"declarado por el vendedor"** en los campos de
  condición. Maneja 404 y ficha vacía.
- **Editor del vendedor** `components/FichaEditor.tsx` (inline en `mis-publicaciones`): 3 pestañas
  + extras, **guardado parcial por bloque** (un `PATCH .../ficha` que envía solo el bloque
  editado; los demás quedan intactos), nada obligatorio, selects con labels es-EC.
- `lib/api.ts` (`obtenerPublicacionDetalle`, `actualizarFichaPublicacion`), `lib/ficha.ts`
  (etiquetas de catálogos), `types/api.ts` (mirror de bloques/catálogos/`FichaSalida`/
  `FichaActualizar`/`PublicacionDetalle` + `completitud_ficha`), `ListingCard` (chip
  "Ficha N% completa").

**Verificación:** `tsc --noEmit` limpio; `eslint` sin errores nuevos (los 4 preexistentes de
`Header`/`admin/*`/`mis-publicaciones` siguen). Revisor: contrato fiel al backend, guardado
parcial correcto, sin PII, copy no agresivo, sin deps nuevas → **APTO**. **Compuerta M1 cerrada.**

**Pendientes / deuda menor**
- Mapear el 422 de rango (p. ej. cilindraje > 10000) a copy es-EC en `FichaEditor`.
- Editar la ficha de una publicación **pausada**: el prellenado usa el `GET` público (solo
  `activa`); haría falta un GET de ficha con scope de dueño. No bloquea M1 (nacen `activa`).
- Siguiente: **M2 — fotos de la publicación** (decisión previa de storage con Marcos).

---

## 2026-07-18 — Market de autos (paso 2): ficha técnica de la publicación

**Rama:** `main`. Decisión de rumbo: el pilar de consulta queda en su techo razonable
(SRI/FGE passthrough, AMT/EPMTSD vía worker residencial, proveedor real pendiente solo de
API key). Arranca el **market de autos** para uso particular y patios: primero, ver
vehículos y su detalle con transparencia para el comprador y registro simple del vendedor.

**Qué se hizo**
- **`fichas_publicacion`** (migración `0017`): 1:1 con `publicaciones_internas` (UK +
  CASCADE). **3 bloques** JSONB nullable — `motor_suspension`, `carroceria`, `interiores` —
  + `extras` (lista JSONB, default `[]`; ej. láminas de seguridad, llantas recién cambiadas).
  El shape lo valida Pydantic (`extra="forbid"`), no la BD → la ficha evoluciona sin migración.
- **Schemas** (`marketplace/schemas.py`): `BloqueMotorSuspension` / `BloqueCarroceria` /
  `BloqueInteriores` (todo opcional; catálogos `Literal` es-EC: combustible, transmisión,
  tracción, estado de componentes, tipo de carrocería, pintura, material de asientos +
  `observaciones` libre por bloque), `ExtraVehiculo` (nombre+detalle, máx. 20),
  `FichaActualizar` (parcial por `model_fields_set`: enviar bloque = reemplaza, `null` =
  borra, omitir = intacto), `FichaSalida` con **`completitud`** (% de campos llenos de los
  3 bloques), `PublicacionDetalleSalida` (feed + ficha). El feed agrega `completitud_ficha`.
- **Endpoints** (`routers/publicaciones.py`): `PATCH /marketplace/publicaciones/{id}/ficha`
  (dueño, upsert, gratis — la transparencia no se cobra) y
  `GET /marketplace/publicaciones/{id}` (público anónimo, solo `activa`, 404 indistinto).
  La ruta dinámica va AL FINAL del router para no capturar `mias` /
  `pendientes-verificacion` (nota en el código). `selectinload(ficha)` en feed/listados.
- Registro en `src/registry.py`.

**Verificación:** `import main` → 42 rutas OpenAPI (PATCH ficha y GET detalle presentes;
rutas literales siguen resolviendo); `Base.metadata` → 16 tablas con `fichas_publicacion`;
`alembic heads` → `0017`; pruebas de schema: payload típico OK, catálogo inválido → 422,
campo con typo → 422 (`extra="forbid"`), completitud parcial calcula bien.

**Revisión de calidad (compuerta M0, agente revisor-calidad):** APTO PARA COMMIT. Sin
bloqueantes. Confirmado: contrato de errores (404 indistinto, ficha gratis sin 402, sin 500),
orden de rutas dinámicas al final, `selectinload(ficha)` sin N+1, migración manual con
`downgrade` + modelo en `registry.py`, privacidad (sin VIN/dueño en el detalle), es-EC no
agresivo, sin deps nuevas. Verificación mínima verde (`import main`, `alembic heads` único
`0017`, schemas rechazan typo/catálogo inválido). Head del código `0017`; **BD Neon aún en
`0016`** (0017 sin aplicar).

**Pendientes**
- **`alembic upgrade head` contra Neon** (verificado: la BD está en `0016`, la migración `0017`
  NO se ha aplicado). Es el paso que cierra la compuerta M0; lo corre Marcos.
- Hallazgos menores del revisor (cosméticos, no bloquean): índice `ix_fichas_publicacion_publicacion_id`
  redundante con la UK (limpiar en futura migración); `PATCH .../ficha` con cuerpo `{}` crea ficha
  vacía → `completitud_ficha` pasa de `null` a `0` (definir en frontend si se pintan distinto).
- Frontend (`consulta-placas-web`): página de detalle de publicación + formulario por
  bloques con barra de completitud; feed muestra `completitud_ficha`.
- Siguientes del market: fotos de la publicación, búsqueda/filtros del feed, cuentas de
  patio (multi-vehículo), contacto comprador-vendedor.

---

## 2026-06-01 — POC proveedor real (`consultas_ec`) + fix de precios en la home

**Rama:** `main`. Integración HTTP real de **un** proveedor para medir costo/cobertura/latencia/
margen, sin activar nada en prod todavía.

- **`providers/consultas_ec.py`**: llamada HTTP real (httpx async, timeout configurable) + mapeo
  **defensivo** al contrato (`_mapear`, nombres es/en, datos anidados). Tolerante a fallos
  (red/HTTP≠200/no-JSON → `estado=error`, nunca lanza). Sin `CONSULTAS_EC_API_KEY`+`BASE_URL` →
  `sin_credenciales`, capacidades vacío (no ofrece ni cobra). Verificado.
- **Costo en `costos_proveedor_consulta`**: `services/proveedor.registrar_costos_proveedor`
  (upsert por producto+proveedor) se llama al cachear un resultado OK con costo.
- **Harness `scripts/evaluar_proveedor.py`**: corre 50–100 placas contra el proveedor activo y
  mide % éxito, latencia (prom/min/max/p95), cobertura de campos, costo y errores. Secuencial
  (`--delay`), `--placas archivo`, `--json`. **Dry-run con mock (60 placas): 100% éxito, cobertura
  total salvo `valores_pendientes`** → valida el harness y el flujo end-to-end.
- **Doc `docs/producto/evaluacion_proveedor_real.md`**: metodología, config, resultados (mock +
  plantilla real PENDIENTE), margen (1 llamada ≈ $0.08 alimenta identificadores+titular; bundle
  margen ~$1.52) y criterio de activación (≥70% éxito, p95 ≤3s, cobertura ≥60%, margen positivo).
- **`.env.example`**: `CONSULTAS_EC_BASE_URL`, `CONSULTAS_EC_COSTO_USD`.
- **Frontend home (`page.tsx`)**: la sección "Planes simples" mostraba el modelo viejo de
  suscripción (Gratis 5 consultas/mes, **Pro $4.99/mes**) que contradecía el modelo por tokens.
  Reescrita a "Precios claros": **Gratis** (datos públicos) + **Datos por tokens** ($0.04,
  desde $1=25), alineada con `/precios`.

**Verificación:** `scripts/validar_desbloqueos` OK; `consultas_ec` sin credenciales degrada limpio;
imports `main`/proveedor OK; harness dry-run mock OK; frontend `tsc --noEmit` OK.

**Pendiente (criterio de salida del POC):** cargar `CONSULTAS_EC_API_KEY` + `BASE_URL`, confirmar
el contrato real (ajustar `_mapear` si difiere), correr el harness con placas reales y decidir
activar o no según §8 del doc. No se agregó migración.

---

## 2026-06-01 — Fase 3: experiencia progresiva de desbloqueo + capa de proveedores

**Rama:** `main`. Preview gratis → desbloqueo de bloques por tokens, con una capa de proveedores
externos lista (sin credenciales reales todavía) y el frontend con tarjetas de desbloqueo.

### Backend — capa de proveedores (`src/modules/consulta/providers/`)
- **Contrato normalizado** `base.ResultadoVehicular` (placa, marca, modelo, anio, color, tipo,
  clase, servicio, chasis, motor, vin, titular, multas, valores_pendientes, proveedor,
  costo_estimado_usd, estado, raw_response) + interfaz `ProveedorVehicular` (capacidades + `consultar`).
- **`mock_provider.py`** funcional: datos deterministas por placa (VIN 17 chars, titular, etc.);
  capacidades `{identificadores_tecnicos, titular_validado}`. Default `PROVEEDOR_VEHICULAR_ACTIVO=mock`.
- **Stubs reales** `consultas_ec.py` / `placaapi_ec.py` / `webservices_ec.py`: leen su API key;
  sin credencial → `capacidades` vacío y `sin_credenciales` (no ofrecen ni cobran). Llamada HTTP = TODO.
- **`selector.py`**: proveedor activo por env var (memoizado). NO scraping, NO captcha.
- **Puente `services/proveedor.py`**: `capacidades_proveedor()` (sin llamar), `leer_proveedor_cacheado()`
  y `asegurar_datos_proveedor()` (llama SOLO si no hay caché; cachea en `consultas` fuente `PROVEEDOR`).
  Cumple "no llamar al proveedor en la consulta gratis" y "no re-llamar si está en caché".

### Backend — perfil adaptado (consolidador + schemas)
- Nuevo schema `Titular` (bloqueado/disponible/validado/nombre_ofuscado/mensaje) + `ofuscar_nombre`
  en `core/ofuscacion.py`. **Nunca** se expone el nombre crudo: solo validación + iniciales.
- `consolidar_placa` recibe `proveedor_datos` (cacheado) y `proveedor_capacidades`: llena VIN/motor/
  chasis y el titular desde el proveedor; `disponible` se calcula por capacidad (sin llamar).
  VIN/motor/chasis/titular siguen ofuscados si el bloque no está desbloqueado (regla #6).
- `routers/consulta.py` (perfil) y `routers/desbloqueos.py` pasan proveedor (solo caché en el preview).
  Al desbloquear un producto-proveedor (`identificadores_tecnicos`/`titular_validado` o el bundle),
  se invoca al proveedor, se cobra **solo si entrega el dato** (409 si no), y se audita proveedor+costo.
- `.env.example`: `PROVEEDOR_VEHICULAR_ACTIVO=mock`, `CONSULTAS_EC_API_KEY`, `PLACAAPI_EC_API_KEY`,
  `WEBSERVICES_EC_API_KEY`.

### Frontend (`consulta-placas-web`)
- Componentes nuevos: `TokenBadge` (costo en tokens + USD ref.), `UnlockCard` (flujo completo:
  login / 402→CTA recargar / 409 / éxito sin recargar / idempotente), `ProductoConsultaCard`
  (preview seguro por código), `ReporteCompraSeguraCard` (bundle).
- `PerfilVehiculo`: sección **"Completa tu revisión del vehículo"** con las tarjetas bloqueadas;
  los datos revelados van a sus tarjetas dedicadas (Identificación, **Titular**, Multas). Se quitó
  el botón inline anterior. Copy es-EC, sin lenguaje agresivo ("Desbloquea solo lo que necesitas").
- `types/api.ts` (+`Titular`, `titular`), `consultar/[placa]` sin cambios de fetch.

**Verificación:** `python -m scripts.validar_desbloqueos` OK (catálogo + gateo + capa mock:
identificadores/titular disponibles por capacidad; titular SIEMPRE ofuscado, nunca crudo);
imports de `main`/routers/proveedor OK; **frontend `tsc --noEmit` OK** (lint: 4 errores
pre-existentes en Header/mis-publicaciones, no en archivos nuevos).

**Pendiente:** integrar un proveedor real (implementar la llamada HTTP en su stub + cargar API key);
SRI/Fiscalía siguen como enlace oficial (sin proveedor confiable / PII). No se agregó migración.

---

## 2026-05-31 — Reajuste comercial del catálogo (Fase 2.5): solo se cobra por valor real

**Rama:** `main`. No se debe cobrar con tokens **datos públicos simples** (clase, servicio,
marca, modelo, año, color, estado de matrícula) que ya vienen de fuentes públicas. Solo se
cobra por datos con **costo de proveedor externo, dificultad real o valor comercial relevante**.

- **Valor del token:** USD 0.05 → **USD 0.04**. `precio_referencial_usd = tokens × 0.04`.
- **Migración 0016** (manual): desactiva `vehiculo_basico`/`vehiculo_tecnico` (`activo=false`);
  renombra `vehiculo_identificadores`→`identificadores_tecnicos` (3t),
  `vehiculo_titular_validado`→`titular_validado` (5t), `vehiculo_multas`→`multas_con_montos`
  (10t); reprecia `reporte_compra_segura` 30→40t y `verificacion_marketplace` 80→100t; siembra
  `consulta_publica_base` (0t), `valores_matricula_sri` (12t) y `alertas_legales` (8t); migra los
  `desbloqueos_consulta` existentes al nuevo código (datos de prueba). Reversible.
- **Seed** (`catalogo_productos.py`): nuevo catálogo de 8 productos + `BUNDLE_INCLUYE` ampliado.
- **Consolidador**: ya **no gatea** `datos_basicos` (ficha pública gratis); identificadores →
  `identificadores_tecnicos`, multas → `multas_con_montos`. `titular_validado`,
  `valores_matricula_sri` y `alertas_legales` salen `disponible=false` (enlace oficial / sin
  proveedor confiable). Alias `POST .../desbloquear` → `identificadores_tecnicos`.
- **Marketplace**: `TOKENS_VERIFICACION_MARKETPLACE` default 80 → 100 (alineado al catálogo).
- **Copy es-EC (tuteo)**: "Validar titular registrado", "Ver identificadores técnicos", "Ver
  multas con valores", "Ver valores de matrícula (SRI)", "Ver alertas legales", "Generar reporte
  compra segura". Sin "paga para ver el dueño".
- **Regla técnica documentada**: la consulta gratuita no llama a proveedores externos; el
  proveedor se invoca solo al desbloquear un producto pagado y su respuesta se cachea; si otro
  producto usa un dato ya cacheado, no se vuelve a llamar.
- **Docs**: `catalogo_productos_consulta.md`, `reglas_monetizacion_tokens.md` (+ paquetes de
  recarga: $1→25t, $2.50→65t, $5→135t, $10→280t), `modelo_tokens_microdesbloqueos.md` (§9),
  `politica_datos_sensibles.md`, AGENTS.md §10.3.

**Verificación:** `python -m scripts.validar_desbloqueos` OK (8 productos, 1 token=USD0.04,
ficha pública gratis, multas gateadas); imports de routers/consolidador/marketplace/registry OK;
`alembic history` encadena `0015 → 0016 (head)`.

**Frontend alineado** (repo `consulta-placas-web`, commit `ac418ed`): página de precios reescrita
al modelo por tokens (1 token = USD 0.04; paquetes $1=25/$2.50=65/$5=135/$10=280); la ficha
pública ya no se pinta con candado (gratis); `PerfilVehiculo` usa los códigos nuevos
(`multas_con_montos`, `identificadores_tecnicos`) y el botón muestra el nombre-acción del
producto; copy corregido ("Conoce"; no se promete SRI/Fiscalía automáticos, frase de enlaces
oficiales). No se rediseñó el marketplace.

**Pendiente:** integrar proveedores reales para activar `titular_validado`/
`valores_matricula_sri`/`alertas_legales` (hoy enlace oficial). Iniciar **Fase 3** sin
inconsistencias comerciales/visuales.

---

## 2026-05-31 — Microdesbloqueos v2: catálogo en BD + auditoría comercial (backend)

**Rama:** `main`. Evolución del v1 (catálogo en código + tabla `desbloqueos`) al v2 pedido.

- **Migración 0015** (manual): crea `productos_consulta` (catálogo: codigo, nombre, tokens,
  `precio_referencial_usd`, sensibilidad, activo, orden), `desbloqueos_consulta` (auditoría:
  tokens_cobrados, precio_referencial_usd, proveedor_usado, costo_estimado_usd,
  resultado_cache_id; UK usuario+placa+producto) y `costos_proveedor_consulta`. **Dropea**
  `desbloqueos` (v1, solo prueba). **Siembra** el catálogo idempotente (ON CONFLICT DO NOTHING).
- **Modelos** `ProductoConsulta` / `DesbloqueoConsulta` / `CostoProveedorConsulta` (reemplazan
  `Desbloqueo`); registrados en `registry.py`.
- **Catálogo en BD** como fuente de verdad; `catalogo_productos.py` queda como definición-semilla
  (`SEED_PRODUCTOS` + `BUNDLE_INCLUYE`). `services/desbloqueos.inicializar_catalogo` siembra
  idempotente; `catalogo_activo`, `obtener_producto`, `productos_desbloqueados`,
  `listar_desbloqueos`, `desbloquear` (débito atómico, idempotente, expande bundle).
- **Consolidador** ahora recibe `catalogo` (filas BD) para armar `productos`; el gateo de
  secciones no cambia.
- **Router dedicado** `routers/desbloqueos.py`: `GET /consultar/{placa}/productos`,
  `POST /consultar/{placa}/desbloquear/{producto_codigo}` (400/422-inactivo/409/402, idempotente),
  alias `POST .../desbloquear`, `GET /consultar/{placa}/desbloqueos`. Montado en `main.py`. Los
  endpoints de desbloqueo salieron de `consulta.py` (el perfil sigue ahí, ahora pasa el catálogo).
- **Schemas**: `ProductoConsultaCreate/Response`, `DesbloqueoConsultaRequest/Response`,
  `EstadoProductosPlacaResponse` (+ `precio_referencial_usd` en `ProductoEstado`).
- **Script de validación** `scripts/validar_desbloqueos.py` (sin BD): catálogo (7 productos,
  1 token=USD0.05) + gateo teaser/unlock.

**Compat:** el frontend desplegado NO cambia — mismos paths (`/desbloquear/{codigo}` y alias),
el perfil mantiene `productos`; los GET nuevos son aditivos.

**Verificación:** `configure_mappers` + carga app OK; 4 rutas presentes; migración 0015 renderiza
(3 tablas + drop + seed ON CONFLICT); `scripts/validar_desbloqueos` pasa.

**Pendientes:** proveedor externo para `titular_validado`/`tecnico` (siguen `disponible=false`);
poblar `costos_proveedor_consulta` cuando exista proveedor; UI para `GET /desbloqueos` (historial).

---

## 2026-05-31 — Cierre de pendientes: verificación 80 tokens + saldo en header + seam proveedor

**Rama:** `main`.

- **Verificación marketplace reconciliada (decisión #2):** se separó *destacar* de *verificar*.
  Publicar premium = 3 tokens (solo destaca, nace `no_verificado`). Nuevo endpoint
  `POST /marketplace/publicaciones/{id}/solicitar-verificacion` (dueño): cobra
  `TOKENS_VERIFICACION_MARKETPLACE`=**80** (402 si falta), deja `pendiente` → cola admin.
  422 si la publicación es light; idempotente si ya está pendiente/verificada. `crear_publicacion`
  y `actualizar_publicacion` ya NO ponen `pendiente` automáticamente.
- **Frontend:** `solicitarVerificacion(id)` + nueva pantalla `/marketplace/mis-publicaciones`
  (lista del dueño con estado de verificación y botón "Solicitar verificación · 80 tokens",
  maneja 402/422) + enlace desde el marketplace. **Saldo de tokens** (🪙 N) visible en el Header.
- **Proveedor titular/técnico (decisión #3):** BLOQUEADO por dependencia externa (no hay proveedor
  autorizado). `vehiculo_titular_validado` y `vehiculo_tecnico` siguen `disponible=false` (no
  cobran). Documentado el punto de integración (`services/proveedor_<x>.py` → poblar en el
  consolidador) para activarlos sin tocar el cobro. NO se hace scraping de padrones.
- **Snapshot** regenerado.

**Verificación:** rutas backend cargan (incluye solicitar-verificacion); `tsc`+`next build` ok.
Sin migración nueva (usa `estado_verificacion`/`verificado_en` existentes).

---

## 2026-05-31 — Microdesbloqueos por tokens (implementación backend + frontend)

**Rama:** `main`.

**Backend**
- Modelo `Desbloqueo` (`src/modules/consulta/models/desbloqueo.py`) + migración **0014**
  (tabla `desbloqueos`, UK usuario+placa+producto; guarda qué se compró, no el dato).
- `services/catalogo_productos.py`: catálogo en código (precios/descripciones/bundle).
- `services/desbloqueos.py`: `productos_desbloqueados`, `desbloquear_producto` (débito atómico
  idempotente, expande bundle), `estado_catalogo`.
- `consolidador.consolidar_placa(placa, resultados, productos_desbloqueados)`: gatea secciones;
  teaser gratis = marca/modelo/año/color + matrícula vigente + veredicto `tiene_pendientes`.
- `auth.dependencies.usuario_actual_opcional` (auth opcional, no 401).
- Endpoints: `GET /consultar/{placa}/perfil` (auth opcional, gateado), `POST
  /consultar/{placa}/desbloquear/{producto}` (400/409/402), y el viejo `/desbloquear` queda
  como **alias** de `vehiculo_identificadores`.

**Frontend**
- Tipos `ProductoEstado`, `DatosBasicos.{matricula_vigente,bloqueado}`, `VehiculoConsolidado.
  {multas_bloqueado,productos,tiene_pendientes}`.
- `consultarPerfil` envía el token si hay sesión (auth opcional) → revela lo ya pagado;
  `desbloquearProducto(placa,codigo)`.
- `PerfilVehiculo`: veredicto desde el backend; `BotonDesbloqueo` (🔓 N tokens, maneja 401/402/409)
  en Datos/ Multas/ Identificación; re-fetch con token al montar.

**Decisiones aplicadas (defaults del plan):** teaser mínimo; `verificacion_marketplace` no se
cablea a la consulta; `tecnico`/`titular_validado` sin fuente → `disponible=false`; bundle no
descuenta lo ya pagado; **402** si falta saldo; **no cobrar** si el dato no está disponible.

**Verificación:** `configure_mappers` + carga de app OK; gateo probado con datos simulados
(teaser oculta clase/multas/VIN, unlock revela); migración 0014 renderiza; `tsc`+`next build` ok.

**Pendientes:** proveedor para `titular_validado`/`tecnico`; reconciliar precio de
`verificacion_marketplace` (80) con el premium=3 actual; mostrar saldo de tokens en el header;
regenerar `proyecto-snapshot.md`.

---

## 2026-05-31 — PLAN: modelo de microdesbloqueos por tokens (solo documentación)

**Rama:** `main` (commit local, **sin push** — no se toca producción todavía).

**Qué se hizo:** planificación y documentación de producto para pasar del desbloqueo
**monolítico** actual (`POST /consultar/{placa}/desbloquear`, revela todos los identificadores
por 1 token) a **microdesbloqueos progresivos**: consulta inicial gratuita (teaser) + productos
pequeños desbloqueables con tokens. Se crearon 4 docs en `docs/producto/`:
`modelo_tokens_microdesbloqueos.md`, `catalogo_productos_consulta.md`,
`reglas_monetizacion_tokens.md`, `politica_datos_sensibles.md`.

**Decisiones tomadas:**
- **1 token = USD 0.05** (referencial). Saldo inicial de cortesía sigue en 5 tokens.
- **Catálogo inicial** (códigos en español, estables como clave de `desbloqueos`):
  `vehiculo_basico` 3 · `vehiculo_tecnico` 2 · `vehiculo_identificadores` 3 ·
  `vehiculo_titular_validado` 5 · `vehiculo_multas` 8 · `reporte_compra_segura` 30 (bundle) ·
  `verificacion_marketplace` 80.
- **Titular = dato sensible (PII):** se maneja **ofuscado o validado** (coincide/no coincide),
  nunca crudo a terceros; valor completo solo al dueño autenticado. Fuente: proveedor autorizado.
- **No cobrar si no hay dato** entregado; **402** si falta saldo; **idempotencia** vía tabla
  `desbloqueos` (UK usuario+placa+producto): no se recobra lo ya comprado.
- **Sin evasión de captcha / anti-bot**: datos vía fuentes ya obtenidas + caché + proveedores
  autorizados + enlaces oficiales asistidos (SRI). El token cobra el acceso, no el bypass.
- El catálogo de productos vive en **código** (`services/catalogo_productos.py`), no en BD
  (precios versionados sin migración); solo `desbloqueos` es tabla nueva (migración 0014, manual).

**Decisiones abiertas (a confirmar antes de implementar):** alcance exacto del teaser gratis;
reconciliar `verificacion_marketplace` (80) con el flujo admin ya construido (premium=3 hoy);
proveedor del titular validado; si el bundle descuenta lo ya pagado.

**Verificación:** sin cambios de código ejecutable; solo documentación. `proyecto-snapshot.md`
sigue vigente (regenerado el 2026-05-31).

**Pendientes / siguiente etapa:** ver "Plan de archivos" en `modelo_tokens_microdesbloqueos.md`
(modelo `Desbloqueo` + migración 0014, `catalogo_productos.py`, `desbloqueos.py`, endpoints
`/productos` y `/desbloquear/{producto}`, gating del consolidador, UI con `BotonDesbloqueo`).

---

## 2026-05-31 — Verificación premium del marketplace (flujo admin completo)

**Rama:** `main`.

**Backend**
- `models.py`: `EstadoVerificacion` suma el valor terminal **`rechazado`** (columna String, sin migración). Nueva columna **`verificado_en`** (timestamp, nullable) en `publicaciones_internas` para auditar cuándo se selló → **migración 0013** (manual, revisada a mano).
- `schemas.py`: `PublicacionInternaSalida` expone `verificado_en`; nuevo `VerificacionPublicacion` (body `decision`, solo `verificado`/`rechazado`, validación de estado terminal).
- `routers/publicaciones.py` (espeja la moderación de referencias):
  - `GET /marketplace/publicaciones/pendientes-verificacion` — cola de premium `pendiente`, más antiguas primero (solo `admin_actual`).
  - `POST /marketplace/publicaciones/{id}/verificar` — marca `verificado` (sella + `verificado_en=now`) o `rechazado` (quita sello). 404 si no existe; **422 si no es premium**.

**Frontend**
- `types/api.ts`: `EstadoVerificacion` suma `rechazado`; `PublicacionInterna` suma `verificado_en`.
- `lib/api.ts`: `listarPublicacionesPendientesVerificacion()` y `verificarPublicacion(id, decision)`.
- Nueva pantalla **`/admin/verificaciones`** (mismo molde que `/admin/moderacion`): cola de premium pendientes con su argumento (mantenimientos) + botones Verificar/Rechazar. Acceso admin en el Header ("Verificar").
- El sello "Verificado por la plataforma" ya vivía en `ListingCard` (se muestra solo con `verificado`).

**Verificación:** `configure_mappers` + carga de `app` OK; rutas nuevas presentes; migración 0013 renderiza el `ADD COLUMN verificado_en`; `tsc` + `next build` del frontend en verde.

**Pendientes:** definir si el sello debe condicionar el orden/box del feed premium; notificar al dueño cuando su premium queda verificada/rechazada (hoy no hay notificaciones).

---

## 2026-05-29 — Integración de las 3 fuentes restantes + rebranding "Revisa tu Carro EC" + rediseño claro

**Rama:** `main`. Continuación del pivote a Perfil Consolidado.

**Backend — `estado_fuentes` catálogo-driven + 3 fuentes nuevas (una por una, con descubrimiento §14)**
- `consolidador.py`: `consolidar_placa(placa, resultados: dict[str,dict])` arma `estado_fuentes`
  recorriendo `CATALOGO_FUENTES` (implementadas = estado vivo; resto = `no_integrada`). Sumar
  fuente = catálogo + scraper + ruteo, sin tocar el consolidador. `_obtener_fuentes_placa` ahora
  devuelve dict keyed por clave.
- **EPMTSD** (oficial, multas): descubrimiento reveló que su portal corre sobre la **misma
  plataforma AxisCloud que AMT** (`ps_empresa=06` vs `03`). Se extrajo el adaptador compartido
  `services/_axiscloud.py` (flujo Playwright + parser de infracciones); `amt.py` y `epmtsd.py`
  quedaron como wrappers delgados. Vía worker híbrido (mismo gotcha de IP datacenter que AMT).
  Verificado en vivo (`consulta_realizada`); AMT re-verificado sin regresión.
- **ConsultasEcuador** (no oficial, chasis/motor): descubrimiento mostró que es página de
  afiliado (widget Bumper) tras **reCAPTCHA** — no scrapeable. Se integró como `consulta_externa`
  (enlace + disclaimer no oficial), sin scraping. Mismo criterio que SRI.
- **EcuadorLegalOnline** (no oficial): sitio de guías con ad-gate/reCAPTCHA y dato de propietario
  de pago (PII). También `consulta_externa` (enlace + disclaimer). Las 7 fuentes quedan
  `implementada=True`.
- Reintento (`FUENTES_WORKER`) ahora incluye EPMTSD; `worker.py CONSULTORES` también.

**Frontend (repo consulta-placas-web)**
- `PerfilVehiculo.tsx`: sección **Identificación** (chasis/motor ofuscados + enlace externo de
  ConsultasEcuador), marcadores **ⓘ no oficial** + disclaimer por ítem, chips del tablero
  clicables cuando son `consulta_externa`.
- **Rebranding** a **"Revisa tu Carro EC"** (antes ConsultaPlacas): nombre evita la ambigüedad de
  "seguro" (póliza); monograma RC. Aplicado en layout/Header/Footer/metadata y páginas.
- **Rediseño visual "Confianza clara"**: de tema oscuro neón (violeta-rosa-ámbar) a **tema claro**
  (fondo #f6f8fc), gradiente de marca **azul→cian**, estados verde/ámbar/rojo, sombras suaves.
  Decidido con el usuario: base clara + azul confianza, prioridad "atracción/que enganche".
  Convertidas TODAS las pantallas (landing, consulta, resultado, login, registro, precios,
  mi-garage, header, footer, inputs). `tsc` + `eslint` limpios; sin tokens `zinc-` restantes.

**Pendiente**
- **Imágenes referenciales del vehículo**: discutido (no hay foto del auto real por placa; opción
  recomendada: híbrido render-por-modelo + ilustración por clase, con sello "referencial").
  Pospuesto por decisión del usuario.
- Licencia de CDN de imágenes si se va por render (imagin.studio u otro).
- Deploy: el frontend en Vercel apunta a prod (Render), que necesita el deploy con los nuevos
  endpoints (`/perfil`, fuentes) antes de que el front los consuma.

---

## 2026-05-29 — Pivote a "Perfil Consolidado de Vehículo" (catálogo + schema + endpoint + frontend)

**Rama:** `main`. Plan de 3 pasos (catálogo → schema consolidado → frontend) + avance del
endpoint consolidado.

**Qué se hizo**
- **Paso 1 — Catálogo de fuentes:** nuevo `src/modules/consulta/services/catalogo_fuentes.py`,
  capa **estática** (no toca scraping). Enums `Prioridad`/`Origen`/`CategoriaDato`, dataclass
  `FuenteCatalogo` y `CATALOGO_FUENTES` con 7 fuentes (ANT, SRI, AMT, FGE oficiales/implementadas;
  EPMTSD, ConsultasEcuador, EcuadorLegalOnline pendientes). Helpers `fuentes_por_categoria`,
  `fuentes_implementadas`.
- **Paso 2 — Schema consolidado:** nuevo `src/modules/consulta/schemas.py` con
  `VehiculoConsolidadoResponse` (secciones `datos_basicos`, `identificacion` ofuscada,
  `valores_tributarios`, `multas_pendientes`, `novedades_legales`) + bloque `estado_fuentes`
  (enum `EstadoFuente` + `desde_estado_servicio`). Listas con `default_factory` para no romper
  con fuentes `en_proceso`.
- **Avance — agregación server-side:** nuevo `services/consolidador.py` (`consolidar_placa`) que
  mapea los dicts crudos por-fuente → `VehiculoConsolidadoResponse`. Router refactorizado: helper
  compartido `_obtener_fuentes_placa` y nuevo endpoint **`GET /consultar/{placa}/perfil`**
  (`response_model=VehiculoConsolidadoResponse`). El endpoint legacy `/consultar/{placa}` (vista
  por fuente) se conserva.
- **Paso 3 — Frontend (repo consulta-placas-web):** nuevo `PerfilVehiculo.tsx` orientado a la
  entidad (tarjeta del auto + secciones Valores/Multas/Legal, skeletons mientras AMT/FGE cargan,
  tablero de chips de fuentes con ⓘ para no oficiales). Migrado a consumir `/perfil` directo:
  `consultarPerfil` en `api.ts`, `page.tsx` fetchea el endpoint consolidado, `consolidar.ts`
  reducido a helpers de lectura (`hayFuentesEnProceso`, `estadoDeFuente`, `marcarFuenteEnProceso`).
  Eliminado `ResultadoConsulta.tsx` (huérfano).

**code-review (high) — 2 bugs corregidos**
- Infracciones AMT **pagadas/anuladas** se contaban como pendientes (se volcaba todo `categorias`);
  corregido a un ítem basado en `infracciones.pendientes` + `total_a_pagar`.
- Tarjeta principal daba veredicto "Sin pendientes" prematuro mientras AMT/FGE cargaban; ahora
  muestra estado neutral "Consultando…" si hay fuentes `en_proceso`.

**Verificación**
- Backend: `import main` registra `/consultar/{placa}/perfil`; `consolidar_placa` produce el JSON
  esperado con fuentes mixtas (completada/consulta_externa/en_proceso/error_fuente).
- Frontend: `tsc --noEmit` y `eslint` en verde.

**Pendientes**
- `identificacion` (chasis/motor) queda preparada pero vacía hasta integrar fuentes no oficiales
  (ConsultasEcuador) — recién ahí se cablea ofuscación en la vista.
- El gateo de secciones por scope del token de compra-venta sigue pendiente (heredado Fase 4).

---

## 2026-05-29 — Resiliencia worker (`error_fuente`) + caché de doble velocidad

**Rama:** `main`. Instrucciones del round-trip a Gemini (Instrucción 1 y 2; la 3 es del
frontend, fuera de este repo).

**Instrucción 1 — límite de reintentos + estado `error_fuente` (✅).** Hallazgo: la cola
**ya** cortaba en `fallido` tras `max_intentos`; el bucle real era **del cliente** (al fallar,
cache miss → re-encola en cada poll → reintento infinito). Solución en dos piezas:
- *Worker/cola*: estado terminal renombrado `fallido` → **`error_fuente`** (más claro para el
  frontend); tope subido a **4** intentos (`MAX_INTENTOS_DEFAULT`, fijado en `encolar_scraping`).
  Sin migración (ni `cola_scraping.estado` ni `consultas.estado` tienen CHECK).
- *API*: `consultar_via_worker` lee la cola (`fuente_en_error_reciente`) en cache miss; si el
  último trabajo quedó `error_fuente` dentro de una **ventana de enfriamiento (12h)**, devuelve
  `estado: error_fuente` (+`error`) **sin re-encolar**. El cliente deja de pollear.
- *Reintento manual*: `POST /consultar/{identificador}/reintentar/{fuente}` (AMT/FGE) reencola
  saltándose el enfriamiento. Resumen de `/consultar` y `/consultar-judicial` agregan
  `amt_error_fuente` / `fge_error_fuente`.

**Instrucción 2 — caché de doble velocidad (✅, ajustada al AS-IS).** `cache.py` define TTL por
naturaleza: transaccional **12h** (`CACHE_TTL_TRANSACCIONAL_MINUTOS`) y estático **90 días**
(`CACHE_TTL_ESTATICO_MINUTOS`). Decisión del usuario: *"la que mejor se ajuste al AS-IS y dé
espacio para el TO-BE"* → **TTL por fuente** (`ttl_para_fuente`): ANT/AMT/FGE = 12h. Como hoy
cada fuente es un solo blob y **ANT mezcla** características (estático) + citaciones
(transaccional), gana la frescura (12h). El TTL de 90 días queda **cableado y reservado** para
cuando, con clientes reales (TO-BE), el perfil del vehículo se cachee como entrada propia.
`obtener_consulta_reciente` ahora deriva el TTL de la fuente; el router dejó de pasar
`CACHE_TTL_MINUTOS` fijo.

**Doc:** AGENTS.md §6 (+estado `error_fuente`) y §8 (TTL doble); skill respuesta-api-estandar;
docs/arquitectura_hibrida.md (`fallido`→`error_fuente`, max 4); `.env.example` (+2 TTL).

**Pendiente (frontend, repo consulta-placas-web · Instrucción 3):** Skeleton + polling cada 4s
mientras `*_en_proceso`; al ver `*_error_fuente` detener polling y mostrar botón "Reintentar
conexión" → `POST /consultar/{identificador}/reintentar/{fuente}`. Tarjeta SRI con botón a
`url_consulta_sri`.

---

## 2026-05-29 — Rotación BD + gateo por scope + anti-captcha SRI (2Captcha)

**Rama:** `main` (Fase 0 ya mergeada). Cambios de esta sesión **sin commitear** al cierre.

**Paso 1 — Validar BD tras rotación de credenciales Neon (✅).** `alembic current` → `0009 (head)`
conectando con las credenciales nuevas del `.env`. Verificado solo en local; pendiente
actualizar la var en Render.

**Paso 2 — Gateo de visualización por `scope` en el enlace compartido (✅).**
- `src/modules/marketplace/schemas.py`: nuevas secciones `KilometrajeCompartido`,
  `MantenimientoCompartido`, `DuenoCompartido` y `VehiculoCompartidoSalida` (hereda de
  `VehiculoSalidaCompartida` → respuesta **retrocompatible**, agrega 3 claves opcionales).
  `desde_enlace(enlace)` lee `enlace.scope` e incluye cada sección solo si su flag es `True`;
  ordena cronológicamente. **Privacidad:** la cédula de dueños previos se ofusca aunque el
  scope habilite la sección (`171*******`).
- `src/modules/marketplace/routers/compartidos.py`: `GET /compartido/{token}` ahora responde
  `VehiculoCompartidoSalida`. No se tocó la migración `0008` ni el modelo.
- Verificado con 3 casos (scope vacío / solo kilometraje / completo).

**Paso 3 — Integración anti-captcha en SRI (proveedor 2Captcha) (⚠️ código listo, falta key + verificación live).**
- Nuevo `src/modules/consulta/services/captcha.py`: cliente 2Captcha con `httpx.AsyncClient`
  (in.php/res.php), key por `TWOCAPTCHA_API_KEY`, polling con timeout, excepciones
  `CaptchaNoConfigurado/SinSaldo/Timeout/Error`.
- `src/modules/consulta/services/sri.py`: si `hay_api_key()`, extrae el `sitekey` del DOM
  (no hardcodeado), resuelve e inyecta el token en `g-recaptcha-response` antes de enviar.
  **Gateado por la env key**: sin `TWOCAPTCHA_API_KEY` el flujo queda idéntico al previo
  (cero riesgo en prod). `.env.example` documenta la nueva var.
- **Verificación live (con key real, saldo $3):** la consulta a SRI devolvió
  `ERROR_CAPTCHA_UNSOLVABLE`. **Discovery del DOM de SRI confirmó: reCAPTCHA Enterprise v3**
  (`enterprise.js?render=...`, `grecaptcha.enterprise`, sin `data-sitekey` ni textarea),
  **sitekey `6LdukTQsAAAAAIcciM4GZq4ibeyplUhmWvlScuQE`**.
- **Implicación:** el scaffold actual (v2 + inyección de `g-recaptcha-response`) es el mecanismo
  equivocado. El rework pendiente para v3: (1) resolver con `version=v3` + `action` + `min_score`
  (el cliente `captcha.py` ya lo soporta); (2) **override de `grecaptcha.enterprise.execute`**
  vía init-script para que SRI tome el token; (3) descubrir el `action` real (se genera en JS al
  click, no está en el HTML estático). v3 enterprise es el caso más difícil; éxito no garantizado.
  La key quedó en `.env` local (gitignored), **no** en Render.

**Decisiones tomadas:** anti-captcha = **2Captcha**; worker correrá en **PC Windows + Task
Scheduler**; tarifario de tokens **se mantiene en 0** por ahora.

**Pendientes:** commitear esta sesión; fondear 2Captcha y verificar SRI live; script de
autoarranque del worker (Task Scheduler) cuando se decida desplegarlo.

### Actualización (misma sesión) — Worker desplegado + SRI: pivote a passthrough

- **Worker autoarranque (Task Scheduler):** hecho y verificado; commit `ab2b5df`. La tarea
  `ConsultaPlacasWorker` autoarranca al iniciar sesión. En la prueba el worker procesó
  **AMT/TBA3373 y FGE/TBA3373 → consulta_realizada** desde IP residencial.

- **SRI — investigación de la vía A (solver) y pivote:**
  - 2Captcha entrega token pero SRI (reCAPTCHA **Enterprise v3**, sitekey
    `6LdukTQsAAAAAIcciM4GZq4ibeyplUhmWvlScuQE`, action `matriculacion_vehicular_valores_pagar`)
    **rechaza el token** (score server-side). Probado e2e con el override de
    `grecaptcha.enterprise.execute`: token inyectado pero sin datos.
  - Comparativa de opciones con costos: A) Capsolver (~$3/1000, ~90% enterprise) + proxy
    residencial (~$1–7/GB) → barato/consulta pero **frágil**, sin garantía; B) **API oficial
    SRI** (convenio) → definitiva, $0, pero trámite; C) aceptar el vacío.
  - **Decisión:** **passthrough** (idea del usuario). SRI deja de scrapearse; `consultar_sri`
    devuelve `estado: consulta_externa` + `url_consulta` (instantáneo, sin Playwright/costo).
    El frontend mostrará un botón al portal del SRI (no se puede iframe:
    `X-Frame-Options: SAMEORIGIN`; tampoco se prefija la placa, SPA Angular).
  - El solver (vía A) queda **DORMIDO** en `_consultar_sri_scraping` + `captcha.py`
    (Capsolver + 2Captcha), reactivable. La vía **B (API oficial)** queda para después.
  - Nuevo estado de contrato **`consulta_externa`** (+ campo `url_consulta`) documentado en
    AGENTS.md §6 y el skill respuesta-api-estandar. Resumen de `/consultar` agrega
    `sri_consulta_externa` y `url_consulta_sri`.

**Pendiente frontend (repo consulta-placas-web):** tarjeta de SRI con botón que abre
`url_consulta` en pestaña nueva + placa visible para copiar.

---

## 2026-05-29 — Fase 0: mudanza a monolito modular (DDD)

**Rama:** `refactor/modulos` (no mergeada a `main` al cierre de la sesión).

**Qué se hizo**
- Reorganización del backend de "por tipo de archivo" (`routers/`, `models/`, `schemas/`,
  `services/`, `auth/`, `utils/` sueltos) a "por dominio de negocio" en `src/`:
  - `src/core/` ← `database.py`, `validators.py`, `ofuscacion.py`.
  - 5 módulos en `src/modules/`: `auth`, `tokens`, `consulta`, `vehiculos`, `marketplace`.
  - `src/registry.py` ← registro único de modelos para `Base.metadata` (lo importa Alembic).
- Endpoints públicos extraídos de `main.py` → `src/modules/consulta/routers/consulta.py`.
  `main.py` quedó limpio (solo `app` + CORS + `include_router`).
- Entrypoints (`main.py`, `run.py`, `worker.py`, `scripts/discover.py`) se mantienen en la raíz.
- Toda la mudanza con `git mv` (historial preservado). **Cero cambios de lógica**; solo imports
  y la extracción literal de endpoints. `alembic/versions/*` intactas; `env.py` solo cambió 2
  imports. BD de Neon no se tocó.
- Documentación: `CLAUDE.md` → `AGENTS.md` (+ shim `CLAUDE.md` con `@AGENTS.md` para auto-load);
  rutas viejas actualizadas en AGENTS.md y los 6 skills; nueva §1.1 (arquitectura modular +
  mapa skill→módulo); snapshot regenerado; se crea esta bitácora.

**Verificación (compuerta superada)**
- `import main` → 35 rutas; `src.registry` → 10 tablas en `Base.metadata`; `import worker` OK.
- `alembic heads` → `0009` (env.py resuelve, sin tocar la BD).
- Server arriba: `GET /health` `{"status":"ok"}`, `/consultar/!!!`→400, `/auth/me` sin token→401,
  `/marketplace`→200 (consultó Neon real).

**Pendientes**
- Commitear y decidir el merge de `refactor/modulos` → `main`.
- Limpieza de cohesión opcional (no hecha, tocaría lógica): separar `TransaccionToken` y los
  schemas de token de `auth` hacia `tokens`.
- Continuar el roadmap: Fase 1 (sellar `auth`+`vehiculos`), 2 (worker scraping), 3 (débito real
  de tokens + ofuscación en vista compartida), 4/5 (OCR end-to-end).
- Operativo heredado: desplegar `worker.py` en IP residencial EC; verificar OCR end-to-end;
  confirmar rotación de credencial de Neon.
