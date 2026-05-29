---
name: respuesta-api-estandar
description: Aplicar el contrato de respuestas estándar del proyecto a servicios de fuentes externas y endpoints públicos. Usar al crear o modificar cualquier función `consultar_*` o cualquier endpoint en main.py.
---

# Respuesta API estándar

Este proyecto agrega información de múltiples fuentes públicas. Para que el cliente (web, app móvil, OCR) consuma todo de forma uniforme, el contrato de respuesta es **invariante**.

## Cuándo usar este skill

- Crear o modificar una función `consultar_<fuente>` en `services/`.
- Crear o modificar un endpoint en [main.py](../../../main.py) o en un router de [routers/](../../../routers/).
- Cambiar el esquema de error.
- Cambiar lo que devuelven los endpoints autenticados (`/auth/*`, `/vehiculos/*`, `/vehiculos/{id}/duenos`, `/vehiculos/{id}/kilometraje`).

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
| `en_proceso` | La fuente (AMT/FGE) se encoló para el worker híbrido; aún no hay resultado. `datos: null`, sin `error`. No se cachea. El cliente reintenta hasta ver `consulta_realizada`. Ver [arquitectura_hibrida.md](../../../docs/arquitectura_hibrida.md). |
| `consulta_externa` | La fuente no se scrapea; se expone el servicio oficial. Devuelve `url_consulta` (enlace al portal) y `datos: null`. Caso SRI (reCAPTCHA Enterprise v3 que rechaza solvers; no se puede iframe por `X-Frame-Options`). El frontend muestra un botón al portal. No se cachea. |

### Reglas
- `datos` es `null` cuando `estado != "consulta_realizada"`.
- `error` aparece **solo** cuando `estado == "error"` o `bloqueado_captcha`.
- `url_consulta` aparece **solo** cuando `estado == "consulta_externa"`.
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
| **201** | Recursos creados (`POST /auth/registro`, `POST /vehiculos`, etc.). |
| **204** | Recursos eliminados (`DELETE`). Sin body. |
| **400** | Validación de input: placa/cédula/VIN con formato inválido. Caso de 4xx para validación de path/query/body. |
| **401** | Auth: token faltante, inválido o expirado. Endpoints públicos NUNCA devuelven 401. |
| **404** | Recurso no encontrado o no pertenece al usuario autenticado (importante: NO distinguir entre "no existe" y "es de otro usuario" — siempre 404). |
| **409** | Conflicto: email duplicado en registro, placa duplicada en el mismo usuario. |
| **422** | Validación de negocio: lectura de kilometraje menor a la máxima, rango de dueño inválido. |
| **5xx** | Fallo del propio servidor (BD caída, bug). **NUNCA** por una fuente externa caída. |

## CORS y Frontend

El backend acepta requests cross-origin solo desde orígenes en `CORS_ORIGINS` (env var coma-separada). Default dev: `http://localhost:3000`. En producción se agrega la URL de Vercel.

Reglas:
- **NO usar `allow_origins=["*"]`** en producción — habilita ataques CSRF si combinás con `allow_credentials=True`.
- Cuando cambie la URL del frontend (preview de Vercel vs prod), actualizar `CORS_ORIGINS` en Render. El frontend no puede consumir la API si su origen no está en la lista.
- El middleware vive en [main.py](../../../main.py).

## Endpoints autenticados — contrato resumido

Endpoints implementados en Fase 2. Todos requieren `Authorization: Bearer <jwt>`.

| Recurso | Verbo + Path | Body | Respuesta |
|---|---|---|---|
| Usuario | `POST /auth/registro` | `UsuarioCrear` | 201 `UsuarioSalida`; 409 si email duplicado |
| Sesión | `POST /auth/login` | form-data `username` (email) + `password` | 200 `Token`; 401 si credenciales mal |
| Perfil | `GET /auth/me` | — | 200 `UsuarioSalida` |
| Vehículo | `POST /vehiculos` | `VehiculoCrear` | 201 `VehiculoSalidaCompleta`; 409 si placa duplicada por usuario |
| Vehículo | `GET /vehiculos` | — | 200 `VehiculoSalidaCompleta[]` (filtrados por `usuario_id`, sin eliminados) |
| Vehículo | `GET /vehiculos/{id}` | — | 200 `VehiculoSalidaCompleta`; 404 si no es del usuario |
| Vehículo | `PATCH /vehiculos/{id}` | `VehiculoActualizar` (parcial) | 200 `VehiculoSalidaCompleta` |
| Vehículo | `DELETE /vehiculos/{id}` | — | 204 (soft delete con `eliminado_en`) |
| Dueño | `POST /vehiculos/{id}/duenos` | `DuenoHistoricoCrear` | 201; si `hasta=None` cierra al activo previo |
| Dueño | `GET /vehiculos/{id}/duenos` | — | 200 lista ordenada por `desde` desc |
| Dueño | `PATCH /vehiculos/{id}/duenos/{id_dueno}` | `DuenoHistoricoActualizar` | 200 |
| Dueño | `DELETE /vehiculos/{id}/duenos/{id_dueno}` | — | 204 (hard delete) |
| Kilometraje | `POST /vehiculos/{id}/kilometraje` | `KilometrajeLecturaCrear` | 201; 422 si menor a máxima |
| Kilometraje | `GET /vehiculos/{id}/kilometraje` | — | 200 lista ordenada por `fecha_lectura` desc |
| Kilometraje | `DELETE /vehiculos/{id}/kilometraje/{id_lectura}` | — | 204 |

Autorización transversal: usar `Depends(vehiculo_propio)` (en [src/modules/auth/dependencies.py](../../../src/modules/auth/dependencies.py)) para todos los endpoints anidados bajo `/vehiculos/{id}/...`. La dependency ya resuelve `Vehiculo` filtrado por `usuario_id` y excluye soft-deleted.

## Anti-patrones

- ❌ Lanzar `HTTPException(503)` porque ANT está caído. Las fuentes externas se reportan en su propio `estado`.
- ❌ Cambiar el nombre de un campo del resumen sin coordinarlo con el frontend ([repo consulta-placas-web](https://github.com/VMarcosGC/consulta-placas-web), `src/types/api.ts` espeja los schemas).
- ❌ Devolver `datos: {}` en lugar de `datos: null` cuando no hay resultados.
- ❌ Inyectar campos extra en la respuesta del servicio sin documentarlos en este skill.
- ❌ Devolver `Vehiculo` o `DuenoHistorico` sin pasar por su schema Pydantic — perdés el control de visibilidad (VIN sin ofuscar, etc.).
- ❌ Distinguir 404 (no existe) vs 403 (no es tuyo) — siempre 404 para no filtrar IDs ajenos.