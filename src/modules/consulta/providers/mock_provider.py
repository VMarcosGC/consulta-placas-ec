"""Proveedor MOCK: datos vehiculares simulados, deterministas por placa.

Permite desarrollar y demostrar el flujo de microdesbloqueos progresivos SIN credenciales de
un proveedor real (que aún no existen). Es el proveedor por defecto
(`PROVEEDOR_VEHICULAR_ACTIVO=mock`). Genera datos estables a partir de la placa (misma placa →
mismos datos), así la demo es reproducible.

Capacidades: `identificadores_tecnicos` y `titular_validado` — los dos productos que hoy NO
tienen otra fuente. Las multas siguen viniendo del scraping público (ANT/AMT), no del mock.
"""
from __future__ import annotations

import hashlib
from decimal import Decimal

from src.modules.consulta.providers.base import (
    ESTADO_OK,
    ProveedorVehicular,
    ResultadoVehicular,
)

# Tablas para derivar datos plausibles de forma determinista desde la placa.
_MARCAS = ["Chevrolet", "Kia", "Hyundai", "Toyota", "Mazda", "Nissan", "Renault", "Volkswagen"]
_MODELOS = ["Sail", "Rio", "Accent", "Corolla", "3", "Sentra", "Logan", "Gol"]
_COLORES = ["Blanco", "Plata", "Negro", "Gris", "Rojo", "Azul"]
_WMI = ["8LD", "9BD", "KNA", "JTD", "MA3", "3N1"]  # prefijos VIN reales (origen variado)
_NOMBRES = ["Juan Carlos Pérez Gómez", "María Fernanda López Andrade", "Luis Alberto Vaca Mora",
            "Andrea Paulina Suárez Ríos", "Diego Armando Castro Vélez"]


def _h(placa: str, sal: str) -> int:
    """Entero estable derivado de la placa + una sal (para variar por campo)."""
    return int(hashlib.sha256(f"{placa}:{sal}".encode()).hexdigest(), 16)


class MockProvider(ProveedorVehicular):
    nombre = "mock"

    @property
    def capacidades(self) -> frozenset[str]:
        return frozenset({"identificadores_tecnicos", "titular_validado"})

    async def consultar(self, placa: str) -> ResultadoVehicular:
        placa = placa.upper()
        wmi = _WMI[_h(placa, "wmi") % len(_WMI)]
        vin = f"{wmi}{(_h(placa, 'vin') % 10**14):014d}"  # 17 caracteres
        motor = f"{_h(placa, 'motor') % 10**10:010d}"
        chasis = vin  # en EC el chasis suele coincidir con el VIN
        anio = 2008 + (_h(placa, "anio") % 17)  # 2008–2024
        return ResultadoVehicular(
            placa=placa,
            proveedor=self.nombre,
            estado=ESTADO_OK,
            marca=_MARCAS[_h(placa, "marca") % len(_MARCAS)],
            modelo=_MODELOS[_h(placa, "modelo") % len(_MODELOS)],
            anio=anio,
            color=_COLORES[_h(placa, "color") % len(_COLORES)],
            tipo="Liviano",
            clase="Automóvil",
            servicio="Particular",
            chasis=chasis,
            motor=motor,
            vin=vin,
            titular=_NOMBRES[_h(placa, "titular") % len(_NOMBRES)],
            multas=[],
            valores_pendientes=None,
            costo_estimado_usd=Decimal("0.00"),  # el mock no cuesta
            raw_response={"mock": True, "placa": placa},
        )
