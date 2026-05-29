# Proyecto Snapshot — consulta_placas_ec (backend)
**Generado:** 2026-05-29
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
- **Fase 0 — Refactor a monolito modular (DDD) [rama `refactor/modulos`, sin merge a `main`]:** todo el backend se reorganizó de "por tipo de archivo" (`routers/`, `models/`, `schemas/`, `services/`, `auth/`, `utils/` sueltos) a "por dominio de negocio" en `src/`. 5 módulos (`auth`, `tokens`, `consulta`, `vehiculos`, `marketplace`) + `src/core/` (database, validators, ofuscacion) + `src/registry.py` (registro único de modelos para Alembic). Movimiento puro con `git mv` (historial preservado) + arreglo de imports; **cero cambios de lógica, BD ni Alembic**. Endpoints públicos extraídos de `main.py` a `src/modules/consulta/routers/consulta.py`; `main.py` quedó limpio (app + CORS + include_router). Entrypoints (`main.py`, `run.py`, `worker.py`, `scripts/discover.py`) siguen en la raíz. Verificado: `import main` (35 rutas), `registry` (10 tablas), `alembic heads`, `/health`, validación 400/401 y `/marketplace` 200 contra Neon. **Documentación actualizada:** `CLAUDE.md` → `AGENTS.md` (+ shim), rutas nuevas en AGENTS.md, los 6 skills y `docs/`, nueva §1.1 (arquitectura + mapa skill→módulo), `docs/bitacora.md` creada, memoria actualizada. **Pendiente:** merge de `refactor/modulos` a `main`.
- **Fase 1 — Consultas públicas + caché:** endpoints `/consultar/{placa}`, `/consultar-judicial/{cedula}`, `/health`. ANT/SRI síncronos en la API; AMT/FGE ahora vía worker (ver abajo). SRI bloqueado por reCAPTCHA invisible. Caché en Postgres con TTL (solo cachea `consulta_realizada`/`sin_resultados`).
- **Fase 2 — Auth + dominio + deploy:** registro/login JWT, CRUD de vehículos (VIN/motor/chasis con 3 niveles de visibilidad y ofuscación), histórico de dueños, kilometraje monotónico. Desplegado en Render + Vercel.
- **Fase 3 — Billetera + Favoritos + Mantenimientos:** `saldo_tokens` (default 5, CHECK ≥ 0) + `transacciones_tokens` (auditoría); favoritos por placa (String, no FK); mantenimientos inmutables con validación monotónica. Migraciones `0004`–`0006`.
  - **Débito real de tokens (nuevo):** [services/tokens.py](services/tokens.py) — `debitar_tokens` atómico (no commitea; el caller controla la transacción), valida saldo, audita en `transacciones_tokens`, `SaldoInsuficiente → 422`. Cableado en `POST /vehiculos/{id}/compartir`. **Costo MVP = 0** (gratis, sin fricción de captación); subir `COSTO_COMPARTIR_TOKENS` activa el cobro.
- **Fase 4 — Compra-venta:** Marketplace público (`GET /marketplace`, `en_venta AND precio>0`, sin VIN/dueño) y token de enlace compartido (`POST /vehiculos/{id}/compartir` + `GET /compartido/{token}`, TTL ≤ 7 días, `scope` JSONB, 404 si no existe/expira). Migraciones `0007`–`0008`.
- **Fase 5 — OCR/foto (endpoint listo, live pendiente):** `POST /consultar-foto` ([routers/ocr.py](routers/ocr.py)) recibe `UploadFile`, extrae la placa con Cloud Vision ([services/vision.py](services/vision.py)) y encadena con `GET /consultar/{placa}`. Caminos 400/503 probados; parser probado contra muestras; lectura acotada al tope. **No verificado end-to-end** (requiere API key real + foto). Falta integrar al frontend.
- **Worker híbrido — código completo, falta desplegar:**
  - `cola_scraping` ([models/cola_scraping.py](models/cola_scraping.py)) + migración `0009` **aplicada a Neon** (índice único parcial para idempotencia).
  - `worker.py` pull-only: `FOR UPDATE SKIP LOCKED`, backoff (30/60/120s), rescate de zombis, apagado limpio. Reusa `services/` sin modificarlos.
  - **API cableada** ([services/cola.py](services/cola.py) + `main.py`): AMT/FGE ya no se scrapean en la API; en cache miss encolan (idempotente) y devuelven `estado: en_proceso` (datos null) dentro del mismo 200. ANT/SRI síncronos. Flags `amt_en_proceso`/`fge_en_proceso` en el resumen. Probado contra Neon (encolado + idempotencia).

### 🔄 En progreso / pendiente acotado
- **Desplegar `worker.py`** en una máquina con IP residencial EC (decisión operativa: PC/Raspberry; sin definir). Hasta entonces, AMT/FGE quedan en `en_proceso` indefinido porque nadie procesa la cola.
- **Verificar OCR end-to-end** (API key Vision real + foto) e integrarlo al frontend.
- **`scope` del enlace:** se persiste y valida, pero la vista compartida solo muestra características del auto; el gateo de kilometraje/mantenimientos/dueños se cableará cuando se agreguen a `VehiculoSalidaCompartida`.
- **Precio en tokens:** definir cuántos tokens cuesta el enlace de compra-venta y la consulta OCR (hoy ambos efectivamente gratis; mecanismo de débito listo).

