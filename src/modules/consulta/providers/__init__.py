"""Capa de proveedores de datos vehiculares (Fase 3).

Un *proveedor* es una fuente de pago/convenio (API oficial o servicio comercial) que entrega
datos que el scraping público no puede: identificadores técnicos (VIN/motor/chasis) y
validación del titular. A diferencia de `services/<fuente>.py` (scraping de portales), aquí
no se raspa nada ni se evade captcha: se consume una API autorizada.

Contrato normalizado: `base.ResultadoVehicular`. Proveedor activo: `selector.obtener_proveedor`
(configurable por `PROVEEDOR_VEHICULAR_ACTIVO`). El proveedor SOLO se invoca al desbloquear un
producto pagado y su respuesta se cachea (ver `services/proveedor.py`); la consulta gratuita
nunca llama al proveedor. Ver docs/producto/modelo_tokens_microdesbloqueos.md y
docs/producto/politica_datos_sensibles.md.
"""
from src.modules.consulta.providers.base import ProveedorVehicular, ResultadoVehicular
from src.modules.consulta.providers.selector import obtener_proveedor

__all__ = ["ProveedorVehicular", "ResultadoVehicular", "obtener_proveedor"]
