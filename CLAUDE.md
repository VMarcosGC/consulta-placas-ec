# CLAUDE.md — Proyecto `consulta_placas_ec`

Este archivo es la fuente de verdad para cualquier agente o desarrollador que toque el proyecto. Léelo completo antes de hacer cambios.

---

## 1. Propósito del proyecto

Plataforma (móvil + web) para que cualquier persona en Ecuador conozca el **estado integral de un vehículo** a partir de su placa, sus características o una foto. Cuatro pilares:

1. **Consulta pública por placa** — agrega información de fuentes oficiales: ANT (matriculación, citaciones), SRI (valores tributarios), AMT Quito (infracciones municipales), **Fiscalía General del Estado / FGE** (noticias del delito asociadas a placa, cédula o nombres — accidentes, robos, denuncias).
2. **Consulta por foto** — el usuario fotografía el vehículo o la placa; OCR/visión extrae la placa y dispara el flujo de consulta.
3. **Historial privado del vehículo** — usuarios autenticados pueden registrar y mantener actualizado: kilometraje, dueños (histórico), mantenimientos, documentos, novedades. Estos datos NO son públicos.
4. **Modo compra-venta con token** — el dueño genera un enlace/token temporal que muestra a un comprador interesado el historial del vehículo sin que este necesite cuenta.

---

## 2. MVP en producción (mayo 2026)

