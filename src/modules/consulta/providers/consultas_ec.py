"""Proveedor ConsultasEC (stub con seam de integración real).

Proveedor comercial hipotético de datos vehiculares por API (NO scraping, NO captcha). La
credencial va en `CONSULTAS_EC_API_KEY`. **Sin credencial**, el proveedor declara `capacidades`
vacío y `consultar` devuelve `sin_credenciales`: no se ofrece ni se cobra ningún producto que
dependa de él. Cuando exista la API real, se implementa la llamada HTTP en `consultar`
(httpx) mapeando la respuesta al contrato `ResultadoVehicular`.

NO se implementa todavía la llamada real (no hay credenciales ni contrato): este archivo deja
el punto de integración listo y tolerante a fallos.
"""
from __future__ import annotations

import os

from src.modules.consulta.providers.base import (
    ESTADO_SIN_CREDENCIALES,
    ProveedorVehicular,
    ResultadoVehicular,
)


class ConsultasECProvider(ProveedorVehicular):
    nombre = "consultas_ec"

    def __init__(self) -> None:
        self.api_key = os.getenv("CONSULTAS_EC_API_KEY", "").strip()

    @property
    def capacidades(self) -> frozenset[str]:
        # Sin credencial no se ofrece nada (no prometemos datos que no podemos entregar).
        if not self.api_key:
            return frozenset()
        return frozenset({"identificadores_tecnicos", "titular_validado"})

    async def consultar(self, placa: str) -> ResultadoVehicular:
        if not self.api_key:
            return ResultadoVehicular(
                placa=placa.upper(),
                proveedor=self.nombre,
                estado=ESTADO_SIN_CREDENCIALES,
                raw_response={"error": "CONSULTAS_EC_API_KEY no configurada"},
            )
        # TODO(integración): llamada HTTP real a la API de ConsultasEC y mapeo al contrato.
        # async with httpx.AsyncClient(timeout=15) as cliente:
        #     r = await cliente.get(URL, params={"placa": placa}, headers={"Authorization": ...})
        #     ... mapear r.json() → ResultadoVehicular(estado=ESTADO_OK, vin=..., titular=...)
        return ResultadoVehicular(
            placa=placa.upper(),
            proveedor=self.nombre,
            estado=ESTADO_SIN_CREDENCIALES,
            raw_response={"error": "Integración real pendiente"},
        )
