# Catálogo de productos de consulta (microdesbloqueos)

**Estado:** IMPLEMENTADO. Reajuste comercial **Fase 2.5 (2026-05-31)**: el catálogo solo cobra
por datos que generan **costo de proveedor externo, dificultad real o valor comercial
relevante**. Los **datos públicos simples** (marca, modelo, año, color, clase, servicio, estado
de matrícula) son **gratis**.
**Equivalencia referencial:** **1 token = USD 0.04** (ver [reglas_monetizacion_tokens.md](reglas_monetizacion_tokens.md)).
**Fuente de verdad técnica:** `src/modules/consulta/services/catalogo_productos.py` (seed) +
tabla `productos_consulta` (BD). Migraciones `0015` (seed inicial) y `0016` (reajuste 2.5).

> Los `codigo` van en **español/snake_case** y son estables (clave en `desbloqueos_consulta`).
> El precio puede ajustarse en BD/seed. La migración `0016` renombró los códigos v1 a estos.

## Tabla de productos (catálogo vigente)

| Código | Nombre (UI, es-EC) | Tokens | USD ref. | Qué revela | Fuente del dato | Sensibilidad | Disponible hoy |
|---|---|---:|---:|---|---|---|---|
| `consulta_publica_base` | Consulta pública base | 0 | 0.00 | Características públicas (marca, modelo, año, color, clase, servicio), estado de matrícula, enlaces oficiales, estado de fuentes y veredicto sí/no | ANT (cacheado) | Baja | ✅ Sí (gratis) |
| `identificadores_tecnicos` | Ver identificadores técnicos | 3 | 0.12 | VIN, motor y chasis **ofuscados a origen** (primeros 3 + país del WMI) + datos técnicos disponibles | Proveedor autorizado / caché | Media | ⚠️ Si la fuente los aporta |
| `titular_validado` | Validar titular registrado | 5 | 0.20 | **No expone nombre/cédula crudo.** Validación ("coincide con la cédula `09######47`") o nombre ofuscado | Proveedor autorizado | Alta (PII) | ❌ Sin proveedor → enlace/no disponible |
| `alertas_legales` | Ver alertas legales | 8 | 0.32 | Novedades legales asociadas (FGE) | Fuente estructurada legalmente segura | Alta | ❌ Sin fuente segura → enlace oficial |
| `multas_con_montos` | Ver multas con valores | 10 | 0.40 | Detalle con **montos** por fuente (ANT/AMT): pendientes, total a pagar, categorías | ANT/AMT (cacheado) | Media (transaccional) | ✅ Si hay multas |
| `valores_matricula_sri` | Ver valores de matrícula (SRI) | 12 | 0.48 | Valores tributarios del SRI (matrícula/impuestos) | SRI (proveedor) | Media | ❌ reCAPTCHA → enlace oficial |
| `reporte_compra_segura` | Generar reporte compra segura | 40 | 1.60 | **Bundle**: identificadores técnicos + multas con valores + alertas legales + valores SRI + titular validado (según disponibilidad) | Combinación de las anteriores | Alta | ⚠️ Si hay algún dato que agrupar |
| `verificacion_marketplace` | Verificación de la plataforma | 100 | 4.00 | Sello "Verificado por la plataforma" para una publicación premium del marketplace | Proveedores + revisión admin | Alta | Flujo marketplace (no consulta) |

### Por qué se ajustó (Fase 2.5)
- **No se cobra por datos públicos simples.** Antes `vehiculo_basico` (3t) y `vehiculo_tecnico`
  (2t) cobraban clase/servicio/fechas/cilindraje, que ya vienen de la fuente pública ANT.
  Esos productos se **desactivaron** (migración `0016`, `activo=false`) y su contenido pasó a
  `consulta_publica_base` (0 tokens, siempre gratis).
