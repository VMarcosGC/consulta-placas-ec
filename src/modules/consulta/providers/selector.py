"""Selector del proveedor vehicular activo (configurable por entorno).

`PROVEEDOR_VEHICULAR_ACTIVO` elige la implementación (default `mock`). Así se cambia de
proveedor sin tocar código: `mock` para desarrollo/demo, o uno real cuando haya credenciales.
La instancia se memoiza por nombre (los proveedores son stateless salvo la API key, que se
lee al construir; reiniciar el proceso recarga env vars).
"""
from __future__ import annotations

import os
from functools import lru_cache

from src.modules.consulta.providers.base import ProveedorVehicular
from src.modules.consulta.providers.mock_provider import MockProvider
from src.modules.consulta.providers.consultas_ec import ConsultasECProvider
from src.modules.consulta.providers.placaapi_ec import PlacaApiECProvider
from src.modules.consulta.providers.webservices_ec import WebServicesECProvider

# Registro nombre → clase. El default es `mock` (no requiere credenciales).
_REGISTRO: dict[str, type[ProveedorVehicular]] = {
    "mock": MockProvider,
    "consultas_ec": ConsultasECProvider,
    "placaapi_ec": PlacaApiECProvider,
    "webservices_ec": WebServicesECProvider,
}

PROVEEDOR_DEFECTO = "mock"


@lru_cache(maxsize=None)
def _instanciar(nombre: str) -> ProveedorVehicular:
    clase = _REGISTRO.get(nombre, _REGISTRO[PROVEEDOR_DEFECTO])
    return clase()


def nombre_proveedor_activo() -> str:
    """Nombre del proveedor activo según `PROVEEDOR_VEHICULAR_ACTIVO` (default `mock`)."""
    nombre = os.getenv("PROVEEDOR_VEHICULAR_ACTIVO", PROVEEDOR_DEFECTO).strip().lower()
    return nombre if nombre in _REGISTRO else PROVEEDOR_DEFECTO


def obtener_proveedor() -> ProveedorVehicular:
    """Instancia (memoizada) del proveedor activo."""
    return _instanciar(nombre_proveedor_activo())
