---
name: desplegar-mvp
description: Desplegar el MVP de consulta_placas_ec en Render (backend Docker) y Vercel (frontend Next.js). Usar al hacer el primer deploy, cambiar plataforma de hosting o diagnosticar problemas de prod.
---

# Desplegar el MVP

Este skill cubre el proceso operativo de desplegar `consulta_placas_ec` en sus dos componentes:

- **Backend** (FastAPI + Playwright) → Render free tier con runtime Docker.
- **Frontend** (Next.js 16) → Vercel free.

Guía exhaustiva paso a paso en [docs/despliegue.md](../../../docs/despliegue.md). Este skill resume el flujo y consolida lecciones aprendidas.

## Arquitectura objetivo

```
Usuario
  ↓ HTTPS
[Vercel] consulta-placas-web.vercel.app   (Next.js 16, static + Server Components)
  ↓ fetch + JWT Bearer
[Render]  consulta-placas-ec.onrender.com  (Docker, FastAPI + Playwright)
  ↓
[Render Postgres]  o  [Supabase / Neon]
  ↓
Fuentes externas (ANT, AMT, FGE, SRI)
```

## Backend — Render (Docker)

### Por qué Docker y no Native Python

El runtime nativo Python de Render NO permite `sudo apt-get`. Playwright requiere libs del sistema (libnss3, libcups2, etc.) que solo se instalan vía apt. Síntoma del intento native: `su: Authentication failure` durante `playwright install --with-deps`.

Solución: imagen Docker oficial de Microsoft con Chromium + libs preinstalados.

### Archivos clave del repo

| Archivo | Rol |
|---|---|
| [`Dockerfile`](../../../Dockerfile) | Imagen base `mcr.microsoft.com/playwright/python:v1.48.0-jammy`, pip install, copy del código, CMD `alembic upgrade head && python run.py`. |
| [`.dockerignore`](../../../.dockerignore) | Excluye venv/cache/secretos del contexto de build. |
| [`render.yaml`](../../../render.yaml) | Blueprint: web service Docker + Postgres free + env vars (con flags `sync: false` para secretos). |
| [`run.py`](../../../run.py) | Lanza uvicorn respetando `HOST`/`PORT` env vars. |
| [`requirements.txt`](../../../requirements.txt) | Incluye `bcrypt>=3.2.0,<4.0.0` pineado (incompatibilidad con passlib 1.7.4). |

### Flujo de deploy

1. **Crear repo en GitHub** (si no existe) y pushear `main`.
2. En Render → **New → Blueprint** → conectar el repo.
3. Render detecta `render.yaml`, propone crear web service + Postgres.
4. **Antes del primer Apply**, configurar env vars `sync: false`:
   - `JWT_SECRET_KEY` — generar con `python -c "import secrets; print(secrets.token_urlsafe(64))"`. NO reusar el de `.env` local.
   - `CORS_ORIGINS` — `http://localhost:3000,<URL-vercel>` (cuando exista el frontend).
5. Apply. Build de Docker tarda ~8–12 min la primera vez (descarga imagen ~1GB).
6. Live → verificar `https://<servicio>.onrender.com/health` devuelve `{"status":"ok"}`.

### Variables de entorno (vista consolidada)

| Variable | Origen | Notas |
|---|---|---|
| `DATABASE_URL` | `fromDatabase` (Render Postgres) | `database.py` reescribe prefijo a `postgresql+psycopg://`. |
| `JWT_SECRET_KEY` | manual (sync: false) | 64 bytes urlsafe. Distinto al de dev. |
| `JWT_ALGORITHM` | render.yaml | `HS256`. |
| `JWT_EXPIRA_MINUTOS` | render.yaml | `1440` (24h). |
| `CACHE_TTL_MINUTOS` | render.yaml | `30`. |
| `CORS_ORIGINS` | manual (sync: false) | coma-separado, incluir URL del frontend Vercel y `http://localhost:3000`. |
| `HOST` | render.yaml | `0.0.0.0` (Render asigna PORT dinámico). |

## Frontend — Vercel (Next.js)

### Archivos clave del repo `consulta-placas-web`

- `package.json` con Next.js 16, React 19, Tailwind 4.
- `.env.local` (gitignored) apunta a `http://localhost:8000` en dev.
- En Vercel se configura `NEXT_PUBLIC_API_URL` apuntando al servicio Render.

