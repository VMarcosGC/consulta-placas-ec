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

## 2. Estado actual vs. visión

### Lo que existe hoy
- [main.py](main.py) — FastAPI con endpoints `GET /consultar/{placa}`, `GET /consultar-judicial/{cedula}`, y `/auth/registro|login|me`.
- [services/ant.py](services/ant.py) — Scraping con Playwright al portal de la ANT. Funcional.
- [services/sri.py](services/sri.py) — Scraping con Playwright al SRI. Devuelve `bloqueado_captcha` (reCAPTCHA invisible).
- [services/amt.py](services/amt.py) — Scraping al portal AXIS de AMT. Funcional.
- [services/fiscalia.py](services/fiscalia.py) — Scraping al SIAF de Fiscalía. Funcional.
- [services/cache.py](services/cache.py) — Caché en Postgres con TTL.
- [utils/validators.py](utils/validators.py) — `validar_placa`, `validar_cedula`.
- [auth/security.py](auth/security.py) — bcrypt + JWT.
- [auth/dependencies.py](auth/dependencies.py) — `usuario_actual` dependency.
- [models/](models/) — `Consulta`, `Usuario`, `Vehiculo`, `DuenoHistorico`, `KilometrajeLectura`.

### Lo que falta (alto nivel)
- CRUD de vehículos/dueños/kilometraje (Fase 2 — Bloque 3+).
- Token de compra-venta.
- OCR de placa desde foto.
- Frontend (móvil + web).

---

## 3. Roadmap por fases

| Fase | Objetivo | Entregables clave |
|---|---|---|
| **1** | Consultas estables + persistencia mínima | ANT/SRI/AMT/FGE integrados; tabla `consultas` (identificador + fuente + JSONB respuesta + timestamp) como caché. |
| **2** | Cuentas y vehículos del usuario | Auth JWT, tablas `usuarios`, `vehiculos`, `duenos_historico`, `kilometraje_lecturas`. |
| **3** | Mantenimientos | Tabla `mantenimientos`: tipo, fecha, kilometraje, taller, costo, adjuntos. |
| **4** | Compra-venta con token | Tabla `enlaces_compartidos`: token, vehículo, expiración, scope de campos visibles. |
| **5** | OCR / foto | Endpoint que recibe imagen → extrae placa (Tesseract o servicio cloud) → flujo normal. |
| **6** | App móvil + web | Stack a decidir cuando se llegue. |

No saltar fases. Cada fase asume las anteriores estables.

---

## 4. Stack estándar

- **Lenguaje**: Python 3.11+
- **API**: FastAPI (async)
- **Scraping**: Playwright async con Chromium. Preferir `httpx` si la fuente sirve HTML estático o JSON.
- **BD**: PostgreSQL (desde Fase 1). Aprovechar JSONB para respuestas crudas.
- **ORM/Migraciones**: SQLAlchemy 2 + Alembic.
- **Validación/serialización**: Pydantic 2.
- **Auth**: passlib[bcrypt] + python-jose (JWT HS256).
- **Frontend**: por definir (Fase 6).

**No agregar dependencias nuevas sin justificación documentada** en el PR o commit.

---

## 5. Convenciones de código

- **Idioma**: nombres de funciones, variables, rutas y campos JSON en **español**. Ejemplos existentes: `consultar_ant`, `validar_placa`, `/consultar/{placa}`, `tiene_pendientes`. Mantener.
- **Servicios externos**: viven en `services/<fuente>.py` y exponen `async def consultar_<fuente>(arg) -> dict`.
- **Validadores de formato**: en `utils/validators.py`. Una función por tipo (`validar_placa`, `validar_cedula`, etc.) que devuelve el valor normalizado o lanza `ValueError`.
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

`bloqueado_captcha`: la fuente respondió pero la submission fue bloqueada silenciosamente por reCAPTCHA invisible (caso actual de SRI). El servicio detectó el bloqueo porque la respuesta vino vacía sin error técnico.

Para la Fiscalía (FGE), el campo de identificación se llama `termino` en vez de `placa` porque el portal acepta placa, cédula, RUC, nombres o NDD.

El endpoint público adiciona un objeto `resumen` con indicadores derivados.

---

## 7. Dependencias externas frágiles

ANT, SRI, AMT y Fiscalía (FGE) son sitios públicos que cambian sin aviso. Reglas:

- **Tolerancia a fallos**: una fuente caída NO debe romper la respuesta global. El endpoint siempre responde, marcando la fuente fallida con `estado: error`.
- **Capturas de debug**: guardar `debug_<fuente>_*.png` en errores de scraping.
- **Caché en BD** (desde Fase 1): respuestas exitosas se guardan; si la última es reciente (< N minutos), no volver a scrapear.

### Limitación conocida: SRI bloqueado por reCAPTCHA
El portal SRI usa **Google reCAPTCHA Enterprise invisible**. Playwright es detectable y la submission falla silenciosamente sin challenge visual. Resultado: el scraper devuelve `estado: bloqueado_captcha`. Workarounds futuros (no en Fase 1):
- Servicios pagos de captcha-solving (2captcha, anti-captcha): ~$1-3 por 1000 resoluciones.
- `playwright-stealth` para reducir detectabilidad (no garantiza).
- Solicitar acceso al API oficial de SRI (proceso administrativo).

