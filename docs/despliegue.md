# Despliegue — Render (free tier) con Docker

Guía para desplegar el backend de `consulta_placas_ec` en [Render](https://render.com) gratis. Pensado para pruebas / medición de funcionalidad con tráfico bajo.

---

## Por qué Docker (y no native Python runtime)

Render free tier ofrece dos runtimes para Python:
- **Native Python**: pip install, pero **NO permite `sudo apt-get`**. Playwright necesita libs del sistema (libnss3, libcups2, etc.) que solo se instalan vía apt → falla `playwright install --with-deps`.
- **Docker**: corremos nuestra propia imagen con las libs preinstaladas. Único camino confiable para Playwright en Render.

El [Dockerfile](../Dockerfile) usa `mcr.microsoft.com/playwright/python:v1.48.0-jammy` (imagen oficial de Microsoft con Chromium + libs ya dentro).

---

## Recursos involucrados

| Componente | Plan | Limitaciones |
|---|---|---|
| **Web Service** (Docker, FastAPI + Playwright) | Free | 512 MB RAM · 0.1 CPU · duerme tras 15 min sin tráfico (cold start ~30s) · 750h/mes |
| **PostgreSQL** | Free | 1 GB storage · **expira en 90 días** (después: $7/mes o migrar a Supabase/Neon) |

Para BD sin caducidad ver sección [Alternativa BD](#alternativa-bd-supabase--neon).

---

## Opción A — Blueprint (un solo click)

1. **Push del repo a GitHub** con todos los archivos (incluido [render.yaml](../render.yaml)).
2. En Render: **New → Blueprint** → conectar el repo.
3. Render lee `render.yaml` y crea:
   - El servicio web `consulta-placas-ec`.
   - La base `consulta-placas-db`.
4. **Antes del primer deploy**, configurar en *Environment* del servicio (variables marcadas `sync: false`):
   - `JWT_SECRET_KEY` — generar con:
     ```bash
     python -c "import secrets; print(secrets.token_urlsafe(64))"
     ```
   - `CORS_ORIGINS` — URL del frontend Next.js, ej: `https://mi-frontend.vercel.app,http://localhost:3000`.
5. Render hace `docker build` con [Dockerfile](../Dockerfile) (descarga la imagen base de Playwright ~1GB la primera vez, luego cachea) y corre el `CMD` definido: `alembic upgrade head && python run.py`.

Si todo va bien: `https://consulta-placas-ec.onrender.com/health` devuelve `{"status":"ok"}`.

---

## Opción B — Manual (sin blueprint)

Si no querés usar `render.yaml`:

1. **Crear PostgreSQL en Render**: Dashboard → New → PostgreSQL → plan Free. Guardá la "Internal Database URL".
2. **Crear Web Service**: New → Web Service → conectar repo.
   - **Runtime: Docker** (NO Python).
   - Dockerfile Path: `./Dockerfile` (default).
   - Health check path: `/health`.
   - Environment variables (todas las del `render.yaml`, manualmente):
     - `DATABASE_URL` = (Internal Database URL del paso 1; `database.py` reescribe el prefijo automáticamente).
     - `JWT_SECRET_KEY` = (generada como arriba).
     - `JWT_ALGORITHM` = `HS256`.
     - `JWT_EXPIRA_MINUTOS` = `1440`.
     - `CACHE_TTL_MINUTOS` = `30`.
     - `CORS_ORIGINS` = `https://<frontend>,http://localhost:3000`.
     - `HOST` = `0.0.0.0`.

---

## Verificación post-deploy

```bash
# Health (no debería cold-startear si está despierto)
curl https://consulta-placas-ec.onrender.com/health

# Registro
curl -X POST https://consulta-placas-ec.onrender.com/auth/registro \
  -H "Content-Type: application/json" \
  -d '{"email":"prueba@test.com","password":"clave12345"}'

# Login
curl -X POST https://consulta-placas-ec.onrender.com/auth/login \
  -d "username=prueba@test.com&password=clave12345"

# Consulta pública (esto despertará el servicio si dormía; primer call ~30s)
curl https://consulta-placas-ec.onrender.com/consultar/TBA3373
```

OpenAPI docs en `https://consulta-placas-ec.onrender.com/docs`.

---

## Limitaciones a anticipar

| Síntoma | Causa | Mitigación |
|---|---|---|
| Build de Docker tarda 5-10 min la primera vez | Descarga de imagen base de Playwright (~1 GB) | Esperado. Builds posteriores son rápidos (cachea capas). |
| Primer request tras 15 min de inactividad tarda 20-40s | Cold start del free tier | Cron externo (UptimeRobot, GitHub Actions) que toque `/health` cada 10 min. |
| Playwright se queda sin memoria al lanzar Chromium | 512MB es tight | Lanzar Chromium con `--single-process --no-zygote` (no implementado aún). Si pasa seguido: pagar plan Starter ($7/mes). |
| Postgres expira a los 90 días | Política de Render | Migrar a Supabase (gratis 500MB, sin caducidad) o Neon. Cambiar `DATABASE_URL`. |
| Logs de scraping (debug_*.png) no persisten | Disco efímero en Render | Aceptable: son diagnóstico, no datos. Para persistir: S3/R2 (extra trabajo). |
| `ModuleNotFoundError: No module named 'psycopg2'` | Render emite URL como `postgresql://` (espera psycopg2) | RESUELTO: `database.py` reescribe a `postgresql+psycopg://` automáticamente. |

---

## Alternativa BD: Supabase / Neon

Si no querés perder la BD en 90 días:

1. Crear proyecto gratis en [Supabase](https://supabase.com) o [Neon](https://neon.tech).
2. Copiar la **connection string** que dan (asegurate de usar el formato `postgresql://`).
3. Convertir a `postgresql+psycopg://...` (psycopg 3) cambiando el prefijo.
4. En Render → Environment: poner ese `DATABASE_URL`. Eliminar la base de Render si ya no la usás.

---

## Frontend (Next.js) — placeholder

Cuando se construya el frontend Next.js, desplegarlo en Vercel free:

1. `npx create-next-app@latest consulta-placas-web`.
2. Configurar variable `NEXT_PUBLIC_API_URL=https://consulta-placas-ec.onrender.com`.
3. Push a GitHub → Import en Vercel → deploy.
4. Volver a Render y agregar la URL del frontend al `CORS_ORIGINS`.

---

## Checklist antes de mergear cambios a `main` (que dispara deploy)

- [ ] `pip install -r requirements.txt` corre limpio localmente.
- [ ] `alembic upgrade head` aplica sin errores en BD local.
- [ ] `python run.py` arranca y `/health` responde 200.
- [ ] No hay secretos hardcodeados (todo lo sensible está en `.env`, que NO se commitea).
