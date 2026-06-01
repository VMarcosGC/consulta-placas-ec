# Reglas de monetización con tokens

**Estado:** VIGENTE. Define cómo se cobran y contabilizan los tokens en los microdesbloqueos.
Reajuste **Fase 2.5 (2026-05-31)**: solo se cobra por datos con costo/dificultad/valor real.
**Relacionados:** [modelo_tokens_microdesbloqueos.md](modelo_tokens_microdesbloqueos.md) · [catalogo_productos_consulta.md](catalogo_productos_consulta.md) · [politica_datos_sensibles.md](politica_datos_sensibles.md) · [AGENTS.md §10.3](../../AGENTS.md).

## 1. Valor del token
- **1 token = USD 0.04** (referencial; el precio real de compra de tokens se define al integrar el gateway de pago, PlaceToPay/MercadoPago).
- **Saldo inicial de cortesía: 5 tokens** ($0.20) por usuario nuevo (regla §10.3 ya vigente). Alcanza para 1–2 microproductos como prueba.
- El saldo **nunca es negativo** (CHECK en BD + validación en `debitar_tokens`).

### 1.1 Paquetes de recarga sugeridos (referenciales)
| Precio | Tokens | USD/token efectivo |
|---:|---:|---:|
| USD 1.00 | 25 | 0.040 |
| USD 2.50 | 65 | 0.038 |
| USD 5.00 | 135 | 0.037 |
| USD 10.00 | 280 | 0.036 |

> Los paquetes mayores dan un pequeño bono (USD/token decreciente). Cifras referenciales hasta
> integrar el gateway de pago; no se venden tokens todavía.

## 1.2 Qué se cobra y qué no (Fase 2.5)
- **Gratis:** datos públicos simples (marca, modelo, año, color, clase, servicio, estado de
  matrícula cuando viene de fuente pública), enlaces oficiales, estado de fuentes y veredicto
  sí/no. Empaquetados en `consulta_publica_base` (0 tokens).
- **Se cobra** solo lo que genera **costo de proveedor externo, dificultad real o valor
  comercial relevante**: identificadores técnicos, multas con montos, titular validado, valores
  SRI, alertas legales, el reporte de compra segura y la verificación de marketplace.
- Datos sin proveedor confiable (titular, SRI, alertas legales) hoy se ofrecen como **enlace
  oficial / no disponible**, no como cobro (ver [politica_datos_sensibles.md](politica_datos_sensibles.md)).

## 2. Cobro
- Todo cobro pasa por `debitar_tokens(sesion, usuario, monto, motivo)` con `motivo` trazable (ej. `desbloqueo:vehiculo_multas:ABC1234`).
- **Atómico**: el débito y la inserción del `Desbloqueo` se commitean juntos; si algo falla, rollback de ambos.
- **Saldo insuficiente → HTTP 402** (Payment Required), nunca 422 ni 500 (excepción de contrato acordada en §10.2 para flujos de pago).
- Toda alteración de saldo deja registro en `transacciones_tokens` (auditoría inmutable, ya existente).

## 3. No cobrar si no hay valor entregado
- Si la fuente **no entrega** el dato del producto para esa placa (no disponible / fuente caída), **no se cobra** y se responde `409`/`sin_dato`. (Mismo principio que el desbloqueo actual, que no cobra si `hay_dato_sensible` es falso.)
- El token paga el **acceso al dato entregado**, no el intento. No se cobra por adelantado.

## 4. Idempotencia (no cobrar dos veces)
- Un producto ya desbloqueado para `(usuario, placa)` **no se recobra**: la tabla `desbloqueos` (UK `usuario_id+placa+producto`) sirve el dato sin nuevo débito.
- Re-llamar al endpoint de desbloqueo de un producto ya comprado → `200` idempotente.

## 5. Bundles
- `reporte_compra_segura` (40 tokens) reúne todos los microproductos de pago en un solo informe (ver catálogo). Al desbloquearlo se marcan **todos** los códigos de `BUNDLE_INCLUYE` como desbloqueados para esa placa (los que aún no tienen proveedor quedan pre-desbloqueados, sin dato hoy).
- **Decisión inicial:** comprar el bundle **no descuenta** lo ya pagado por productos sueltos. Revisable.

## 6. Caché y frescura — no llamar al proveedor en la consulta gratuita
- **La consulta gratuita NO invoca proveedores externos de pago.** El teaser + `consulta_publica_base` se sirven solo con datos ya obtenidos/cacheados de fuentes públicas. El cobro paga el **acceso/empaquetado del dato**, nunca un intento a ciegas.
- El proveedor externo (cuando exista) se llama **solo cuando el usuario solicita un desbloqueo pagado** de ese producto, y su respuesta se **guarda/cachea**.
- Si otro producto necesita un dato **ya disponible en caché**, **no** se vuelve a llamar al proveedor: se sirve de caché (el cobro del nuevo producto sigue aplicando si revela algo distinto).
- El cobro es por **acceso al dato**, esté fresco o cacheado. Datos transaccionales (multas, valores) usan TTL corto (12h); características del vehículo, TTL largo. Un desbloqueo no "congela" el dato: futuras vistas muestran el dato vigente de caché.

## 7. Reembolsos
- No hay reembolso automático de tokens ya cobrados por un dato entregado.
- Si tras cobrar el dato resultó erróneo por la fuente, se evalúa caso a caso (soporte). Documentar incidencias.

## 8. Trazabilidad / métricas (futuro)
- `motivo` de cada transacción permite medir qué productos se desbloquean más.
- La tabla `desbloqueos` permite analítica de conversión (teaser → compra) sin exponer PII.

## 9. Qué NO se hace (límite ético/legal)
- No se cobran tokens por **evadir** captchas/anti-bot. Donde una fuente exige captcha (SRI, FGE), se ofrece **enlace oficial asistido** o **proveedor autorizado**, no bypass.
- No se revende dato de terceros fuera de lo que permita la fuente/proveedor y la política de datos sensibles.
