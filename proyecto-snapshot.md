# Proyecto Snapshot — consulta_placas_ec (backend)
**Generado:** 2026-05-29 (rev. resiliencia worker + caché doble velocidad + frontend Instrucción 3)
**Herramienta origen:** Claude Code / VS Code
**Propósito de este archivo:** Subir a Gemini para continuar planificación TO-BE

---

## 1. ¿Qué es este proyecto?

Backend de una plataforma (móvil + web) para que cualquier persona en Ecuador conozca el **estado integral de un vehículo** a partir de su placa, sus características o una foto. Agrega información de fuentes oficiales (ANT, SRI, AMT Quito, Fiscalía/FGE) y permite a usuarios autenticados llevar el historial privado del auto (kilometraje, dueños, mantenimientos), una billetera de tokens, favoritos y un modo compra-venta (marketplace público + enlaces temporales). Este repo es el **backend FastAPI + Playwright**; el frontend Next.js vive en un repo separado (`consulta-placas-web`).

## 2. Stack tecnológico

- **Lenguaje:** Python 3.11+ (prod: imagen Docker Playwright con Python 3.10).
- **API:** FastAPI con **arquitectura de monolito modular (DDD)**: el código vive en `src/modules/<dominio>/` (auth, tokens, consulta, vehiculos, marketplace) + `src/core/` (infra y utils compartidos). `main.py` solo monta routers. Pydantic 2 para validación/serialización.
- **Scraping:** Playwright async (Chromium) en `src/modules/consulta/services/<fuente>.py`.
- **OCR:** Google Cloud Vision vía REST (`images:annotate`, TEXT_DETECTION) con `httpx` + API key (`GOOGLE_VISION_API_KEY`). Sin SDK pesado.
- **BD:** PostgreSQL 16 en **Neon** (externa, serverless). JSONB para respuestas crudas, `scope` de enlaces y `payload` de la cola.
- **ORM/Migraciones:** SQLAlchemy 2 + Alembic (migraciones **manuales**, `0001`–`0009`).
- **Auth:** `passlib[bcrypt]` (con `bcrypt<4.0` pineado) + `python-jose` (JWT HS256).
- **Worker híbrido:** proceso `worker.py` standalone (sin FastAPI), coordina vía tabla de cola en Postgres (sin broker externo).
- **Deploy:** Docker en Render (backend) + Vercel (frontend). Cron externo (UptimeRobot) contra `/health` por el cold start del free tier.

## 3. Estado actual — AS-IS

### ✅ Completado
- **Fase 0 — Refactor a monolito modular (DDD) [mergeado a `main` y pusheado, commit `6e33ca2`]:** todo el backend se reorganizó de "por tipo de archivo" (`routers/`, `models/`, `schemas/`, `services/`, `auth/`, `utils/` sueltos) a "por dominio de negocio" en `src/`. 5 módulos (`auth`, `tokens`, `consulta`, `vehiculos`, `marketplace`) + `src/core/` (database, validators, ofuscacion) + `src/registry.py` (registro único de modelos para Alembic). Movimiento puro con `git mv` (historial preservado) + arreglo de imports; **cero cambios de lógica, BD ni Alembic**. Endpoints públicos extraídos de `main.py` a `src/modules/consulta/routers/consulta.py`; `main.py` quedó limpio (app + CORS + include_router). Entrypoints (`main.py`, `run.py`, `worker.py`, `scripts/discover.py`) siguen en la raíz. Verificado: `import main` (35 rutas), `registry` (10 tablas), `alembic heads`, `/health`, validación 400/401 y `/marketplace` 200 contra Neon. **Documentación actualizada:** `CLAUDE.md` → `AGENTS.md` (+ shim), rutas nuevas en AGENTS.md, los 6 skills y `docs/`, nueva §1.1 (arquitectura + mapa skill→módulo), `docs/bitacora.md` creada, memoria actualizada. **Ya en producción:** merge fast-forward a `main` + push → Render redesplegando con la estructura nueva (entrypoints `main:app` sin cambios).
- **Fase 1 — Consultas públicas + caché:** endpoints `/consultar/{placa}`, `/consultar-judicial/{cedula}`, `/health`. ANT síncrono en la API; AMT/FGE vía worker (ver abajo); **SRI por passthrough** (`consulta_externa` + `url_consulta`, ver decisiones). Caché en Postgres con TTL (solo cachea `consulta_realizada`/`sin_resultados`).
- **Fase 2 — Auth + dominio + deploy:** registro/login JWT, CRUD de vehículos (VIN/motor/chasis con 3 niveles de visibilidad y ofuscación), histórico de dueños, kilometraje monotónico. Desplegado en Render + Vercel.
- **Fase 3 — Billetera + Favoritos + Mantenimientos:** `saldo_tokens` (default 5, CHECK ≥ 0) + `transacciones_tokens` (auditoría); favoritos por placa (String, no FK); mantenimientos inmutables con validación monotónica. Migraciones `0004`–`0006`.
  - **Débito real de tokens (nuevo):** [services/tokens.py](services/tokens.py) — `debitar_tokens` atómico (no commitea; el caller controla la transacción), valida saldo, audita en `transacciones_tokens`, `SaldoInsuficiente → 422`. Cableado en `POST /vehiculos/{id}/compartir`. **Costo MVP = 0** (gratis, sin fricción de captación); subir `COSTO_COMPARTIR_TOKENS` activa el cobro.
