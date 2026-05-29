# Bitácora de trabajo — `consulta_placas_ec`

Registro cronológico de **lo que se hace en cada sesión** (decisiones, cambios, pendientes).
Complementa, no reemplaza:
- [AGENTS.md](../AGENTS.md) — fuente de verdad (reglas, fases, convenciones).
- [proyecto-snapshot.md](../proyecto-snapshot.md) — foto del estado AS-IS completo.

Entradas nuevas arriba (más reciente primero). Formato por entrada:
fecha · rama · qué se hizo · verificación · pendientes.

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
