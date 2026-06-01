# Checklist — Verificación premium del marketplace

Guía operativa para el **administrador** que otorga (o niega) el sello
**"Verificado por la plataforma"** a una publicación premium. Complementa las reglas
de [AGENTS.md §10.6](../../AGENTS.md).

## Estados (`estado_verificacion`)
| Estado | Significado | Sello visible |
|---|---|---|
| `no_verificado` | Publicación **light** (no aplica a verificación). | No |
| `pendiente` | Premium recién publicada, esperando revisión del admin. | No (muestra "Verificación pendiente") |
| `verificado` | Admin aprobó el sello. Registra `verificado_en`. | **Sí** ("Verificado por la plataforma") |
| `rechazado` | Admin negó el sello. No vuelve a la cola. | No |

> Solo las publicaciones **premium** entran a la cola. Verificar una light devuelve **422**.

## Cómo acceder
- Iniciar sesión con un correo incluido en `ADMIN_EMAILS`.
- En el header aparece el enlace **"Verificar"** → `/admin/verificaciones`.
- (API: `GET /marketplace/publicaciones/pendientes-verificacion`, solo admin → 403 si no lo es.)

## Antes de marcar VERIFICADO — revisar
- [ ] La **placa** tiene formato ecuatoriano válido y es legible.
- [ ] Hay un **vehículo vinculado** del garage (habilita los argumentos premium).
- [ ] El bloque **historial documentado** muestra mantenimientos coherentes (cantidad y último kilometraje razonables).
- [ ] El **precio** es plausible (no $0 ni valores absurdos).
- [ ] El **título/descripción** no contienen datos sensibles de terceros ni spam.
- [ ] No hay señales de suplantación (la placa/datos no contradicen lo declarado).

Si todo cuadra → **Verificar**. Si no → **Rechazar** (se puede volver a evaluar si el dueño corrige y re-sube a premium).

## Efectos de cada decisión
- **Verificar** → `estado_verificacion = verificado`, `verificado_en = <ahora>`, sello visible en el feed (`ListingCard`) y sale de la cola.
- **Rechazar** → `estado_verificacion = rechazado`, `verificado_en = NULL`, sin sello, sale de la cola.

## Notas
- La decisión es **terminal** desde este endpoint (no se puede devolver a `pendiente`).
- El cobro de tokens del plan premium ocurre **al publicar** (§10.3), no en la verificación. Rechazar **no** reembolsa tokens.
- Pendiente (no implementado): notificar al dueño cuando su publicación queda verificada o rechazada.
