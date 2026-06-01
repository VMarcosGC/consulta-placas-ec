"""Definición-semilla del catálogo de productos de microdesbloqueo.

Desde la v2 el catálogo VIVE EN BD (`productos_consulta`). Este módulo es la **fuente
canónica del seed**: la usa `services/desbloqueos.inicializar_catalogo` para sembrar/
asegurar el catálogo de forma idempotente (no duplica). Las migraciones 0015 (seed inicial)
y 0016 (reajuste comercial: solo se cobra por costo/dificultad/valor real) lo dejan en este
mismo estado. **1 token ≈ USD 0.04.**

Regla comercial (Fase 2.5, 2026-05-31): los **datos públicos simples** (marca, modelo, año,
color, clase, servicio, estado de matrícula) son **gratis** vía `consulta_publica_base`; solo
se cobran datos que generan **costo de proveedor externo**, **dificultad real** o **valor
comercial relevante**. Ver docs/producto/catalogo_productos_consulta.md,
reglas_monetizacion_tokens.md y modelo_tokens_microdesbloqueos.md.
"""
from __future__ import annotations

from enum import Enum


class Sensibilidad(str, Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"


# (codigo, nombre, descripcion, tokens, precio_referencial_usd, sensibilidad, orden)
# precio_referencial_usd = tokens * 0.04 (1 token ≈ USD 0.04).
SEED_PRODUCTOS: list[dict] = [
    {
        "codigo": "consulta_publica_base",
        "nombre": "Consulta pública base",
        "descripcion": "Gratis: características públicas (marca, modelo, año, color, clase, servicio), estado de matrícula, enlaces oficiales y estado de fuentes.",
        "tokens": 0,
        "precio_referencial_usd": "0.00",
        "sensibilidad": "baja",
        "orden": 10,
    },
    {
        "codigo": "identificadores_tecnicos",
        "nombre": "Ver identificadores técnicos",
        "descripcion": "VIN, motor y chasis ofuscados a origen (primeros caracteres + país del WMI) más datos técnicos disponibles.",
        "tokens": 3,
        "precio_referencial_usd": "0.12",
        "sensibilidad": "media",
        "orden": 20,
    },
    {
        "codigo": "titular_validado",
        "nombre": "Validar titular registrado",
        "descripcion": "Validación del titular (coincide/ofuscado), nunca el dato crudo. Requiere proveedor autorizado.",
        "tokens": 5,
        "precio_referencial_usd": "0.20",
        "sensibilidad": "alta",
        "orden": 30,
    },
    {
        "codigo": "alertas_legales",
        "nombre": "Ver alertas legales",
        "descripcion": "Novedades legales asociadas (FGE). Requiere fuente estructurada y legalmente segura; si no, se ofrece el enlace oficial.",
        "tokens": 8,
        "precio_referencial_usd": "0.32",
        "sensibilidad": "alta",
        "orden": 40,
    },
    {
        "codigo": "multas_con_montos",
        "nombre": "Ver multas con valores",
        "descripcion": "Detalle con montos por fuente (ANT/AMT): pendientes, total a pagar y categorías.",
        "tokens": 10,
        "precio_referencial_usd": "0.40",
        "sensibilidad": "media",
        "orden": 50,
    },
    {
        "codigo": "valores_matricula_sri",
        "nombre": "Ver valores de matrícula (SRI)",
        "descripcion": "Valores tributarios del SRI. Sin proveedor automático confiable: se ofrece el enlace oficial asistido.",
        "tokens": 12,
        "precio_referencial_usd": "0.48",
        "sensibilidad": "media",
        "orden": 60,
    },
    {
        "codigo": "reporte_compra_segura",
        "nombre": "Generar reporte compra segura",
        "descripcion": "Informe consolidado: identificadores técnicos + multas con valores + alertas legales + valores SRI + titular validado (según disponibilidad).",
        "tokens": 40,
        "precio_referencial_usd": "1.60",
        "sensibilidad": "alta",
        "orden": 70,
    },
    {
        "codigo": "verificacion_marketplace",
        "nombre": "Verificación de la plataforma",
        "descripcion": "Sello Verificado por la plataforma para una publicación premium del marketplace.",
        "tokens": 100,
        "precio_referencial_usd": "4.00",
        "sensibilidad": "alta",
        "orden": 80,
    },
]

# Códigos que el bundle `reporte_compra_segura` desbloquea de una vez. Incluye todos los
# microproductos de pago; los que aún no tienen fuente/proveedor quedan pre-desbloqueados
# para esa placa (sin dato hoy, listos cuando el proveedor exista).
BUNDLE_INCLUYE: dict[str, tuple[str, ...]] = {
    "reporte_compra_segura": (
        "identificadores_tecnicos",
        "multas_con_montos",
        "alertas_legales",
        "valores_matricula_sri",
        "titular_validado",
    ),
}
