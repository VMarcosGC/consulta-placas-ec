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
├── main.py                 # FastAPI: públicos + include_router. AMT/FGE vía worker.
├── run.py                  # launcher API (WindowsProactorEventLoopPolicy)
├── worker.py               # worker híbrido pull-only (cola_scraping)
├── database.py             # engine, SessionLocal, Base, env vars
├── alembic/versions/       # 0001..0009 (migraciones manuales)
├── auth/                   # security.py (bcrypt+JWT), dependencies.py
├── models/                 # consulta, usuario(+TransaccionToken), vehiculo,
│                           # vehiculo_favorito, dueno_historico,
│                           # kilometraje_lectura, mantenimiento, enlace_compartido,
│                           # cola_scraping
├── schemas/                # auth, vehiculo, dueno_historico, kilometraje,
│                           # favorito, mantenimiento, enlace_compartido
├── routers/                # auth, vehiculos, duenos, kilometraje, tokens,
│                           # favoritos, mantenimientos, marketplace, compartidos, ocr
├── services/               # ant, sri, amt, fiscalia, cache, vision (OCR),
│                           # cola (encolado), tokens (débito)
├── utils/                  # validators.py, ofuscacion.py
├── scripts/discover.py     # descubrimiento de selectores para scraping
├── docs/                   # arquitectura.md (Mermaid), despliegue.md,
│                           # arquitectura_hibrida.md (diseño worker)
├── Dockerfile · render.yaml · requirements.txt
└── .claude/skills/         # 6 skills del proyecto
```

## 5. Skills y herramientas configuradas

- **CLAUDE.md** presente (workspace + proyecto): fuente de verdad, fases, reglas de negocio 10.x.
- **Skills del proyecto** (`.claude/skills/`): `agregar-fuente-consulta`, `desplegar-mvp`, `modelo-dominio-vehiculo`, `respuesta-api-estandar` (incluye estado `en_proceso`), `scraping-respetuoso`, `validacion-datos-ec`.
- **Diagramas vivos** en `docs/arquitectura.md`: topología con worker cableado, secuencia auth, secuencia consulta (nota worker), secuencia OCR §2c, ER con `cola_scraping`, roadmap. Diseño híbrido en `docs/arquitectura_hibrida.md`.

## 6. Decisiones técnicas tomadas

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
ceb593a feat: débito transaccional de tokens en creación de enlace compartido
d740d2c feat: cablear worker híbrido - AMT/FGE vía cola_scraping (en_proceso)
719e079 docs: regenerar snapshot tras Fase 5 OCR y worker híbrido
16c5e25 feat: worker híbrido - cola en Postgres, modelo y migración 0009
e44cbb8 feat: Fase 5 - endpoint OCR con Google Cloud Vision y diseño worker
8374529 docs: regenerar snapshot del proyecto tras cierre de Fase 4
```
**Working tree limpio.** Rama `main` **al día con `origin/main`** (todo pusheado). Neon en revisión `0009`.

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
