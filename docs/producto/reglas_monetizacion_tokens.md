# Reglas de monetización con tokens

**Estado:** PLAN. Define cómo se cobran y contabilizan los tokens en los microdesbloqueos.
**Relacionados:** [modelo_tokens_microdesbloqueos.md](modelo_tokens_microdesbloqueos.md) · [catalogo_productos_consulta.md](catalogo_productos_consulta.md) · [AGENTS.md §10.3](../../AGENTS.md).

## 1. Valor del token
- **1 token = USD 0.05** (referencial; el precio real de compra de tokens se define al integrar el gateway de pago, PlaceToPay/MercadoPago).
- **Saldo inicial de cortesía: 5 tokens** ($0.25) por usuario nuevo (regla §10.3 ya vigente). Alcanza para 1–2 microproductos como prueba.
- El saldo **nunca es negativo** (CHECK en BD + validación en `debitar_tokens`).

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
- `reporte_compra_segura` (30 tokens) agrupa varios productos con descuento (ver catálogo). Al desbloquearlo se marcan **todos** los productos `incluye=[...]` como desbloqueados para esa placa.
- **Decisión inicial:** comprar el bundle **no descuenta** lo ya pagado por productos sueltos (el bundle ya es barato). Revisable.

## 6. Caché y frescura
- El cobro es por **acceso al dato**, esté fresco o cacheado. Si el dato está en caché vigente (TTL §8 de AGENTS), se sirve sin re-consultar la fuente.
- Datos transaccionales (multas, valores) usan TTL corto (12h); características del vehículo, TTL largo. Un desbloqueo no "congela" el dato: futuras vistas muestran el dato vigente de caché.

## 7. Reembolsos
- No hay reembolso automático de tokens ya cobrados por un dato entregado.
- Si tras cobrar el dato resultó erróneo por la fuente, se evalúa caso a caso (soporte). Documentar incidencias.

## 8. Trazabilidad / métricas (futuro)
- `motivo` de cada transacción permite medir qué productos se desbloquean más.
- La tabla `desbloqueos` permite analítica de conversión (teaser → compra) sin exponer PII.

## 9. Qué NO se hace (límite ético/legal)
- No se cobran tokens por **evadir** captchas/anti-bot. Donde una fuente exige captcha (SRI, FGE), se ofrece **enlace oficial asistido** o **proveedor autorizado**, no bypass.
- No se revende dato de terceros fuera de lo que permita la fuente/proveedor y la política de datos sensibles.
