# Proyecto Snapshot — consulta_placas_ec

**Generado:** 2026-05-28
**Herramienta origen:** Claude Code (VS Code, Windows 11)
**Propósito de este archivo:** Subir a Gemini AI Studio (u otro LLM) para continuar la planificación TO-BE sin re-explicar contexto.
**Rama git:** `main` · **Último commit:** `9551220 docs: actualizar CLAUDE.md y skills tras cierre de Fase 2 + MVP en producción`
**Working tree:** `CLAUDE.md` modificado (sin commitear) + este snapshot sin trackear.

---

## 1. ¿Qué es este proyecto?

Plataforma (web + futura app móvil) para que cualquier persona en Ecuador conozca el **estado integral de un vehículo** a partir de su placa, sus características o una foto. El backend agrega información de cuatro fuentes oficiales (ANT, SRI, AMT Quito, Fiscalía General del Estado), gestiona auth JWT y mantiene un historial privado de cada vehículo (dueños, kilometraje, mantenimientos). Está pensado en cuatro pilares: **consulta pública por placa**, **consulta por foto** (OCR de placa), **historial privado del vehículo** (solo dueño autenticado), y **modo compra-venta** (token temporal privado + marketplace público).

Dominio: información vehicular pública ecuatoriana + CRM personal de vehículos. Usuarios finales: dueños de vehículos, compradores potenciales, talleres.

## 2. Stack tecnológico

**Backend (este repo)**
- Python 3.11+ (en producción: imagen Docker con Python 3.10 vía Playwright official `mcr.microsoft.com/playwright/python:v1.48.0-jammy`).
- FastAPI + uvicorn (routers organizados en `routers/`).
- Playwright async + Chromium para todo el scraping.
- PostgreSQL 16 + SQLAlchemy 2 + Alembic (migraciones manuales).
- Pydantic 2 + `pydantic-settings`.
- Auth: `passlib[bcrypt]` con `bcrypt<4.0` pineado (incompatibilidad con passlib 1.7.4) + `python-jose` (JWT HS256).
- Driver BD: `psycopg[binary]>=3.2.0` (psycopg 3).

