---
name: modelo-dominio-vehiculo
description: Agregar o modificar entidades del dominio (vehículo, dueño, mantenimiento, kilometraje, enlaces compartidos) con SQLAlchemy + Alembic. Usar al agregar/cambiar campos o entidades del modelo de datos.
---

# Modelo de dominio del vehículo

Este skill cubre la persistencia del dominio del proyecto. La Fase 1 creó `consultas` (caché). La Fase 2 introdujo `usuarios`, `vehiculos`, `duenos_historico`, `kilometraje_lecturas`. Fases 3-4 agregarán `mantenimientos` y `enlaces_compartidos`.

## Cuándo usar este skill

- Crear una entidad nueva.
- Agregar/modificar/eliminar un campo de una entidad existente.
- Cambiar relaciones entre entidades.

## Entidades

| Entidad | Fase | Migración | Propósito | Estado |
|---|---|---|---|---|
| `consultas` | 1 | `0001` | Caché de respuestas crudas de fuentes públicas (`placa + fuente + JSONB respuesta`). | ✅ existe |
| `usuarios` | 2 | `0002` | Cuentas autenticadas (`email` único, `password_hash` bcrypt, `nombre`). | ✅ existe |
| `vehiculos` | 2 | `0002` + `0003` | Vehículos del usuario con identificadores sensibles. | ✅ existe |
| `duenos_historico` | 2 | `0002` | Cambios de propietario en el tiempo (con `validar_cedula`). | ✅ existe |
| `kilometraje_lecturas` | 2 | `0002` | Lecturas inmutables con validación monotónica. | ✅ existe |
| `mantenimientos` | 3 | — | Tipo, fecha, km, taller, costo, adjuntos. | ⏳ pendiente |
| `enlaces_compartidos` | 4 | — | Tokens de compra-venta: vehículo, expiración, scope. | ⏳ pendiente |

### Campos de `vehiculos` (estado actual, migración 0003)

| Campo | Tipo | Notas |
|---|---|---|
| `id` | BigInteger PK | autoincrement |
| `usuario_id` | BigInteger FK → usuarios | ON DELETE CASCADE |
| `placa` | String(10) | índice. Único por usuario (`uq_vehiculos_usuario_placa`). |
| `vin` | String(17) nullable | ISO 3779. Validar con `validar_vin`. Ofuscable. |
| `numero_motor` | String(50) nullable | Sensible. Ofuscable con `ofuscar_identificador`. |
| `numero_chasis` | String(50) nullable | Sensible. Ofuscable. |
| `marca`, `modelo`, `color` | String nullable | Datos públicos del vehículo. |
| `anio` | Integer nullable | |
| `creado_en`, `actualizado_en` | TimestampTZ | |
| `eliminado_en` | TimestampTZ nullable | Soft delete. NULL = activo. |

### Schemas Pydantic asociados (en `schemas/vehiculo.py`)

- `VehiculoCrear` — entrada para POST. Valida placa y VIN.
- `VehiculoActualizar` — entrada para PATCH. Todos los campos opcionales.
- `VehiculoSalidaCompleta` — vista del dueño autenticado, sin ofuscación.
- `VehiculoSalidaCompartida` — vista para portador de token (Fase 4); VIN/motor/chasis envueltos en `IdentificadorOfuscado` con valor parcial + país del WMI.
- `VehiculoSalidaPublica` — vista mínima sin campos sensibles.

## Estructura del proyecto

```
consulta_placas_ec/
├── models/             ← SQLAlchemy ORM (un archivo por entidad)
├── schemas/            ← Pydantic (entrada/salida de API). Múltiples vistas por entidad cuando aplica.
├── routers/            ← APIRouter por grupo: auth, vehiculos, duenos, kilometraje
├── auth/               ← security.py (bcrypt + JWT), dependencies.py (usuario_actual, vehiculo_propio)
├── utils/              ← validators.py (placa, cédula, VIN), ofuscacion.py (VIN decoder + máscaras)
├── alembic/            ← Migraciones (manuales, no autogenerate-only)
│   └── versions/
├── alembic.ini
└── database.py         ← engine, SessionLocal, Base, env vars
```

## Pasos para agregar/modificar una entidad

