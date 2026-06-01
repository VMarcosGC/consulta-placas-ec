# Evaluación de proveedor real de datos vehiculares (POC — Fase 3)

**Estado:** POC implementado · **medición real PENDIENTE de credenciales** (API key + endpoint).
**Fecha:** 2026-06-01.
**Relacionados:** [modelo_tokens_microdesbloqueos.md](modelo_tokens_microdesbloqueos.md) · [reglas_monetizacion_tokens.md](reglas_monetizacion_tokens.md) · [politica_datos_sensibles.md](politica_datos_sensibles.md) · `src/modules/consulta/providers/` · `scripts/evaluar_proveedor.py`.

---

## 1. Objetivo
Integrar **un único** proveedor real para validar, en ambiente controlado, **costo, cobertura,
latencia, campos disponibles y margen** del modelo de microdesbloqueos, y decidir con datos si se
activa en producción. No se integran varios proveedores en paralelo.

## 2. Proveedor objetivo
Preferencia: **1) `consultas_ec`** · 2) `placaapi_ec` · 3) `webservices_ec`. Se implementó la
integración HTTP real en **`consultas_ec`** ([providers/consultas_ec.py](../../src/modules/consulta/providers/consultas_ec.py)).
Se usará el primero que tenga **API key + endpoint** disponibles.

## 3. Qué se implementó (POC, código)
- **Llamada HTTP real** (httpx, async, timeout configurable) en `ConsultasECProvider.consultar`.
  Tolerante a fallos: red caída / HTTP ≠ 200 / no-JSON → `estado=error`, **nunca** lanza excepción.
- **Mapeo defensivo** `_mapear` al contrato `ResultadoVehicular` (acepta nombres es/en y datos
  anidados bajo `data`/`vehiculo`/`resultado`). Campos del contrato:
  `placa, marca, modelo, anio, color, tipo, clase, servicio, chasis, motor, vin, titular, multas,
  valores_pendientes, proveedor, costo_estimado_usd, estado, raw_response`.
- **Sin credenciales** (`CONSULTAS_EC_API_KEY`/`CONSULTAS_EC_BASE_URL` vacías): `capacidades`
  vacío y `estado=sin_credenciales` → no se ofrece ni se cobra nada (no se promete lo que no se
  puede entregar). Verificado.
- **El proveedor se invoca SOLO al desbloquear** un producto pagado, con caché en `consultas`
  (fuente `PROVEEDOR`); nunca en el preview gratis y no se re-llama si hay caché vigente
  ([services/proveedor.py](../../src/modules/consulta/services/proveedor.py)).
- **No se cobra si no hay dato** entregable (regla 409). **Titular nunca crudo**: validación +
  nombre ofuscado (iniciales).
- **Costo registrado** en `costos_proveedor_consulta` (`registrar_costos_proveedor`, upsert por
  producto+proveedor) para análisis de margen.

> El **contrato externo exacto no está confirmado**. El `_mapear` es defensivo; al obtener la doc
> real del proveedor se ajusta solo el mapeo y la forma del request (params/headers).

## 4. Configuración (env)
```
PROVEEDOR_VEHICULAR_ACTIVO=consultas_ec
CONSULTAS_EC_API_KEY=<tu_api_key>
CONSULTAS_EC_BASE_URL=https://<endpoint-del-proveedor>/vehiculo   # recibe ?placa=ABC1234
CONSULTAS_EC_COSTO_USD=0.08    # costo estimado por consulta (margen)
# CONSULTAS_EC_TIMEOUT=15
```
Con `PROVEEDOR_VEHICULAR_ACTIVO=mock` (default) el sistema usa el proveedor simulado.

## 5. Metodología de medición
Harness: [scripts/evaluar_proveedor.py](../../scripts/evaluar_proveedor.py). Corre un lote de
**50–100 placas controladas** secuencialmente (no paraleliza contra la misma fuente; `--delay`
para respetar límites de tasa) y mide: **% éxito**, **latencia** (prom/min/max/p95), **cobertura
de campos**, **costo** (suma y prom/consulta) y **errores frecuentes**. No toca BD.

```
# Lote de demo (formato válido, no reales):
python -m scripts.evaluar_proveedor --n 60 --json reporte.json
# Lote real (placas conocidas, una por línea):
python -m scripts.evaluar_proveedor --placas placas_controladas.txt --delay 0.5 --json reporte.json
```
> Para la medición REAL usar `--placas` con placas verídicas y conocidas (no las generadas).

## 6. Resultados

### 6.1 Dry-run con `mock` (validación del harness, 60 placas, 2026-06-01)
| Métrica | Valor (mock) |
|---|---|
| % éxito | 100% (60/60 `consulta_realizada`) |
| Latencia | prom ~0 ms (sin red) |
| Cobertura | marca/modelo/anio/color/tipo/clase/servicio/chasis/motor/vin/titular = 100%; `valores_pendientes` = 0% |
| Costo | $0.00 (el mock no cuesta) |
| Errores | ninguno |

Confirma que el harness, el mapeo y el flujo de gateo/ofuscación funcionan punta a punta.

### 6.2 Proveedor real `consultas_ec` — **PENDIENTE**
Requiere `CONSULTAS_EC_API_KEY` + `CONSULTAS_EC_BASE_URL` + lote de placas reales. Completar:

| Métrica | Objetivo / umbral | Resultado real |
|---|---|---|
| % éxito | ≥ 70% | _pendiente_ |
| Latencia p95 | ≤ 3000 ms | _pendiente_ |
| Cobertura VIN/motor/chasis | ≥ 60% | _pendiente_ |
| Cobertura titular | ≥ 60% | _pendiente_ |
| Costo por consulta | medido (env `*_COSTO_USD`) | _pendiente_ |
| Errores frecuentes | — | _pendiente_ |

## 7. Margen del modelo (referencial, 1 token ≈ USD 0.04)
Una sola llamada al proveedor (≈ $0.08 estimado) puede alimentar **identificadores + titular**:

| Producto | Tokens | Precio ref. | Costo proveedor | Margen |
|---|---:|---:|---:|---:|
| `identificadores_tecnicos` | 3 | $0.12 | ~$0.08 | ~$0.04 |
| `titular_validado` | 5 | $0.20 | (misma llamada) | ~$0.12 |
| `reporte_compra_segura` | 40 | $1.60 | ~$0.08 | ~$1.52 |

> El margen es positivo si el costo real por consulta se mantiene ≲ $0.10. Si el proveedor cobra
> por campo o supera ~$0.12/consulta, reevaluar precios de `identificadores_tecnicos`.

## 8. Criterio de decisión (activar o no en producción)
Activar `consultas_ec` en prod **solo si**, en la medición real: % éxito ≥ 70%, latencia p95
≤ 3 s, cobertura de identificadores y titular ≥ 60%, y **margen positivo** en al menos el bundle.
Si no se cumplen, mantener `mock` para demo y evaluar el siguiente proveedor (preferencia 2/3),
**uno a la vez**.

## 9. Recomendación final
**PENDIENTE de la medición real.** El POC (integración + caché + costo + harness + ofuscación de
PII) está listo y verificado con `mock`. Falta: (a) cargar `CONSULTAS_EC_API_KEY` + `BASE_URL`,
(b) confirmar el contrato real y ajustar `_mapear` si difiere, (c) correr el harness con 50–100
placas reales y llenar §6.2/§7, (d) decidir con §8. **No** se activa SRI automático ni se expone
PII cruda; **no** se evade captcha.