- **Fase 4 — Compra-venta:** Marketplace público (`GET /marketplace`, `en_venta AND precio>0`, sin VIN/dueño) y token de enlace compartido (`POST /vehiculos/{id}/compartir` + `GET /compartido/{token}`, TTL ≤ 7 días, `scope` JSONB, 404 si no existe/expira). Migraciones `0007`–`0008`.
  - **Gateo por scope (nuevo, commit `0bb6637`):** `GET /compartido/{token}` ahora respeta el `scope`: `VehiculoCompartidoSalida` agrega kilometraje/mantenimientos/duenos_historico como secciones opcionales, incluidas solo si el flag está en `True`. Cédula de dueños previos ofuscada. Retrocompatible.
- **Autoarranque del worker (nuevo, commit `ab2b5df`):** Task Scheduler en Windows (modo "solo con sesión iniciada"), `scripts/worker_*.ps1` + `docs/worker.md`. Tarea `ConsultaPlacasWorker` instalada y verificada (procesó AMT/FGE reales desde IP residencial).
- **SRI por passthrough (nuevo, commit `9563cac`):** SRI usa reCAPTCHA Enterprise v3 (rechaza tokens de solver). `consultar_sri` devuelve `estado: consulta_externa` + `url_consulta` (instantáneo, sin Playwright ni costo); el frontend mostrará un botón al portal. Solver (Capsolver/2Captcha) DORMIDO en `_consultar_sri_scraping`/`captcha.py`.
- **Fase 5 — OCR/foto (endpoint listo, live pendiente):** `POST /consultar-foto` ([routers/ocr.py](routers/ocr.py)) recibe `UploadFile`, extrae la placa con Cloud Vision ([services/vision.py](services/vision.py)) y encadena con `GET /consultar/{placa}`. Caminos 400/503 probados; parser probado contra muestras; lectura acotada al tope. **No verificado end-to-end** (requiere API key real + foto). Falta integrar al frontend.
- **Worker híbrido — operativo:**
  - `cola_scraping` ([src/modules/consulta/models/cola_scraping.py](src/modules/consulta/models/cola_scraping.py)) + migración `0009` **aplicada a Neon** (índice único parcial para idempotencia).
  - `worker.py` pull-only: `FOR UPDATE SKIP LOCKED`, backoff (30/60/120s), rescate de zombis. Reusa `services/` sin modificarlos.
  - **API cableada**: AMT/FGE no se scrapean en la API; en cache miss encolan (idempotente) y devuelven `estado: en_proceso` (datos null) dentro del mismo 200. Flags `amt_en_proceso`/`fge_en_proceso` en el resumen.
  - **Autoarranque** vía Task Scheduler (`ConsultaPlacasWorker`, modo logon) instalado en la PC del usuario; procesó AMT/FGE reales desde IP residencial.
