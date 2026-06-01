"""Definición-semilla del catálogo de productos de microdesbloqueo.

Desde la v2 el catálogo VIVE EN BD (`productos_consulta`). Este módulo es la **fuente
canónica del seed**: la usa `services/desbloqueos.inicializar_catalogo` para sembrar/
asegurar el catálogo de forma idempotente (no duplica). La migración 0015 también siembra
estos mismos valores (literal, self-contained). 1 token ≈ USD 0.05.

Ver docs/producto/catalogo_productos_consulta.md y modelo_tokens_microdesbloqueos.md.
"""
from __future__ import annotations

from enum import Enum


class Sensibilidad(str, Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"


# (codigo, nombre, descripcion, tokens, precio_referencial_usd, sensibilidad, orden)
SEED_PRODUCTOS: list[dict] = [
    {
        "codigo": "vehiculo_basico",
        "nombre": "Ficha básica",
        "descripcion": "Clase, servicio y fechas de matrícula (marca/modelo/año/color son gratis).",
        "tokens": 3,
        "precio_referencial_usd": "0.15",
        "sensibilidad": "baja",
        "orden": 10,
    },
    {
        "codigo": "vehiculo_tecnico",
        "nombre": "Datos técnicos",
        "descripcion": "Cilindraje, tipo de motor, transmisión y combustible (según disponibilidad).",
        "tokens": 2,
        "precio_referencial_usd": "0.10",
        "sensibilidad": "baja",
        "orden": 20,
    },
    {
        "codigo": "vehiculo_identificadores",
        "nombre": "VIN, motor y chasis",
        "descripcion": "Identificadores ofuscados a origen (primeros caracteres + país del WMI).",
        "tokens": 3,
        "precio_referencial_usd": "0.15",
        "sensibilidad": "media",
        "orden": 30,
    },
    {
        "codigo": "vehiculo_titular_validado",
        "nombre": "Titular validado",
        "descripcion": "Validación del titular (coincide/ofuscado), nunca el dato crudo. Requiere proveedor autorizado.",
        "tokens": 5,
        "precio_referencial_usd": "0.25",
        "sensibilidad": "alta",
        "orden": 40,
    },
    {
        "codigo": "vehiculo_multas",
        "nombre": "Multas e infracciones",
        "descripcion": "Detalle con montos por fuente (ANT/AMT): pendientes, total a pagar y categorías.",
        "tokens": 8,
        "precio_referencial_usd": "0.40",
        "sensibilidad": "media",
        "orden": 50,
    },
    {
        "codigo": "reporte_compra_segura",
        "nombre": "Reporte de compra segura",
        "descripcion": "Combo con descuento: ficha básica + técnico + identificadores + multas.",
        "tokens": 30,
        "precio_referencial_usd": "1.50",
        "sensibilidad": "alta",
        "orden": 60,
    },
    {
        "codigo": "verificacion_marketplace",
        "nombre": "Verificación de la plataforma",
        "descripcion": "Sello Verificado por la plataforma para una publicación premium del marketplace.",
        "tokens": 80,
        "precio_referencial_usd": "4.00",
        "sensibilidad": "alta",
        "orden": 70,
    },
]

# Códigos que el bundle `reporte_compra_segura` desbloquea de una vez.
BUNDLE_INCLUYE: dict[str, tuple[str, ...]] = {
    "reporte_compra_segura": (
        "vehiculo_basico",
        "vehiculo_tecnico",
        "vehiculo_identificadores",
        "vehiculo_multas",
    ),
}
