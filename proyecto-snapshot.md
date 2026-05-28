# Proyecto Snapshot — consulta_placas_ec

**Generado:** 2026-05-28
**Herramienta origen:** Claude Code (VS Code, Windows 11)
**Propósito de este archivo:** Subir a Gemini AI Studio (u otro LLM) para continuar la planificación TO-BE sin re-explicar contexto.
**Rama git:** `main` · **Último commit:** `c91f915 docs: cerrar Fase 3 en CLAUDE.md y actualizar diagramas`
**Working tree:** limpio (Fase 3 commiteada; nada pusheado al remoto todavía).

---

## 1. ¿Qué es este proyecto?

Plataforma (web + futura app móvil) para que cualquier persona en Ecuador conozca el **estado integral de un vehículo** a partir de su placa, sus características o una foto. El backend agrega información de cuatro fuentes oficiales (ANT, SRI, AMT Quito, Fiscalía General del Estado), gestiona auth JWT y mantiene un historial privado de cada vehículo (dueños, kilometraje, mantenimientos), más una billetera de tokens y favoritos. Cuatro pilares: **consulta pública por placa**, **consulta por foto** (OCR, futuro), **historial privado del vehículo** (solo dueño autenticado), y **compra-venta** (token privado + marketplace público, Fase 4).

Dominio: información vehicular pública ecuatoriana + CRM personal de vehículos. Usuarios finales: dueños de vehículos, compradores potenciales, talleres.

## 2. Stack tecnológico

**Backend (este repo)**
- Python 3.11+ (en producción: imagen Docker con Python 3.10 vía Playwright official `mcr.microsoft.com/playwright/python:v1.48.0-jammy`).
- FastAPI + uvicorn (routers organizados en `routers/`).
- Playwright async + Chromium para todo el scraping.
- **PostgreSQL 16 en Neon** (externa, serverless) + SQLAlchemy 2 + Alembic (migraciones manuales).
- Pydantic 2.
- Auth: `passlib[bcrypt]` con `bcrypt<4.0` pineado + `python-jose` (JWT HS256).
- Driver BD: `psycopg[binary]>=3.2.0` (psycopg 3).