1. **Editar el modelo** en `models/<entidad>.py`. Nombres de tabla y columnas **en español, snake_case**: `kilometraje_lecturas.fecha_lectura`, `enlaces_compartidos.fecha_expiracion`.
2. **Registrar en `models/__init__.py`** para que Alembic la detecte vía `import models`.
3. **Generar migración**:
   ```powershell
   alembic revision --autogenerate -m "agregar_campo_<nombre>_a_<entidad>"
   ```
4. **Revisar la migración generada** antes de aplicar. Autogenerate de Alembic no detecta bien:
   - Renombres (los ve como drop + add → perdés datos).
   - Cambios de tipo con conversión implícita.
   - Índices parciales o constraints complejos.
5. **Aplicar la migración**:
   ```powershell
   alembic upgrade head
   ```
6. **Actualizar schema Pydantic** en `schemas/<entidad>.py`. Separar `<Entidad>Crear`, `<Entidad>Actualizar`, `<Entidad>Salida`.
7. **Actualizar endpoints** que toquen la entidad.
8. **Si el campo es sensible** (dueño actual, kilometraje, mantenimiento con costo): revisar que el token de compra-venta tenga el scope adecuado.

## Reglas de modelado

- **Idioma**: nombres en español (tablas, columnas, relaciones).
- **PKs**: `id` BigInteger autoincremental.
- **Timestamps**: todas las tablas tienen `creado_en` y `actualizado_en` (excepto las inmutables como `kilometraje_lecturas` que solo tiene `creado_en`).
- **Soft delete**: usar `eliminado_en TIMESTAMP NULL` cuando se necesite (no `DELETE` físico de datos de usuario). Ya en `vehiculos`.
- **Placa**: indexada y única por usuario en `vehiculos` (`uq_vehiculos_usuario_placa`). No globalmente única — la misma placa puede tener varios dueños en la historia.
- **FKs**: usar `ondelete="CASCADE"` para hijos del usuario (vehículos, mantenimientos, etc.). Cuando el usuario se borra, todo su árbol se va.
- **Datos crudos de fuentes** (en `consultas`): columna JSONB. Permite indexar paths frecuentes con `CREATE INDEX ... ON consultas USING GIN ((respuesta->'ant'))`.

## Privacidad y compartición

Al diseñar cualquier endpoint que devuelva entidades del dominio:

- **Default**: sólo el dueño autenticado ve sus datos. Usar `Depends(usuario_actual)` para el header `Authorization`, y `Depends(vehiculo_propio)` para resolver un vehículo del usuario por path param (`/vehiculos/{vehiculo_id}/...`). Ambas están en [auth/dependencies.py](../../../auth/dependencies.py).
- **Schemas con visibilidad** (ver `schemas/vehiculo.py`):
  - Dueño → `VehiculoSalidaCompleta` (todo visible).
  - Token compra-venta → `VehiculoSalidaCompartida` (VIN/motor/chasis ofuscados).
  - Listado público → `VehiculoSalidaPublica` (sin campos sensibles).
- **Token de compra-venta** (`enlaces_compartidos` — Fase 4): cada token tiene un campo `scope` (JSON) que enumera qué entidades/campos puede ver el portador. Default mínimo: marca, modelo, año. Opt-in para: kilometraje, mantenimientos, dueños históricos.
- **Caducidad del token**: máximo 7 días. Validar `fecha_expiracion > now()` en cada uso.

Ver [CLAUDE.md sección 9](../../../CLAUDE.md) para el modelo completo de privacidad y [validacion-datos-ec](../validacion-datos-ec/SKILL.md) para las funciones de ofuscación.

## Anti-patrones

- ❌ Aplicar migraciones autogeneradas sin revisarlas.
- ❌ Hacer `DELETE` físico de datos del usuario (usar soft delete con `eliminado_en`).
- ❌ Endpoints que devuelven `Vehiculo` sin filtrar por dueño autenticado o token válido.
- ❌ Token con expiración mayor a 7 días o sin expiración.
- ❌ Renombrar columnas al inglés.
- ❌ Mezclar el modelo SQLAlchemy con el schema Pydantic en el mismo archivo.
- ❌ Olvidar registrar el nuevo modelo en `models/__init__.py` (Alembic no lo verá vía `import models`).
- ❌ Devolver una instancia del modelo SQLAlchemy directamente sin pasar por el schema Pydantic apropiado (perdés control de qué campos se serializan).
- ❌ Distinguir en el response entre "no existe" (404) y "es de otro usuario" (403) — siempre 404 para no filtrar IDs ajenos.
