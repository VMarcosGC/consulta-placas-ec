"""Catálogo de productos de microdesbloqueo de la consulta (Pilar 1+).

Fuente de verdad de **precios y descripciones** (igual que `catalogo_fuentes.py` lo es
de las fuentes). Vive en código —no en BD— para versionar el precio con el repo sin
migración. La tabla `desbloqueos` solo guarda el `codigo` (clave estable, en español).

Ver docs/producto/catalogo_productos_consulta.md y modelo_tokens_microdesbloqueos.md.
1 token ≈ USD 0.05 (referencial). El cobro real lo hace `tokens.service.debitar_tokens`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Sensibilidad(str, Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"


@dataclass(frozen=True)
class ProductoConsulta:
    codigo: str
    nombre: str
    tokens: int
    sensibilidad: Sensibilidad
    descripcion: str
    # Para bundles: códigos de productos que quedan incluidos al comprar este.
    incluye: tuple[str, ...] = field(default=())


# Orden de declaración = orden de presentación en la UI.
CATALOGO_PRODUCTOS: dict[str, ProductoConsulta] = {
    "vehiculo_basico": ProductoConsulta(
        codigo="vehiculo_basico",
        nombre="Ficha básica",
        tokens=3,
        sensibilidad=Sensibilidad.BAJA,
        descripcion="Clase, servicio y fechas de matrícula/caducidad (además de marca/modelo/año/color, que son gratis).",
    ),
    "vehiculo_tecnico": ProductoConsulta(
        codigo="vehiculo_tecnico",
        nombre="Datos técnicos",
        tokens=2,
        sensibilidad=Sensibilidad.BAJA,
        descripcion="Cilindraje, tipo de motor, transmisión y combustible (según disponibilidad de la fuente).",
    ),
    "vehiculo_identificadores": ProductoConsulta(
        codigo="vehiculo_identificadores",
        nombre="VIN, motor y chasis",
        tokens=3,
        sensibilidad=Sensibilidad.MEDIA,
        descripcion="Identificadores ofuscados a origen (primeros caracteres + país del WMI).",
    ),
    "vehiculo_titular_validado": ProductoConsulta(
        codigo="vehiculo_titular_validado",
        nombre="Titular (validado)",
        tokens=5,
        sensibilidad=Sensibilidad.ALTA,
        descripcion="Validación del titular (coincide/ofuscado), nunca el dato crudo. Requiere proveedor autorizado.",
    ),
    "vehiculo_multas": ProductoConsulta(
        codigo="vehiculo_multas",
        nombre="Multas e infracciones",
        tokens=8,
        sensibilidad=Sensibilidad.MEDIA,
        descripcion="Detalle con montos por fuente (ANT/AMT): pendientes, total a pagar y categorías.",
    ),
    "reporte_compra_segura": ProductoConsulta(
        codigo="reporte_compra_segura",
        nombre="Reporte de compra segura",
        tokens=30,
        sensibilidad=Sensibilidad.ALTA,
        descripcion="Combo con descuento: ficha básica + técnico + identificadores + multas (y condición legal cuando esté disponible).",
        incluye=(
            "vehiculo_basico",
            "vehiculo_tecnico",
            "vehiculo_identificadores",
            "vehiculo_multas",
        ),
    ),
    # NOTA: `verificacion_marketplace` (80 tokens) NO es un producto de la consulta por
    # placa; pertenece al flujo del marketplace (sello "Verificado por la plataforma",
    # que hoy aprueba un admin). Se documenta en el catálogo de producto pero no se
    # expone aquí para no mezclar dominios ni romper el premium actual. Ver
    # docs/producto/catalogo_productos_consulta.md (decisión abierta #2).
}


def producto(codigo: str) -> ProductoConsulta | None:
    """Devuelve el producto del catálogo o None si el código no existe."""
    return CATALOGO_PRODUCTOS.get(codigo)
