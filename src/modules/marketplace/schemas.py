"""Schemas Pydantic para los enlaces de compra-venta (Fase 4).

El dueño genera un enlace temporal de solo lectura. El `scope` es opt-in: por
defecto el portador solo ve las características del auto (ofuscadas, vía
`VehiculoSalidaCompartida`); cada flag adicional habilita una sección del
historial privado en la vista compartida (`VehiculoCompartidoSalida`).
"""

import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from urllib.parse import quote, urlparse

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

from src.core.ofuscacion import ofuscar_identificador
from src.core.validators import validar_placa
from src.modules.vehiculos.schemas.vehiculo import VehiculoSalidaCompartida
from src.modules.marketplace.models import (
    EstadoCita,
    EstadoModeracion,
    EstadoPresencia,
    EstadoPublicacion,
    EstadoVerificacion,
    FichaPublicacion,
    FranjaPresencia,
    PlanPublicacion,
    PublicacionInterna,
    TipoVendedor,
)

# TTL máximo del enlace (regla 10.6 y skill modelo-dominio-vehiculo).
DIAS_VALIDEZ_MAX = 7

# Vigencia de un anuncio: a las N semanas sin renovar cae al final del feed y de la
# búsqueda, y el dueño ve "Renovar" (si sigue activo). Empuja a depurar data vieja sin
# borrar nada (decisión Marcos 2026-08-27). Env-overridable por si el umbral queda corto
# o largo. Es la MISMA constante que usa el router (la importa de acá: una sola fuente).
SEMANAS_VIGENCIA_PUBLICACION = int(os.getenv("PUBLICACION_SEMANAS_VIGENCIA", "3"))


