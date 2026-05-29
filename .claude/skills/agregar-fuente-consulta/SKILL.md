---
name: agregar-fuente-consulta
description: Agregar una nueva fuente de consulta vehicular (ANT, SRI, AMT, Fiscalía, Registro Civil, etc.) siguiendo el patrón del proyecto. Usar cuando el usuario pida "integrar X", "agregar fuente X", "consultar también Y".
---

# Agregar una nueva fuente de consulta

Este skill aplica al proyecto [consulta_placas_ec](../../../AGENTS.md). Lee `AGENTS.md` antes de proceder si aún no lo has hecho.

## Cuándo usar este skill

El usuario pide integrar una fuente nueva: Registro Civil, otra municipalidad, IESS, etc.

## Pasos

### 0. Descubrimiento (obligatorio antes de codear)

Antes de escribir una sola línea del scraper:

1. Investigar la URL exacta. Si la fuente es un portal grande, verificar **a qué subpath redirige** desde el botón "Consultar".
2. Si es página dinámica/JS, correr [scripts/discover.py](../../../scripts/discover.py) actualizando la URL en `main()`. Devuelve `discover_<fuente>.png` y `discover_<fuente>.txt` con frames + selectores reales.
3. Leer ambos archivos (Read tool acepta PNG). Identificar: iframes, dropdowns nativos vs custom, inputs, botones, captchas, overlays.
4. **Solo entonces** escribir el scraper.

Saltar este paso costó ~6 iteraciones en AMT antes de descubrir el iframe + dropdown nativo. Ver [scraping-respetuoso](../scraping-respetuoso/SKILL.md) — tabla de lecciones aprendidas.

### 1. Decidir el método de acceso

- **¿La fuente tiene API pública o HTML estático?** → usar `httpx` (más rápido, menos frágil).
- **¿La fuente exige JavaScript, sesión, captcha?** → usar Playwright async, como [src/modules/consulta/services/ant.py](../../../src/modules/consulta/services/ant.py).
- Por defecto, intentar primero `httpx`. Solo escalar a Playwright si es necesario.
- **Verificar si la fuente filtra por IP**: si funciona en local pero no desde Render/cloud, casi seguro que sí. Ver [AGENTS.md §8](../../../AGENTS.md). Considerá la limitación antes de prometer disponibilidad en producción.

### 2. Crear el archivo del servicio

Ruta: `services/<fuente>.py`. Convención del nombre: minúsculas, sin tildes, sin guiones (ej: `amt.py`, `fiscalia.py`).

Contrato obligatorio:

```python
async def consultar_<fuente>(termino: str) -> dict:
    resultado = {
        "fuente": "<NOMBRE_CORTO>",   # ej: "FGE", "AMT", "RC"
        "placa": termino,             # o "termino" si acepta varios tipos
        "estado": "",
        "datos": None,
    }
    try:
        # ... lógica de consulta y parsing ...
        resultado["estado"] = "consulta_realizada"
        resultado["datos"] = datos_parseados
    except Exception as e:
        resultado["estado"] = "error"
        resultado["error"] = repr(e)
    return resultado
```

Reglas:
- **Nunca propagar excepciones**. Capturar todo y devolver `estado: error`.
- Estructura de respuesta exacta como dice `AGENTS.md` sección 6 y el skill `respuesta-api-estandar`.
- Si la fuente no aplica para la placa (ej: AMT solo Quito), devolver `estado: sin_resultados`.

### 3. Separar parsing de I/O

Como en [src/modules/consulta/services/ant.py](../../../src/modules/consulta/services/ant.py), la función `parsear_respuesta_<fuente>(texto)` debe vivir aparte de la función async. Esto permite probar el parser con fixtures sin tocar la red.

### 4. Registrar la fuente en `main.py`

En [main.py](../../../main.py):

1. Importar: `from services.<fuente> import consultar_<fuente>`.
2. Llamar dentro de `consultar_placa`: `resultado_<fuente> = await consultar_con_cache(sesion, placa_limpia, "<COD>", consultar_<fuente>)`.
3. Agregar al dict de respuesta: `"<fuente>": resultado_<fuente>`.
4. Si aporta indicadores agregables (citaciones, multas, denuncias), actualizar `resumen` con los flags correspondientes y subir `fuentes_consultadas`.

### 5. Reflejar la fuente en el frontend

El frontend ([consulta-placas-web](https://github.com/VMarcosGC/consulta-placas-web)) consume los campos de `/consultar/{placa}`. Para que la nueva fuente aparezca:

1. Agregar tipos a [`src/types/api.ts`](../../../../consulta-placas-web/src/types/api.ts): `Datos<Fuente>`, agregar la fuente al union de `FuenteRespuesta.fuente`, agregar campos al `ResumenConsulta`.
2. Agregar la card a [`src/components/ResultadoConsulta.tsx`](../../../../consulta-placas-web/src/components/ResultadoConsulta.tsx).
3. Si suma un valor agregable al resumen, agregar la `Metrica` correspondiente.

Si el frontend ya está deployado en Vercel, el push al repo dispara el rebuild automático.

### 6. Aplicar el skill `scraping-respetuoso`

Si la fuente es web, revisar el skill [scraping-respetuoso](../scraping-respetuoso/SKILL.md): timeouts, headless, reintentos, screenshots de debug, paso de descubrimiento previo obligatorio, manejo de IP datacenter.

### 7. Documentar particularidades

Si la fuente tiene cobertura limitada (ej: AMT solo Quito, Fiscalía acepta varios identificadores, alguna fuente solo funciona desde IP residencial), anotarlo en un comentario corto al inicio del archivo del servicio.

## Anti-patrones

- ❌ Devolver `None` o lanzar excepción desde el servicio.
- ❌ Mezclar parsing con I/O en la misma función.
- ❌ Hardcodear datos del navegador o credenciales en el código.
- ❌ Importar el parser desde otro servicio — cada fuente tiene su propio parser.
- ❌ Escribir el scraper sin haber hecho el paso de descubrimiento primero.