- **Resiliencia del worker + estado `error_fuente` (nuevo, commits `2b0f40f`/`ad9ff42`):** al agotar `max_intentos` (subido a **4**) el trabajo queda terminal en `error_fuente` (antes `fallido`) y **no vuelve a la cola** — corta el bucle de polling del cliente ante una fuente caída. La API lee la cola en cache miss (`fuente_en_error_reciente`) y devuelve `estado: error_fuente` durante una ventana de enfriamiento (12h) en vez de re-encolar a ciegas. Nuevo `POST /consultar/{identificador}/reintentar/{fuente}` (AMT/FGE; FGE acepta placa o cédula) para el botón "Reintentar". Resumen suma `amt_error_fuente`/`fge_error_fuente`. Sin migración (ninguna columna `estado` tiene CHECK).
- **Caché de doble velocidad (nuevo, commits `2b0f40f`/`d162370`):** TTL por naturaleza del dato en [src/modules/consulta/services/cache.py](src/modules/consulta/services/cache.py): transaccional **12h** (`CACHE_TTL_TRANSACCIONAL_MINUTOS`), estático **90d** (`CACHE_TTL_ESTATICO_MINUTOS`). AS-IS: cada fuente es un blob único y ANT mezcla ambos → se rige por 12h (gana la frescura); el TTL estático queda **reservado** para cuando, con clientes reales (TO-BE), el perfil del vehículo se cachee como entrada propia. Vars declaradas en `render.yaml`.
- **Frontend Instrucción 3 — interfaz reactiva (repo `consulta-placas-web`, commit `2272926`, desplegado en Vercel):** `ResultadoConsulta` pasa a client component con **polling silencioso cada 4s** mientras AMT/FGE estén `en_proceso`; **Skeleton** animado por fuente; tarjeta `error_fuente` con botón "Reintentar conexión con la fuente" → llama al endpoint de reintento y reanuda el polling; SRI `consulta_externa` → botón al portal oficial. Sin dependencias nuevas (fetch + hooks). `next build` y typecheck OK.

### 🔄 En progreso / pendiente acotado
- **Frontend (repo `consulta-placas-web`):** ✅ polling `en_proceso` (4s) + Skeletons, ✅ `error_fuente` + botón reintentar, ✅ botón SRI `consulta_externa`. **Pendiente:** integración de OCR (subir foto → consulta).
- **Verificar OCR end-to-end** (API key Vision real + foto).
- **Prueba de humo en vivo** del ciclo `en_proceso → error_fuente → reintentar` con el worker corriendo y una fuente caída real.
- **Precio en tokens:** definir cuántos tokens cuesta el enlace de compra-venta y la consulta OCR (hoy ambos en 0; mecanismo de débito listo).
- **SRI vía B (definitiva):** evaluar convenio / API oficial del SRI para el valor tributario (la vía A —solver— quedó dormida).
- **Lint preexistente** en el frontend (`Header.tsx`, `mi-garage/page.tsx`): 2 errores + 1 warning de `react-hooks` ajenos a los cambios de hoy; no bloquean el build.

### ⚠️ Problemas / deuda técnica / decisiones
- **SRI = reCAPTCHA Enterprise v3 (score-based).** Probado: 2Captcha/Capsolver entregan token pero SRI lo rechaza por score; no se puede iframe (`X-Frame-Options: SAMEORIGIN`). **Decisión: passthrough** (`consulta_externa` + `url_consulta`, botón al portal oficial). Solver dormido en `_consultar_sri_scraping`/`captcha.py`. Vía definitiva = API oficial (B), pendiente.
- **AMT y FGE bloqueados en cloud por IP de datacenter** (Render). Mitigado con el worker híbrido residencial (ya operativo con autoarranque).
- **Decisiones:** worker = cola en Postgres (no broker); OCR = Cloud Vision; costo de compartir/OCR = 0 en MVP; anti-captcha evaluado (2Captcha/Capsolver) y descartado para SRI por el v3 enterprise.
- **Seguridad pendiente:** rotar la contraseña de Neon y **la API key de 2Captcha** (ambas expuestas en chat). Las keys viven solo en `.env` (gitignored) y dashboards de prod.
- **Sincronía remoto:** ambos repos en `main` al día con `origin/main`. Backend hasta `ad9ff42` (Render redesplegando); frontend hasta `2272926` (Vercel redesplegando).

