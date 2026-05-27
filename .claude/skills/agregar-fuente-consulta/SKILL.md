---
name: agregar-fuente-consulta
description: Agregar una nueva fuente de consulta vehicular (ANT, SRI, AMT, Fiscalía, Registro Civil, etc.) siguiendo el patrón del proyecto. Usar cuando el usuario pida "integrar X", "agregar fuente X", "consultar también Y".
---

# Agregar una nueva fuente de consulta

Este skill aplica al proyecto [consulta_placas_ec](../../../CLAUDE.md). Lee `CLAUDE.md` antes de proceder si aún no lo has hecho.

## Cuándo usar este skill

El usuario pide integrar una fuente nueva: Registro Civil, otra municipalidad, etc.

## Pasos

### 1. Decidir el método de acceso

- **¿La fuente tiene API pública o HTML estático?** → usar `httpx` (más rápido, menos frágil).
- **¿La fuente exige JavaScript, sesión, captcha?** → usar Playwright async, como [services/ant.py](../../../services/ant.py).
- Por defecto, intentar primero `httpx`. Solo escalar a Playwright si es necesario.

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
- Estructura de respuesta exacta como dice `CLAUDE.md` sección 6 y el skill `respuesta-api-estandar`.
- Si la fuente no aplica para la placa (ej: AMT solo Quito), devolver `estado: sin_resultados`.

### 3. Separar parsing de I/O

Como en [services/ant.py](../../../services/ant.py), la función `parsear_respuesta_<fuente>(texto)` debe vivir aparte de la función async. Esto permite probar el parser con fixtures sin tocar la red.

### 4. Registrar la fuente en `main.py`

En [main.py](../../../main.py):

1. Importar: `from services.<fuente> import consultar_<fuente>`.
2. Llamar dentro de `consultar_placa`: `resultado_<fuente> = await consultar_con_cache(sesion, placa_limpia, "<COD>", consultar_<fuente>)`.
3. Agregar al dict de respuesta: `"<fuente>": resultado_<fuente>`.
4. Si aporta indicadores agregables (citaciones, multas, denuncias), actualizar `resumen` con los flags correspondientes y subir `fuentes_consultadas`.

### 5. Aplicar el skill `scraping-respetuoso`

Si la fuente es web, revisar el skill [scraping-respetuoso](../scraping-respetuoso/SKILL.md): timeouts, headless, reintentos, screenshots de debug, paso de descubrimiento previo obligatorio.

### 6. Documentar particularidades

Si la fuente tiene cobertura limitada (ej: AMT solo Quito, Fiscalía acepta varios identificadores), anotarlo en un comentario corto al inicio del archivo del servicio.

## Anti-patrones

- ❌ Devolver `None` o lanzar excepción desde el servicio.
- ❌ Mezclar parsing con I/O en la misma función.
- ❌ Hardcodear datos del navegador o credenciales en el código.
- ❌ Importar el parser desde otro servicio — cada fuente tiene su propio parser.
- ❌ Escribir el scraper sin haber hecho el paso de descubrimiento primero.
