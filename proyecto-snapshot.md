# Proyecto Snapshot — consulta_placas_ec (backend)
**Generado:** 2026-05-28
**Herramienta origen:** Claude Code / VS Code
**Propósito de este archivo:** Subir a Gemini para continuar planificación TO-BE

---

## 1. ¿Qué es este proyecto?

Backend de una plataforma (móvil + web) para que cualquier persona en Ecuador conozca el **estado integral de un vehículo** a partir de su placa, sus características o una foto. Agrega información de fuentes oficiales (ANT, SRI, AMT Quito, Fiscalía/FGE) y permite a usuarios autenticados llevar el historial privado del auto (kilometraje, dueños, mantenimientos), una billetera de tokens, favoritos y un modo compra-venta (marketplace público + enlaces temporales). Este repo es el **backend FastAPI + Playwright**; el frontend Next.js vive en un repo separado (`consulta-placas-web`).

## 2. Stack tecnológico

- **Lenguaje:** Python 3.11+ (prod: imagen Docker Playwright con Python 3.10).
- **API:** FastAPI con routers en `routers/`; Pydantic 2 para validación/serialización.
- **Scraping:** Playwright async (Chromium) en `services/<fuente>.py`.
- **OCR:** Google Cloud Vision vía REST (`images:annotate`, TEXT_DETECTION) con `httpx` + API key (`GOOGLE_VISION_API_KEY`). Sin SDK pesado.
- **BD:** PostgreSQL 16 en **Neon** (externa, serverless). JSONB para respuestas crudas, `scope` de enlaces y `payload` de la cola.
- **ORM/Migraciones:** SQLAlchemy 2 + Alembic (migraciones **manuales**, `0001`–`0009`).
- **Auth:** `passlib[bcrypt]` (con `bcrypt<4.0` pineado) + `python-jose` (JWT HS256).
- **Worker híbrido:** proceso `worker.py` standalone (sin FastAPI), coordina vía tabla de cola en Postgres (sin broker externo).
- **Deploy:** Docker en Render (backend) + Vercel (frontend). Cron externo (UptimeRobot) contra `/health` por el cold start del free tier.

## 3. Estado actual — AS-IS

### ✅ Completado
- **Fase 1 — Consultas públicas + caché:** endpoints `/consultar/{placa}`, `/consultar-judicial/{cedula}`, `/health`. ANT/AMT/FGE funcionan en local; SRI bloqueado por reCAPTCHA invisible. Caché en Postgres con TTL (solo cachea `consulta_realizada`/`sin_resultados`).
- **Fase 2 — Auth + dominio + deploy:** registro/login JWT, CRUD de vehículos (VIN/motor/chasis con 3 niveles de visibilidad y ofuscación), histórico de dueños, kilometraje monotónico. Desplegado en Render + Vercel.
- **Fase 3 — Billetera + Favoritos + Mantenimientos:** `saldo_tokens` (default 5, CHECK ≥ 0) + `transacciones_tokens` (auditoría); favoritos por placa (String, no FK); mantenimientos inmutables con validación monotónica. Migraciones `0004`–`0006`. BD migrada a Neon.
- **Fase 4 — Compra-venta:** Marketplace público y token de enlace compartido. Migraciones `0007`–`0008` aplicadas a Neon.
  - `GET /marketplace` (anónimo): lista autos con `en_venta = True AND precio_venta_usd > 0`, no eliminados. `selectinload(mantenimientos)` para derivar `total_mantenimientos` sin N+1. Salida `VehiculoSalidaMarketplace`: VIN nivel `oculto` (solo país), **sin nombre del dueño**.
  - `POST /vehiculos/{id}/compartir` (dueño, TTL ≤ 7 días) + `GET /compartido/{token}` (público) → `VehiculoSalidaCompartida` ofuscado. `token` único (UK), `scope` JSONB opt-in. Token inexistente/expirado → 404.

