---
name: respuesta-api-estandar
description: Aplicar el contrato de respuestas estándar del proyecto a servicios de fuentes externas y endpoints públicos. Usar al crear o modificar cualquier función `consultar_*` o cualquier endpoint en main.py.
---

# Respuesta API estándar

Este proyecto agrega información de múltiples fuentes públicas. Para que el cliente (web, app móvil, OCR) consuma todo de forma uniforme, el contrato de respuesta es **invariante**.

## Cuándo usar este skill

- Crear o modificar una función `consultar_<fuente>` en `services/`.
- Crear o modificar un endpoint en [main.py](../../../main.py).
- Cambiar el esquema de error.

## Contrato — Servicio externo

Toda función `consultar_<fuente>(arg: str) -> dict` debe devolver:

```json
{
  "fuente": "ANT",
  "placa": "ABC1234",
  "estado": "consulta_realizada",
  "datos": { ... },
  "error": "string opcional"
}
```

Para Fiscalía, `placa` se llama `termino` porque acepta varios identificadores (placa, cédula, RUC, nombres).

### Valores válidos de `estado`

| Estado | Cuándo |
|---|---|
| `consulta_realizada` | La fuente respondió y se parseó correctamente. |
| `sin_resultados` | La fuente respondió pero no hay datos para esa placa. |
| `pendiente_integracion` | La fuente está stub (no se usa actualmente; todas las fuentes están integradas). |
| `error` | Cualquier fallo (timeout, parser, conexión). Incluir `"error": "..."` con `repr(e)`. |
| `bloqueado_captcha` | reCAPTCHA invisible bloqueó silenciosamente. Caso SRI. |

### Reglas
- `datos` es `null` cuando `estado != "consulta_realizada"`.
- `error` aparece **solo** cuando `estado == "error"` o `bloqueado_captcha`.
- `fuente` es un código corto y estable (`ANT`, `SRI`, `AMT`, `FGE`, etc.). No cambiarlo después.
- `placa` es la placa **ya normalizada** (mayúsculas, sin guiones).

## Contrato — Endpoint público

`GET /consultar/{placa}` devuelve:

```json
{
  "placa": "ABC1234",
  "ant":  { ...respuesta del servicio... },
  "sri":  { ... },
  "amt":  { ... },
  "fge":  { ... },
  "resumen": {
    "fuentes_consultadas": 4,
    "ant_consultado": true,
    "sri_consultado": false,
    "amt_consultado": true,
    "fge_consultado": true,
    "tiene_citaciones_pendientes_ant": false,
    "total_citaciones_ant": 0,
    ...
    "estado_general": "sin_pendientes"
  }
}
```

### Reglas del `resumen`
- Es un objeto **derivado** — no llamar a las fuentes desde aquí; sólo combinar lo ya consultado.
- `estado_general` es un agregado simple: `"con_pendientes"` si alguna fuente reporta algo a resolver; si no, `"sin_pendientes"`.
- Cuando se agregue una fuente nueva con indicadores agregables, sumar al `resumen` con campos análogos.

## Códigos HTTP

| Código | Cuándo |
|---|---|
| **200** | Respuesta normal, **incluso si todas las fuentes fallaron**. El cliente decide qué hacer con cada `estado` interno. |
| **400** | Validación de input: placa con formato inválido. Único caso de 4xx para validación. |
| **401** | Auth: token faltante o inválido. |
| **409** | Conflicto: ej. email ya existe en registro. |
| **5xx** | Fallo del propio servidor (BD caída, bug). **NUNCA** por una fuente externa caída. |

## Anti-patrones

- ❌ Lanzar `HTTPException(503)` porque ANT está caído. Las fuentes externas se reportan en su propio `estado`.
- ❌ Cambiar el nombre de un campo del resumen sin coordinarlo con el frontend.
- ❌ Devolver `datos: {}` en lugar de `datos: null` cuando no hay resultados.
- ❌ Inyectar campos extra en la respuesta del servicio sin documentarlos en este skill.