"""Schemas Pydantic para los enlaces de compra-venta (Fase 4).

El dueño genera un enlace temporal de solo lectura. El `scope` es opt-in: por
defecto el portador solo ve las características del auto (ofuscadas, vía
`VehiculoSalidaCompartida`); cada flag adicional habilita una sección del
historial privado en la vista compartida (`VehiculoCompartidoSalida`).
"""

from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.ofuscacion import ofuscar_identificador
from src.core.validators import validar_placa
from src.modules.vehiculos.schemas.vehiculo import VehiculoSalidaCompartida
from src.modules.marketplace.models import (
    EstadoModeracion,
    EstadoPublicacion,
    EstadoVerificacion,
    PlanPublicacion,
    PublicacionInterna,
)

# TTL máximo del enlace (regla 10.6 y skill modelo-dominio-vehiculo).
DIAS_VALIDEZ_MAX = 7

# Secciones del historial privado que el scope puede habilitar (opt-in).
SCOPE_PERMITIDO = {"kilometraje", "mantenimientos", "duenos_historico"}


class EnlaceCompartidoCrear(BaseModel):
    dias_validez: int = Field(default=DIAS_VALIDEZ_MAX, ge=1, le=DIAS_VALIDEZ_MAX)
    scope: dict[str, bool] = Field(default_factory=dict)

    @field_validator("scope")
    @classmethod
    def _scope_valido(cls, v: dict[str, bool]) -> dict[str, bool]:
        invalidas = set(v) - SCOPE_PERMITIDO
        if invalidas:
            raise ValueError(
                f"Claves de scope no permitidas: {sorted(invalidas)}. "
                f"Válidas: {sorted(SCOPE_PERMITIDO)}."
            )
        return v


class EnlaceCompartidoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    token: str
    scope: dict[str, bool]
    creado_en: datetime
    fecha_expiracion: datetime


# ──────────────── Vista compartida con historial gateado por scope ────────────────
#
# Cada sección del historial privado solo se incluye si el `scope` del enlace la
# habilita; si no, el campo queda en `None` (se oculta). Las secciones usan schemas
# propios (no los `*Salida` internos) para no filtrar ids internos ni datos de más.

class KilometrajeCompartido(BaseModel):
    """Lectura de kilometraje visible al portador del token (sin ids internos)."""
    kilometros: int
    fecha_lectura: datetime
    nota: str | None


class MantenimientoCompartido(BaseModel):
    """Mantenimiento visible al portador del token (sin ids internos)."""
    tipo: str
    fecha: date
    kilometraje_relacionado: int
    taller: str | None
    costo: Decimal | None


class DuenoCompartido(BaseModel):
    """Tramo de propiedad visible al portador. La cédula del dueño (PII de un
    tercero) se ofusca aunque el scope habilite la sección: solo se muestran los
    primeros dígitos. `hasta=None` ⇒ dueño actual."""
    desde: date
    hasta: date | None
    nombre_dueno: str | None
    cedula_ofuscada: str | None


class VehiculoCompartidoSalida(VehiculoSalidaCompartida):
    """Vista del portador del token: características ofuscadas (heredadas de
    `VehiculoSalidaCompartida`) + secciones del historial habilitadas por el `scope`.

    Es retrocompatible con la respuesta previa: añade tres claves opcionales que
    quedan en `None` cuando el scope no las habilita.
    """
    kilometraje: list[KilometrajeCompartido] | None = None
    mantenimientos: list[MantenimientoCompartido] | None = None
    duenos_historico: list[DuenoCompartido] | None = None

    @classmethod
    def desde_enlace(cls, enlace) -> "VehiculoCompartidoSalida":
        """Construye la vista leyendo `enlace.scope` y `enlace.vehiculo`.

        Las secciones se devuelven ordenadas cronológicamente (ascendente). Solo
        se incluye una sección si su flag de scope es `True`.
        """
        vehiculo = enlace.vehiculo
        scope = enlace.scope or {}

        # Características + identificadores ofuscados (lógica del módulo vehiculos).
        base = VehiculoSalidaCompartida.desde_modelo(vehiculo).model_dump()

        kilometraje = None
        if scope.get("kilometraje"):
            kilometraje = [
                KilometrajeCompartido(
                    kilometros=l.kilometros,
                    fecha_lectura=l.fecha_lectura,
                    nota=l.nota,
                )
                for l in sorted(vehiculo.kilometraje_lecturas, key=lambda x: x.fecha_lectura)
            ]

        mantenimientos = None
        if scope.get("mantenimientos"):
            mantenimientos = [
                MantenimientoCompartido(
                    tipo=m.tipo,
                    fecha=m.fecha,
                    kilometraje_relacionado=m.kilometraje_relacionado,
                    taller=m.taller,
                    costo=m.costo,
                )
                for m in sorted(vehiculo.mantenimientos, key=lambda x: x.fecha)
            ]

        duenos_historico = None
        if scope.get("duenos_historico"):
            duenos_historico = [
                DuenoCompartido(
                    desde=d.desde,
                    hasta=d.hasta,
                    nombre_dueno=d.nombre_dueno,
                    cedula_ofuscada=ofuscar_identificador(d.cedula_dueno, 3),
                )
                for d in sorted(vehiculo.duenos_historico, key=lambda x: x.desde)
            ]

        return cls(
            **base,
            kilometraje=kilometraje,
            mantenimientos=mantenimientos,
            duenos_historico=duenos_historico,
        )