| Componente | URL | Plataforma |
|---|---|---|
| **Backend** (FastAPI + Playwright en Docker) | [consulta-placas-ec.onrender.com](https://consulta-placas-ec.onrender.com) | Render free tier |
| **Frontend** (Next.js 16 + Tailwind 4) | [consulta-placas-web.vercel.app](https://consulta-placas-web.vercel.app) | Vercel free |
| **PostgreSQL** | (interna) | Render |
| **Repo backend** | [VMarcosGC/consulta-placas-ec](https://github.com/VMarcosGC/consulta-placas-ec) | GitHub |
| **Repo frontend** | [VMarcosGC/consulta-placas-web](https://github.com/VMarcosGC/consulta-placas-web) | GitHub |

Ver detalle de deploy en [docs/despliegue.md](docs/despliegue.md) y skill [desplegar-mvp](.claude/skills/desplegar-mvp/SKILL.md).

---

## 3. Estado por fase

### Fase 1 — Consultas estables ✅ cerrada
- [main.py](main.py) — FastAPI con endpoints públicos `/consultar/{placa}`, `/consultar-judicial/{cedula}` y `/health`.
- [services/ant.py](services/ant.py) — ANT con Playwright. Funcional local y cloud.
- [services/sri.py](services/sri.py) — SRI. Devuelve `bloqueado_captcha` (reCAPTCHA Enterprise invisible).
- [services/amt.py](services/amt.py) — AMT con iframe detection y manejo de overlay "Consultando". Funcional local; bloqueado en cloud (ver sección 8).
- [services/fiscalia.py](services/fiscalia.py) — Fiscalía SIAF. Funcional local; bloqueado en cloud.
- [services/cache.py](services/cache.py) — Caché en Postgres con TTL configurable. Solo cachea `consulta_realizada` y `sin_resultados`.

### Fase 2 — Auth + dominio + deploy ✅ cerrada
- [auth/security.py](auth/security.py) — bcrypt (pin `<4.0` por bug con passlib) + JWT HS256.
- [auth/dependencies.py](auth/dependencies.py) — `usuario_actual` y `vehiculo_propio` dependencies.
- [routers/auth.py](routers/auth.py) — `POST /auth/registro`, `POST /auth/login`, `GET /auth/me`.
- [routers/vehiculos.py](routers/vehiculos.py) — CRUD completo de vehículos del usuario (con VIN, motor, chasis).
- [routers/duenos.py](routers/duenos.py) — Histórico de dueños con cierre automático del anterior.
- [routers/kilometraje.py](routers/kilometraje.py) — Lecturas inmutables con validación monotónica.
- [models/](models/) — `Consulta`, `Usuario`, `Vehiculo`, `DuenoHistorico`, `KilometrajeLectura`.
- [schemas/vehiculo.py](schemas/vehiculo.py) — 3 niveles de visibilidad: `Completa`, `Compartida` (ofuscado), `Publica`.
- [utils/validators.py](utils/validators.py) — `validar_placa`, `validar_cedula`, `validar_vin` (ISO 3779/3780).
- [utils/ofuscacion.py](utils/ofuscacion.py) — `ofuscar_vin`, `decodificar_origen_vin`, tabla `PAISES_VIN` (WMI).
- **Deploy**: Docker (imagen oficial de Playwright) en Render + Vercel para el frontend.
- **Frontend**: Next.js 16 App Router + Tailwind 4 + tema oscuro con gradient brand. Landing comercial + consulta pública + auth + mi-garage + precios. Vive en repo separado [consulta-placas-web](https://github.com/VMarcosGC/consulta-placas-web).

### Próximas fases
| Fase | Objetivo | Entregables clave |
|---|---|---|
| **3** | Mantenimientos | Tabla `mantenimientos`: tipo, fecha, kilometraje, taller, costo, adjuntos. |
| **4** | Compra-venta con token | Tabla `enlaces_compartidos`: token, vehículo, expiración, scope. Usa `VehiculoSalidaCompartida` (ya implementado). |
| **5** | OCR / foto | Endpoint que recibe imagen → extrae placa (Tesseract o servicio cloud) → flujo normal. |
| **6** | Mobile + features de pago | App móvil, integración con gateway local (PlaceToPay/MercadoPago). |

No saltar fases. Cada una asume las anteriores estables.

---

## 4. Stack estándar

### Backend (repo `consulta_placas_ec`)
- **Lenguaje**: Python 3.11+ (en producción: imagen Docker con Python 3.10 vía Playwright official).
- **API**: FastAPI con routers organizados en `routers/`.
- **Scraping**: Playwright async con Chromium. Preferir `httpx` si la fuente sirve HTML estático o JSON.
- **BD**: PostgreSQL (JSONB para respuestas crudas; índices compuestos en `consultas`).
- **ORM/Migraciones**: SQLAlchemy 2 + Alembic (migraciones manuales para versionado predecible).
- **Validación/serialización**: Pydantic 2.
- **Auth**: `passlib[bcrypt]` (con `bcrypt<4.0` pineado) + `python-jose` (JWT HS256).
- **Deploy**: Docker (imagen `mcr.microsoft.com/playwright/python:v1.48.0-jammy`) en Render.

### Frontend (repo `consulta-placas-web`)
- **Framework**: Next.js 16 (App Router, Turbopack, RSC).
- **UI**: React 19 + Tailwind CSS 4 (theme inline con `@theme`).
- **Tono visual**: moderno joven — theme dark, gradient `violet-500 → pink-500 → amber-500`.
- **Cliente HTTP**: `fetch` nativo en wrapper tipado (`src/lib/api.ts`).
- **Auth**: JWT en `localStorage` (sin SSR para páginas privadas).
- **Deploy**: Vercel free.

**No agregar dependencias nuevas sin justificación documentada** en el PR o commit.

---

## 5. Convenciones de código

- **Idioma**: nombres de funciones, variables, rutas, columnas y campos JSON en **español**, en ambos repos. Ejemplos: `consultar_ant`, `validar_placa`, `/consultar/{placa}`, `kilometraje_lecturas.fecha_lectura`, componente `ConsultaForm`. Mantener.
- **Servicios externos**: viven en `services/<fuente>.py` y exponen `async def consultar_<fuente>(arg) -> dict`.
- **Routers**: cada grupo de endpoints en `routers/<grupo>.py` con `APIRouter(prefix=..., tags=[...])`. `main.py` solo orquesta `include_router`.
- **Schemas Pydantic**: `schemas/<entidad>.py`. Convención: `<Entidad>Crear`, `<Entidad>Actualizar`, `<Entidad>Salida` (más variantes de visibilidad si aplica, ver vehículo).
- **Validadores**: `utils/validators.py`. Una función por tipo (`validar_placa`, `validar_cedula`, `validar_vin`) que devuelve el valor normalizado o lanza `ValueError`.
- **Manejo de errores en servicios**: un servicio externo **nunca debe propagar excepciones al endpoint**. Captura todo y devuelve `{"estado": "error", "error": "..."}`.

Ver skills en [.claude/skills/](.claude/skills/) para procedimientos detallados.

---

## 6. Estructura de respuesta estándar

Toda función `consultar_<fuente>` devuelve:

```json
{
  "fuente": "ANT|SRI|AMT|FGE",
  "placa": "ABC1234",
  "estado": "consulta_realizada|error|pendiente_integracion|sin_resultados|bloqueado_captcha",
  "datos": { ... } | null,
  "error": "string (solo cuando estado=error o bloqueado_captcha)"
}
```

`bloqueado_captcha`: la fuente respondió pero la submission fue bloqueada silenciosamente (caso SRI con reCAPTCHA invisible). El servicio detecta el bloqueo porque la respuesta vino vacía sin error técnico.

Para la Fiscalía (FGE), el campo de identificación se llama `termino` en vez de `placa` porque el portal acepta placa, cédula, RUC, nombres o NDD.

El endpoint público adiciona un objeto `resumen` con indicadores derivados. Ver skill [respuesta-api-estandar](.claude/skills/respuesta-api-estandar/SKILL.md).

---

## 7. Identificadores sensibles y ofuscación

Los datos en `vehiculos` incluyen identificadores que NO deben mostrarse completos a terceros:
- `vin` (17 caracteres, ISO 3779/3780)
- `numero_motor`
- `numero_chasis`

Tres niveles de visibilidad implementados en [schemas/vehiculo.py](schemas/vehiculo.py) y [utils/ofuscacion.py](utils/ofuscacion.py):

| Nivel | Uso | Qué muestra |
|---|---|---|
| `completo` | Dueño autenticado en `/vehiculos/{id}` | Valor sin ofuscar. |
| `origen` | Token de compra-venta (Fase 4) | Primeros 3 caracteres + país decodificado del WMI. |
| `oculto` | Vistas públicas mínimas | Solo país de origen; el valor literal nunca aparece. |

Ver skill [validacion-datos-ec](.claude/skills/validacion-datos-ec/SKILL.md) para reglas de validación y decodificación.

---

## 8. Dependencias externas frágiles y limitaciones conocidas

ANT, SRI, AMT y Fiscalía (FGE) son sitios públicos que cambian sin aviso. Reglas:

- **Tolerancia a fallos**: una fuente caída NO debe romper la respuesta global. El endpoint siempre responde 200, marcando la fuente fallida con `estado: error`.
- **Capturas de debug**: guardar `debug_<fuente>_*.png` en errores de scraping (gitignored).
- **Caché en BD**: respuestas con `estado in {consulta_realizada, sin_resultados}` se guardan; errores y `bloqueado_captcha` NO se cachean (para reintentar).

### Limitación 1: SRI bloqueado por reCAPTCHA
El portal SRI usa **Google reCAPTCHA Enterprise invisible**. Playwright es detectable y la submission falla silenciosamente sin challenge visual. Resultado: `estado: bloqueado_captcha`. Pasa **tanto en local como en cloud**. Workarounds futuros:
- Servicios pagos de captcha-solving (2captcha, anti-captcha): ~$1-3 por 1000 resoluciones.
- `playwright-stealth` para reducir detectabilidad (no garantiza).
- Solicitar acceso al API oficial de SRI (proceso administrativo).

### Limitación 2: IPs de datacenter bloqueadas (AMT y FGE)
Descubierto al desplegar en Render (mayo 2026). Los portales de **AMT y Fiscalía** detectan IPs de proveedores cloud (Render, AWS, GCP) y sirven páginas distintas o desafíos anti-bot. Diferencia observada:

| Fuente | Local (IP residencial Ecuador/SA) | Render (IP datacenter US) |
|---|---|---|
| ANT | ✅ funciona | ✅ funciona |
| SRI | 📌 reCAPTCHA invisible | 📌 reCAPTCHA invisible |
| AMT | ✅ funciona | ❌ sirve `inputCode.jsp` (challenge) |
| FGE | ✅ funciona | ❌ sirve página sin `input#pwd` |

**No es un bug del código** — el código corre idéntico, los servidores responden distinto según IP origen.

Opciones para mitigar:
1. **Aceptar la limitación en cloud** (estado actual del MVP). Para demos: usar local. Para producción de bajo volumen: ANT puede ser suficiente.
2. **Proxy residencial pago** (Bright Data, Smartproxy, IPRoyal): $50–300/mes. Configurar en el cliente Playwright.
3. **Arquitectura híbrida**: backend FastAPI en cloud + workers de scraping en local/raspberry con IP residencial, que pushean resultados a la BD del cloud.
4. **API oficial** con cada institución: proceso administrativo, lento pero definitivo.

Antes de proponer cambios en `services/amt.py` o `services/fiscalia.py` para "arreglar" un error en producción, verificar si está corriendo desde IP residencial (local) o datacenter (Render). El skill [scraping-respetuoso](.claude/skills/scraping-respetuoso/SKILL.md) tiene la matriz de síntomas.

---

## 9. Privacidad y datos sensibles

| Tipo de dato | Acceso |
|---|---|
| Consultas a fuentes públicas (ANT/SRI/AMT/FGE) | Anónimo. Sin auth. |
| Vehículos guardados, dueños históricos, kilometraje, mantenimientos | Requiere cuenta del dueño. Filtrar por `usuario_id` en cada query. |
| VIN, motor, chasis | Mostrar completos solo al dueño autenticado; ofuscar para terceros. |
| Compartir compra-venta | Token con expiración ≤ 7 días, scope explícito (qué campos muestra). |

Reglas duras:
- Nunca devolver datos privados en el endpoint público `/consultar/{placa}`.
- Usar `Depends(usuario_actual)` o `Depends(vehiculo_propio)` para todo endpoint que toque datos del usuario.
- El scope del token define qué se ve; default mínimo, opt-in para cada campo sensible.

---

## 10. Cómo correr localmente (Windows + PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
Copy-Item .env.example .env   # primera vez; ajustar DATABASE_URL y JWT_SECRET_KEY
alembic upgrade head
python run.py
```

Probar:
```powershell
curl http://localhost:8000/consultar/ABC1234
```

**Importante**:
- Usar `python run.py`, NO `uvicorn main:app --reload`. En Windows, uvicorn deja activa `WindowsSelectorEventLoopPolicy` en el worker, lo cual rompe Playwright con `NotImplementedError`. El launcher [run.py](run.py) fija `WindowsProactorEventLoopPolicy` correctamente.
- En local, las 3 fuentes (ANT/AMT/FGE) funcionan. SRI siempre devuelve `bloqueado_captcha`.

### Frontend local (en repo separado)

```powershell
cd ..\consulta-placas-web
npm install
# .env.local apunta a http://localhost:8000 por default
npm run dev      # http://localhost:3000
```

---

## 11. Despliegue (MVP en cloud)

Ver guía completa en [docs/despliegue.md](docs/despliegue.md). Resumen:

- **Backend**: Render web service plan free, **runtime Docker** (no native Python). Imagen base `mcr.microsoft.com/playwright/python:v1.48.0-jammy`. Blueprint en [render.yaml](render.yaml).
- **BD**: PostgreSQL en Render free (90 días gratis, después $7/mes o migrar a Supabase/Neon).
- **Frontend**: Vercel free. `NEXT_PUBLIC_API_URL` apunta al servicio Render. CORS estricto en backend con `CORS_ORIGINS`.

### Reglas duras del deploy
- **Toda config sensible va en env vars** (`.env` local, dashboard de Render/Vercel en prod). Nada hardcodeado.
- **`HOST=0.0.0.0` y `PORT` dinámico** en producción (ya soportado en [run.py](run.py)).
- **CORS estricto**: solo la URL del frontend más localhost para dev.
- **Cold start del free tier**: ~30s tras 15 min de inactividad. Mitigar con cron externo (UptimeRobot) que toque `/health` cada 10 min.
- **DATABASE_URL prefix**: Render emite `postgresql://`, psycopg 3 requiere `postgresql+psycopg://`. `database.py` reescribe automático.
- **bcrypt fix**: `bcrypt<4.0` pineado por incompatibilidad con `passlib==1.7.4` (`AttributeError: __about__`).

Skill paso a paso: [desplegar-mvp](.claude/skills/desplegar-mvp/SKILL.md).

---

## 12. Diagramas de arquitectura

Diagramas vivos del sistema en [docs/arquitectura.md](docs/arquitectura.md) (Mermaid). Renderizan nativos en VSCode, GitHub y GitLab. Mantener actualizados:
- Cada vez que cierre un bloque del roadmap → marcar el nodo correspondiente.
- Cuando se agregue una fuente → sumar a la topología y la secuencia.
- Cuando se cree una entidad → sumar al ER.

---

## 13. Disciplina de iteración (anti trial-and-error)

Cada iteración fallida cuesta tiempo del usuario. Reglas obligatorias antes de proponer código nuevo de scraping o parsing:

1. **Evidencia antes que suposición**. Si vamos a tocar una fuente nueva o desconocida: primero un paso de descubrimiento (screenshot + dump de frames) y solo después escribir el scraper completo. No iterar a ciegas sobre selectores.
2. **Aprovechar lecciones documentadas**. Antes de escribir un servicio nuevo, leer el skill [scraping-respetuoso](.claude/skills/scraping-respetuoso/SKILL.md) y los gotchas registrados (iframe, componentes custom, captcha invisible, overlay de loading, IPs datacenter).
3. **Parser sobre HTML real, no sobre regex adivinados**. Si no se vio el HTML/screenshot, el parser es especulativo. Decirlo explícitamente y dejar TODO claro.
4. **Higiene de refactor**. Al cambiar nombres de variables o estructuras, hacer grep del nombre viejo y eliminarlo completamente — no dejar referencias muertas que aparecen en runtime (NameError, KeyError).
5. **Tests de parser con muestras de texto** antes de pegarlo al scraper. Un parser que no se probó con texto crudo real es deuda técnica.
6. **Una sola pregunta clarificadora a la vez**. Si hay dudas críticas, preguntar antes de codear. No suponer.
7. **Local vs cloud**: si un servicio falla solo en cloud y no en local, casi siempre es IP o ENV — NO código. Verificar antes de "arreglar".

Aplicación práctica: para AMT terminamos en ~6 rondas porque saltamos estos pasos. Para futuras fuentes, seguir el orden.

---

## 14. Qué NO hacer

- No reescribir nombres al inglés.
- No mockear las fuentes en tests de integración — usar fixtures HTML guardados.
- No exponer respuestas crudas de scraping al usuario final; siempre pasar por el parser.
- No agregar dependencias nuevas sin justificación documentada.
- No saltar fases del roadmap sin acordarlo explícitamente.
- No paralelizar requests contra la misma fuente (ver skill `scraping-respetuoso`).
- No commitear `.env` o variables sensibles. Todas las claves se generan o se piden por env var.
- No mezclar lógica de UI con lógica de scraping — frontend y backend están separados a propósito.
- No agregar campos sensibles (VIN, motor, chasis, kilometraje real) a respuestas públicas — usar schemas con nivel de visibilidad apropiado.
