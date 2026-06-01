"""Proveedor PlacaAPI EC (stub con seam de integración real).

Proveedor comercial hipotético de datos vehiculares por API (NO scraping, NO captcha). La
credencial va en `PLACAAPI_EC_API_KEY`. Mismo contrato y reglas que `consultas_ec.py`: sin
credencial → `capacidades` vacío y `consultar` devuelve `sin_credenciales`. La llamada HTTP
real queda como TODO (no hay credenciales ni contrato todavía).
"""
from __future__ import annotations

import os

from src.modules.consulta.providers.base import (
    ESTADO_SIN_CREDENCIALES,
    ProveedorVehicular,
    ResultadoVehicular,
)


class PlacaApiECProvider(ProveedorVehicular):
    nombre = "placaapi_ec"

    def __init__(self) -> None:
        self.api_key = os.getenv("PLACAAPI_EC_API_KEY", "").strip()

    @property
    def capacidades(self) -> frozenset[str]:
        if not self.api_key:
            return frozenset()
        return frozenset({"identificadores_tecnicos"})

    async def consultar(self, placa: str) -> ResultadoVehicular:
        if not self.api_key:
            return ResultadoVehicular(
                placa=placa.upper(),
                proveedor=self.nombre,
                estado=ESTADO_SIN_CREDENCIALES,
                raw_response={"error": "PLACAAPI_EC_API_KEY no configurada"},
            )
        # TODO(integración): llamada HTTP real a PlacaAPI EC y mapeo al contrato.
        return ResultadoVehicular(
            placa=placa.upper(),
            proveedor=self.nombre,
            estado=ESTADO_SIN_CREDENCIALES,
            raw_response={"error": "Integración real pendiente"},
        )