def semanas_desde_publicacion(momento: datetime) -> int:
    """Semanas COMPLETAS desde `momento` hasta ahora (>= 0). 0 = esta semana.

    Tolera `momento` naïve (se asume UTC): en pruebas se arman modelos a mano sin
    pasar por la BD, así que la tz-awareness no está garantizada.
    """
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=timezone.utc)
    dias = (datetime.now(timezone.utc) - momento).days
    return max(0, dias // 7)


def publicacion_vigente(momento: datetime) -> bool:
    """True mientras el anuncio no haya cumplido `SEMANAS_VIGENCIA_PUBLICACION`
    semanas sin renovar. `momento` es `renovada_en` (internas) o `creado_en` (ref.)."""
    return semanas_desde_publicacion(momento) < SEMANAS_VIGENCIA_PUBLICACION


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


# Catálogo CERRADO de ciudades donde puede estar un auto en venta (migración 0023).
#
# Vive en el código y no en una tabla, igual que los catálogos de la ficha técnica
# (`Combustible`, `Transmision`, …): cambia rara vez, lo decide quien despliega, no hay
# nada que auditar y el `Literal` regala el 422 con la lista de opciones. Agregar una
# ciudad después es una línea; limpiar texto libre ya escrito por los vendedores, no.
#
# Los valores van tal como se muestran (no `snake_case` como los catálogos de la ficha):
# `PublicacionReferenciada.ciudad` es texto libre que el aportante copia del anuncio
# original, así que la tarjeta del feed pinta el valor tal cual venga de cualquiera de
# las dos entidades, sin embellecerlo en una rama y no en la otra.
CiudadPublicacion = Literal[
    "Quito",
    "Guayaquil",
    "Cuenca",
    "Ambato",
    "Manta",
    "Loja",
    "Machala",
    "Santo Domingo",
    "Portoviejo",
    "Ibarra",
    "Riobamba",
    "Esmeraldas",
]


class PublicacionInternaCrear(BaseModel):
    """Alta de una publicación. Monetización suspendida (§1.0.3): `premium` es gratis y
    solo marca el anuncio como destacado."""

    placa: str = Field(min_length=6, max_length=10)
    titulo: str | None = Field(default=None, max_length=160)
    descripcion: str | None = Field(default=None, max_length=2000)
    # Dónde está el auto en venta. Opcional: un anuncio sin ciudad se publica igual (y
    # queda en NULL). Se acepta del cliente y NO se deriva de `Vehiculo.ciudad_registro`,
    # que es dónde se matriculó: prellenar el formulario con ese valor para que el
    # vendedor lo CONFIRME es tarea del frontend, no una inferencia silenciosa del backend.
    ciudad: CiudadPublicacion | None = None
    # Recorrido declarado por el vendedor. Opcional: publicar sin kilometraje es válido y
    # NO entra al umbral de activación. Mismos límites que
    # `PublicacionReferenciadaCrear.kilometraje` (0 … 2 000 000 km), para que la tarjeta
    # del feed lea un solo campo con un solo contrato. Fuera de rango → 422 vía `Field`
    # (§10.2), nunca 500. Igual que la ciudad, NO se deriva del garage: prellenar el
    # formulario con la última lectura para que el vendedor la CONFIRME es tarea del
    # frontend; el kilometraje del garage es privado y opt-in (ver `SCOPE_PERMITIDO`).
    kilometraje: int | None = Field(default=None, ge=0, le=2_000_000)
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
    """Edición parcial. Monetización suspendida (§1.0.3): cambiar el `plan` no cobra.

    Para los campos opcionales del auto (`titulo`, `descripcion`, `ciudad`,
    `kilometraje`) el router mira `model_fields_set`: **omitir** el campo = no lo toca;
    enviarlo en **`null`** = lo borra (el vendedor se equivocó al teclear y quiere dejarlo
    en blanco). `precio_usd` no es opcional (`gt=0`), solo se reemplaza.
    """

    titulo: str | None = Field(default=None, max_length=160)
    descripcion: str | None = Field(default=None, max_length=2000)
    # Cambiar o vaciar la ciudad del anuncio (el auto se mudó, o el vendedor se equivocó).
    # `null` explícito la borra; omitir el campo la deja intacta (ver el docstring y
    # `model_fields_set` en el router).
    ciudad: CiudadPublicacion | None = None
    # Corregir o vaciar el recorrido declarado. Misma semántica que la ciudad. Mismos
    # límites que el alta (0 … 2 000 000) → 422 fuera de rango, nunca 500.
    kilometraje: int | None = Field(default=None, ge=0, le=2_000_000)
    precio_usd: Decimal | None = Field(default=None, gt=0)
    plan: PlanPublicacion | None = None
    estado: EstadoPublicacion | None = None


class ResumenMantenimientos(BaseModel):
    """Resumen de mantenimientos del vehículo vinculado (argumento de venta premium)."""

    total: int = 0
    ultima_fecha: date | None = None
    # OJO: este NO es el mismo kilometraje que `PublicacionInternaSalida.kilometraje`, y
    # la duplicación es deliberada (ver la nota de convivencia allá). Aquí:
    # `max(kilometraje_relacionado)` de los mantenimientos del garage = **el odómetro en
    # el último service**, un hecho verificable contra el historial y solo visible en
    # premium. Allá: lo que el vendedor declara hoy para el anuncio. Ninguno sobra.
    ultimo_kilometraje: int | None = None


class SelloMecanica(BaseModel):
    """Sello "revisado por mecánica" de una publicación (migración 0028)."""

    nombre: str
    ciudad: str
    certificado_en: datetime


class PublicacionInternaSalida(BaseModel):
    """Vista pública de una publicación interna. Sin VIN ni nombre del dueño."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    placa: str
    titulo: str | None
    descripcion: str | None
    # Ciudad donde está el auto en venta. Se declara `str | None` y no `CiudadPublicacion`
    # a propósito: el catálogo se impone al ESCRIBIR (422 en el alta y la edición); si
    # algún día se retira una ciudad de la lista, las filas viejas deben poder LEERSE, no
    # convertir un GET público en un 500. De paso queda del mismo tipo que
    # `PublicacionReferenciadaSalida.ciudad`, que es texto libre.
    ciudad: str | None = None
    # Recorrido declarado por el vendedor para este anuncio (migración 0024).
    #
    # ── Por qué hay DOS kilometrajes en este schema y ninguno sobra ──
    # Este campo es «el odómetro HOY, según el vendedor»: un dato declarado, presente en
    # cualquier plan, que el comprador necesita para decidir si abre el anuncio.
    # `mantenimientos.ultimo_kilometraje` (abajo) es «el odómetro en el ÚLTIMO SERVICE»:
    # derivado del garage, verificable contra el historial y solo en premium.
    # Son dos hechos distintos y ambos legítimos: el segundo respalda al primero (si el
    # service de hace 3 meses marcaba 78 000 y el anuncio dice 42 000, hay algo que
    # explicar). Borrar uno "porque se repite" perdería justo esa comparación.
    # Mismo nombre y mismo tipo que `PublicacionReferenciadaSalida.kilometraje`, para que
    # la tarjeta del feed pinte ambas entidades con un solo campo. Sin `ge`/`le` aquí a
    # propósito (igual que la ciudad): el rango se impone al ESCRIBIR; si mañana se baja
    # el tope, las filas viejas deben poder LEERSE, no volver 500 un GET público.
    kilometraje: int | None = None
    precio_usd: Decimal
    plan: PlanPublicacion
    estado: EstadoPublicacion
    # Fecha en que el anuncio pasó a `vendida` (migración 0031). `None` salvo que
    # `estado == vendida`. El frontend arma con esto el "resumen de vendidos".
    vendido_en: datetime | None = None
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
    # Antigüedad del anuncio (migración 0026). `renovada_en` es publicación o última
    # renovación; el frontend pinta "hace N semanas" desde ahí. `vigente=False` = ya
    # cumplió `SEMANAS_VIGENCIA_PUBLICACION` semanas sin renovar → el feed y la
    # búsqueda lo mandan al final. `puede_renovar` = el dueño puede volver a ponerlo
    # al frente (solo si además está `activa`); es data derivada, no expone nada
    # privado, pero el frontend solo muestra el botón en las vistas del dueño.
    renovada_en: datetime
    semanas_publicada: int = 0
    vigente: bool = True
    puede_renovar: bool = False
    # Sello "revisado por mecánica" (migración 0028). `None` = sin sello. Lo activa el
    # vendedor canjeando un código que le dio la mecánica. Es distinto de `verificado`
    # (sello de la plataforma, §10.6): este nombra a la mecánica y la fecha.
    sello_mecanica: "SelloMecanica | None" = None
    # "Me gusta" público = cuántos usuarios tienen esta PLACA en favoritos. No hay tabla
    # nueva: se cuenta sobre `vehiculos_favoritos`. En el feed, más "me gusta" empuja la
    # publicación hacia arriba dentro de su nivel (relevancia). El router pasa el conteo;
    # 0 por defecto (una publicación recién salida, o los tests que no lo calculan).
    total_favoritos: int = 0

    @classmethod
    def desde_modelo(
        cls, p: PublicacionInterna, total_favoritos: int = 0
    ) -> "PublicacionInternaSalida":
        """Deriva características y, si es premium, el resumen de mantenimientos del
        vehículo vinculado (que el router debe cargar con selectinload).

        `total_favoritos` = "me gusta" de esta placa; lo calcula el router en lote
        (una sola query agrupada) y lo pasa acá para no hacer N+1."""
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
            ciudad=p.ciudad,
            kilometraje=p.kilometraje,
            precio_usd=p.precio_usd,
            plan=PlanPublicacion(p.plan),
            estado=EstadoPublicacion(p.estado),
            vendido_en=getattr(p, "vendido_en", None),
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
            # `renovada_en` puede venir None en pruebas (modelos armados a mano sin
            # pasar por la BD, donde el server_default no corre): se cae a `creado_en`.
            renovada_en=(p.renovada_en or p.creado_en),
            semanas_publicada=semanas_desde_publicacion(p.renovada_en or p.creado_en),
            vigente=publicacion_vigente(p.renovada_en or p.creado_en),
            puede_renovar=(
                p.estado == EstadoPublicacion.ACTIVA.value
                and not publicacion_vigente(p.renovada_en or p.creado_en)
            ),
            total_favoritos=total_favoritos,
            sello_mecanica=(
                SelloMecanica(
                    nombre=p.mecanica_nombre,
                    ciudad=p.mecanica_ciudad,
                    certificado_en=p.certificado_mecanica_en,
                )
                if getattr(p, "mecanica_nombre", None)
                and getattr(p, "certificado_mecanica_en", None)
                else None
            ),
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


# Tope de fotos de una referencia externa (M2.8). Menor que el de una publicación propia
# (12): la referencia es un puntero al anuncio original, no el anuncio en sí.
MAX_FOTOS_REFERENCIA = 5


def _validar_fotos_referencia(v: list[str]) -> list[str]:
    """Normaliza la lista de fotos: URLs http(s) válidas, sin vacíos y sin duplicados."""
    limpias: list[str] = []
    for url in v:
        url = (url or "").strip()
        if not url:
            continue
        if len(url) > 2048:
            raise ValueError("La URL de la foto es demasiado larga.")
        _validar_url_externa(url)
        if url not in limpias:
            limpias.append(url)
    if len(limpias) > MAX_FOTOS_REFERENCIA:
        raise ValueError(f"Puedes subir hasta {MAX_FOTOS_REFERENCIA} fotos por referencia.")
    return limpias


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
    # Referencias ricas (M2.8): el aportante copia los detalles del anuncio original.
    descripcion: str | None = Field(default=None, max_length=2000)
    ciudad: str | None = Field(default=None, max_length=80)
    kilometraje: int | None = Field(default=None, ge=0, le=2_000_000)
    fotos: list[str] = Field(default_factory=list, max_length=MAX_FOTOS_REFERENCIA)

    @field_validator("url_externa")
    @classmethod
    def _url_valida(cls, v: str) -> str:
        return _validar_url_externa(v)

    @field_validator("fotos")
    @classmethod
    def _fotos_validas(cls, v: list[str]) -> list[str]:
        return _validar_fotos_referencia(v)

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
    descripcion: str | None = Field(default=None, max_length=2000)
    ciudad: str | None = Field(default=None, max_length=80)
    kilometraje: int | None = Field(default=None, ge=0, le=2_000_000)
    fotos: list[str] | None = Field(default=None, max_length=MAX_FOTOS_REFERENCIA)
    activa: bool | None = None

    @field_validator("placa")
    @classmethod
    def _placa_valida(cls, v: str | None) -> str | None:
        return validar_placa(v) if v else None

    @field_validator("fotos")
    @classmethod
    def _fotos_validas(cls, v: list[str] | None) -> list[str] | None:
        return _validar_fotos_referencia(v) if v is not None else None


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
    descripcion: str | None = None
    ciudad: str | None = None
    kilometraje: int | None = None
    fotos: list[str] = Field(default_factory=list)
    estado_moderacion: EstadoModeracion
    activa: bool
    creado_en: datetime

    # Antigüedad (migración 0026): una referencia externa también envejece. No se
    # "renueva" (la trae un aportante, no el vendedor), pero SÍ cae al final del feed
    # y de la búsqueda al perder vigencia. Se deriva de `creado_en` (no hay
    # `renovada_en`). Mismo par de campos que `PublicacionInternaSalida`, para que la
    # tarjeta del feed los lea igual en las dos entidades.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def semanas_publicada(self) -> int:
        return semanas_desde_publicacion(self.creado_en)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def vigente(self) -> bool:
        return publicacion_vigente(self.creado_en)


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
# "Tipo de vehículo" del filtro del comprador. Va de livianos a pesados: los
# comerciales (volqueta, tanquero, tractor, cabezal, trailer, maquinaria) se sumaron
# el 2026-08-27 a pedido de Marcos. Es un `Literal` en JSONB (bloque `carroceria`),
# así que ampliarlo NO requiere migración; solo que el frontend tenga etiqueta e ícono.
TipoCarroceria = Literal[
    "sedan", "suv", "hatchback", "camioneta", "coupe", "furgoneta", "van",
    "bus", "buseta", "camion", "volqueta", "tanquero", "tractor", "cabezal",
    "trailer", "maquinaria", "moto", "otro",
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
    # ID del vendedor (opaco), SOLO en el detalle: el comprador lo necesita para dejarle
    # una calificación (`/marketplace/vendedores/{id}/calificar`). No es PII — ni teléfono
    # ni nombre; el resto de la identidad del vendedor sigue sin serializarse.
    vendedor_id: int | None = None

    @classmethod
    def desde_modelo(
        cls, p: PublicacionInterna, total_favoritos: int = 0
    ) -> "PublicacionDetalleSalida":
        base = PublicacionInternaSalida.desde_modelo(p, total_favoritos).model_dump()
        # `p.fotos` viene ordenado por `orden` asc (order_by del relationship).
        return cls(
            **base,
            ficha=FichaSalida.desde_modelo(p.ficha),
            fotos=[FotoSalida.model_validate(f) for f in p.fotos],
            vendedor_id=p.vendedor_id,
        )


class FeedMarketplaceSalida(BaseModel):
    """Feed público en tres niveles: premium destacados, light, y referenciados.

    El frontend pinta cada nivel en su sección (premium arriba, referenciados al pie).
    """

    premium: list[PublicacionInternaSalida] = Field(default_factory=list)
    estandar: list[PublicacionInternaSalida] = Field(default_factory=list)
    referenciadas: list[PublicacionReferenciadaSalida] = Field(default_factory=list)


# ════════════ Distribución geográfica (portada: "¿dónde están los autos?") ════════════
#
# Conteo de publicaciones activas por provincia y región, para que la portada muestre
# de un vistazo dónde hay stock y el comprador filtre desde ahí. Se deriva de `ciudad`
# vía `geografia.py` (no hay columna provincia/región). Solo BD propia (§10.2).


class ProvinciaDistribucionSalida(BaseModel):
    provincia: str
    total: int


class RegionDistribucionSalida(BaseModel):
    region: str
    total: int
    provincias: list[ProvinciaDistribucionSalida] = Field(default_factory=list)


class DistribucionGeograficaSalida(BaseModel):
    """`GET /marketplace/distribucion`.

    `total` = todas las publicaciones activas (internas + referencias aprobadas).
    `con_ubicacion` = las que caen en una provincia reconocida (`ciudad` del catálogo
    o alias). `total - con_ubicacion` = sin ubicación clara (no se listan por
    provincia, pero cuentan en el total)."""

    total: int
    con_ubicacion: int
    regiones: list[RegionDistribucionSalida] = Field(default_factory=list)


# ════════════════ Búsqueda del comprador (MC2 — lista plana paginada) ════════════════
#
# A diferencia del feed (3 cubos curados para la portada MC1), la búsqueda devuelve una
# LISTA PLANA ordenada, filtrable y paginada por cursor keyset, que la app futura (MC3,
# reel vertical) reutiliza tal cual. Cada item lleva un discriminador `tipo_publicacion`
# para que el frontend elija la tarjeta (interna vs referenciada). Se reusan los schemas
# de salida existentes → misma garantía de privacidad (ni VIN ni nombre del dueño).


class ItemBusqueda(BaseModel):
    """Un resultado de la búsqueda plana. Solo uno de `interna`/`referenciada` viene
    lleno, según el discriminador `tipo_publicacion`."""

    tipo_publicacion: Literal["interna", "referenciada"]
    interna: PublicacionInternaSalida | None = None
    referenciada: PublicacionReferenciadaSalida | None = None


class ResultadoBusquedaSalida(BaseModel):
    """Página de resultados de `GET /marketplace/buscar`.

    `siguiente_cursor` es un token opaco (base64) que se pasa tal cual en el próximo
    request para traer la siguiente página; `None` cuando ya no hay más resultados.
    """

    items: list[ItemBusqueda] = Field(default_factory=list)
    siguiente_cursor: str | None = None


# ════════════ Vendedor y contacto comprador-vendedor (TASK-001) ════════════
#
# PRIVACIDAD (§9): `telefono` aparece ÚNICAMENTE en el perfil PROPIO del vendedor
# (`VendedorPerfilSalida`, detrás de `usuario_actual`) y en la respuesta del endpoint
# de contacto (`ContactoVendedorSalida`). **Nunca** en los schemas de listado ni de
# detalle de publicación: un teléfono servido en un feed público lo cosechan bots en
# días. La acción explícita del comprador es la barrera contra ese scraping, y de paso
# produce la métrica de contactos (`ContactoRevelado`).
#
# No es monetización: el contacto es libre y gratuito (§1.0.3).

# Caracteres que un humano teclea al escribir un teléfono; todo lo demás se rechaza en
# vez de ignorarse en silencio (un teléfono con letras casi siempre es un error real).
_CARACTERES_TELEFONO = set("0123456789 +-().")
_DIGITOS = set("0123456789")

_AYUDA_TELEFONO = (
    "Ingresa un celular ecuatoriano: 10 dígitos que empiezan con 09 "
    "(ej. 0987654321) o el formato internacional 593 + 9 dígitos "
    "(ej. 593987654321)."
)


def normalizar_telefono_ec(valor: str) -> str:
    """Valida un celular ecuatoriano y lo devuelve en **E.164 sin `+`** (`5939XXXXXXXX`).

    Ese es exactamente el formato que consume `https://wa.me/<numero>`, así que se
    guarda normalizado y el enlace se arma sin transformaciones adicionales.

    Acepta separadores de tecleo (espacios, guiones, paréntesis, `+`) y las dos formas
    acordadas: `09XXXXXXXX` (10 dígitos) y `5939XXXXXXXX` (E.164). Convencionales
    (02…, 07…) quedan FUERA a propósito: el canal de contacto es WhatsApp.

    Lanza `ValueError` (→ 422 en el endpoint) con un mensaje que dice cómo corregirlo.
    """
    texto = (valor or "").strip()
    if not texto:
        raise ValueError(_AYUDA_TELEFONO)
    if any(c not in _CARACTERES_TELEFONO for c in texto):
        raise ValueError(_AYUDA_TELEFONO)

    digitos = "".join(c for c in texto if c in _DIGITOS)

    if len(digitos) == 10 and digitos.startswith("09"):
        return "593" + digitos[1:]
    if len(digitos) == 12 and digitos.startswith("5939"):
        return digitos
    raise ValueError(_AYUDA_TELEFONO)


def armar_whatsapp_url(telefono: str, referencia: str | None = None) -> str:
    """Arma el enlace de WhatsApp con un mensaje prellenado en es-EC, no agresivo.

    `referencia` es el título o la placa del anuncio, para que el vendedor sepa de cuál
    de sus autos le escriben. El comprador puede editar el texto antes de enviarlo: es
    una sugerencia, no un mensaje automático.
    """
    if referencia:
        mensaje = (
            f"Hola, vi tu anuncio de {referencia} en Revisa tu Carro EC "
            "y me interesa. ¿Sigue disponible?"
        )
    else:
        mensaje = (
            "Hola, vi tu anuncio en Revisa tu Carro EC y me interesa. "
            "¿Sigue disponible?"
        )
    return f"https://wa.me/{telefono}?text={quote(mensaje)}"


class VendedorActualizar(BaseModel):
    """Edición parcial del perfil de vendedor (`PATCH /marketplace/vendedor/mi-perfil`).

    Semántica por campo (el router usa `model_fields_set`): omitirlo lo deja intacto.
    Enviar `nombre_publico: null` **borra** el nombre; enviar `telefono: null` retira el
    número (el anuncio deja de poder contactarse: 409).

    El nombre público **no se hereda** del nombre de la cuenta: publicarlo es una decisión
    explícita del vendedor (compuerta M5). Por eso cargar un teléfono sin `nombre_publico`
    —o borrar el nombre teniendo teléfono cargado— responde **422**: los dos salen juntos
    por el endpoint de contacto, así que el número es lo que te vuelve público.
    """

    nombre_publico: str | None = Field(default=None, min_length=2, max_length=120)
    telefono: str | None = Field(default=None, max_length=20)

    @field_validator("telefono")
    @classmethod
    def _telefono_valido(cls, v: str | None) -> str | None:
        return normalizar_telefono_ec(v) if v is not None else None


class VendedorPerfilSalida(BaseModel):
    """Perfil PROPIO del vendedor. Solo lo ve su dueño (`Depends(usuario_actual)`),
    por eso incluye el teléfono tal como lo guardó."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tipo: TipoVendedor
    nombre_publico: str | None
    telefono: str | None
    telefono_verificado: bool
    creado_en: datetime


class ContactoVendedorSalida(BaseModel):
    """Respuesta del endpoint de contacto: el único lugar público con el teléfono."""

    telefono: str
    nombre_publico: str | None
    whatsapp_url: str


# ════════════════ Calificaciones (comprador → vendedor) ════════════════


class CalificacionCrear(BaseModel):
    estrellas: int = Field(ge=1, le=5)
    comentario: str | None = Field(default=None, max_length=1000)
    # Contexto: desde qué anuncio se calificó. Opcional, no cambia la unicidad.
    publicacion_id: int | None = None


class CalificacionSalida(BaseModel):
    """Una calificación pública. El autor se muestra por su primer nombre o
    'Un comprador' — nunca el email ni el id."""

    estrellas: int
    comentario: str | None
    autor: str
    creado_en: datetime


class ResumenCalificaciones(BaseModel):
    """Promedio y conteo. `promedio` es `None` cuando no hay ninguna (línea base: no se
    muestra una nota baja, simplemente no hay nota)."""

    promedio: float | None = None
    total: int = 0


class CalificacionesVendedorSalida(BaseModel):
    resumen: ResumenCalificaciones
    items: list[CalificacionSalida] = Field(default_factory=list)
    # La calificación que dejó ESTE usuario (si hay sesión y ya calificó), para
    # prellenar el formulario. `None` para anónimos o quien aún no calificó.
    mia: CalificacionSalida | None = None


# ════════════════ Sello "revisado por mecánica" (códigos, migración 0028) ════════════════


class CodigosCertificacionCrear(BaseModel):
    """Un admin genera N códigos para una mecánica (la plataforma decide a quién)."""

    mecanica_nombre: str = Field(min_length=2, max_length=120)
    mecanica_ciudad: str = Field(min_length=2, max_length=80)
    cantidad: int = Field(default=1, ge=1, le=50)
    dias_validez: int = Field(default=30, ge=1, le=90)


class CodigoCertificacionSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    codigo: str
    mecanica_nombre: str
    mecanica_ciudad: str
    creado_en: datetime
    expira_en: datetime
    usado_en: datetime | None = None
    usado_publicacion_id: int | None = None


class CertificarConCodigo(BaseModel):
    """El vendedor canjea el código que le dio la mecánica en SU publicación."""

    codigo: str = Field(min_length=4, max_length=24)


# ════════════════ Directorio de servicios automotrices (migración 0029) ════════════════

CategoriaServicio = Literal[
    "mecanica",
    "mecanica_certificada",
    "centro_servicio",
    "lavadero",
    "luces",
    "accesorios",
    "otro",
]


class ServicioCrear(BaseModel):
    """Alta de un negocio. Entra `pendiente`; un admin lo aprueba. `certificado` NO se
    acepta del cliente (solo un admin lo marca)."""

    nombre: str = Field(min_length=2, max_length=120)
    categoria: CategoriaServicio
    provincia: str = Field(min_length=2, max_length=80)
    ciudad: str = Field(min_length=2, max_length=80)
    descripcion: str | None = Field(default=None, max_length=1000)
    telefono: str | None = Field(default=None, max_length=20)
    whatsapp: str | None = Field(default=None, max_length=20)
    direccion: str | None = Field(default=None, max_length=200)
    horario: str | None = Field(default=None, max_length=120)
    url_externa: str | None = Field(default=None, max_length=500)
    # Preferencia operativa que el negocio SÍ declara solo (no es un sello de confianza).
    acepta_agendamiento: bool = False

    @field_validator("provincia")
    @classmethod
    def _provincia_valida(cls, v: str) -> str:
        # Import local para no crear un ciclo (geografia no importa schemas).
        from src.modules.marketplace import geografia

        if v not in geografia.PROVINCIAS:
            raise ValueError(
                f"Provincia no válida. Opciones: {list(geografia.PROVINCIAS)}."
            )
        return v


class ServicioSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    categoria: CategoriaServicio
    provincia: str
    ciudad: str
    descripcion: str | None
    telefono: str | None
    whatsapp: str | None
    direccion: str | None
    horario: str | None
    url_externa: str | None
    certificado: bool
    acepta_agendamiento: bool = False
    estado_moderacion: EstadoModeracion
    activo: bool
    creado_en: datetime

    @field_validator("acepta_agendamiento", mode="before")
    @classmethod
    def _agenda_no_nula(cls, v: object) -> bool:
        # La columna es NOT NULL DEFAULT false; solo un objeto ORM armado a mano (tests)
        # llega con `None` antes del flush. Se normaliza a False.
        return bool(v)


class ModeracionServicio(BaseModel):
    """Decisión de un admin: aprobar o rechazar (terminal). Opcional `certificado`."""

    decision: EstadoModeracion
    certificado: bool | None = None

    @field_validator("decision")
    @classmethod
    def _terminal(cls, v: EstadoModeracion) -> EstadoModeracion:
        if v == EstadoModeracion.PENDIENTE:
            raise ValueError("La decisión debe ser 'aprobada' o 'rechazada'.")
        return v


# ════════════════ Puntos de encuentro seguros (migración 0033) ════════════════
# Un catálogo de lugares curados (admin) donde comprador y vendedor se ven en
# persona. Un vendedor anuncia que va a llevar UNA publicación suya a un punto en
# una fecha/franja; el comprador ve, por punto, qué autos van a estar ahí.

FRANJAS_LEGIBLES: dict[str, str] = {
    "manana": "Mañana",
    "tarde": "Tarde",
    "noche": "Noche",
    "todo_el_dia": "Todo el día",
}


class PuntoEncuentroCrear(BaseModel):
    """Alta de un punto de encuentro. Solo admin."""

    nombre: str = Field(min_length=3, max_length=120)
    ciudad: str = Field(default="Quito", max_length=80)
    sector: str | None = Field(default=None, max_length=120)
    direccion: str = Field(min_length=3, max_length=200)
    referencia: str | None = Field(default=None, max_length=300)
    latitud: Decimal | None = Field(default=None, ge=-90, le=90)
    longitud: Decimal | None = Field(default=None, ge=-180, le=180)
    horario: str | None = Field(default=None, max_length=120)
    tiene_seguridad: bool = False
    notas: str | None = Field(default=None, max_length=500)
    orden: int = 0


class PuntoEncuentroActualizar(BaseModel):
    """Edición parcial de un punto de encuentro. Solo admin."""

    nombre: str | None = Field(default=None, min_length=3, max_length=120)
    sector: str | None = Field(default=None, max_length=120)
    direccion: str | None = Field(default=None, min_length=3, max_length=200)
    referencia: str | None = Field(default=None, max_length=300)
    latitud: Decimal | None = Field(default=None, ge=-90, le=90)
    longitud: Decimal | None = Field(default=None, ge=-180, le=180)
    horario: str | None = Field(default=None, max_length=120)
    tiene_seguridad: bool | None = None
    notas: str | None = Field(default=None, max_length=500)
    activo: bool | None = None
    orden: int | None = None


class PuntoEncuentroSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    ciudad: str
    sector: str | None
    direccion: str
    referencia: str | None
    latitud: Decimal | None
    longitud: Decimal | None
    horario: str | None
    tiene_seguridad: bool
    notas: str | None
    activo: bool
    orden: int
    # Cuántas presencias `anunciada` (fecha >= hoy) tiene este punto ahora mismo.
    # Lo calcula el router en lote; 0 por defecto para no romper construcciones a mano.
    presencias_activas: int = 0


class VehiculoEnPresencia(BaseModel):
    """Resumen del auto anunciado — se lee de la publicación en vivo (no se
    duplica): si el precio cambia o el anuncio se borra, el punto refleja eso."""

    publicacion_id: int
    placa: str
    titulo: str | None
    marca: str | None
    modelo: str | None
    anio: int | None
    precio_usd: Decimal
    foto_portada: str | None


class PresenciaCrear(BaseModel):
    """El vendedor anuncia que va a llevar `publicacion_id` a este punto."""

    publicacion_id: int
    fecha: date
    franja: FranjaPresencia
    nota: str | None = Field(default=None, max_length=300)

    @field_validator("fecha")
    @classmethod
    def _no_en_el_pasado(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("La fecha no puede ser anterior a hoy.")
        return v


class PresenciaActualizar(BaseModel):
    """El vendedor reprograma o cierra su propia presencia."""

    fecha: date | None = None
    franja: FranjaPresencia | None = None
    nota: str | None = Field(default=None, max_length=300)
    estado: EstadoPresencia | None = None

    @field_validator("estado")
    @classmethod
    def _estado_terminal(cls, v: EstadoPresencia | None) -> EstadoPresencia | None:
        if v == EstadoPresencia.ANUNCIADA:
            raise ValueError(
                "No se puede volver a 'anunciada'. Crea una presencia nueva."
            )
        return v

    @field_validator("fecha")
    @classmethod
    def _no_en_el_pasado(cls, v: date | None) -> date | None:
        if v is not None and v < date.today():
            raise ValueError("La fecha no puede ser anterior a hoy.")
        return v


class PresenciaSalida(BaseModel):
    id: int
    punto_id: int
    fecha: date
    franja: FranjaPresencia
    estado: EstadoPresencia
    nota: str | None
    creado_en: datetime
    vehiculo: VehiculoEnPresencia


class PuntoEncuentroDetalleSalida(PuntoEncuentroSalida):
    """Detalle público de un punto: sus datos + la matriz de autos anunciados."""

    presencias: list[PresenciaSalida] = []


class PuntoResumenSalida(BaseModel):
    """Punto mínimo, para colgar de `MiPresenciaSalida` sin anidar todo el detalle."""

    id: int
    nombre: str
    ciudad: str
    sector: str | None


class MiPresenciaSalida(BaseModel):
    """Una presencia propia, con el punto y el auto resumidos (para 'Mis anuncios
    en puntos de encuentro')."""

    id: int
    punto: PuntoResumenSalida
    fecha: date
    franja: FranjaPresencia
    estado: EstadoPresencia
    nota: str | None
    creado_en: datetime
    vehiculo: VehiculoEnPresencia


# ════════════════ Agendamiento de citas para servicios (migración 0034) ════════════════
# La plataforma ofrece agendamiento: el negocio opta (`acepta_agendamiento`), el
# cliente pide una cita y el negocio la confirma / reprograma / rechaza.

MotivoCita = Literal[
    "mantenimiento",
    "revision",
    "diagnostico",
    "lavado",
    "accesorios",
    "otro",
]
FranjaAgenda = Literal["manana", "tarde", "noche", "todo_el_dia"]

MOTIVO_CITA_LEGIBLE: dict[str, str] = {
    "mantenimiento": "Mantenimiento",
    "revision": "Revisión general",
    "diagnostico": "Diagnóstico / falla",
    "lavado": "Lavado / detailing",
    "accesorios": "Accesorios / instalación",
    "otro": "Otro",
}


class CitaCrear(BaseModel):
    """El cliente pide una cita en un servicio que acepta agendamiento."""

    nombre_contacto: str = Field(min_length=2, max_length=120)
    telefono_contacto: str | None = Field(default=None, max_length=20)
    vehiculo: str | None = Field(default=None, max_length=120)
    motivo: MotivoCita
    fecha: date
    franja: FranjaAgenda
    nota: str | None = Field(default=None, max_length=400)

    @field_validator("fecha")
    @classmethod
    def _no_en_el_pasado(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("La fecha no puede ser anterior a hoy.")
        return v


class CitaActualizar(BaseModel):
    """El cliente reprograma su cita (mientras esté `solicitada`), la cancela, o
    acepta la contraoferta del negocio (`estado: confirmada`)."""

    fecha: date | None = None
    franja: FranjaAgenda | None = None
    nota: str | None = Field(default=None, max_length=400)
    estado: Literal["cancelada", "confirmada"] | None = None

    @field_validator("fecha")
    @classmethod
    def _no_en_el_pasado(cls, v: date | None) -> date | None:
        if v is not None and v < date.today():
            raise ValueError("La fecha no puede ser anterior a hoy.")
        return v


class RespuestaNegocio(BaseModel):
    """El negocio responde una cita solicitada."""

    decision: Literal["confirmada", "rechazada", "reprogramada", "cumplida"]
    respuesta: str | None = Field(default=None, max_length=400)
    fecha_propuesta: date | None = None
    franja_propuesta: FranjaAgenda | None = None

    @field_validator("fecha_propuesta")
    @classmethod
    def _propuesta_no_en_el_pasado(cls, v: date | None) -> date | None:
        if v is not None and v < date.today():
            raise ValueError("La fecha propuesta no puede ser anterior a hoy.")
        return v


class CitaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    servicio_id: int
    servicio_nombre: str | None = None
    servicio_ciudad: str | None = None
    nombre_contacto: str
    telefono_contacto: str | None
    vehiculo: str | None
    motivo: MotivoCita
    fecha: date
    franja: FranjaAgenda
    nota: str | None
    estado: EstadoCita
    respuesta_negocio: str | None
    fecha_propuesta: date | None
    franja_propuesta: FranjaAgenda | None
    creado_en: datetime
