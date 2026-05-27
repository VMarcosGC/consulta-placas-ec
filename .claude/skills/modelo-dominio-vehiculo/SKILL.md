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

| Entidad | Fase | Propósito | Estado |
|---|---|---|---|
| `consultas` | 1 | Caché de respuestas crudas de fuentes públicas. | ✅ existe |
| `usuarios` | 2 | Cuentas autenticadas. | ✅ existe |
| `vehiculos` | 2 | Vehículos registrados por usuarios. | ✅ existe |
| `duenos_historico` | 2 | Cambios de propietario en el tiempo. | ✅ existe |
| `kilometraje_lecturas` | 2 | Lecturas de kilometraje con fecha. | ✅ existe |
| `mantenimientos` | 3 | Tipo, fecha, km, taller, costo, adjuntos. | ⏳ pendiente |
| `enlaces_compartidos` | 4 | Tokens de compra-venta: vehículo, expiración, scope. | ⏳ pendiente |

## Estructura del proyecto

```
consulta_placas_ec/
├── models/             ← SQLAlchemy ORM (un archivo por entidad)
├── schemas/            ← Pydantic (entrada/salida de API)
├── alembic/            ← Migraciones
│   └── versions/
├── alembic.ini
└── database.py         ← engine, SessionLocal, Base
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

- **Default**: sólo el dueño autenticado ve sus datos. Usar `Depends(usuario_actual)` y filtrar por `usuario_id`.
- **Token de compra-venta** (`enlaces_compartidos` — Fase 4): cada token tiene un campo `scope` (JSON) que enumera qué entidades/campos puede ver el portador. Default mínimo: marca, modelo, año. Opt-in para: kilometraje, mantenimientos, dueños históricos.
- **Caducidad**: máximo 7 días. Validar `fecha_expiracion > now()` en cada uso.

Ver [CLAUDE.md sección 8](../../../CLAUDE.md) para el modelo completo de privacidad.

## Anti-patrones

- ❌ Aplicar migraciones autogeneradas sin revisarlas.
- ❌ Hacer `DELETE` físico de datos del usuario (usar soft delete).
- ❌ Endpoints que devuelven `Vehiculo` sin filtrar por dueño autenticado o token válido.
- ❌ Token con expiración mayor a 7 días o sin expiración.
- ❌ Renombrar columnas al inglés.
- ❌ Mezclar el modelo SQLAlchemy con el schema Pydantic en el mismo archivo.
- ❌ Olvidar registrar el nuevo modelo en `models/__init__.py` (Alembic no lo verá).