### 🔄 En progreso / pendiente acotado
- **Fase 5 — OCR/foto (endpoint implementado, live pendiente):** `POST /consultar-foto` ([routers/ocr.py](routers/ocr.py)) recibe `UploadFile`, extrae la placa con Cloud Vision ([services/vision.py](services/vision.py)) y encadena con `GET /consultar/{placa}`. Validado: caminos 400 (no-imagen / vacía / > 8 MB / sin placa) y 503 (sin API key) con TestClient; parser de placa probado contra 7 muestras de texto crudo; lectura acotada al tope y detección de error embebido del API. **No verificado end-to-end** el camino feliz (requiere API key real de Vision + BD en vivo). Falta integrarlo al frontend.
- **Worker híbrido (infraestructura lista, sin cablear a la API):**
  - ✅ `cola_scraping` ([models/cola_scraping.py](models/cola_scraping.py)) + migración manual `0009`: estados (`pendiente`/`en_proceso`/`completado`/`fallido`), `intentos`/`max_intentos`, `payload` JSONB, `disponible_en`/`tomado_en`, e **índice único parcial** para idempotencia.
  - ✅ `worker.py` pull-only: `FOR UPDATE SKIP LOCKED`, backoff exponencial (30/60/120s), rescate de zombis, apagado limpio, manejo exhaustivo de excepciones. Reusa `services/` sin modificarlos. Importa y pasa sanity checks; **no probado end-to-end** (requiere trabajos encolados + IP residencial).
  - ⏳ **Falta:** que la API encole en `cola_scraping` ante cache miss de AMT/FGE y devuelva el estado `en_proceso`; dejar de instanciar Chromium para esas fuentes en Render. Diseño en [docs/arquitectura_hibrida.md](docs/arquitectura_hibrida.md).
- **Débito real de tokens:** el servicio que descuenta saldo (422 por saldo insuficiente) se implementará junto a la primera función de pago. Hoy la billetera es solo lectura + auditoría inicial.
- **`scope` del enlace:** se persiste y valida, pero la vista compartida actual solo muestra características del auto; el gateo de kilometraje/mantenimientos/dueños se cableará cuando se agreguen a `VehiculoSalidaCompartida`.

### ⚠️ Problemas / deuda técnica / decisiones
- **SRI bloqueado por reCAPTCHA Enterprise invisible** (local y cloud). No es bug; requiere anti-captcha (2Captcha/Anti-Captcha — proveedor sin decidir) o API oficial. El worker híbrido **no** lo resuelve.
- **AMT y FGE bloqueados en cloud por IP de datacenter** (Render). Funcionan desde IP residencial (local). El worker híbrido es la mitigación elegida.
- **Decisión 2026-05-28:** scraping cloud = **worker híbrido con IP residencial**, comunicado vía **tabla de cola en Postgres/Neon** (no Redis/RabbitMQ — cero infra nueva). Infra ya implementada; falta cablear a la API. La **ubicación física** del worker (PC/Raspberry con IP residencial EC) es decisión operativa pendiente; el código es agnóstico.
- **Decisión 2026-05-28:** OCR de Fase 5 usa **Google Cloud Vision (API externa)**, no pytesseract local — mejor precisión y imagen Docker liviana, a cambio de costo (~$1.5/1000) y una env var de credencial.
- **Seguridad pendiente:** rotar la contraseña de Neon (quedó expuesta en historial de chat de una sesión previa). Vive solo en `.env` (gitignored) y en el dashboard de Render (`sync: false`).
- **Nada pusheado al remoto:** los commits de Fases 3, 4 y de esta sesión (OCR + worker) están solo en local.

## 4. Estructura de archivos actual

```
consulta_placas_ec/
├── main.py                 # FastAPI: endpoints públicos + include_router (incluye ocr)
├── run.py                  # launcher API (WindowsProactorEventLoopPolicy)
├── worker.py               # worker híbrido pull-only (cola_scraping) ← NUEVO
├── database.py             # engine, SessionLocal, Base, env vars
├── alembic/versions/       # 0001..0009 (migraciones manuales)
├── auth/                   # security.py (bcrypt+JWT), dependencies.py
├── models/                 # consulta, usuario(+TransaccionToken), vehiculo,
│                           # vehiculo_favorito, dueno_historico,
│                           # kilometraje_lectura, mantenimiento, enlace_compartido,
│                           # cola_scraping  ← NUEVO
├── schemas/                # auth, vehiculo, dueno_historico, kilometraje,
│                           # favorito, mantenimiento, enlace_compartido
├── routers/                # auth, vehiculos, duenos, kilometraje, tokens,
│                           # favoritos, mantenimientos, marketplace, compartidos,
│                           # ocr  ← NUEVO (POST /consultar-foto)
├── services/               # ant, sri, amt, fiscalia, cache (Playwright),
│                           # vision  ← NUEVO (Cloud Vision OCR)
├── utils/                  # validators.py, ofuscacion.py
├── scripts/discover.py     # descubrimiento de selectores para scraping
├── docs/                   # arquitectura.md (Mermaid), despliegue.md,
│                           # arquitectura_hibrida.md  ← NUEVO (diseño worker)
├── Dockerfile · render.yaml · requirements.txt
└── .claude/skills/         # 6 skills del proyecto
```