## 4. Estructura de archivos actual

```
consulta_placas_ec/
├── main.py                 # FastAPI: solo app + CORS + include_router de cada módulo
├── run.py                  # launcher API (WindowsProactorEventLoopPolicy); lanza "main:app"
├── worker.py               # worker híbrido pull-only (cola_scraping); entrypoint en raíz
├── scripts/discover.py     # descubrimiento de selectores para scraping
├── src/
│   ├── registry.py         # importa TODOS los modelos → Base.metadata (lo usa Alembic)
│   ├── core/               # database.py (engine/Base/env), validators.py, ofuscacion.py
│   └── modules/
│       ├── auth/           # models(Usuario,TransaccionToken), schemas, security, dependencies, router
│       ├── tokens/         # service.py (debitar_tokens), router.py
│       ├── consulta/       # routers/{consulta,ocr} · services/{ant,sri,amt,fiscalia,cache,cola,vision} · models/{consulta,cola_scraping}
│       ├── vehiculos/      # models/ · schemas/ · routers/{vehiculos,duenos,kilometraje,mantenimientos,favoritos}
│       └── marketplace/    # models(enlace_compartido), schemas, routers/{marketplace,compartidos}
├── alembic/                # env.py (→ import src.registry) + versions/ 0001..0009 (manuales, intactas)
├── docs/                   # arquitectura.md (Mermaid), despliegue.md, arquitectura_hibrida.md
├── Dockerfile · render.yaml · requirements.txt
└── .claude/skills/         # 6 skills del proyecto (refs a rutas viejas: actualizar)
```

**Dependencias entre módulos (interfaz pública, dirección permitida):** `tokens`→`auth`,
`vehiculos`→`auth`, `marketplace`→`vehiculos`+`tokens`, `consulta`→`core`; todos→`core`.
Regla de oro: los módulos se hablan por funciones de servicio expuestas, no importando
internals ajenos fuera de esa dirección.

## 5. Skills y herramientas configuradas

- **AGENTS.md** (proyecto; renombrada de CLAUDE.md, con shim `@AGENTS.md`): fuente de verdad, fases, reglas de negocio 10.x, §1.1 arquitectura modular + mapa skill→módulo.
- **Skills del proyecto** (`.claude/skills/`): `agregar-fuente-consulta`, `desplegar-mvp`, `modelo-dominio-vehiculo`, `respuesta-api-estandar` (incluye estados `en_proceso`, `error_fuente`, `consulta_externa`), `scraping-respetuoso`, `validacion-datos-ec`.
- **Diagramas vivos** en `docs/arquitectura.md`: topología con worker cableado, secuencia auth, secuencia consulta (nota worker), secuencia OCR §2c, ER con `cola_scraping`, roadmap. Diseño híbrido en `docs/arquitectura_hibrida.md`.

## 6. Decisiones técnicas tomadas