### ⚠️ Problemas / deuda técnica / decisiones
- **SRI bloqueado por reCAPTCHA Enterprise invisible** (local y cloud). El worker híbrido **no** lo resuelve; requiere proveedor anti-captcha (2Captcha/Anti-Captcha — sin decidir, sin cuenta/fondos/API key) o API oficial.
- **AMT y FGE bloqueados en cloud por IP de datacenter** (Render). El worker híbrido con IP residencial es la mitigación; código listo, falta el despliegue físico.
- **Decisión 2026-05-28:** scraping cloud = worker híbrido + tabla de cola en Postgres (no broker externo). OCR Fase 5 = Cloud Vision (API externa, no Tesseract). Costo de compartir enlace = 0 en MVP (no frenar captación; palanca de ingreso preservada para activar después).
- **Seguridad pendiente:** confirmar rotación de la contraseña de Neon (quedó expuesta en historial de chat previo). El `.env` local conecta OK a Neon; vive solo en `.env` (gitignored) y dashboard de Render (`sync: false`).
- **Sincronía remoto:** `main` está al día con `origin/main` (todo pusheado, incluido OCR, worker, cola y débito de tokens).

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
- **Skills del proyecto** (`.claude/skills/`): `agregar-fuente-consulta`, `desplegar-mvp`, `modelo-dominio-vehiculo`, `respuesta-api-estandar` (incluye estado `en_proceso`), `scraping-respetuoso`, `validacion-datos-ec`.
- **Diagramas vivos** en `docs/arquitectura.md`: topología con worker cableado, secuencia auth, secuencia consulta (nota worker), secuencia OCR §2c, ER con `cola_scraping`, roadmap. Diseño híbrido en `docs/arquitectura_hibrida.md`.

## 6. Decisiones técnicas tomadas

- **Arquitectura modular (DDD), 2026-05-29:** un módulo = una capacidad de negocio (no una tabla). 5 módulos hoy; techo del producto final ~6–7 (OCR vive dentro de `consulta`; pagos crecerá `tokens`). App y web son clientes de la misma API → **no** suman módulos al backend. Modelos compartidos: `Usuario`+`TransaccionToken` quedan juntos en `auth` (tokens los importa); schemas de token en `auth.schemas` (split de cohesión es limpieza opcional futura, no se hizo para no tocar lógica).
- **Migraciones manuales** (no autogenerate a ciegas), nombre descriptivo por archivo.
- **Separación CRUD ↔ scraping:** el CRUD del MVP toca solo la BD propia; nunca invoca Playwright. La cola es exclusiva del pipeline de scraping.
- **Contrato de error:** 422 validación de negocio (incl. saldo insuficiente), 404 propiedad (no 403), 400 input, 409 conflicto, 201/204 create/delete; nunca 500 por fuente externa. OCR: fallo de lectura → 400; sin API key → 503. AMT/FGE encolados → 200 con `estado: en_proceso` por fuente (no 202, para no romper el agregado).
- **Idioma español estricto** en tablas, columnas, rutas y variables.
- **Privacidad por niveles:** `completo` (dueño), `origen` (token), `oculto` (público). VIN/motor/chasis nunca completos a terceros.
- **OCR:** Cloud Vision REST + `httpx` + API key (no SDK, no Tesseract).
- **Worker híbrido:** comunicación API↔worker por tabla de cola en Postgres con `FOR UPDATE SKIP LOCKED`, índice único parcial (idempotencia), backoff exponencial y rescate de zombis. Reusa los servicios de scraping sin modificarlos.
- **Tokens:** `debitar_tokens` no commitea (atomicidad controlada por el caller); `monto<=0` es no-op; costo de compartir = 0 en MVP.

## 7. Últimos cambios (git log)

```
7865e53 docs: snapshot tras cablear worker híbrido y débito de tokens
ceb593a feat: débito transaccional de tokens en creación de enlace compartido
d740d2c feat: cablear worker híbrido - AMT/FGE vía cola_scraping (en_proceso)
719e079 docs: regenerar snapshot tras Fase 5 OCR y worker híbrido
16c5e25 feat: worker híbrido - cola en Postgres, modelo y migración 0009
```
**Rama actual:** `refactor/modulos` (Fase 0 modular, **sin commitear ni mergear** todavía;
60 archivos en staging = movimientos `git mv` + imports). `main` sigue al día con `origin/main`
e intacto (de ahí despliega Render). Neon en revisión `0009`.

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

1. **Desplegar `worker.py`** en una máquina con IP residencial EC (definir cuál: PC siempre encendida / Raspberry Pi), con `DATABASE_URL` de Neon y arranque persistente (systemd / Programador de tareas). Sin esto, AMT/FGE quedan en `en_proceso`.
2. **Confirmar rotación de la contraseña de Neon** y que `.env` (local + Render) tenga la vigente.
3. **Verificar OCR end-to-end:** configurar `GOOGLE_VISION_API_KEY`, probar `POST /consultar-foto` con foto real, integrar al frontend (subir foto → consulta) y manejar `en_proceso` (polling) en la UI.
4. **Definir precios en tokens** (enlace de compra-venta, consulta OCR) y activar el cobro subiendo las constantes; cablear débito también en OCR si se decide cobrarlo.
5. **Decidir proveedor anti-captcha para SRI** (2Captcha/Anti-Captcha): crear cuenta, fondear, generar API key e integrar en `services/sri.py`.
6. **Frontend:** consumir flags `amt_en_proceso`/`fge_en_proceso` y `estado: en_proceso` para mostrar "cargando" + reintento en esas fuentes.
```
