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
- **BD:** PostgreSQL 16 en **Neon** (externa, serverless). JSONB para respuestas crudas y para `scope` de enlaces.
- **ORM/Migraciones:** SQLAlchemy 2 + Alembic (migraciones **manuales**, `0001`–`0008`).
- **Auth:** `passlib[bcrypt]` (con `bcrypt<4.0` pineado) + `python-jose` (JWT HS256).
- **Deploy:** Docker en Render (backend) + Vercel (frontend). Cron externo (UptimeRobot) contra `/health` por el cold start del free tier.

## 3. Estado actual — AS-IS

### ✅ Completado
- **Fase 1 — Consultas públicas + caché:** endpoints `/consultar/{placa}`, `/consultar-judicial/{cedula}`, `/health`. ANT/AMT/FGE funcionan en local; SRI bloqueado por reCAPTCHA invisible. Caché en Postgres con TTL (solo cachea `consulta_realizada`/`sin_resultados`).
- **Fase 2 — Auth + dominio + deploy:** registro/login JWT, CRUD de vehículos (VIN/motor/chasis con 3 niveles de visibilidad y ofuscación), histórico de dueños, kilometraje monotónico. Desplegado en Render + Vercel.
- **Fase 3 — Billetera + Favoritos + Mantenimientos:** `saldo_tokens` (default 5, CHECK ≥ 0) + `transacciones_tokens` (auditoría); favoritos por placa (String, no FK); mantenimientos inmutables con validación monotónica. Migraciones `0004`–`0006`. BD migrada a Neon.
- **Fase 4 — Compra-venta:** Marketplace público y token de enlace compartido. Migraciones `0007`–`0008` aplicadas a Neon (head = `0008`).
  - `GET /marketplace` (anónimo): lista autos con `en_venta = True AND precio_venta_usd > 0`, no eliminados. `selectinload(mantenimientos)` para derivar `total_mantenimientos` sin N+1. Salida `VehiculoSalidaMarketplace`: VIN nivel `oculto` (solo país), **sin nombre del dueño**.
  - `POST /vehiculos/{id}/compartir` (dueño, TTL ≤ 7 días) + `GET /compartido/{token}` (público) → `VehiculoSalidaCompartida` ofuscado. `token` único (UK), `scope` JSONB opt-in. Token inexistente/expirado → 404.

### 🔄 En progreso / pendiente acotado
- **Débito real de tokens:** el servicio que descuenta saldo (422 por saldo insuficiente) se implementará junto a la primera función de pago. Hoy la billetera es solo lectura + auditoría inicial.
- **`scope` del enlace:** se persiste y valida (claves `kilometraje`/`mantenimientos`/`duenos_historico`), pero la vista compartida actual solo muestra características del auto; el gateo de esas secciones se cableará cuando se agreguen a `VehiculoSalidaCompartida`.

### ⚠️ Problemas / deuda técnica / decisiones
- **SRI bloqueado por reCAPTCHA Enterprise invisible** (local y cloud). No es bug; requiere anti-captcha o API oficial.
- **AMT y FGE bloqueados en cloud por IP de datacenter** (Render). Funcionan desde IP residencial (local). Aislar contenedores en otra red NO lo resuelve.
- **Decisión 2026-05-28:** estrategia de scraping cloud = **worker híbrido con IP residencial** (backend en Render, worker scraping en máquina residencial que empuja a Neon). Resuelve AMT/FGE a ~$0; SRI pospuesto (2captcha si hace falta). Aún no implementado.
- **Seguridad pendiente:** rotar la contraseña de Neon (quedó expuesta en historial de chat de una sesión previa). Vive solo en `.env` (gitignored) y en el dashboard de Render (`sync: false`).
- **Nada pusheado al remoto** todavía: los commits de Fases 3 y 4 están solo en local.

## 4. Estructura de archivos actual