- **Arquitectura modular (DDD), 2026-05-29:** un módulo = una capacidad de negocio (no una tabla). 5 módulos hoy; techo del producto final ~6–7 (OCR vive dentro de `consulta`; pagos crecerá `tokens`). App y web son clientes de la misma API → **no** suman módulos al backend. Modelos compartidos: `Usuario`+`TransaccionToken` quedan juntos en `auth` (tokens los importa); schemas de token en `auth.schemas` (split de cohesión es limpieza opcional futura, no se hizo para no tocar lógica).
- **Migraciones manuales** (no autogenerate a ciegas), nombre descriptivo por archivo.
- **Separación CRUD ↔ scraping:** el CRUD del MVP toca solo la BD propia; nunca invoca Playwright. La cola es exclusiva del pipeline de scraping.
- **Contrato de error:** 422 validación de negocio (incl. saldo insuficiente), 404 propiedad (no 403), 400 input, 409 conflicto, 201/204 create/delete; nunca 500 por fuente externa. OCR: fallo de lectura → 400; sin API key → 503. AMT/FGE encolados → 200 con `estado: en_proceso` por fuente (no 202, para no romper el agregado); fuente caída tras 4 intentos → `estado: error_fuente` (terminal, con enfriamiento de 12h y endpoint de reintento). Caché: nunca guarda `error`/`bloqueado_captcha`/`error_fuente`.
- **Idioma español estricto** en tablas, columnas, rutas y variables.
- **Privacidad por niveles:** `completo` (dueño), `origen` (token), `oculto` (público). VIN/motor/chasis nunca completos a terceros.
- **OCR:** Cloud Vision REST + `httpx` + API key (no SDK, no Tesseract).
- **Worker híbrido:** comunicación API↔worker por tabla de cola en Postgres con `FOR UPDATE SKIP LOCKED`, índice único parcial (idempotencia), backoff exponencial y rescate de zombis. Reusa los servicios de scraping sin modificarlos.
- **Tokens:** `debitar_tokens` no commitea (atomicidad controlada por el caller); `monto<=0` es no-op; costo de compartir = 0 en MVP.

## 7. Últimos cambios (git log)

Backend (`consulta_placas_ec`):
```
ad9ff42 fix: reintentar FGE acepta placa o cédula según el flujo de origen
d162370 chore: declarar CACHE_TTL_TRANSACCIONAL/ESTATICO_MINUTOS en render.yaml
2b0f40f feat: resiliencia worker (error_fuente) + caché de doble velocidad
1e29e5e docs: regenerar snapshot (gateo scope, worker autostart, SRI passthrough)
9563cac feat: SRI por passthrough (consulta_externa) + solver dormido
```
Frontend (`consulta-placas-web`):
```
2272926 feat: polling de fuentes asincronas (AMT/FGE) + reintento + SRI passthrough
130c683 MVP visual: landing comercial + consulta publica + auth + mi-garage + precios
```
**Rama actual:** `main` en ambos repos, **al día con `origin/main`**. Backend última `ad9ff42`;
frontend última `2272926`. Render y Vercel redesplegando. Neon en revisión `0009` (sin cambios
de schema desde la Fase 0; `error_fuente`/TTL no requirieron migración).

## 8. Para continuar en Gemini — instrucciones

> Eres un asistente de arquitectura y planificación de software.
> Tienes el contexto completo del proyecto arriba.
> El usuario quiere planificar el TO-BE: próximos pasos, mejoras, nuevas funcionalidades.
> Cuando el usuario describa qué quiere hacer, responde con:
> 1. Evaluación de impacto sobre lo existente
> 2. Archivos a crear o modificar
> 3. Skills de Claude Code a activar
> 4. Estructura sugerida de la solución
> 5. Posibles riesgos o dependencias

## 9. Próximos pasos sugeridos

1. **Prueba de humo en vivo** del ciclo asíncrono: worker corriendo + una fuente caída → confirmar `en_proceso` → Skeleton → `error_fuente` → botón reintentar → `consulta_realizada` en la UI real.
2. **Rotar** la contraseña de Neon y la API key de 2Captcha (ambas expuestas en chat); confirmar que `.env` (local + Render) tenga las vigentes.
3. **Verificar OCR end-to-end:** configurar `GOOGLE_VISION_API_KEY`, probar `POST /consultar-foto` con foto real e **integrar al frontend** (subir foto → consulta) — único pendiente del frontend.
4. **Definir precios en tokens** (enlace de compra-venta, consulta OCR) y activar el cobro subiendo las constantes; cablear débito también en OCR si se decide cobrarlo.
5. **SRI vía B (definitiva):** evaluar convenio / API oficial del SRI (la vía A —solver Capsolver/2Captcha— quedó dormida por el reCAPTCHA Enterprise v3).
6. **Limpiar lint preexistente** del frontend (`Header.tsx`, `mi-garage/page.tsx`) si se quiere CI verde.
```