## 5. Skills y herramientas configuradas

- **CLAUDE.md** presente (workspace + proyecto): fuente de verdad, fases, reglas de negocio 10.x.
- **Skills del proyecto** (`.claude/skills/`): `agregar-fuente-consulta`, `desplegar-mvp`, `modelo-dominio-vehiculo`, `respuesta-api-estandar`, `scraping-respetuoso`, `validacion-datos-ec`.
- **Diagramas vivos** en `docs/arquitectura.md` (topología con OCR + worker, auth, secuencia de consulta, **secuencia OCR §2c**, ER con `cola_scraping`, roadmap). Diseño híbrido aparte en `docs/arquitectura_hibrida.md`.

## 6. Decisiones técnicas tomadas

- **Migraciones manuales** (no autogenerate a ciegas), nombre descriptivo por archivo.
- **Separación CRUD ↔ scraping:** el CRUD del MVP toca solo la BD propia; nunca invoca Playwright. La cola es exclusiva del pipeline de scraping.
- **Contrato de error:** 422 validación de negocio, 404 propiedad (no 403), 400 input, 409 conflicto, 201/204 en create/delete; nunca 500 por fuente externa caída. (OCR: fallo de lectura → 400; sin API key → 503.)
- **Idioma español estricto** en tablas, columnas, rutas y variables.
- **Privacidad por niveles:** `completo` (dueño), `origen` (token compra-venta), `oculto` (público). VIN/motor/chasis nunca completos a terceros.
- **Marketplace:** `selectinload` obligatorio; nunca expone VIN completo ni nombre del dueño.
- **BD:** Neon sobre el Postgres free de Render (que expira a los 90 días).
- **OCR (Fase 5):** Cloud Vision REST + `httpx` + API key (no SDK, no Tesseract). `vision.py` nunca propaga excepciones.
- **Worker híbrido:** comunicación API↔worker por **tabla de cola en Postgres** con `FOR UPDATE SKIP LOCKED`, índice único parcial (idempotencia), backoff exponencial y rescate de zombis. Sin broker externo. Reusa los servicios de scraping sin modificarlos.

## 7. Últimos cambios (git log)

```
16c5e25 feat: worker híbrido - cola en Postgres, modelo y migración 0009
e44cbb8 feat: Fase 5 - endpoint OCR con Google Cloud Vision y diseño worker
8374529 docs: regenerar snapshot del proyecto tras cierre de Fase 4
c00bb6c docs: cerrar Fase 4 en CLAUDE.md y actualizar diagramas
ae540bf feat: Fase 4 - marketplace publico y token de compra-venta
bf6a2e4 docs: regenerar snapshot del proyecto tras cierre de Fase 3
```
**Working tree limpio.** Rama `main`. Nada pusheado al remoto. La migración `0009` aún no se aplicó a Neon.

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

1. **Seguridad inmediata:** rotar la contraseña de Neon y actualizar `DATABASE_URL` en `.env` local y en Render.
2. **Push + migración:** subir los commits pendientes (Fases 3, 4, OCR y worker) a GitHub, aplicar `alembic upgrade head` (incluye `0009`) y verificar el deploy en Render.
3. **Cablear el worker a la API:** encolar AMT/FGE en `cola_scraping` ante cache miss, devolver estado `en_proceso`, y dejar de instanciar Chromium para esas fuentes en Render. Desplegar `worker.py` en una máquina con IP residencial EC (definir cuál).
4. **Verificar OCR end-to-end:** configurar `GOOGLE_VISION_API_KEY`, probar `POST /consultar-foto` con foto real e integrar al frontend.
5. **Decidir proveedor anti-captcha para SRI** (2Captcha/Anti-Captcha) si se prioriza desbloquear esa fuente.
6. **Cablear el débito de tokens y el `scope` del enlace** cuando llegue la primera función de pago y se amplíe la vista compartida.
```
