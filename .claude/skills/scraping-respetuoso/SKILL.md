---
name: scraping-respetuoso
description: Criterios para hacer scraping a fuentes públicas (ANT, SRI, AMT, Fiscalía) sin abusar de ellas ni romper en producción. Usar al crear o modificar cualquier archivo en services/ o introducir cualquier nuevo scraping.
---

# Scraping respetuoso

Las fuentes que consultamos son **servicios públicos del Estado ecuatoriano**. Tratarlas mal nos saca del aire (bloqueos por IP, cambios anti-bot, mala reputación). Este skill define el mínimo no negociable.

## Estado actual de fuentes (mayo 2026)

| Fuente | Local (IP residencial) | Render (IP datacenter) | Notas |
|---|---|---|---|
| ANT | ✅ funciona | ✅ funciona | Servicio sin filtrado fuerte de IP. |
| AMT | ✅ funciona | ❌ sirve `inputCode.jsp` (challenge anti-bot) | Iframe + dropdown nativo + overlay "Consultando". |
| SRI | 📌 `bloqueado_captcha` | 📌 `bloqueado_captcha` | reCAPTCHA Enterprise invisible, no automatizable sin proxy/servicio captcha. |
| FGE | ✅ funciona | ❌ sirve página sin `input#pwd` | Acepta cédula, RUC, placa, nombres en mismo input. |

**Implicación**: el MVP en producción solo agrega ANT desde cloud. Para AMT/FGE en producción se requiere proxy residencial pago o arquitectura híbrida (ver [CLAUDE.md §8](../../../CLAUDE.md)).

## Cuándo usar este skill

- Crear un servicio nuevo en `services/`.
- Modificar un servicio existente.
- Cualquier código que haga requests HTTP a sitios externos.
- Antes de "arreglar" un servicio que falla en cloud pero funciona en local — primero verificar IP origen.

## Patrón obligatorio para fuentes nuevas/desconocidas

Antes de escribir el scraper completo, ejecutar un **paso de descubrimiento** que reduce iteraciones de prueba y error:

1. Lanzar Playwright contra la URL, esperar `networkidle` + 2s.
2. Guardar `discover_<fuente>.png` (full_page=True) y volcar `page.frames` con sus URLs.
3. Leer el screenshot (Read tool acepta PNG) para identificar: dropdowns, inputs, botones, iframes, overlays, captchas.
4. **Solo entonces** escribir el scraper con selectores derivados de evidencia, no de adivinación.

Ver [scripts/discover.py](../../../scripts/discover.py) — script reutilizable que ya hace este paso.

## Criterios obligatorios

### 1. Modo headless en producción
Playwright debe ir `headless=True`. Algunos portales detectan headless; usar `user_agent` realista en `new_context()`.

### 2. Timeouts explícitos
- Navegación: 60 segundos máximo.
- Espera entre acciones: usar `wait_for_selector` apuntando al elemento real, NO `wait_for_timeout` ciegos.

### 3. User-Agent realista (httpx o Playwright)
```python
USER_AGENT_REAL = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)
```

### 4. Rate-limit por fuente
- Máximo **1 request por placa, por fuente, cada N minutos** (default 30).
- Implementado con la tabla `consultas`: antes de scrapear, mirar si hay caché reciente.
- **Nunca hacer N requests en bucle para "warming"** ni pruebas masivas.

### 5. Reintentos controlados
- Máximo 2 reintentos por request.
- Backoff exponencial: 2s, 4s.
- Si fallan ambos, devolver `estado: error` y dejar al endpoint responder con las otras fuentes.

### 6. Concurrencia
- **Paralelo entre fuentes distintas** (ANT y SRI a la vez): permitido y deseable.
- **Secuencial dentro de la misma fuente**: nunca disparar 2 requests paralelas al mismo dominio.

### 7. Debugging en errores
- Guardar screenshot (`page.screenshot(path="debug_<fuente>.png", full_page=True)`) cuando el parser falla pero la página cargó.
- Considerar guardar también el HTML (`await page.content()`) en errores recurrentes.
- Estos archivos están en `.gitignore` — no se commitean.

### 8. Cerrar siempre el navegador
Usar `async with async_playwright() as p:` o `try/finally` para `browser.close()`.