**Frontend (repo separado [consulta-placas-web](https://github.com/VMarcosGC/consulta-placas-web))**
- Next.js 16 (App Router, Turbopack, RSC).
- React 19 + Tailwind CSS 4.
- JWT en localStorage (sin SSR para páginas privadas).
- Tono visual: dark mode con gradient `violet-500 → pink-500 → amber-500`.

**Deploy**
- Backend en **Render free tier** con runtime **Docker** (Native Python no admite `sudo apt-get` necesario para libs de Playwright).
- PostgreSQL en Render free (1 GB, **expira a 90 días** → migrar a Supabase/Neon antes de codear Fases 3 y 4).
- Frontend en **Vercel free**.

## 3. Estado actual — AS-IS

### Completado

**Fase 1 — Consultas estables + caché**
- `GET /consultar/{placa}` → consulta paralela a ANT + SRI + AMT + FGE, devuelve respuesta agregada con `resumen` de indicadores.
- `GET /consultar-judicial/{cedula}` → solo FGE, búsqueda por cédula con dígito verificador validado.
- `GET /health` → health-check instantáneo (no toca BD).
- Caché en PostgreSQL con TTL configurable ([services/cache.py](services/cache.py)). Solo cachea estados `consulta_realizada` y `sin_resultados`; errores y `bloqueado_captcha` no se cachean.
- 5 servicios externos en `services/` con contrato unificado (`fuente`, `placa`/`termino`, `estado`, `datos`, `error`).

**Fase 2 — Auth + dominio + deploy**
- Registro/login JWT en [routers/auth.py](routers/auth.py): `POST /auth/registro`, `POST /auth/login`, `GET /auth/me`.
- CRUD completo de vehículos del usuario ([routers/vehiculos.py](routers/vehiculos.py)) con VIN, motor, chasis.
- Histórico de dueños con cierre automático del anterior ([routers/duenos.py](routers/duenos.py)).
- Lecturas de kilometraje inmutables con validación monotónica ([routers/kilometraje.py](routers/kilometraje.py)).
- 5 entidades persistidas (`Consulta`, `Usuario`, `Vehiculo`, `DuenoHistorico`, `KilometrajeLectura`) en 3 migraciones Alembic.
- Tres niveles de visibilidad para identificadores sensibles VIN/motor/chasis: `completo`, `origen` (ofuscado al país WMI), `oculto`.
- Validadores oficiales EC: `validar_placa`, `validar_cedula` (módulo 10), `validar_vin` (ISO 3779/3780 con dígito verificador).
- Deploy MVP funcionando: backend en [consulta-placas-ec.onrender.com](https://consulta-placas-ec.onrender.com) y frontend en [consulta-placas-web.vercel.app](https://consulta-placas-web.vercel.app).

**Documentación de reglas para Fases 3 y 4 (2026-05-28, sin commitear)**
- Nueva **sección 10 de `CLAUDE.md` — "Reglas de Negocio del MVP (Fases 3 y 4)"**, con 3 bloques: infraestructura (requisitos previos), arquitectura/código y reglas de negocio. Captura las leyes inmutables bajo las que se programarán Billetera, Favoritos, Mantenimientos y Marketplace.
- Roadmap (sección 3 de `CLAUDE.md`) actualizado: Fase 3 = Billetera + Favoritos + Mantenimientos; Fase 4 = compra-venta con **dos mecanismos que coexisten** (token privado `enlaces_compartidos` + Marketplace público).
- `CLAUDE.md` pasó de 14 a 15 secciones.

### En progreso / pendiente de implementación

- **Las Fases 3 y 4 están documentadas pero NO codeadas.** No existen aún las tablas `transacciones_tokens`, `vehiculos_favoritos`, `mantenimientos`, ni las columnas de marketplace (`en_venta`, `precio_venta_usd`, `url_externa`) en `vehiculos`, ni los routers `/favoritos`, `/marketplace`, `/mantenimientos`.
- El cambio a `CLAUDE.md` está sin commitear (working tree).
- El frontend Next.js vive en repo separado y evoluciona en paralelo.

### Problemas y deuda técnica identificada

**Limitaciones aceptadas (no son bugs, son restricciones de las fuentes):**

| Síntoma | Causa real | Estado |
|---|---|---|
| SRI siempre devuelve `bloqueado_captcha` | reCAPTCHA Enterprise invisible; Playwright es detectable | Estructural — pasa en local y en cloud |
| AMT y FGE bloqueados solo en Render | Portales gob.ec detectan IPs de datacenter (Render, AWS, GCP) y sirven challenges anti-bot | Solo en cloud; local funciona |
| Postgres Render expira a 90 días | Política del plan free | Requisito previo: migrar a Supabase o Neon antes de codear Fases 3 y 4 |
| Cold start ~30s tras 15 min inactivo | Render free duerme servicios | Mitigable con cron externo (UptimeRobot) pegándole a `/health` |
| Playwright 512 MB tight para Chromium | RAM del free tier | Posible: lanzar Chromium con `--single-process --no-zygote` o pagar Starter ($7/mes) |

**Deuda concreta:**
- No hay README.md en el repo (solo `CLAUDE.md`). Si se abre al público, hace falta.
- No hay tests automatizados (ni unitarios ni de integración). El proyecto descansa en disciplina manual + skills documentados.
- Hay 3 PNG de debug (`debug_amt_resultado.png`, `debug_fge_resultado.png`, `debug_sri_resultado.png`) en la raíz del repo — deberían estar en `.gitignore` o moverse a `debug/`.
- No hay proxy residencial configurado — bloquea AMT/FGE en cloud (no afecta a las nuevas fuentes CRUD de Fases 3 y 4, que no usan scraping).
- `.env` está presente en working tree con valores reales pero **ya está cubierto por `.gitignore`** (verificado con `git check-ignore`).
- Discrepancia de nombre resuelta: el spec de Fases 3/4 llamó `SECRET_KEY` a la variable del JWT, pero el código real usa `JWT_SECRET_KEY` (en `database.py`, `auth/security.py`, `render.yaml`, `.env.example`). Se mantiene `JWT_SECRET_KEY`; renombrar sería un refactor aparte.

## 4. Estructura de archivos actual

```
consulta_placas_ec/
├── main.py                       # FastAPI: endpoints públicos + orquestación
├── database.py                   # SQLAlchemy engine, sesiones, env vars (JWT_SECRET_KEY)
├── run.py                        # Launcher (fija WindowsProactorEventLoopPolicy)
├── requirements.txt
├── Dockerfile                    # Base playwright/python:v1.48.0-jammy
├── render.yaml                   # Blueprint Render: web Docker + Postgres
├── alembic.ini
├── .env.example
├── CLAUDE.md                     # Fuente de verdad del proyecto (15 secciones)
├── .claude/
│   └── skills/                   # 6 skills propios del proyecto
│       ├── agregar-fuente-consulta/
│       ├── desplegar-mvp/
│       ├── modelo-dominio-vehiculo/
│       ├── respuesta-api-estandar/
│       ├── scraping-respetuoso/
│       └── validacion-datos-ec/
├── alembic/
│   └── versions/
│       ├── 0001_crear_tabla_consultas.py
│       ├── 0002_usuarios_vehiculos_duenos_kilometraje.py
│       └── 0003_motor_y_chasis_en_vehiculos.py
├── auth/
│   ├── security.py               # hashear/verificar password, JWT
│   └── dependencies.py           # usuario_actual, vehiculo_propio
├── routers/
│   ├── auth.py
│   ├── vehiculos.py
│   ├── duenos.py
│   └── kilometraje.py
├── services/
│   ├── ant.py                    # Playwright. Funcional local y cloud
│   ├── sri.py                    # Bloqueado por reCAPTCHA Enterprise
│   ├── amt.py                    # Playwright + iframe + overlay. OK local; bloqueado cloud
│   ├── fiscalia.py               # SIAF FGE. OK local; bloqueado cloud
│   └── cache.py                  # Caché en Postgres con TTL
├── models/
│   ├── consulta.py
│   ├── usuario.py
│   ├── vehiculo.py
│   ├── dueno_historico.py
│   └── kilometraje_lectura.py
├── schemas/
│   ├── auth.py
│   ├── vehiculo.py               # 3 niveles de visibilidad
│   ├── dueno_historico.py
│   └── kilometraje.py
├── utils/
│   ├── validators.py             # validar_placa, validar_cedula, validar_vin
│   └── ofuscacion.py             # ofuscar_vin, decodificar_origen_vin, PAISES_VIN
├── scripts/
│   └── discover.py               # Helper de descubrimiento para nuevas fuentes
├── docs/
│   ├── arquitectura.md           # 4 diagramas Mermaid vivos
│   └── despliegue.md             # Guía Render + Docker
├── debug_amt_resultado.png       # Diagnóstico scraping (deberían ir a /debug)
├── debug_fge_resultado.png
└── debug_sri_resultado.png
```

(Sin `node_modules/`, `__pycache__/`, ni `.venv/` — gitignored.)

## 5. Skills y herramientas configuradas

**Skills propios del proyecto** (en [.claude/skills/](.claude/skills/)):

| Skill | Cuándo activarlo |
|---|---|
| `agregar-fuente-consulta` | Integrar una nueva fuente vehicular (ANT, SRI, AMT, etc.) siguiendo el patrón. |
| `desplegar-mvp` | Deploy en Render (backend Docker) y Vercel (frontend Next.js). |
| `modelo-dominio-vehiculo` | Agregar/modificar entidades con SQLAlchemy + Alembic. |
| `respuesta-api-estandar` | Aplicar contrato unificado a servicios y endpoints. |
| `scraping-respetuoso` | Criterios para scrapear sin abusar ni romper en producción. |
| `validacion-datos-ec` | Validar/normalizar placa, cédula, RUC, VIN. |

**Skills globales del usuario** (en `~/.claude/skills/`) relevantes:
- `project-snapshot` (el que generó este archivo).

**Bibliotecas externas disponibles a nivel workspace** (en `porpuestas_code/`):
- `marketingskills/` — 42 skills de Corey Haines (read-only, consultables vía Read).
- `ui-ux-pro-max-skill/` — 7 sub-skills + CLI `search.py` con 67 estilos / 161 paletas / 57 fuentes.

## 6. Decisiones técnicas tomadas

**Lenguaje del código**: todo en español (variables, funciones, rutas, columnas, JSON fields). Ej.: `consultar_ant`, `validar_placa`, `/consultar/{placa}`, `kilometraje_lecturas.fecha_lectura`, `vehiculos_favoritos`, `precio_venta_usd`. No traducir.

**Scraping con Playwright async**: porque ANT, AMT y FGE renderizan JS / usan iframes / SPAs. Se prefiere `httpx` si una fuente sirve HTML estático o JSON; ninguna lo hace hoy.

**Separación CRUD ↔ scraping (regla de Fases 3 y 4)**: los módulos Billetera, Favoritos, Mantenimientos y Marketplace tocan **solo** la BD propia. Bajo ningún concepto invocan los servicios de Playwright. El scraping sigue siendo de solo lectura. Razón: desacoplar la fragilidad del scraping del CRUD del usuario.

**Caché en BD vs Redis**: Postgres es suficiente para el volumen actual; un servicio menos que gestionar.

**SQLAlchemy 2 + migraciones manuales (no autogenerate)**: control predecible y reviewable. Cada migración tiene un nombre descriptivo (`0002_usuarios_vehiculos_duenos_kilometraje.py`, próxima `0004_billetera.py`).

**Eager loading en Marketplace**: las consultas que carguen vehículos en venta con sus relaciones usan `selectinload` para evitar N+1.

**JWT en lugar de session cookies**: el frontend es Next.js SPA con localStorage; no hay flujo SSR autenticado. CORS estricto con `CORS_ORIGINS` env var.

**Ofuscación de VIN/motor/chasis**: 3 niveles (`completo`, `origen`, `oculto`) en `schemas/vehiculo.py`. Default mínimo, opt-in por campo. El Marketplace público nunca expone VIN completo ni nombre del dueño.

**Compra-venta con dos mecanismos que coexisten** (decisión 2026-05-28):
- *Token privado* (Fase 4 original): enlace temporal `enlaces_compartidos` / `VehiculoSalidaCompartida`, scope opt-in, expiración ≤ 7 días, comprador puntual sin cuenta.
- *Marketplace público*: `GET /marketplace`, listado abierto condicionado a `en_venta=True` y `precio_venta_usd>0`, con privacidad de VIN/dueño y `url_externa` de contacto.

**Economía de tokens**: saldo inicial 5 por usuario, nunca negativo (`>= 0`), toda alteración audita en `transacciones_tokens`.

**Contrato de error de negocio**: errores como "tokens insuficientes" o "no es tu vehículo" devuelven HTTP 400/403 con JSON estructurado, nunca crash/500.

**Docker en Render (no native Python)**: porque el runtime native no admite `sudo apt-get` necesario para Chromium. Imagen base oficial `mcr.microsoft.com/playwright/python:v1.48.0-jammy`.

**`run.py` en vez de `uvicorn main:app --reload`**: en Windows, uvicorn deja `WindowsSelectorEventLoopPolicy` activa en el worker, lo cual rompe Playwright con `NotImplementedError`. El launcher fija `WindowsProactorEventLoopPolicy`.

**Pin `bcrypt<4.0`**: `passlib==1.7.4` lee `bcrypt.__about__.__version__`, removido en bcrypt 4.x → `AttributeError`. Pineado hasta migrar a `argon2-cffi` o `bcrypt` directo.

**Contrato de respuesta unificado**: toda `consultar_<fuente>` devuelve `{fuente, placa|termino, estado, datos|null, error?}`. Estados: `consulta_realizada`, `error`, `pendiente_integracion`, `sin_resultados`, `bloqueado_captcha`. Una fuente caída nunca rompe la respuesta global.

**Disciplina anti trial-and-error**: antes de tocar una fuente nueva, screenshot + dump de frames primero, parser después. La iteración de AMT (~6 rondas) fue la lección que motivó esta regla.

## 7. Últimos cambios

```
[WORKING TREE — sin commitear]
M  CLAUDE.md   # +sección 10 "Reglas de Negocio del MVP (Fases 3 y 4)"; roadmap fase 3/4 expandido
?? proyecto-snapshot.md

9551220 docs: actualizar CLAUDE.md y skills tras cierre de Fase 2 + MVP en producción
        7 archivos · +465 / −90  (CLAUDE.md y 6 skills)

cb65632 docs: documentar limitacion de scraping desde IPs de datacenter (Render)
        1 archivo  · +19         (docs/despliegue.md)

489da33 Fix: pinear bcrypt<4.0 por incompatibilidad con passlib 1.7.4
        1 archivo  · +4          (requirements.txt)

2023bf6 Render: pivot a runtime Docker para soportar Playwright
        9 archivos · +74 / −34   (Dockerfile, render.yaml, database.py, docs)

3942b3b Inicial: Fases 1 y 2 completas
        51 archivos · +3968      (todo el árbol base)
```

## 8. Para continuar en Gemini — instrucciones

> Eres un asistente de arquitectura y planificación de software.
>
> Tienes el contexto completo del proyecto `consulta_placas_ec` arriba: backend FastAPI + Playwright en Docker desplegado en Render, con frontend Next.js separado en Vercel. Fase 1 y Fase 2 cerradas (consultas públicas con caché + auth JWT + CRUD de vehículos/dueños/kilometraje). **Fases 3 (Billetera + Favoritos + Mantenimientos) y 4 (compra-venta: token privado + Marketplace público) están documentadas como reglas inmutables en la sección 10 de `CLAUDE.md` pero aún NO codeadas.** Fases 5 (OCR de placa) y 6 (app móvil) más adelante.
>
> El usuario quiere planificar el TO-BE: próximos pasos, mejoras, nuevas funcionalidades. Cuando describa qué quiere hacer, responde con:
> 1. **Evaluación de impacto** sobre lo existente (qué se rompe, qué se mantiene).
> 2. **Archivos a crear o modificar** (con rutas exactas siguiendo la convención `routers/`, `services/`, `models/`, `schemas/`, `utils/`).
> 3. **Skills de Claude Code a activar** del set `agregar-fuente-consulta`, `desplegar-mvp`, `modelo-dominio-vehiculo`, `respuesta-api-estandar`, `scraping-respetuoso`, `validacion-datos-ec`.
> 4. **Estructura sugerida** de la solución (nuevas entidades, endpoints, migración Alembic si aplica).
> 5. **Posibles riesgos o dependencias** (limitaciones de scraping en cloud, captcha, tamaño RAM, expiración Postgres, etc.).
>
> **Reglas duras a respetar** (sección 10 de `CLAUDE.md`):
> - Todo en español (identificadores, rutas, columnas: `vehiculos_favoritos`, `transacciones_tokens`, `precio_venta_usd`, `/marketplace`).
> - No saltar fases del roadmap sin acordarlo explícitamente.
> - No agregar dependencias nuevas sin justificación.
> - Los módulos CRUD del MVP (Billetera, Favoritos, Mantenimientos, Marketplace) NO invocan los servicios de Playwright — solo tocan la BD.
> - Migraciones Alembic manuales con nombre descriptivo (ej. `0004_billetera.py`); nada de `--autogenerate` a ciegas.
> - Marketplace usa `selectinload` (evitar N+1).
> - Economía de tokens: saldo inicial 5, nunca negativo, auditar toda transacción en `transacciones_tokens`.
> - Favoritos: placa como `String` (no FK), validada con `validar_placa`.
> - Mantenimientos: fecha y kilometraje monotónicos (≥ último registro); solo sobre vehículos propios (JWT).
> - Marketplace: solo aparecen autos con `en_venta=True` y `precio_venta_usd>0`; nunca exponer VIN completo ni nombre del dueño.
> - Errores de negocio → HTTP 400/403 con JSON estructurado, nunca 500.

## 9. Próximos pasos sugeridos

Ordenados por prioridad y por dependencia con el roadmap.

1. **Requisito previo — migrar Postgres Render → Supabase o Neon** (PostgreSQL 16+) antes de codear Fases 3 y 4. Crear el proyecto, obtener `DATABASE_URL` y colocarla en `.env` local + env vars de Render. Es prerequisito explícito del spec del MVP.
2. **Fase 3 — Billetera de tokens**. Tabla `transacciones_tokens` (auditoría) + campo de saldo en `Usuario` (inicial 5, `>= 0`). Migración `0004_billetera.py`. Router `/tokens` o servicio de débito/crédito con validación de saldo. Errores de negocio → HTTP 400.
3. **Fase 3 — Favoritos**. Tabla `vehiculos_favoritos` con placa como `String` (no FK), validada con `validar_placa`. Router `/favoritos` (CRUD propio del usuario).
4. **Fase 3 — Mantenimientos**. Tabla `mantenimientos`: `tipo`, `fecha`, `kilometraje_relacionado`, `taller`, `costo`, opcional `adjuntos`. Router `routers/mantenimientos.py` + schema + relación `Vehiculo.mantenimientos`. Reusar patrón de `kilometraje` (validación monotónica fecha+km; propiedad por `Depends(vehiculo_propio)`).
5. **Fase 4 — Token de compra-venta**. Tabla `enlaces_compartidos`: `token UK`, `vehiculo_id FK`, `scope JSONB`, `fecha_expiracion`. Endpoint público `GET /compartido/{token}` que devuelve `VehiculoSalidaCompartida` (ya implementado en `schemas/vehiculo.py`). TTL ≤ 7 días, scope opt-in por campo.
6. **Fase 4 — Marketplace público**. Columnas `en_venta`, `precio_venta_usd`, `url_externa` en `vehiculos` (migración). Endpoint `GET /marketplace` con `selectinload`, filtro `en_venta=True AND precio_venta_usd>0`, salida con VIN ofuscado y sin nombre del dueño.
7. **Mover PNGs de debug** a carpeta `debug/` gitignored o eliminarlos del repo (no son útiles versionados).
8. **Cron externo para evitar cold start**: UptimeRobot o GitHub Actions pegando a `/health` cada 10 min. Cero costo.
9. **Decisión sobre AMT y FGE en producción** (no bloquea Fases 3 y 4, que son CRUD sin scraping): aceptar la limitación de IPs de datacenter, o invertir en proxy residencial ($50–300/mes) o arquitectura híbrida (workers locales).
10. **Tests de parser con HTML fixtures**: convertir los 3 PNGs de debug en `tests/fixtures/<fuente>.html` y testear los parsers de `services/` aisladamente.
11. **README.md público mínimo** si se abre el repo a colaboradores. Reutilizar contenido de `CLAUDE.md` y `docs/despliegue.md`.

---

**Nota de privacidad de este snapshot**: no incluye contraseñas, JWT secrets, ni datos personales. Las URLs públicas (Render, Vercel) y los identificadores genéricos (placa de ejemplo `ABC1234`) son los únicos datos concretos. El archivo `.env` con valores reales NO está incluido y está fuera de git (verificado).
