# Catálogo de productos de consulta (microdesbloqueos)

**Estado:** PLAN (precios iniciales propuestos; no implementado).
**Equivalencia referencial:** **1 token = USD 0.05** (ver [reglas_monetizacion_tokens.md](reglas_monetizacion_tokens.md)).
**Fuente de verdad técnica (futura):** `src/modules/consulta/services/catalogo_productos.py`.

> Los `codigo` van en **español/snake_case** y son estables (no se renombran: se usan como clave en la tabla `desbloqueos`). El precio puede ajustarse en código sin migración.

## Tabla de productos

| Código | Nombre (UI, es-EC) | Tokens | USD ref. | Qué revela | Fuente del dato | Sensibilidad |
|---|---|---:|---:|---|---|---|
| `vehiculo_basico` | Ficha básica | 3 | 0.15 | Ficha completa de características: marca, modelo, año, color, clase, servicio, fechas de matrícula/caducidad | ANT (cacheado) | Baja |
| `vehiculo_tecnico` | Datos técnicos | 2 | 0.10 | Cilindraje, tipo de motor, transmisión, combustible, tonelaje (según disponibilidad) | ANT/SRI (cacheado) | Baja |
| `vehiculo_identificadores` | VIN, motor y chasis | 3 | 0.15 | Identificadores **ofuscados a origen** (primeros 3 + país del WMI). El valor completo solo al dueño autenticado | Proveedor autorizado / caché | **Media** |
| `vehiculo_titular_validado` | Titular (validado) | 5 | 0.25 | **No expone el nombre/cédula crudo.** Devuelve validación ("coincide con la cédula X***") o nombre parcial ofuscado | Proveedor autorizado | **Alta (PII)** |
| `vehiculo_multas` | Multas e infracciones | 8 | 0.40 | Detalle con **montos** por fuente (ANT/AMT): pendientes, total a pagar, categorías | ANT/AMT (cacheado) + enlace oficial SRI asistido | Media (transaccional) |
| `reporte_compra_segura` | Reporte de compra segura | 30 | 1.50 | **Bundle** con descuento: básico + técnico + identificadores + multas + condición legal (robo, prendas, gravámenes, traspasos, RTV) | Combinación de las anteriores + EPMTSD (enlace asistido/proveedor) | Media/Alta |
| `verificacion_marketplace` | Verificación de la plataforma | 80 | 4.00 | Sello "Verificado por la plataforma" para una publicación premium: valida titular + condición legal + revisión humana | Proveedores + revisión admin | Alta |

### Notas por producto
- **`reporte_compra_segura` (30)** cuesta menos que comprar por separado (3+2+3+8 = 16 tokens los datos del vehículo, + condición legal): el descuento está en agrupar la **condición legal** (lo más caro de obtener) en el combo. Define explícitamente qué incluye vía `incluye=[...]` en el catálogo.
- **`verificacion_marketplace` (80)** — RESUELTO (2026-05-31): se separó "destacar premium" de "verificar". Publicar premium cuesta **3 tokens** (solo destaca, nace `no_verificado`); el dueño luego **solicita** el sello con `POST /marketplace/publicaciones/{id}/solicitar-verificacion` (**80 tokens** → `pendiente` → cola admin `/admin/verificaciones`). Es un producto del **marketplace**, no de la consulta por placa. Ver [checklist_verificacion_marketplace.md](checklist_verificacion_marketplace.md).
- **`vehiculo_titular_validado`**: por política, **nunca** se expone el dato crudo del titular sin necesidad; preferir validación/ofuscación (ver [politica_datos_sensibles.md](politica_datos_sensibles.md)).

## Gratis (teaser, sin tokens)
- Marca, modelo, año, color.
- Estado de matrícula: vigente / vencida.
- Veredicto binario: ¿tiene pendientes? **sí/no** (sin montos ni detalle).

## Mapeo sección del perfil → producto (gating)
| Sección de `VehiculoConsolidadoResponse` | Producto que la desbloquea |
|---|---|
| `datos_basicos` (completo) | `vehiculo_basico` |
| datos técnicos (nuevo bloque) | `vehiculo_tecnico` |
| `identificacion` (VIN/motor/chasis) | `vehiculo_identificadores` |
| titular (nuevo, ofuscado/validado) | `vehiculo_titular_validado` |
| `multas_detalle` (con montos) | `vehiculo_multas` |
| condición legal (nuevo) + todo lo anterior | `reporte_compra_segura` |

> Total catálogo individual: 3+2+3+5+8 = **21 tokens** ($1.05) si se compra todo suelto sin condición legal; el `reporte_compra_segura` (30, $1.50) añade la condición legal con descuento implícito.
