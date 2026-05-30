"""Esquemas Pydantic del módulo de consulta.

Modelo del **Perfil Consolidado de Vehículo**: en vez de exponer una caja por
fuente, el backend agrega las respuestas parciales (ANT/SRI/AMT/FGE/…) en
secciones temáticas orientadas a la entidad vehículo (datos básicos, multas,
novedades legales, …). Ver AGENTS.md §6 y el catálogo en `catalogo_fuentes.py`.

Esto es **solo la estructura**: aquí no se cambian endpoints ni se cablea la
agregación. Las listas nacen vacías para que una fuente `en_proceso` no rompa
la respuesta —el frontend muestra skeletons mientras se completan.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from src.modules.consulta.services.catalogo_fuentes import Origen, Prioridad


class EstadoFuente(str, Enum):
    """Estado consolidado de una fuente dentro del perfil.

    Simplifica los `estado` crudos de cada servicio (AGENTS.md §6) a lo que el
    frontend necesita para decidir entre dato, skeleton o aviso de error.
    """

    COMPLETADA = "completada"           # consulta_realizada
    SIN_RESULTADOS = "sin_resultados"   # la fuente respondió, sin datos
    EN_PROCESO = "en_proceso"           # worker híbrido aún trabajando
    ERROR_FUENTE = "error_fuente"       # fuente oficial caída tras reintentos
    ERROR = "error"                     # error técnico del scraping
    CONSULTA_EXTERNA = "consulta_externa"  # se ofrece enlace al portal (SRI)
    NO_INTEGRADA = "no_integrada"       # fuente del catálogo aún sin servicio

    @classmethod
    def desde_estado_servicio(cls, estado: str | None) -> "EstadoFuente":
        """Mapea el `estado` crudo de una función `consultar_*` a este enum."""
        mapa = {
            "consulta_realizada": cls.COMPLETADA,
            "sin_resultados": cls.SIN_RESULTADOS,
            "en_proceso": cls.EN_PROCESO,
            "error_fuente": cls.ERROR_FUENTE,
            "error": cls.ERROR,
            "bloqueado_captcha": cls.ERROR,
            "consulta_externa": cls.CONSULTA_EXTERNA,
            "pendiente_integracion": cls.NO_INTEGRADA,
        }
        return mapa.get(estado or "", cls.ERROR)

    @property
    def esta_cargando(self) -> bool:
        return self is EstadoFuente.EN_PROCESO


class EstadoFuenteItem(BaseModel):
    """Estado de una fuente concreta, para pintar el tablero de fuentes."""

    clave: str = Field(..., description="Identificador corto de la fuente (ANT, SRI, …)")
    nombre: str = Field(..., description="Nombre legible de la institución/portal")
    prioridad: Prioridad
    origen: Origen
    estado: EstadoFuente
    detalle: str | None = Field(
        None, description="Mensaje de error o URL externa, según el estado"
    )


class DatosBasicos(BaseModel):
    """Características generales del vehículo (sección de carga rápida)."""

    marca: str | None = None
    modelo: str | None = None
    anio: int | None = Field(None, description="Año del vehículo")
    color: str | None = None
    clase: str | None = None
    servicio: str | None = None
    fecha_matricula: str | None = None
    fecha_caducidad: str | None = Field(None, description="Vencimiento de la matrícula")
    pais_origen: str | None = None


class Identificacion(BaseModel):
    """Identificadores sensibles, SIEMPRE ofuscados para terceros (AGENTS.md §7)."""

    vin_ofuscado: str | None = None
    numero_motor_ofuscado: str | None = None
    numero_chasis_ofuscado: str | None = None
    pais_origen: str | None = Field(None, description="País decodificado del WMI del VIN")


class MultaItem(BaseModel):
    """Multa/citación/infracción combinada de las fuentes de tránsito (resumen)."""

    fuente: str = Field(..., description="Origen del registro (ANT, AMT, EPMTSD)")
    concepto: str | None = Field(None, description="Descripción o categoría de la multa")
    valor_usd: float | None = None
    estado: str | None = Field(None, description="pendiente, pagada, en_impugnacion, …")
    fecha: str | None = None


class CategoriaMulta(BaseModel):
    """Desglose de citaciones/infracciones por estado (pendientes, pagadas, …)."""

    etiqueta: str
    cantidad: int = 0
    monto_usd: float | None = Field(None, description="None cuando la fuente no informa monto (ANT)")


class MultaDetalle(BaseModel):
    """Detalle por fuente de tránsito: total, pendientes y desglose por categoría."""

    fuente: str = Field(..., description="ANT, AMT o EPMTSD")
    ambito: str = Field(..., description="Cobertura legible: Nacional, Quito, Santo Domingo")
    total_registros: int = 0
    pendientes: int = 0
    total_a_pagar_usd: float | None = None
    categorias: list[CategoriaMulta] = Field(default_factory=list)


class NovedadLegal(BaseModel):
    """Noticia del delito / novedad legal combinada (FGE y futuras fuentes)."""

    fuente: str = Field(..., description="Origen del registro (FGE, …)")
    ndd: str | None = Field(None, description="Número de noticia del delito")
    delito: str | None = None
    fecha: str | None = None
    lugar: str | None = None
    unidad: str | None = None


class ValoresTributarios(BaseModel):
    """Valores tributarios del vehículo (SRI)."""

    fuente: str = "SRI"
    matricula_usd: float | None = None
    total_a_pagar_usd: float | None = None
    url_consulta: str | None = Field(
        None, description="Portal oficial cuando la fuente es consulta_externa"
    )


class VehiculoConsolidadoResponse(BaseModel):
    """Perfil consolidado del vehículo agregado desde todas las fuentes.

    Orientado a la entidad, no al proveedor. Las listas pueden venir vacías
    mientras `estado_fuentes` reporte fuentes `en_proceso`.
    """

    placa: str
    datos_basicos: DatosBasicos = Field(default_factory=DatosBasicos)
    identificacion: Identificacion = Field(default_factory=Identificacion)
    valores_tributarios: ValoresTributarios | None = None
    multas_pendientes: list[MultaItem] = Field(default_factory=list)
    multas_detalle: list[MultaDetalle] = Field(
        default_factory=list, description="Desglose por fuente (ANT/AMT/EPMTSD) con categorías"
    )
    novedades_legales: list[NovedadLegal] = Field(default_factory=list)
    estado_fuentes: list[EstadoFuenteItem] = Field(default_factory=list)

    @property
    def cargando(self) -> bool:
        """True si alguna fuente sigue `en_proceso` (el frontend muestra loader)."""
        return any(f.estado is EstadoFuente.EN_PROCESO for f in self.estado_fuentes)

    @property
    def tiene_pendientes(self) -> bool:
        """True si hay multas, valores tributarios o novedades legales."""
        valor_sri = (
            self.valores_tributarios.total_a_pagar_usd if self.valores_tributarios else None
        )
        return bool(self.multas_pendientes) or bool(self.novedades_legales) or bool(valor_sri)
