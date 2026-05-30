"""Catálogo maestro de fuentes de datos vehiculares.

Capa de **configuración estática** (no toca la lógica de consulta). Registra
formalmente cada fuente conocida —oficial o no— con su prioridad (proxy de la
latencia/orden esperado), su origen y qué categorías de dato aporta. Sirve de
base para el "Perfil Consolidado de Vehículo": cuando el backend agregue las
respuestas parciales de varias fuentes, este catálogo define de dónde sale cada
sección temática y con qué confianza (oficial vs. no oficial).

Pivote a perfil consolidado — ver AGENTS.md §1 y §6. Aquí NO se scrapea nada;
solo se describe el universo de fuentes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Prioridad(str, Enum):
    """Prioridad de la fuente, proxy de su latencia/orden de presentación.

    `ALTA` = rápida y troncal (se muestra primero); `BAJA` = lenta o no oficial
    (se completa de fondo). No es un nivel de confianza —eso lo da `Origen`.
    """

    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


class Origen(str, Enum):
    """Procedencia de la fuente: institución oficial vs. portal de terceros.

    `NO_OFICIAL` obliga a mostrar disclaimer en el frontend (ver Paso 3).
    """

    OFICIAL = "oficial"
    NO_OFICIAL = "no_oficial"


class CategoriaDato(str, Enum):
    """Secciones temáticas del perfil consolidado a las que aporta una fuente.

    Alineadas 1:1 con los bloques de `VehiculoConsolidadoResponse` (Paso 2):
    una fuente que declara `MULTAS` alimenta `multas_pendientes`, etc.
    """

    DATOS_BASICOS = "datos_basicos"          # marca, modelo, año, color, clase
    IDENTIFICACION = "identificacion"        # chasis, motor, VIN (ofuscados)
    VALORES_TRIBUTARIOS = "valores_tributarios"  # matrícula, impuestos a pagar
    MULTAS = "multas"                        # citaciones/infracciones pendientes
    NOVEDADES_LEGALES = "novedades_legales"  # denuncias, noticias del delito


@dataclass(frozen=True)
class FuenteCatalogo:
    """Descripción estática de una fuente de datos vehiculares."""

    clave: str                               # identificador corto y estable (ANT, SRI, ...)
    nombre: str                              # nombre legible de la institución/portal
    prioridad: Prioridad
    origen: Origen
    categorias: tuple[CategoriaDato, ...]    # secciones temáticas que alimenta
    atributos: tuple[str, ...] = field(default_factory=tuple)  # campos puntuales que aporta
    implementada: bool = False               # ¿ya existe services/<fuente>.py activo?
    descripcion: str = ""

    @property
    def es_oficial(self) -> bool:
        return self.origen is Origen.OFICIAL


# ── Catálogo maestro ────────────────────────────────────────────────────────
# Orden de declaración = orden sugerido de presentación (alta → baja prioridad).
# `implementada=True` solo para las fuentes con servicio activo hoy (ANT/SRI/AMT/FGE).
CATALOGO_FUENTES: dict[str, FuenteCatalogo] = {
    "ANT": FuenteCatalogo(
        clave="ANT",
        nombre="Agencia Nacional de Tránsito",
        prioridad=Prioridad.ALTA,
        origen=Origen.OFICIAL,
        categorias=(
            CategoriaDato.DATOS_BASICOS,
            CategoriaDato.MULTAS,
        ),
        atributos=("marca", "modelo", "anio_vehiculo", "color", "clase", "citaciones"),
        implementada=True,
        descripcion="Matriculación y citaciones de tránsito a nivel nacional.",
    ),
    "SRI": FuenteCatalogo(
        clave="SRI",
        nombre="Servicio de Rentas Internas",
        prioridad=Prioridad.ALTA,
        origen=Origen.OFICIAL,
        categorias=(
            CategoriaDato.DATOS_BASICOS,
            CategoriaDato.VALORES_TRIBUTARIOS,
        ),
        atributos=("marca", "modelo", "anio_modelo", "matricula", "total_a_pagar"),
        implementada=True,
        descripcion=(
            "Valores tributarios del vehículo (matrícula, impuestos). "
            "Hoy se expone como consulta externa por reCAPTCHA Enterprise (ver AGENTS.md §8)."
        ),
    ),
    "AMT": FuenteCatalogo(
        clave="AMT",
        nombre="Agencia Metropolitana de Tránsito (Quito)",
        prioridad=Prioridad.MEDIA,
        origen=Origen.OFICIAL,
        categorias=(CategoriaDato.MULTAS,),
        atributos=("infracciones", "total_a_pagar", "pendientes"),
        implementada=True,
        descripcion="Infracciones municipales del Distrito Metropolitano de Quito.",
    ),
    "FGE": FuenteCatalogo(
        clave="FGE",
        nombre="Fiscalía General del Estado",
        prioridad=Prioridad.MEDIA,
        origen=Origen.OFICIAL,
        categorias=(CategoriaDato.NOVEDADES_LEGALES,),
        atributos=("denuncias", "noticias_delito"),
        implementada=True,
        descripcion=(
            "Noticias del delito (SIAF) por placa/cédula/RUC/nombres. Desde may-2026 el "
            "portal exige hCaptcha → se expone como consulta_externa (enlace), no scraping."
        ),
    ),
    "EPMTSD": FuenteCatalogo(
        clave="EPMTSD",
        nombre="EP Municipal de Tránsito de Santo Domingo",
        prioridad=Prioridad.MEDIA,
        origen=Origen.OFICIAL,
        categorias=(CategoriaDato.MULTAS,),
        atributos=("infracciones", "total_a_pagar", "pendientes"),
        implementada=True,
        descripcion=(
            "Infracciones municipales de Santo Domingo de los Tsáchilas. Mismo portal "
            "AxisCloud que AMT (ps_empresa=06). Vía worker híbrido como AMT."
        ),
    ),
    "ConsultasEcuador": FuenteCatalogo(
        clave="ConsultasEcuador",
        nombre="ConsultasEcuador (portal de terceros)",
        prioridad=Prioridad.BAJA,
        origen=Origen.NO_OFICIAL,
        categorias=(CategoriaDato.IDENTIFICACION,),
        atributos=("numero_chasis", "numero_motor"),
        implementada=True,
        descripcion=(
            "Aportaría chasis/motor, pero el portal está tras reCAPTCHA (como SRI) y es "
            "una página de afiliado, no una API. Se expone como consulta_externa (enlace + "
            "disclaimer no oficial), sin scraping."
        ),
    ),
    "EcuadorLegalOnline": FuenteCatalogo(
        clave="EcuadorLegalOnline",
        nombre="Ecuador Legal Online (portal de terceros)",
        prioridad=Prioridad.BAJA,
        origen=Origen.NO_OFICIAL,
        categorias=(CategoriaDato.NOVEDADES_LEGALES,),
        atributos=(),
        implementada=True,
        descripcion=(
            "Sitio de guías con ad-gate/reCAPTCHA; el dato (propietario por placa) es de "
            "pago y es PII. Se expone como consulta_externa (enlace + disclaimer no oficial), "
            "sin scraping."
        ),
    ),
}


def fuentes_por_categoria(categoria: CategoriaDato) -> list[FuenteCatalogo]:
    """Fuentes que alimentan una sección temática, ordenadas por prioridad."""
    orden = {Prioridad.ALTA: 0, Prioridad.MEDIA: 1, Prioridad.BAJA: 2}
    seleccionadas = [
        f for f in CATALOGO_FUENTES.values() if categoria in f.categorias
    ]
    return sorted(seleccionadas, key=lambda f: orden[f.prioridad])


def fuentes_implementadas() -> list[FuenteCatalogo]:
    """Fuentes con servicio de scraping activo hoy (ANT/SRI/AMT/FGE)."""
    return [f for f in CATALOGO_FUENTES.values() if f.implementada]