### Flujo de deploy

1. **Push del repo** a GitHub.
2. En Vercel → **New Project** → importar el repo `consulta-placas-web`.
3. Framework Preset: detecta Next.js automático.
4. Environment Variables → agregar:
   - `NEXT_PUBLIC_API_URL=https://consulta-placas-ec.onrender.com`
5. Deploy. Tarda ~1–2 min.
6. **Volver a Render** y agregar la URL de Vercel al `CORS_ORIGINS` (separado por coma del `localhost:3000`).
7. Verificar que el frontend pueda consultar el backend sin errores CORS en la consola del browser.

## Diagnóstico de problemas reales

| Síntoma | Causa | Fix |
|---|---|---|
| Build falla con `su: Authentication failure` | Native runtime, intento de `apt-get` | Cambiar a runtime Docker (este skill ya lo asume). |
| `(trapped) error reading bcrypt version`, 500 en `/auth/registro` | bcrypt 4.x incompatible con passlib 1.7.4 | Pinear `bcrypt<4.0` en requirements.txt y redeployar. |
| `ModuleNotFoundError: No module named 'psycopg2'` | Render emite `postgresql://`, SQLAlchemy busca psycopg2 | Reescribir prefijo a `postgresql+psycopg://` en `database.py` (ya está). |
| Cold start de 30–40s tras 15 min inactividad | Free tier duerme | Cron externo (UptimeRobot) tocando `/health` cada 10 min. |
| `RuntimeError: JWT_SECRET_KEY no configurada` al arrancar | Env var `sync: false` no fue seteada en el dashboard | Ir a Environment del servicio en Render y agregarla. |
| Build tarda mucho (>15 min) | Primer build descarga imagen base ~1GB | Esperado. Builds siguientes cachean capas; solo el step de pip install se re-ejecuta si cambia `requirements.txt`. |
| AMT/FGE devuelven `error` en cloud pero funcionan en local | IP de datacenter bloqueada por anti-bot | NO es bug. Aceptar limitación o usar proxy residencial. Ver [scraping-respetuoso](../scraping-respetuoso/SKILL.md). |
| Frontend en Vercel da CORS error | URL de Vercel no está en `CORS_ORIGINS` del backend | Agregar en Render → Environment → `CORS_ORIGINS`, redeploy automático. |

## Anti-patrones del deploy

- ❌ Reusar `JWT_SECRET_KEY` de dev en prod (compromete todos los tokens emitidos en dev).
- ❌ Hardcodear `DATABASE_URL` en código en lugar de leer de env.
- ❌ `allow_origins=["*"]` con `allow_credentials=True` (vulnerabilidad CSRF).
- ❌ Commitear `.env`, `.env.local`, `.env.production` — siempre gitignored.
- ❌ Native Python runtime con Playwright en Render (fallará 100%).
- ❌ Olvidar reescribir el prefijo de `DATABASE_URL` para psycopg 3.
- ❌ "Arreglar" código para que AMT/FGE funcionen en cloud sin verificar primero la diferencia IP residencial vs datacenter.

## Costos del free tier (estado mayo 2026)

| Recurso | Plan | Limitaciones | Cuándo escalar |
|---|---|---|---|
| Render web service | Free | 512MB RAM · sleep 15 min · 750h/mes | Sleep molesto en demos → Starter $7/mes. Memoria justa con Playwright → mismo plan o mayor. |
| Render Postgres | Free | 1GB · **expira a 90 días** | Antes del día 80: migrar a Supabase o Neon (free ilimitado en tiempo) o pagar $7/mes. |
| Vercel | Free | Sin sleep · ancho de banda limitado | Cuando se acerque a 100GB/mes. |

## Próximas decisiones de hosting

Documentadas en orden de prioridad cuando el MVP necesite madurar:

1. **Mantener Render Docker, migrar BD a Neon/Supabase** antes del día 90 (gratis indefinido).
2. **Evaluar proxy residencial** si AMT/FGE en cloud es necesario para el producto.
3. **Cron warmer en GitHub Actions** que hace `GET /health` cada 10 min para evitar cold starts (no cuesta nada).
4. **Plan de pago** ($7/mes Render Starter) cuando los usuarios reales lleguen y el sleep sea bloqueante.