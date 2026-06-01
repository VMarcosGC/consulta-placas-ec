# Bitácora de trabajo — `consulta_placas_ec`

Registro cronológico de **lo que se hace en cada sesión** (decisiones, cambios, pendientes).
Complementa, no reemplaza:
- [AGENTS.md](../AGENTS.md) — fuente de verdad (reglas, fases, convenciones).
- [proyecto-snapshot.md](../proyecto-snapshot.md) — foto del estado AS-IS completo.

Entradas nuevas arriba (más reciente primero). Formato por entrada:
fecha · rama · qué se hizo · verificación · pendientes.

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