# ════════════════ Publicaciones del marketplace (Pilar 4 — feed mixto) ════════════════
#
# Dos entidades: internas (las publica un usuario sobre su placa, con plan light/premium)
# y referenciadas (anuncios raspados de portales externos). El feed público las mezcla en
# tres niveles. Privacidad §10.6: nunca VIN completo ni nombre del dueño.


class PublicacionInternaCrear(BaseModel):
    """Alta de una publicación. El `plan` premium se cobra en el router (tokens)."""

    placa: str = Field(min_length=6, max_length=10)
    titulo: str | None = Field(default=None, max_length=160)
    descripcion: str | None = Field(default=None, max_length=2000)
    precio_usd: Decimal = Field(gt=0, description="Precio de venta; debe ser > 0")
    plan: PlanPublicacion = PlanPublicacion.LIGHT
    vehiculo_id: int | None = Field(
        default=None,
        description="Vehículo del garage a vincular (habilita detalles premium)",
    )

    @field_validator("placa")
    @classmethod
    def _placa_valida(cls, v: str) -> str:
        return validar_placa(v)


class PublicacionInternaActualizar(BaseModel):
    """Edición parcial. `plan=premium` dispara el cobro de tokens en el router."""

    titulo: str | None = Field(default=None, max_length=160)
    descripcion: str | None = Field(default=None, max_length=2000)
    precio_usd: Decimal | None = Field(default=None, gt=0)
    plan: PlanPublicacion | None = None
    estado: EstadoPublicacion | None = None


class ResumenMantenimientos(BaseModel):
    """Resumen de mantenimientos del vehículo vinculado (argumento de venta premium)."""

    total: int = 0
    ultima_fecha: date | None = None
    ultimo_kilometraje: int | None = None