- **Solo se cobra por costo real, dificultad real o valor comercial:** identificadores
  (requieren proveedor/empaquetado), multas con montos (valor comercial de compra-venta),
  titular validado (PII + proveedor), valores SRI (proveedor), alertas legales (fuente segura).

### Renombres aplicados (migración 0016)
| Código v1 (0015) | Código vigente | Cambio |
|---|---|---|
| `vehiculo_basico` (3t) | — (desactivado) | Datos públicos → gratis en `consulta_publica_base` |
| `vehiculo_tecnico` (2t) | — (desactivado) | Plegado en `identificadores_tecnicos` |
| `vehiculo_identificadores` (3t) | `identificadores_tecnicos` (3t) | Renombrado |
| `vehiculo_titular_validado` (5t) | `titular_validado` (5t) | Renombrado |
| `vehiculo_multas` (8t) | `multas_con_montos` (10t) | Renombrado + precio |
| `reporte_compra_segura` (30t) | `reporte_compra_segura` (40t) | Precio |
| `verificacion_marketplace` (80t) | `verificacion_marketplace` (100t) | Precio |
| — | `valores_matricula_sri` (12t) | Nuevo |
| — | `alertas_legales` (8t) | Nuevo |

### Notas por producto
- **`reporte_compra_segura` (40)** reúne en un solo informe todos los microproductos de pago.
  Define qué incluye vía `BUNDLE_INCLUYE` en el seed; al desbloquearlo se marcan todos sus
  códigos (los que aún no tienen proveedor quedan pre-desbloqueados, sin dato hoy).
- **`verificacion_marketplace` (100)** — producto del **marketplace**, no de la consulta por
  placa. Publicar premium cuesta **3 tokens** (solo destaca, nace `no_verificado`); el dueño
  luego **solicita** el sello con `POST /marketplace/publicaciones/{id}/solicitar-verificacion`
  (**100 tokens** → `pendiente` → cola admin). Constante `TOKENS_VERIFICACION_MARKETPLACE`.
  Ver [checklist_verificacion_marketplace.md](checklist_verificacion_marketplace.md).
- **`titular_validado`**: por política, **nunca** se expone el dato crudo del titular; preferir
  validación/ofuscación (ver [politica_datos_sensibles.md](politica_datos_sensibles.md)).

## Gratis (sin tokens) — `consulta_publica_base`
- Marca, modelo, año, color, **clase, servicio** (toda la ficha pública).
- Estado de matrícula: vigente / vencida (cuando viene de fuente pública).
- Enlaces oficiales (portal SRI, etc.) y estado de las fuentes.
- Veredicto binario: ¿tiene pendientes? **sí/no** (sin montos ni detalle).

## Copy público (es-EC, tuteo)
Evitar frases como "paga para ver el dueño". Usar:
- **"Validar titular registrado"** (no "ver el dueño").
- **"Ver identificadores técnicos"**.
- **"Ver multas con valores"**.
- **"Ver valores de matrícula (SRI)"**.
- **"Ver alertas legales"**.
- **"Generar reporte compra segura"**.

## Mapeo sección del perfil → producto (gating)
| Sección de `VehiculoConsolidadoResponse` | Producto que la desbloquea |
|---|---|
| `datos_basicos` (completo) + `estado_fuentes` + veredicto | `consulta_publica_base` (gratis) |
| `identificacion` (VIN/motor/chasis ofuscados) | `identificadores_tecnicos` |
| titular (ofuscado/validado) | `titular_validado` |
| `multas_detalle` (con montos) | `multas_con_montos` |
| `valores_tributarios` (montos SRI) | `valores_matricula_sri` |
| `novedades_legales` (detalle) | `alertas_legales` |
| todo lo anterior en un informe | `reporte_compra_segura` |

> Datos sin proveedor confiable (`titular_validado`, `valores_matricula_sri`, `alertas_legales`)
> hoy salen como **enlace oficial / no disponible** (`disponible=false`), no como cobro. El
> mecanismo de gateo/cobro queda listo para cuando exista el proveedor autorizado.
