# Política de datos sensibles

**Estado:** PLAN / guía vigente. Aplica a microdesbloqueos, marketplace y compartidos.
**Relacionados:** [modelo_tokens_microdesbloqueos.md](modelo_tokens_microdesbloqueos.md) · [AGENTS.md §7 y §9](../../AGENTS.md) · `src/core/ofuscacion.py`.

## 1. Principio
Minimización: **no exponer un dato sensible si no es necesario**, y cuando se exponga, hacerlo **ofuscado** o como **validación** (sí/no) en vez del valor crudo. El pago de tokens **no** habilita exponer PII de terceros de forma innecesaria: paga el acceso a lo mínimo útil.

## 2. El titular / dueño es dato sensible (alta sensibilidad)
- El **nombre y la cédula del titular** son PII de una persona. **No** se publican crudos en vistas públicas ni en el marketplace (regla §10.6: el marketplace nunca expone el nombre real del dueño).
- Producto `vehiculo_titular_validado` (ver catálogo): preferir, en orden:
  1. **Validación** ("el titular **coincide** con la cédula `09######47`" → sí/no), sin revelar el nombre. Ideal para compra-venta: el comprador confirma que quien vende es el titular, sin recibir el dato.
  2. **Ofuscación** (nombre parcial: "J*** P*** G***", cédula parcial). Solo si el proveedor autorizado lo permite.
  3. Valor completo **solo** al propio titular autenticado sobre su vehículo (garage), nunca a un tercero.
- La fuente del titular debe ser un **proveedor autorizado** o convenio, no scraping de un padrón.

## 3. Identificadores (VIN, motor, chasis) — sensibilidad media
- Por defecto **ofuscados a nivel `origen`** (primeros 3 caracteres + país del WMI), vía `src/core/ofuscacion.py`.
- El valor **completo** solo se muestra al **dueño autenticado** del vehículo en su garage. Para terceros (consulta/compartido), nivel `origen` u `oculto`.
- El producto `vehiculo_identificadores` revela el nivel ofuscado, no el crudo, salvo dueño.

## 4. Datos transaccionales (multas, valores) — sensibilidad media
- Las multas/citaciones son del vehículo (placa), no PII de un tercero identificado. Se pueden mostrar con montos tras desbloqueo.
- Los **valores del SRI** (matrícula/impuestos) hoy no se obtienen automáticamente (reCAPTCHA): se ofrece **enlace oficial asistido**, no bypass.

## 5. Retención y caché
- No almacenar PII de terceros más de lo necesario. La caché (`consultas`) guarda respuestas de fuente con TTL; los datos de **titular** validado **no** deben persistirse crudos: guardar el resultado de la **validación** (booleano/ofuscado), no el nombre/cédula.
- La tabla `desbloqueos` guarda **qué** producto compró el usuario (código + placa + tokens), **no** el contenido del dato sensible.

## 6. Acceso por rol
| Rol | Titular | VIN/motor/chasis | Multas |
|---|---|---|---|
| Anónimo (teaser) | No | No | No (solo veredicto sí/no) |
| Usuario que paga (tercero) | Validación/ofuscado | Ofuscado (origen) | Detalle con montos |
| Dueño autenticado (garage) | Completo (es su dato) | Completo | Detalle |
| Admin | Según función (moderación/verificación) | Ofuscado salvo necesidad | Detalle |

## 7. Límite ético/legal (recordatorio)
- No evasión de captcha ni bypass anti-bot.
- Datos de terceros solo vía fuente/proveedor autorizado y dentro de su licencia de uso.
- Cumplir la Ley Orgánica de Protección de Datos Personales (Ecuador): finalidad, minimización, y derecho del titular. Ante duda sobre exponer un dato de persona → **ofuscar o validar, no exponer**.