**Frontend (repo separado [consulta-placas-web](https://github.com/VMarcosGC/consulta-placas-web))**
- Next.js 16 (App Router, Turbopack, RSC) + React 19 + Tailwind CSS 4.
- JWT en localStorage. Dark mode con gradient `violet-500 → pink-500 → amber-500`.

**Deploy**
- Backend en **Render free tier** con runtime **Docker**.
- BD en **Neon** (ya no se provisiona Postgres en Render; expiraba a 90 días). `DATABASE_URL` se setea manualmente en el dashboard de Render (secreta).
- Frontend en **Vercel free**.

## 3. Estado actual — AS-IS

### Completado

**Fase 1 — Consultas estables + caché**
- `GET /consultar/{placa}` (ANT+SRI+AMT+FGE en paralelo, con `resumen`), `GET /consultar-judicial/{cedula}` (FGE), `GET /health`.
- Caché en PostgreSQL con TTL ([services/cache.py](services/cache.py)). Solo cachea `consulta_realizada` y `sin_resultados`.
- 5 servicios en `services/` con contrato unificado.

**Fase 2 — Auth + dominio + deploy**
- JWT (registro/login/me), CRUD de vehículos, dueños históricos, kilometraje monotónico.
- Ofuscación VIN/motor/chasis en 3 niveles. Validadores EC (placa, cédula, VIN).
- MVP desplegado: backend en Render, frontend en Vercel.

**Fase 3 — Billetera + Favoritos + Mantenimientos ✅ (recién cerrada)**
- **Migración de BD a Neon** (PostgreSQL 16). Migraciones `0004`–`0006` aplicadas; head=`0006`.
- **Billetera**: `Usuario.saldo_tokens` (default 5, CHECK `>= 0`, constante `SALDO_INICIAL_TOKENS`) + modelo `TransaccionToken` (auditoría inmutable). Endpoints `GET /tokens/saldo` y `GET /tokens/transacciones`. El registro graba la transacción `saldo_inicial` (+5) para que el ledger cuadre con el saldo.
- **Perfil de vehículo ampliado**: `transmision`, `tipo_motor`, `ciudad_registro`.
- **Favoritos**: tabla `vehiculos_favoritos`, placa como `String` (no FK), validada con `validar_placa`, única por usuario+placa. CRUD en `/favoritos`.
- **Mantenimientos**: tabla `mantenimientos` (`tipo`, `fecha`, `kilometraje_relacionado`, `taller`, `costo`), anidada en `/vehiculos/{id}/mantenimientos`, inmutable, con validación monotónica fecha+km (422) y propiedad por JWT.
- **Contrato de errores reconciliado**: validación de negocio → **422**, propiedad ajena → **404** (no 403), formato → 400, conflictos → 409.

### En progreso / pendiente

- **Débito de tokens real**: el servicio que descuenta tokens (con `SaldoInsuficiente` → 422) se implementará junto a la primera función de pago (ej. "consultar placa cuesta 1 token"). Hoy la billetera es solo lectura + grant inicial auditado.
- **Fase 4 no iniciada**: token de compra-venta (`enlaces_compartidos`) + Marketplace público (`en_venta`, `precio_venta_usd`, `url_externa`, `GET /marketplace` con `selectinload`).
- El frontend Next.js (repo separado) aún no consume los endpoints nuevos de Fase 3.

### Problemas y deuda técnica

| Síntoma | Causa | Estado |
|---|---|---|
| SRI siempre `bloqueado_captcha` | reCAPTCHA Enterprise invisible | Estructural (local y cloud) |
| AMT/FGE bloqueados en Render | IPs de datacenter detectadas | Solo en cloud; local funciona |
| Cold start ~30s | Render free duerme | Mitigable con UptimeRobot a `/health` |

- Sin tests automatizados (descansa en disciplina + skills + smoke tests manuales).
- Sin README.md público.
- `.env` con valores reales en local, gitignored (verificado). **La contraseña de Neon quedó en el historial del chat de la sesión — conviene rotarla.**
- Mantenimientos sin PATCH a propósito (editar fecha/km rompería la monotonía); para corregir, borrar y re-registrar.
- `adjuntos` de mantenimientos omitido (requiere storage de archivos; va en fase posterior).

## 4. Estructura de archivos actual

```
consulta_placas_ec/
├── main.py                       # FastAPI: endpoints públicos + include_router (auth, vehiculos, duenos, kilometraje, tokens, favoritos, mantenimientos)
├── database.py                   # engine, sesiones, env vars (DATABASE_URL→Neon, JWT_SECRET_KEY)
├── run.py                        # Launcher (WindowsProactorEventLoopPolicy)
├── requirements.txt
├── Dockerfile                    # Base playwright/python:v1.48.0-jammy
├── render.yaml                   # Render web Docker; DATABASE_URL sync:false (Neon, externa)
├── CLAUDE.md                     # Fuente de verdad (15 secciones; sección 10 = reglas MVP Fases 3-4)
├── .claude/skills/               # 6 skills propios
├── alembic/versions/
│   ├── 0001_crear_tabla_consultas.py
│   ├── 0002_usuarios_vehiculos_duenos_kilometraje.py
│   ├── 0003_motor_y_chasis_en_vehiculos.py
│   ├── 0004_perfil_vehiculo_billetera.py    # Fase 3
│   ├── 0005_favoritos.py                     # Fase 3
│   └── 0006_mantenimientos.py                # Fase 3
├── auth/                         # security.py (bcrypt+JWT), dependencies.py (usuario_actual, vehiculo_propio)
├── routers/
│   ├── auth.py                   # + grant saldo_inicial en registro
│   ├── vehiculos.py              # POST usa model_dump (persiste todos los campos)
│   ├── duenos.py
│   ├── kilometraje.py
│   ├── tokens.py                 # Fase 3: GET /tokens/saldo, /tokens/transacciones
│   ├── favoritos.py              # Fase 3: CRUD /favoritos
│   └── mantenimientos.py         # Fase 3: CRUD /vehiculos/{id}/mantenimientos
├── services/                     # ant, sri, amt, fiscalia, cache (Playwright; SOLO lectura, no tocados por CRUD)
├── models/
│   ├── consulta.py · usuario.py (+TransaccionToken, SALDO_INICIAL_TOKENS) · vehiculo.py (+perfil)
│   ├── vehiculo_favorito.py      # Fase 3
│   ├── dueno_historico.py · kilometraje_lectura.py
│   └── mantenimiento.py          # Fase 3
├── schemas/
│   ├── auth.py (+saldo_tokens, TransaccionTokenSalida, SaldoTokens)
│   ├── vehiculo.py (+perfil) · dueno_historico.py · kilometraje.py
│   ├── favorito.py               # Fase 3
│   └── mantenimiento.py          # Fase 3
├── utils/                        # validators.py, ofuscacion.py
├── scripts/discover.py
├── docs/
│   ├── arquitectura.md           # diagramas Mermaid (actualizados a Fase 3)
│   └── despliegue.md
└── debug/                        # PNGs de scraping (gitignored)
```

(Sin `node_modules/`, `__pycache__/`, ni `.venv/` — gitignored.)

## 5. Skills y herramientas configuradas

**Skills propios** (en `.claude/skills/`): `agregar-fuente-consulta`, `desplegar-mvp`, `modelo-dominio-vehiculo`, `respuesta-api-estandar`, `scraping-respetuoso`, `validacion-datos-ec`.

**Bibliotecas a nivel workspace** (en `porpuestas_code/`): `marketingskills/` (42 skills), `ui-ux-pro-max-skill/` (7 sub-skills + CLI `search.py`).

## 6. Decisiones técnicas clave

- **Idioma español** en todo identificador (tablas, columnas, rutas, variables).
- **Separación CRUD ↔ scraping**: Billetera/Favoritos/Mantenimientos/Marketplace tocan solo la BD; nunca invocan Playwright.
- **Migraciones manuales** (no autogenerate a ciegas), nombre descriptivo (`0004_perfil_vehiculo_billetera.py`).
- **Billetera**: saldo inicial 5, nunca negativo (CHECK + futura validación de débito), toda alteración auditada en `transacciones_tokens`. El grant inicial se audita en el registro.
- **Favoritos**: placa como `String` (no FK) → se puede seguir una placa inexistente.
- **Mantenimientos**: inmutables; monotonía de fecha+km validada en el router (comparando con el máximo); propiedad por `vehiculo_propio`.
- **Compra-venta (Fase 4)**: token privado y Marketplace público **coexisten** (no se reemplazan).
- **Contrato de error**: 422 negocio / 404 propiedad / 400 formato / 409 conflicto / nunca 500 por fuente externa.
- **BD en Neon** (Render free Postgres expiraba a 90 días).
- **`JWT_SECRET_KEY`** es el nombre real de la variable del JWT (el spec lo llamó `SECRET_KEY`).
- `run.py` en vez de `uvicorn --reload` (event loop policy en Windows). Pin `bcrypt<4.0`. Docker en Render. Contrato `consultar_<fuente>` unificado.

## 7. Últimos cambios (commits de esta sesión)

```
c91f915 docs: cerrar Fase 3 en CLAUDE.md y actualizar diagramas
4e09776 feat: Fase 3 - mantenimientos del vehiculo
ab10270 feat: Fase 3 - billetera de tokens, favoritos y perfil de vehiculo ampliado
11d4505 chore: limpieza de debug y backend apuntando a BD externa (Neon)
c83c259 docs: reglas de negocio MVP (Fases 3 y 4) + snapshot del proyecto
9551220 docs: actualizar CLAUDE.md y skills tras cierre de Fase 2 + MVP en produccion
```

## 8. Para continuar en Gemini — instrucciones

> Eres un asistente de arquitectura y planificación de software.
>
> Tienes el contexto completo del proyecto `consulta_placas_ec`: backend FastAPI + Playwright en Docker (Render), BD PostgreSQL 16 en Neon, frontend Next.js separado (Vercel). **Fases 1, 2 y 3 cerradas** (consultas+caché; auth+CRUD vehículos/dueños/kilometraje; billetera de tokens + favoritos + mantenimientos + perfil de vehículo ampliado). **Fase 4 pendiente**: token de compra-venta (`enlaces_compartidos`) + Marketplace público (`en_venta`, `precio_venta_usd`, `url_externa`, `GET /marketplace` con `selectinload`). Fases 5 (OCR) y 6 (móvil) más adelante.
>
> Cuando el usuario describa qué quiere hacer, responde con: (1) impacto sobre lo existente, (2) archivos a crear/modificar con rutas exactas, (3) skills a activar, (4) estructura sugerida (entidades, endpoints, migración Alembic), (5) riesgos/dependencias.
>
> **Reglas duras** (sección 10 de CLAUDE.md): todo en español; no saltar fases; módulos CRUD no invocan Playwright; migraciones manuales con nombre descriptivo; Marketplace con `selectinload`; tokens (saldo 5, ≥0, auditar en `transacciones_tokens`); favoritos placa `String` + `validar_placa`; mantenimientos monotónicos + propiedad JWT; Marketplace solo `en_venta=True AND precio_venta_usd>0`, nunca VIN completo ni nombre del dueño; errores de negocio → 422, propiedad → 404, nunca 500 por fuente externa.

## 9. Próximos pasos sugeridos

1. **Fase 4 — Token de compra-venta**. Tabla `enlaces_compartidos` (`token UK`, `vehiculo_id FK`, `scope JSONB`, `fecha_expiracion`). Endpoint público `GET /compartido/{token}` → `VehiculoSalidaCompartida` (ya existe). TTL ≤ 7 días, scope opt-in. Migración `0007`.
2. **Fase 4 — Marketplace público**. Columnas `en_venta`, `precio_venta_usd`, `url_externa` en `vehiculos` (migración). `GET /marketplace` con `selectinload`, filtro `en_venta=True AND precio_venta_usd>0`, salida con VIN ofuscado y sin nombre del dueño.
3. **Servicio de débito de tokens** (`ajustar_saldo` + `SaldoInsuficiente`→422) cuando se introduzca la primera función de pago que consuma tokens.
4. **Rotar la contraseña de Neon** (quedó en el historial del chat) y confirmar `DATABASE_URL` en Render.
5. **Frontend**: consumir los endpoints de Fase 3 (billetera, favoritos, mantenimientos) en el repo `consulta-placas-web`.
6. **Cron externo** (UptimeRobot) contra `/health` para evitar cold start.
7. **Tests de parser con HTML fixtures** y un README.md público mínimo.

---

**Nota de privacidad**: este snapshot no incluye contraseñas, JWT secrets ni datos personales. El `.env` con valores reales está fuera de git.