---

## 8. Privacidad y datos sensibles

| Tipo de dato | Acceso |
|---|---|
| Consultas a fuentes públicas (ANT/SRI/AMT/FGE) | Anónimo. Sin auth. |
| Vehículos guardados, dueños históricos, kilometraje, mantenimientos | Requiere cuenta del dueño. Nunca exponer por placa pública. |
| Compartir compra-venta | Token con expiración ≤ 7 días, scope explícito (qué campos muestra). |

Reglas duras:
- Nunca devolver datos privados en el endpoint público `/consultar/{placa}`.
- El scope del token define qué se ve; default mínimo, opt-in para cada campo sensible.

---

## 9. Cómo correr localmente (Windows + PowerShell)

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
Copy-Item .env.example .env   # solo la primera vez; ajusta DATABASE_URL y JWT_SECRET_KEY
alembic upgrade head
python run.py
```

Probar:
```powershell
curl http://localhost:8000/consultar/ABC1234
```

**Importante**: usar `python run.py` y NO `uvicorn main:app --reload`. En Windows, uvicorn con `--reload` deja activa `WindowsSelectorEventLoopPolicy` en el worker, lo cual rompe Playwright con `NotImplementedError`. El launcher [run.py](run.py) fija `WindowsProactorEventLoopPolicy` correctamente.

---

## 9.5. Despliegue (versión web para pruebas)

El backend se despliega en **Render free tier** para pruebas/medición de funcionalidad. Plan documentado en [docs/despliegue.md](docs/despliegue.md). Resumen:

- **Backend**: Render web service, plan free. Build con [build.sh](build.sh) (instala deps + Chromium). Start: `alembic upgrade head && python run.py`. Health check en `/health`.
- **BD**: PostgreSQL en Render free (90 días) o Supabase/Neon free (sin caducidad).
- **Frontend**: Next.js en Vercel free, consume API vía `NEXT_PUBLIC_API_URL`. Origen permitido vía `CORS_ORIGINS` env var.
- **Blueprint**: [render.yaml](render.yaml) define todo el stack para deploy de un click.

Reglas duras para mantener el deploy sano:
- **Toda config sensible va en env vars** (`.env` local, dashboard de Render en prod). Nada hardcodeado.
- **`HOST=0.0.0.0` y `PORT` dinámico** en producción (ya soportado en [run.py](run.py)).
- **CORS estricto en prod**: solo la URL del frontend más localhost para dev.
- **Endpoints públicos sin auth NO devuelven datos privados** (vehículos, kilometraje, dueños). Ver sección 8.
- **Cold start**: el free tier duerme tras 15 min sin tráfico. Primer request tarda ~30s. Si es bloqueante, cron externo en `/health` cada 10 min.

## 10. Diagramas de arquitectura

Diagramas vivos del sistema en [docs/arquitectura.md](docs/arquitectura.md) (Mermaid). Renderizan nativos en VSCode, GitHub y GitLab. Mantener actualizados:
- Cada vez que cierre un bloque del roadmap → marcar el nodo correspondiente.
- Cuando se agregue una fuente → sumar a la topología y la secuencia.
- Cuando se cree una entidad → sumar al ER.

## 11. Disciplina de iteración (anti trial-and-error)

Cada iteración fallida cuesta tiempo del usuario. Reglas obligatorias antes de proponer código nuevo de scraping o parsing:

1. **Evidencia antes que suposición**. Si vamos a tocar una fuente nueva o desconocida: primero un paso de descubrimiento (screenshot + dump de frames) y solo después escribir el scraper completo. No iterar a ciegas sobre selectores.
2. **Aprovechar lecciones documentadas**. Antes de escribir un servicio nuevo, leer el skill [scraping-respetuoso](.claude/skills/scraping-respetuoso/SKILL.md) y los gotchas registrados (iframe, componentes custom, captcha invisible, overlay de loading).
3. **Parser sobre HTML real, no sobre regex adivinados**. Si no se vio el HTML/screenshot, el parser es especulativo. Decirlo explícitamente y dejar TODO claro.
4. **Higiene de refactor**. Al cambiar nombres de variables o estructuras, hacer grep del nombre viejo y eliminarlo completamente — no dejar referencias muertas que aparecen en runtime (NameError, KeyError).
5. **Tests de parser con muestras de texto** antes de pegarlo al scraper. Un parser que no se probó con texto crudo real es deuda técnica.
6. **Una sola pregunta clarificadora a la vez**. Si hay dudas críticas, preguntar antes de codear. No suponer.

Aplicación práctica: para AMT terminamos en ~6 rondas porque saltamos estos pasos. Para SRI/FJ y futuras fuentes, seguir el orden.

## 12. Qué NO hacer

- No reescribir nombres al inglés.
- No mockear las fuentes en tests de integración — usar fixtures HTML guardados.
- No exponer respuestas crudas de scraping al usuario final; siempre pasar por el parser.
- No agregar dependencias nuevas sin justificación documentada.
- No saltar fases del roadmap sin acordarlo explícitamente.
- No paralelizar requests contra la misma fuente (ver skill `scraping-respetuoso`).