class PublicacionInternaSalida(BaseModel):
    """Vista pública de una publicación interna. Sin VIN ni nombre del dueño."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    placa: str
    titulo: str | None
    descripcion: str | None
    precio_usd: Decimal
    plan: PlanPublicacion
    estado: EstadoPublicacion
    estado_verificacion: EstadoVerificacion
    destacado: bool
    verificado: bool = False
    # Características derivadas del vehículo vinculado (si lo hay). Nunca VIN.
    marca: str | None = None
    modelo: str | None = None
    anio: int | None = None
    # Argumento premium: solo presente si plan=premium y hay vehículo vinculado.
    mantenimientos: ResumenMantenimientos | None = None
    creado_en: datetime

    @classmethod
    def desde_modelo(cls, p: PublicacionInterna) -> "PublicacionInternaSalida":
        """Deriva características y, si es premium, el resumen de mantenimientos del
        vehículo vinculado (que el router debe cargar con selectinload)."""
        veh = p.vehiculo
        es_premium = p.plan == PlanPublicacion.PREMIUM.value

        mantenimientos: ResumenMantenimientos | None = None
        if es_premium and veh is not None and veh.mantenimientos:
            regs = veh.mantenimientos
            mantenimientos = ResumenMantenimientos(
                total=len(regs),
                ultima_fecha=max(m.fecha for m in regs),
                ultimo_kilometraje=max(m.kilometraje_relacionado for m in regs),
            )

        return cls(
            id=p.id,
            placa=p.placa,
            titulo=p.titulo,
            descripcion=p.descripcion,
            precio_usd=p.precio_usd,
            plan=PlanPublicacion(p.plan),
            estado=EstadoPublicacion(p.estado),
            estado_verificacion=EstadoVerificacion(p.estado_verificacion),
            destacado=p.destacado,
            verificado=p.estado_verificacion == EstadoVerificacion.VERIFICADO.value,
            marca=getattr(veh, "marca", None),
            modelo=getattr(veh, "modelo", None),
            anio=getattr(veh, "anio", None),
            mantenimientos=mantenimientos,
            creado_en=p.creado_en,
        )


# Dominio del anuncio → etiqueta de fuente legible. El primer match por substring
# gana; lo no reconocido cae en "Otro portal" (igual guardamos el host real abajo).
_FUENTES_POR_DOMINIO = {
    "facebook.com": "Facebook Marketplace",
    "fb.com": "Facebook Marketplace",
    "olx.com": "OLX",
    "patiotuerca.com": "PatioTuerca",
    "mercadolibre.com": "Mercado Libre",
    "marketplace.com": "Mercado Libre",  # mercadolibre acorta a varios TLD
}


def _derivar_fuente(url: str) -> str:
    """Deriva la etiqueta de fuente a partir del host de la URL.

    No accede a la red: solo parsea el dominio. Para hosts desconocidos devuelve el
    propio host (sin `www.`), así el feed siempre muestra de dónde viene el anuncio.
    """
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    for dominio, etiqueta in _FUENTES_POR_DOMINIO.items():
        if dominio in host:
            return etiqueta
    return host or "Otro portal"


def _validar_url_externa(v: str) -> str:
    """Exige una URL http(s) con host. No verifica que el anuncio exista (sin red)."""
    v = v.strip()
    partes = urlparse(v)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise ValueError("La URL debe ser un enlace http(s) válido con dominio.")
    return v


class PublicacionReferenciadaCrear(BaseModel):
    """Alta de una referencia: el usuario pega el link y completa los datos a mano.

    No raspamos el portal (decisión 2026-05-30): los campos los teclea el aportante.
    `fuente` se deriva del dominio del link, no se acepta del cliente. Entra en
    moderación `pendiente`.
    """

    url_externa: str = Field(max_length=500)
    marca: str | None = Field(default=None, max_length=80)
    modelo: str | None = Field(default=None, max_length=120)
    anio: int | None = Field(default=None, ge=1900, le=2100)
    precio_usd: Decimal | None = Field(default=None, gt=0)
    imagen_url: str | None = Field(default=None, max_length=2048)
    placa: str | None = Field(default=None, max_length=10)

    @field_validator("url_externa")
    @classmethod
    def _url_valida(cls, v: str) -> str:
        return _validar_url_externa(v)

    @field_validator("placa")
    @classmethod
    def _placa_valida(cls, v: str | None) -> str | None:
        return validar_placa(v) if v else None

    def fuente_derivada(self) -> str:
        return _derivar_fuente(self.url_externa)


class PublicacionReferenciadaActualizar(BaseModel):
    """Edición parcial por el aportante. Cambiar el contenido vuelve a moderación
    `pendiente` (lo decide el router) para evitar bait-and-switch tras aprobar."""

    marca: str | None = Field(default=None, max_length=80)
    modelo: str | None = Field(default=None, max_length=120)
    anio: int | None = Field(default=None, ge=1900, le=2100)
    precio_usd: Decimal | None = Field(default=None, gt=0)
    imagen_url: str | None = Field(default=None, max_length=2048)
    placa: str | None = Field(default=None, max_length=10)
    activa: bool | None = None

    @field_validator("placa")
    @classmethod
    def _placa_valida(cls, v: str | None) -> str | None:
        return validar_placa(v) if v else None


class PublicacionReferenciadaSalida(BaseModel):
    """Vista de un anuncio referenciado de un portal externo."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    placa: str | None
    marca: str | None
    modelo: str | None
    anio: int | None
    precio_usd: Decimal | None
    fuente: str
    url_externa: str
    imagen_url: str | None
    estado_moderacion: EstadoModeracion
    activa: bool
    creado_en: datetime


class ModeracionReferencia(BaseModel):
    """Decisión de un admin sobre una referencia pendiente: aprobarla o rechazarla."""

    decision: EstadoModeracion

    @field_validator("decision")
    @classmethod
    def _decision_terminal(cls, v: EstadoModeracion) -> EstadoModeracion:
        if v == EstadoModeracion.PENDIENTE:
            raise ValueError("La decisión debe ser 'aprobada' o 'rechazada'.")
        return v


class FeedMarketplaceSalida(BaseModel):
    """Feed público en tres niveles: premium destacados, light, y referenciados.

    El frontend pinta cada nivel en su sección (premium arriba, referenciados al pie).
    """

    premium: list[PublicacionInternaSalida] = Field(default_factory=list)
    estandar: list[PublicacionInternaSalida] = Field(default_factory=list)
    referenciadas: list[PublicacionReferenciadaSalida] = Field(default_factory=list)
