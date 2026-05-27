---
name: validacion-datos-ec
description: Validar y normalizar identificadores ecuatorianos (placa, cédula, RUC, VIN) según los formatos oficiales. Usar al crear o modificar validadores, o al recibir cualquier identificador del usuario o de una fuente externa.
---

# Validación de datos ecuatorianos

Todos los validadores viven en [utils/validators.py](../../../utils/validators.py). Una función por tipo, con la convención `validar_<tipo>(valor: str) -> str` que devuelve el valor **normalizado** o lanza `ValueError` con un mensaje en español.

## Cuándo usar este skill

- Agregar un nuevo validador.
- Modificar un validador existente.
- Cualquier endpoint que reciba un identificador como path/query/body.

## Identificadores soportados

### Placa vehicular
- **Formato actual**: `^[A-Z]{3}[0-9]{3,4}$` — 3 letras + 3 o 4 dígitos.
- **Variantes a considerar** cuando se requiera ampliar:
  - **Motos**: en algunas provincias 2 letras + 4 dígitos (ej: `MA1234`).
  - **Comerciales/taxis**: pueden incluir prefijos específicos.
  - **Diplomáticas/oficiales**: formato distinto.
- **Normalización**: mayúsculas, eliminar guiones y espacios. Ya implementado.

### Cédula (10 dígitos) — `validar_cedula` ya implementado
- 10 dígitos numéricos.
- Los **dos primeros** son código de provincia (01–24, o 30 transferidos).
- El **tercero** es < 6 para personas naturales.
- **Dígito verificador**: algoritmo módulo 10 sobre los primeros 9 dígitos con coeficientes alternos `2,1,2,1,2,1,2,1,2`. Si el producto es ≥ 10, restar 9. Sumar todos los productos. El verificador es `(10 - (suma % 10)) % 10`.

### RUC (13 dígitos)
- 13 dígitos.
- Los **dos primeros**: código de provincia (01–24).
- El **tercer dígito** distingue el tipo:
  - `0–5` → persona natural (los primeros 10 dígitos son una cédula válida; los 3 últimos suelen ser `001`).
  - `6` → entidad pública.
  - `9` → sociedad privada/extranjera.
- Termina típicamente en `001`, `002`, etc. (establecimiento).

### VIN (chasis) — `validar_vin` ya implementado
- Exactamente 17 caracteres alfanuméricos.
- **No puede contener** las letras `I`, `O`, `Q` (para evitar confusión con 1 y 0).
- Mayúsculas siempre.
- Dígito verificador en **posición 9** según ISO 3779/3780: suma ponderada con pesos `[8,7,6,5,4,3,2,10,0,9,8,7,6,5,4,3,2]` y transliteración de letras (`A=1, B=2, ..., R=9, S=2, ..., Z=9`). El residuo mod 11 da el dígito; 10 se representa como `X`.

### Decodificación del origen del VIN

El **primer carácter** del VIN (parte del WMI = primeros 3) identifica la región/país. Tabla `PAISES_VIN` en [utils/ofuscacion.py](../../../utils/ofuscacion.py). Ejemplos relevantes para Ecuador:

| Carácter 1 | Origen |
|---|---|
| `1`, `4`, `5` | Estados Unidos |
| `3` | México |
| `9` | Brasil |
| `J` | Japón |
| `K` | Corea del Sur |
| `L` | China |
| `M` | India / Indonesia / Tailandia |
| `W` | Alemania |
| `V` | Francia / España / Austria |

Función: `decodificar_origen_vin(vin) -> {pais, wmi, descripcion}`.

### Ofuscación de identificadores sensibles

VIN, número de motor y número de chasis son sensibles. Mostrar el valor completo solo al dueño autenticado. Para vistas compartidas (compra-venta con token), usar el nivel `"origen"` que mantiene los primeros 3 caracteres + el país decodificado.

Niveles implementados en [utils/ofuscacion.py](../../../utils/ofuscacion.py):
- `completo`: valor sin ofuscar.
- `origen`: primeros 3 caracteres + máscara (`JTD**************`).
- `oculto`: sin valor; solo el país y la descripción del WMI.

Esquemas Pydantic correspondientes en [schemas/vehiculo.py](../../../schemas/vehiculo.py):
- `VehiculoSalidaCompleta` (dueño).
- `VehiculoSalidaCompartida` (token de compra-venta).
- `VehiculoSalidaPublica` (sin VIN/motor/chasis).

## Estructura estándar de un validador

```python
def validar_<tipo>(valor: str) -> str:
    valor = valor.upper().strip().replace("-", "").replace(" ", "")
    # ... reglas de formato ...
    if not <condicion>:
        raise ValueError("<tipo> inválido: <motivo>")
    # ... reglas de checksum si aplica ...
    return valor
```

Reglas:
- Siempre **normalizar primero** (case, whitespace, separadores).
- Mensajes de error en español, descriptivos.
- Una sola responsabilidad por validador. No mezclar validación de placa y de cédula en una función.
- El validador devuelve el valor normalizado; los callers deben usar ese valor de ahí en adelante.

## Uso en endpoints

```python
try:
    placa_limpia = validar_placa(placa)
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
```

## Anti-patrones

- ❌ Validar con regex sin normalizar primero (acepta `abc-1234` o falla por mayúsculas).
- ❌ Devolver `True/False` en lugar de devolver el valor normalizado o lanzar.
- ❌ Validar checksum de cédula con tabla de coeficientes mal copiada — verificar contra cédulas reales conocidas.
- ❌ Aceptar VIN con letras I/O/Q "porque algunos sistemas las usan" — no, el estándar es claro.