### 9. No hardcodear esperas largas "por si acaso"
`wait_for_timeout(8000)` es un parche. Preferir `wait_for_selector` con el elemento esperado. Solo usar timeout fijo cuando el sitio no expone un selector estable.

## Windows + asyncio + Playwright

Playwright lanza Chromium como subprocess. En Windows, `asyncio` solo soporta subprocess con `WindowsProactorEventLoopPolicy`. Síntoma cuando falla: `NotImplementedError()` al lanzar el navegador.

- Lanzar la app SIEMPRE con [run.py](../../../run.py), nunca con `uvicorn main:app --reload` directo.
- `run.py` fija la política antes de cargar uvicorn (monkey-patch `uvicorn.loops.asyncio.asyncio_setup`).
- Si necesitás reload, exportá `UVICORN_RELOAD=1` antes de `python run.py` — y aceptá el riesgo de que en algún worker se pierda la política.

## Cloud (Render Docker) + Playwright

Render free tier con runtime nativo Python **no permite `sudo apt-get`**, y `playwright install --with-deps chromium` lo necesita para libs del sistema (libnss3, libcups2, etc.).

Fix definitivo: **runtime Docker** con imagen oficial de Microsoft:

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.48.0-jammy
# Chromium + libs ya preinstalados.
```

Ver [Dockerfile](../../../Dockerfile) y [render.yaml](../../../render.yaml). El skill [desplegar-mvp](../desplegar-mvp/SKILL.md) detalla el flujo completo.

## Lecciones aprendidas (errores reales en este repo)

| Síntoma | Causa real | Cómo evitarlo |
|---|---|---|
| `input:visible` no encuentra nada pero el form está en pantalla | Form dentro de iframe | Iterar `page.frames` y operar sobre el frame correcto |
| `click("text=Cédula")` falla con "element is not visible" | Es un `<option>` de `<select>` nativo, no clickeable | Usar `select_option(label=...)` sobre el `<select>` padre |
| Datos correctos pero números absurdos (ej: 3373 cuando es la placa) | Regex genérica capturó otro número del DOM | Regex anclada a etiqueta exacta del bloque destino |
| `NotImplementedError` al lanzar Chromium en Windows | uvicorn fuerza `WindowsSelectorEventLoopPolicy` | Lanzar con [run.py](../../../run.py) (monkey-patch + Proactor) |
| "Browser not supported" en el portal | UA por defecto de Playwright detectado | Pasar `user_agent` realista al `new_context` |
| Datos parciales en el screenshot | Overlay "Consultando" todavía visible | `wait_for_selector("text=Consultando", state="hidden")` |
| `NameError`/`KeyError` tras refactor | Referencias muertas a variables/claves viejas | Grep del nombre viejo y eliminar TODAS las apariciones |
| `consulta_realizada` con datos vacíos | reCAPTCHA invisible bloqueó submission silenciosa | Detectar respuesta vacía → `estado: bloqueado_captcha` |
| Funciona en local, falla en Render (ej: "Form no encontrado", iframes inesperados) | IP datacenter bloqueada por anti-bot del portal | NO es bug de código. Aceptar la limitación, usar proxy residencial, o cambiar a arquitectura híbrida. Ver CLAUDE.md §8. |
| `playwright install --with-deps` falla en Render con `sudo: command not found` | Native Python runtime no permite apt-get | Usar runtime Docker con imagen `mcr.microsoft.com/playwright/python`. Ver skill desplegar-mvp. |
| Build de Docker en Render exit code 1 sin causa clara tras `playwright install` | bcrypt 4 incompatible con passlib | Pinear `bcrypt>=3.2.0,<4.0.0` en requirements.txt. |

## Anti-patrones detectados

| Anti-patrón | Por qué es malo |
|---|---|
| Adivinar selectores sin ver la página | Genera 5+ iteraciones de prueba y error |
| Click en `<option>` directo | No es clickeable, hay que usar `select_option` |
| `headless=False` en producción | Abre Chrome visible, consume recursos |
| `wait_for_timeout(8000)` ciego | Si la página tarda más, falla; si tarda menos, desperdicia |
| Parser regex sin haber visto el HTML | Asunción ciega, parser frágil |
