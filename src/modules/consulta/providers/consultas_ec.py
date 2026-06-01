"""Proveedor ConsultasEC — integración HTTP real (POC, Fase 3).

Proveedor comercial de datos vehiculares por **API REST** (NO scraping, NO captcha). Es el
primer proveedor real del POC (preferencia 1). Config por entorno:

- `CONSULTAS_EC_API_KEY`   — credencial. Sin ella, `capacidades` vacío y `sin_credenciales`.
- `CONSULTAS_EC_BASE_URL`  — endpoint que recibe la placa (ej. https://api.proveedor/v1/vehiculo).
- `CONSULTAS_EC_COSTO_USD` — costo estimado por consulta (para margen; default 0.08).

El **contrato externo exacto no está confirmado**: el mapeo (`_mapear`) es **defensivo** y acepta
los nombres de campo más comunes (es/en). Al confirmar el contrato real con el proveedor, ajustar
solo `_mapear` y la forma del request. Sigue la disciplina de servicios externos: captura todo y
devuelve el contrato normalizado; NUNCA propaga excepciones.
"""
from __future__ import annotations

import logging
import os
from decimal import Decimal, InvalidOperation

import httpx

from src.modules.consulta.providers.base import (
    ESTADO_ERROR,
    ESTADO_OK,
    ESTADO_SIN_CREDENCIALES,
    ESTADO_SIN_DATOS,
    ProveedorVehicular,
    ResultadoVehicular,
)

logger = logging.getLogger(__name__)

TIMEOUT_SEGUNDOS = float(os.getenv("CONSULTAS_EC_TIMEOUT", "15"))


def _primero(d: dict, *claves: str):
    """Primer valor no vacío entre varias claves candidatas (tolerante a nombres es/en)."""
    for k in claves:
        v = d.get(k)
        if v not in (None, "", []):
            return v
    return None


def _a_int(valor) -> int | None:
    try:
        return int(str(valor).strip()[:4])
    except (TypeError, ValueError):
        return None


class ConsultasECProvider(ProveedorVehicular):
    nombre = "consultas_ec"

    def __init__(self) -> None:
        self.api_key = os.getenv("CONSULTAS_EC_API_KEY", "").strip()
        self.base_url = os.getenv("CONSULTAS_EC_BASE_URL", "").strip()
        try:
            self.costo = Decimal(os.getenv("CONSULTAS_EC_COSTO_USD", "0.08"))
        except InvalidOperation:
            self.costo = Decimal("0.08")

    @property
    def configurado(self) -> bool:
        return bool(self.api_key and self.base_url)

    @property
    def capacidades(self) -> frozenset[str]:
        # Sin credencial/endpoint no se ofrece nada (no prometemos lo que no podemos entregar).
        if not self.configurado:
            return frozenset()
        return frozenset({"identificadores_tecnicos", "titular_validado"})

    async def consultar(self, placa: str) -> ResultadoVehicular:
        placa = placa.upper()
        if not self.configurado:
            return ResultadoVehicular(
                placa=placa,
                proveedor=self.nombre,
                estado=ESTADO_SIN_CREDENCIALES,
                raw_response={"error": "CONSULTAS_EC_API_KEY o CONSULTAS_EC_BASE_URL no configuradas"},
            )

        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SEGUNDOS) as cliente:
                respuesta = await cliente.get(
                    self.base_url,
                    params={"placa": placa},
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Accept": "application/json",
                    },
                )
        except httpx.HTTPError as e:  # timeout, DNS, conexión… → error tolerante
            logger.warning("ConsultasEC fallo de red para %s: %r", placa, e)
            return ResultadoVehicular(
                placa=placa, proveedor=self.nombre, estado=ESTADO_ERROR,
                costo_estimado_usd=None, raw_response={"error": f"red: {e!r}"},
            )

        if respuesta.status_code != 200:
            logger.warning("ConsultasEC HTTP %s para %s", respuesta.status_code, placa)
            return ResultadoVehicular(
                placa=placa, proveedor=self.nombre, estado=ESTADO_ERROR,
                raw_response={"http_status": respuesta.status_code, "body": respuesta.text[:500]},
            )

        try:
            payload = respuesta.json()
        except ValueError:
            return ResultadoVehicular(
                placa=placa, proveedor=self.nombre, estado=ESTADO_ERROR,
                raw_response={"error": "respuesta no-JSON", "body": respuesta.text[:500]},
            )

        return self._mapear(placa, payload if isinstance(payload, dict) else {"data": payload})

    def _mapear(self, placa: str, payload: dict) -> ResultadoVehicular:
        """Mapea la respuesta externa al contrato normalizado (defensivo, es/en).

        Acepta el dato a nivel raíz o anidado bajo `data`/`vehiculo`/`resultado`. Ajustar aquí
        cuando se confirme el contrato real del proveedor.
        """
        d = payload
        for envoltura in ("data", "vehiculo", "resultado", "result"):
            if isinstance(payload.get(envoltura), dict):
                d = payload[envoltura]
                break

        marca = _primero(d, "marca", "brand", "make")
        vin = _primero(d, "vin", "VIN")
        motor = _primero(d, "motor", "numero_motor", "engine", "engine_number")
        chasis = _primero(d, "chasis", "numero_chasis", "chassis", "chassis_number") or vin
        titular = _primero(d, "titular", "propietario", "owner", "owner_name")

        # Hay dato útil si vino al menos un identificador o característica relevante.
        hay_dato = any([marca, vin, motor, chasis, titular,
                        _primero(d, "modelo", "model")])
        estado = ESTADO_OK if hay_dato else ESTADO_SIN_DATOS

        return ResultadoVehicular(
            placa=placa,
            proveedor=self.nombre,
            estado=estado,
            marca=marca,
            modelo=_primero(d, "modelo", "model"),
            anio=_a_int(_primero(d, "anio", "año", "anio_modelo", "year", "model_year")),
            color=_primero(d, "color"),
            tipo=_primero(d, "tipo", "type", "tipo_vehiculo"),
            clase=_primero(d, "clase", "class", "vehicle_class"),
            servicio=_primero(d, "servicio", "service", "tipo_servicio"),
            chasis=chasis,
            motor=motor,
            vin=vin,
            titular=titular,
            multas=_primero(d, "multas", "infracciones", "fines") or [],
            valores_pendientes=_primero(d, "valores_pendientes", "total_a_pagar", "pending_amount"),
            costo_estimado_usd=self.costo if estado == ESTADO_OK else None,
            raw_response=payload,
        )
