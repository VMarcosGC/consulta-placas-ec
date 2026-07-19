"""Schemas Pydantic para los enlaces de compra-venta (Fase 4).

El dueño genera un enlace temporal de solo lectura. El `scope` es opt-in: por
defecto el portador solo ve las características del auto (ofuscadas, vía
`VehiculoSalidaCompartida`); cada flag adicional habilita una sección del
historial privado en la vista compartida (`VehiculoCompartidoSalida`).
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.ofuscacion import ofuscar_identificador
from src.core.validators import validar_placa
from src.modules.vehiculos.schemas.vehiculo import VehiculoSalidaCompartida
from src.modules.marketplace.models import (
    EstadoModeracion,
    EstadoPublicacion,
    EstadoVerificacion,
    FichaPublicacion,
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
    verificado_en: datetime | None = None
    # Características derivadas del vehículo vinculado (si lo hay). Nunca VIN.
    marca: str | None = None
    modelo: str | None = None
    anio: int | None = None
    # Argumento premium: solo presente si plan=premium y hay vehículo vinculado.
    mantenimientos: ResumenMantenimientos | None = None
    # % de completitud de la ficha técnica (None = el vendedor aún no la crea).
    # Señal de transparencia en el feed; el detalle completo vive en
    # GET /marketplace/publicaciones/{id}.
    completitud_ficha: int | None = None
    # URL de la primera foto por `orden` (portada del feed); None si no hay fotos.
    # El router carga `fotos` con selectinload para evitar N+1.
    foto_portada: str | None = None
    creado_en: datetime

    @classmethod
    def desde_modelo(cls, p: PublicacionInterna) -> "PublicacionInternaSalida":
        """Deriva características y, si es premium, el resumen de mantenimientos del
        vehículo vinculado (que el router debe cargar con selectinload)."""
        veh = p.vehiculo
        es_premium = p.plan == PlanPublicacion.PREMIUM.value
        ficha = p.ficha  # el router la carga con selectinload donde hay listados

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
            verificado_en=p.verificado_en,
            marca=getattr(veh, "marca", None),
            modelo=getattr(veh, "modelo", None),
            anio=getattr(veh, "anio", None),
            mantenimientos=mantenimientos,
            completitud_ficha=(
                calcular_completitud_ficha(
                    ficha.motor_suspension, ficha.carroceria, ficha.interiores
                )
                if ficha is not None
                else None
            ),
            # `p.fotos` viene ordenado por `orden` asc (order_by del relationship):
            # la primera es la portada. El router lo carga con selectinload (sin N+1).
            foto_portada=(p.fotos[0].url if p.fotos else None),
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


class VerificacionPublicacion(BaseModel):
    """Decisión de un admin sobre una publicación premium pendiente de verificación.

    Solo acepta los estados terminales `verificado` o `rechazado`; no se puede
    devolver a `pendiente` ni a `no_verificado` desde este endpoint.
    """

    decision: EstadoVerificacion

    @field_validator("decision")
    @classmethod
    def _decision_terminal(cls, v: EstadoVerificacion) -> EstadoVerificacion:
        if v not in (EstadoVerificacion.VERIFICADO, EstadoVerificacion.RECHAZADO):
            raise ValueError("La decisión debe ser 'verificado' o 'rechazado'.")
        return v


# ════════════════ Ficha técnica de la publicación (market de autos) ════════════════
#
# Tres bloques + extras (2026-07-18). Filosofía: sencillo de registrar (todos los
# campos opcionales, catálogos cerrados donde hay valores típicos, `observaciones`
# libre por bloque) y sencillo de consultar (un solo GET público devuelve todo +
# % de completitud). `extra="forbid"` en los bloques: un campo con typo → 422, no
# se guarda basura silenciosa en el JSONB.

# Catálogos (Literal → si llega un valor inválido, el 422 lista las opciones).
Combustible = Literal["gasolina", "diesel", "hibrido", "electrico", "glp"]
Transmision = Literal["manual", "automatica", "cvt", "semiautomatica"]
Traccion = Literal["4x2", "4x4", "awd"]
EstadoComponente = Literal["excelente", "bueno", "regular", "requiere_atencion"]
TipoCarroceria = Literal[
    "sedan", "suv", "hatchback", "camioneta", "coupe", "furgoneta", "bus", "camion",
    "moto", "otro",
]
EstadoPintura = Literal["original", "retoques", "repintado_parcial", "repintado_total"]
MaterialAsientos = Literal["tela", "cuero", "cuerina", "mixto"]


class BloqueMotorSuspension(BaseModel):
    """Bloque 1 — mecánica. Todo opcional: el vendedor llena lo que sabe."""

    model_config = ConfigDict(extra="forbid")

    combustible: Combustible | None = None
    cilindraje_cc: int | None = Field(default=None, ge=49, le=10000)
    transmision: Transmision | None = None
    traccion: Traccion | None = None
    estado_motor: EstadoComponente | None = None
    estado_suspension: EstadoComponente | None = None
    fugas_visibles: bool | None = None
    cambios_recientes: str | None = Field(
        default=None, max_length=500,
        description="Ej.: 'amortiguadores delanteros nuevos (06/2026)'",
    )
    observaciones: str | None = Field(default=None, max_length=1000)


class BloqueCarroceria(BaseModel):
    """Bloque 2 — exterior."""

    model_config = ConfigDict(extra="forbid")

    tipo: TipoCarroceria | None = None
    numero_puertas: int | None = Field(default=None, ge=0, le=6)
    color: str | None = Field(default=None, max_length=40)
    estado_pintura: EstadoPintura | None = None
    choques_reparados: bool | None = None
    oxido_visible: bool | None = None
    estado_general: EstadoComponente | None = None
    observaciones: str | None = Field(default=None, max_length=1000)


class BloqueInteriores(BaseModel):
    """Bloque 3 — interiores."""

    model_config = ConfigDict(extra="forbid")

    material_asientos: MaterialAsientos | None = None
    estado_asientos: EstadoComponente | None = None
    aire_acondicionado: bool | None = Field(
        default=None, description="True = tiene y funciona"
    )
    sistema_audio: str | None = Field(default=None, max_length=120)
    estado_tablero: EstadoComponente | None = None
    observaciones: str | None = Field(default=None, max_length=1000)


class ExtraVehiculo(BaseModel):
    """Un extra del auto: 'láminas de seguridad', 'llantas recién cambiadas', etc."""

    model_config = ConfigDict(extra="forbid")

    nombre: str = Field(min_length=2, max_length=80)
    detalle: str | None = Field(
        default=None, max_length=300,
        description="Ej.: 'juego completo, cambiadas a los 62.000 km (05/2026)'",
    )


# Pares (nombre de bloque, schema) — única lista a tocar si se agrega un bloque.
_BLOQUES_FICHA: list[tuple[str, type[BaseModel]]] = [
    ("motor_suspension", BloqueMotorSuspension),
    ("carroceria", BloqueCarroceria),
    ("interiores", BloqueInteriores),
]


def calcular_completitud_ficha(
    motor_suspension: dict | None,
    carroceria: dict | None,
    interiores: dict | None,
) -> int:
    """% de campos llenos sobre el total de los 3 bloques (extras no cuentan).

    Guía al vendedor ('te falta llenar interiores') y le da al comprador una señal
    de qué tan transparente es el anuncio.
    """
    datos_por_bloque = {
        "motor_suspension": motor_suspension,
        "carroceria": carroceria,
        "interiores": interiores,
    }
    total = 0
    llenos = 0
    for nombre, schema in _BLOQUES_FICHA:
        campos = list(schema.model_fields)
        total += len(campos)
        datos = datos_por_bloque[nombre] or {}
        llenos += sum(1 for c in campos if datos.get(c) is not None)
    return round(100 * llenos / total) if total else 0


class FichaActualizar(BaseModel):
    """Edición parcial de la ficha: solo se tocan los bloques ENVIADOS.

    Semántica por bloque: enviarlo lo REEMPLAZA completo; enviarlo en `null` lo
    borra; no enviarlo lo deja como está (el router usa `model_fields_set`).
    `extras` igual: la lista enviada reemplaza a la anterior.
    """

    motor_suspension: BloqueMotorSuspension | None = None
    carroceria: BloqueCarroceria | None = None
    interiores: BloqueInteriores | None = None
    extras: list[ExtraVehiculo] | None = Field(default=None, max_length=20)


class FichaSalida(BaseModel):
    """Vista de la ficha (misma para dueño y comprador: aquí no hay PII)."""

    motor_suspension: BloqueMotorSuspension | None = None
    carroceria: BloqueCarroceria | None = None
    interiores: BloqueInteriores | None = None
    extras: list[ExtraVehiculo] = Field(default_factory=list)
    completitud: int = Field(description="% de campos llenos de los 3 bloques (0-100)")
    actualizado_en: datetime | None = None

    @classmethod
    def desde_modelo(cls, f: FichaPublicacion | None) -> "FichaSalida | None":
        if f is None:
            return None
        return cls(
            motor_suspension=(
                BloqueMotorSuspension.model_validate(f.motor_suspension)
                if f.motor_suspension else None
            ),
            carroceria=(
                BloqueCarroceria.model_validate(f.carroceria) if f.carroceria else None
            ),
            interiores=(
                BloqueInteriores.model_validate(f.interiores) if f.interiores else None
            ),
            extras=[ExtraVehiculo.model_validate(e) for e in (f.extras or [])],
            completitud=calcular_completitud_ficha(
                f.motor_suspension, f.carroceria, f.interiores
            ),
            actualizado_en=f.actualizado_en,
        )


# ════════════════ Fotos de la publicación (M2 — market de autos) ════════════════
#
# El binario no pasa por el backend: el navegador sube directo a Cloudinary con una
# firma (services/cloudinary.py) y aquí solo se registra/valida la URL de entrega.

# Bloque con el que se agrupa la foto en la galería. `general` = sin bloque específico.
BloqueFoto = Literal["motor_suspension", "carroceria", "interiores", "general"]


class FirmaSubidaSalida(BaseModel):
    """Datos que el navegador necesita para subir directo a Cloudinary (firmado)."""

    cloud_name: str
    api_key: str
    timestamp: int
    signature: str
    folder: str


class FotoRegistrar(BaseModel):
    """Registro de una foto YA subida a Cloudinary: solo se persiste su URL.

    La URL se valida en el router contra NUESTRO cloud (https + res.cloudinary.com +
    cloud_name); aquí solo se acota longitud/forma. `orden` opcional: por defecto la
    foto va al final de la galería.
    """

    url: str = Field(min_length=10, max_length=2048)
    bloque: BloqueFoto | None = None
    orden: int | None = Field(default=None, ge=0)


class FotoReordenar(BaseModel):
    """Nuevo orden de la galería: la lista de `foto_id` en la secuencia deseada.

    Debe contener EXACTAMENTE el conjunto de fotos de la publicación (ni de más ni de
    menos); el router valida la coincidencia y responde 422 si no cuadra.
    """

    orden: list[int] = Field(min_length=1, description="foto_id en el nuevo orden")


class FotoSalida(BaseModel):
    """Vista de una foto de la publicación (sin PII: aquí no hay datos del dueño)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    url: str
    bloque: str | None
    orden: int


class PublicacionDetalleSalida(PublicacionInternaSalida):
    """Detalle público de una publicación: todo lo del feed + ficha técnica + fotos."""

    ficha: FichaSalida | None = None
    fotos: list[FotoSalida] = Field(default_factory=list)

    @classmethod
    def desde_modelo(cls, p: PublicacionInterna) -> "PublicacionDetalleSalida":
        base = PublicacionInternaSalida.desde_modelo(p).model_dump()
        # `p.fotos` viene ordenado por `orden` asc (order_by del relationship).
        return cls(
            **base,
            ficha=FichaSalida.desde_modelo(p.ficha),
            fotos=[FotoSalida.model_validate(f) for f in p.fotos],
        )


class FeedMarketplaceSalida(BaseModel):
    """Feed público en tres niveles: premium destacados, light, y referenciados.

    El frontend pinta cada nivel en su sección (premium arriba, referenciados al pie).
    """

    premium: list[PublicacionInternaSalida] = Field(default_factory=list)
    estandar: list[PublicacionInternaSalida] = Field(default_factory=list)
    referenciadas: list[PublicacionReferenciadaSalida] = Field(default_factory=list)