```
consulta_placas_ec/
├── main.py                 # FastAPI: endpoints públicos + include_router
├── run.py                  # launcher (WindowsProactorEventLoopPolicy)
├── database.py             # engine, SessionLocal, Base, env vars
├── alembic/versions/       # 0001..0008 (migraciones manuales)
├── auth/                   # security.py (bcrypt+JWT), dependencies.py
├── models/                 # consulta, usuario(+TransaccionToken), vehiculo,
│                           # vehiculo_favorito, dueno_historico,
│                           # kilometraje_lectura, mantenimiento, enlace_compartido
├── schemas/                # auth, vehiculo, dueno_historico, kilometraje,
│                           # favorito, mantenimiento, enlace_compartido
├── routers/                # auth, vehiculos, duenos, kilometraje, tokens,
│                           # favoritos, mantenimientos, marketplace, compartidos
├── services/               # ant, sri, amt, fiscalia, cache (Playwright)
├── utils/                  # validators.py, ofuscacion.py
├── scripts/discover.py     # descubrimiento de selectores para scraping
├── docs/                   # arquitectura.md (Mermaid), despliegue.md
├── Dockerfile · render.yaml · requirements.txt
└── .claude/skills/         # 6 skills del proyecto
```

## 5. Skills y herramientas configuradas

- **CLAUDE.md** presente (workspace + proyecto): fuente de verdad, fases, reglas de negocio 10.x.
- **Skills del proyecto** (`.claude/skills/`): `agregar-fuente-consulta`, `desplegar-mvp`, `modelo-dominio-vehiculo`, `respuesta-api-estandar`, `scraping-respetuoso`, `validacion-datos-ec`.
- **Diagramas vivos** en `docs/arquitectura.md` (topología, auth, secuencia de consulta, ER, roadmap) — actualizados tras cada bloque.

## 6. Decisiones técnicas tomadas

- **Migraciones manuales** (no autogenerate a ciegas), nombre descriptivo por archivo.
- **Separación CRUD ↔ scraping:** el CRUD del MVP toca solo la BD propia; nunca invoca Playwright.
- **Contrato de error:** 422 validación de negocio, 404 propiedad (no 403), 400 input, 409 conflicto, 201/204 en create/delete; nunca 500 por fuente externa caída.
- **Idioma español estricto** en tablas, columnas, rutas y variables.
- **Privacidad por niveles:** `completo` (dueño), `origen` (token compra-venta), `oculto` (público). VIN/motor/chasis nunca completos a terceros.
- **Marketplace:** `selectinload` obligatorio; nunca expone VIN completo ni nombre del dueño.
- **BD:** se eligió Neon sobre el Postgres free de Render (que expira a los 90 días).

## 7. Últimos cambios (git log)

```
c00bb6c docs: cerrar Fase 4 en CLAUDE.md y actualizar diagramas
ae540bf feat: Fase 4 - marketplace publico y token de compra-venta
bf6a2e4 docs: regenerar snapshot del proyecto tras cierre de Fase 3
c91f915 docs: cerrar Fase 3 en CLAUDE.md y actualizar diagramas
4e09776 feat: Fase 3 - mantenimientos del vehiculo
ab10270 feat: Fase 3 - billetera de tokens, favoritos y perfil de vehiculo ampliado
11d4505 chore: limpieza de debug y backend apuntando a BD externa (Neon)
```
Working tree limpio. Rama `main`. Nada pusheado al remoto.

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
2. **Push al remoto:** subir los commits de Fases 3 y 4 a GitHub y verificar el deploy en Render (migraciones `0007`/`0008` ya están en Neon).
3. **Implementar Fase 5 — OCR/foto:** endpoint que reciba imagen → extraiga placa (Tesseract o servicio cloud) → dispare el flujo de consulta normal.
4. **Worker híbrido de scraping** (decisión ya tomada): worker en IP residencial que empuje resultados a Neon, desbloqueando AMT/FGE en producción.
5. **Cablear el débito de tokens y el `scope` del enlace** cuando llegue la primera función de pago y se amplíe la vista compartida.
