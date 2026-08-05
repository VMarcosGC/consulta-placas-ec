import enum
from datetime import datetime
from decimal import Decimal
from sqlalchemy import (
    String, DateTime, BigInteger, Integer, Boolean, Numeric, ForeignKey,
    CheckConstraint, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


# ── Enumeraciones del marketplace interno ───────────────────────────────────
# Se guardan como String en la BD (no enum nativo de PG) para evolucionar sin
# migraciones de tipo; la validación de valores vive en los schemas Pydantic.

class PlanPublicacion(str, enum.Enum):
    """Nivel de una publicación interna."""

    LIGHT = "light"      # gratis: aparece en el feed, sin destacar
    PREMIUM = "premium"  # pagado con tokens: destacado + detalles + verificable


class EstadoPublicacion(str, enum.Enum):
    """Ciclo de vida de una publicación interna.

    `BORRADOR` (M2.8) es el estado inicial: el vendedor arma el anuncio con calma
    (ficha y fotos) y NADIE más lo ve — ni el feed ni la URL pública (404). Solo pasa a
    `ACTIVA` cuando su ficha llega al umbral (`UMBRAL_FICHA_PUBLICACION`).

    La columna es `String` en BD, así que sumar un valor NO requiere migración de tipo.
    Transición permitida hacia afuera del borrador: **solo** `borrador → activa` (si se
    permitiera `borrador → pausada → activa`, el anuncio llegaría al feed sin pasar por el
    umbral ni por el cobro). Tampoco se vuelve a `borrador`: para ocultar está `pausada`.
    Ver `_aplicar_transicion_estado` en `routers/publicaciones.py`.
    """

    BORRADOR = "borrador"
    ACTIVA = "activa"
    PAUSADA = "pausada"
    VENDIDA = "vendida"


class EstadoVerificacion(str, enum.Enum):
    """Estado de verificación 'Verificado por la plataforma' (solo premium).

    Flujo: una publicación premium nace `pendiente`; un admin la marca `verificado`
    (muestra el sello) o `rechazado` (sin sello, no vuelve a la cola). `no_verificado`
    es el estado de las publicaciones light (no aplican a verificación).
    """

    NO_VERIFICADO = "no_verificado"
    PENDIENTE = "pendiente"
    VERIFICADO = "verificado"
    RECHAZADO = "rechazado"


class EstadoModeracion(str, enum.Enum):
    """Estado de moderación de una referencia aportada por un usuario.

    Las referencias las trae el propio usuario (un link de Facebook Marketplace u
    otro portal), así que entran como `pendiente` y un administrador las aprueba
    antes de que aparezcan en el feed público. `rechazada` las descarta sin borrar.
    """

    PENDIENTE = "pendiente"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"


class TipoVendedor(str, enum.Enum):
    """Naturaleza del vendedor detrás de una publicación (AGENTS §1.0.4).

    En la **etapa 1** (ciclo vigente) solo se usa `PARTICULAR`: un vendedor es una
    persona natural y su relación con la cuenta es 1:1 (la impone la UK de
    `vendedores.usuario_id`). `PATIO` queda declarado desde ya porque la etapa 2 solo
    tiene que levantar esa UK y empezar a usar el valor: un cambio aditivo, sin
    reescribir el modelo ni migrar cuatro tablas con datos reales.

    Se guarda como String (no enum nativo de PG), igual que el resto de enums de este
    módulo: sumar un valor no requiere migración de tipo.
    """

    PARTICULAR = "particular"
    PATIO = "patio"


class Vendedor(Base):
    """Identidad COMERCIAL de quien vende, separada de la cuenta de autenticación.

    Por qué existe una tabla aparte y el teléfono no vive en `Usuario` (§1.0.4):
    - `Usuario` es identidad de cuenta (email, contraseña, saldo). El teléfono de
      contacto es un dato **comercial**, público bajo pedido, que puede cambiar sin
      que cambie la cuenta y que en la etapa 2 pertenecerá al patio, no a la persona.
    - Insertar la capa ahora, con 2 publicaciones internas y 3 referencias en
      producción, cuesta un backfill trivial; hacerlo cuando existan patios costaría
      migrar cuatro tablas con datos reales.

    `telefono` se guarda **normalizado a E.164 sin `+`** (ej. `593987654321`), que es
    justo el formato que consume `https://wa.me/<numero>`; la normalización la hace
    `normalizar_telefono_ec` en schemas.py. NULL = el vendedor todavía no lo cargó
    (el endpoint de contacto responde 409, no 500).

    `telefono_verificado` queda reservado: la verificación por SMS/OTP está fuera del
    alcance de este ciclo, así que hoy siempre es `False`.
    """

    __tablename__ = "vendedores"
    # UK nombrada igual que en la migración 0021 (evita drift al diffear el esquema).
    # Es la que impone el 1:1 cuenta ↔ vendedor de la etapa 1; la etapa 2 la levanta.
    __table_args__ = (
        UniqueConstraint("usuario_id", name="uq_vendedores_usuario_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
    )
    tipo: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=TipoVendedor.PARTICULAR.value,
        default=TipoVendedor.PARTICULAR.value,
    )
    # Nombre con el que el comprador lo ve. Nullable como `Usuario.nombre`: si la cuenta
    # no tiene nombre, se prefiere NULL ("no informado") antes que inventar un valor.
    nombre_publico: Mapped[str | None] = mapped_column(String(120), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(20), nullable=True)
    telefono_verificado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relación unidireccional hacia la cuenta: `Usuario` (módulo auth) no se toca.
    usuario: Mapped["Usuario"] = relationship("Usuario")  # noqa: F821


class ContactoRevelado(Base):
    """Registro ANÓNIMO de cada vez que se reveló el contacto de un vendedor.

    Es una métrica de producto ("cuántos compradores pidieron el número de este
    anuncio"), no un registro de vigilancia (§9): **no se guarda ni IP, ni
    user-agent, ni el usuario que pidió el contacto**. El contacto es público y
    gratuito (§1.0.3), así que ni siquiera hay sesión que registrar.

    Apunta a UNA publicación: interna o referenciada. El CheckConstraint impone que
    haya exactamente una de las dos, para que no existan filas huérfanas ni ambiguas.
    """

    __tablename__ = "contactos_revelados"
    __table_args__ = (
        CheckConstraint(
            "(publicacion_interna_id IS NOT NULL)::int "
            "+ (publicacion_referenciada_id IS NOT NULL)::int = 1",
            name="ck_contactos_revelados_exactamente_una_publicacion",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    publicacion_interna_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("publicaciones_internas.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    publicacion_referenciada_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("publicaciones_referenciadas.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EnlaceCompartido(Base):
    """Enlace temporal de solo lectura sobre un vehículo, para mostrarle el
    historial a un comprador interesado sin que necesite cuenta (Fase 4).

    Reglas (CLAUDE.md 10.6):
    - `token` es único (UK) y se genera aleatorio; es la única credencial de acceso.
    - `fecha_expiracion` impone un TTL máximo de 7 días desde la creación.
    - `scope` (JSONB) es opt-in: enumera qué secciones del historial puede ver el
      portador (default mínimo = solo características del auto, ofuscadas).
    """

    __tablename__ = "enlaces_compartidos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    vehiculo_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("vehiculos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    fecha_expiracion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    vehiculo: Mapped["Vehiculo"] = relationship(  # noqa: F821
        back_populates="enlaces_compartidos"
    )


class PublicacionInterna(Base):
    """Publicación de venta creada por un usuario de la plataforma (Pilar 4).

    A diferencia de las referenciadas (raspadas de portales externos), estas las
    publica un usuario sobre una placa suya. El `plan` define el nivel:
    - `light` (gratis): aparece en el feed sin destacar.
    - `premium` (pagado con tokens): `destacado=True`, muestra mantenimientos/consumos
      derivados del garage del usuario y puede llevar la etiqueta
      "Verificado por la plataforma" (`estado_verificacion=verificado`).

    Se relaciona con el Usuario (dueño de la publicación) y con la Placa. El vínculo
    a `vehiculo_id` es OPCIONAL: cuando el usuario tiene esa placa registrada en su
    garage, permite derivar los detalles premium (mantenimientos). Si la borra, el
    FK queda en NULL pero la publicación sobrevive (la placa basta como identidad).
    """

    __tablename__ = "publicaciones_internas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("usuarios.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Identidad comercial que vende (TASK-001). Nullable: las publicaciones anteriores a
    # la migración 0021 quedaron backfilleadas, pero una publicación puede existir sin
    # perfil de vendedor cargado. `usuario_id` NO se reemplaza: sigue siendo la cuenta
    # dueña del registro (permisos), mientras `vendedor_id` es a quién contacta el
    # comprador. En la etapa 2 (patios) ambos dejan de coincidir.
    vendedor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("vendedores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vehiculo_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("vehiculos.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    placa: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    titulo: Mapped[str | None] = mapped_column(String(160), nullable=True)
    descripcion: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    precio_usd: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    plan: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=PlanPublicacion.LIGHT.value,
        default=PlanPublicacion.LIGHT.value,
    )
    estado: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=EstadoPublicacion.ACTIVA.value,
        default=EstadoPublicacion.ACTIVA.value,
    )
    estado_verificacion: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=EstadoVerificacion.NO_VERIFICADO.value,
        default=EstadoVerificacion.NO_VERIFICADO.value,
    )
    # Momento en que un admin marcó la publicación como verificada (auditoría).
    # NULL mientras no esté verificada (pendiente/rechazado/no_verificado).
    verificado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Momento del débito del plan premium (M2.8). Hace el cobro IDEMPOTENTE por dato:
    # solo se debita si es NULL. Sin esta marca, caminos como
    # `light → premium (borrador) → activa` cobraban dos veces.
    # NULL = todavía no se cobró (o es light, o es un premium anterior a M2.8 que ya
    # se cobró al crearse: como ya está activa, nunca vuelve a pasar por el cobro).
    premium_cobrado_en: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    destacado: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Vínculo opcional al vehículo del garage (one-directional: no toca el modelo
    # Vehiculo). El router usa selectinload sobre `vehiculo.mantenimientos` para
    # derivar los detalles premium sin N+1.
    vehiculo: Mapped["Vehiculo | None"] = relationship("Vehiculo")  # noqa: F821

    # Vendedor al que contacta el comprador (unidireccional). NUNCA se serializa en el
    # feed ni en el detalle: su teléfono solo sale por el endpoint de contacto.
    vendedor: Mapped["Vendedor | None"] = relationship("Vendedor")

    # Ficha técnica 1:1 (bloques motor/suspensión, carrocería, interiores + extras).
    # Se borra junto con la publicación (delete-orphan).
    ficha: Mapped["FichaPublicacion | None"] = relationship(
        "FichaPublicacion",
        back_populates="publicacion",
        uselist=False,
        cascade="all, delete-orphan",
    )

    # Fotos de la publicación (M2). Ordenadas por `orden` ascendente: la primera es
    # la portada del feed. Se borran junto con la publicación (delete-orphan).
    fotos: Mapped[list["FotoPublicacion"]] = relationship(
        "FotoPublicacion",
        back_populates="publicacion",
        cascade="all, delete-orphan",
        order_by="FotoPublicacion.orden.asc()",
    )


class FichaPublicacion(Base):
    """Ficha técnica de una publicación interna: el detalle transparente del auto.

    Tres bloques de datos + extras (decisión 2026-07-18, arranque del market de autos):
    1. `motor_suspension` — mecánica: combustible, cilindraje, transmisión, tracción,
       estado de motor y suspensión.
    2. `carroceria` — exterior: tipo, puertas, color, pintura, choques reparados, óxido.
    3. `interiores` — asientos, A/C, audio, tablero.
    `extras` — lista libre de equipamiento adicional (láminas de seguridad, llantas
    recién cambiadas, etc.).

    Los bloques se guardan como JSONB **validados por los schemas Pydantic**
    (`BloqueMotorSuspension`, `BloqueCarroceria`, `BloqueInteriores` en schemas.py,
    con `extra="forbid"`): la BD no exige el shape, el contrato lo exige la API.
    Esto permite evolucionar campos de la ficha sin migración. Bloque en NULL =
    el vendedor aún no lo llena (la completitud se deriva en el schema de salida).
    """

    __tablename__ = "fichas_publicacion"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    publicacion_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("publicaciones_internas.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    motor_suspension: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    carroceria: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    interiores: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    extras: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    publicacion: Mapped["PublicacionInterna"] = relationship(
        "PublicacionInterna", back_populates="ficha"
    )


class FotoPublicacion(Base):
    """Foto de una publicación interna (M2 — fotos del market de autos).

    El binario NO vive aquí: se sube directo desde el navegador a Cloudinary con una
    firma que genera el backend; esta tabla solo guarda la `url` de entrega resultante
    (decisión 2026-07-19). La `url` se valida contra NUESTRO cloud antes de persistir
    (ver services/cloudinary.py y el router).

    `bloque` es opcional y agrupa la foto con un bloque de la ficha
    (`motor_suspension|carroceria|interiores|general`); su catálogo lo valida Pydantic,
    no la BD (mismo criterio que la ficha). `orden` fija la posición en la galería: la
    primera (orden más bajo) es la portada del feed.
    """

    __tablename__ = "fotos_publicacion"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    publicacion_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("publicaciones_internas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 2048: las URLs de CDN traen transformaciones y versiones firmadas y superan los
    # 500 con facilidad (mismo criterio que PublicacionReferenciada.imagen_url).
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # Catálogo validado en Pydantic: motor_suspension|carroceria|interiores|general.
    bloque: Mapped[str | None] = mapped_column(String(20), nullable=True)
    orden: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    publicacion: Mapped["PublicacionInterna"] = relationship(
        "PublicacionInterna", back_populates="fotos"
    )


class PublicacionReferenciada(Base):
    """Anuncio de venta de un portal externo, REFERENCIADO en nuestro feed.

    No alojamos el anuncio: solo guardamos los datos mínimos que el aportante
    teclea y un enlace a su origen (`url_externa`, p. ej. Facebook Marketplace).
    Decisión 2026-05-30: NO se raspa el portal (FB exige login y bloquea bots);
    es el usuario quien trae el link y completa marca/modelo/precio. El link puebla
    nuestra BD de forma barata y siempre devuelve el tráfico al anuncio original.

    `usuario_id` es el aportante (NULL si algún día se siembra por otra vía). Como
    las trae el usuario, entran en `estado_moderacion=pendiente` y un admin las
    aprueba antes de que el feed las muestre. `url_externa` es única (dedup: el
    mismo anuncio no entra dos veces). La placa puede ser desconocida.
    """

    __tablename__ = "publicaciones_referenciadas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Vendedor del anuncio referenciado (TASK-001). `usuario_id` SE CONSERVA porque aquí
    # documenta al **aportante**, que no siempre es quien vende: son dos roles distintos
    # y borrar uno perdería información.
    vendedor_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("vendedores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    placa: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    marca: Mapped[str | None] = mapped_column(String(80), nullable=True)
    modelo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    anio: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    precio_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    fuente: Mapped[str] = mapped_column(String(80), nullable=False)
    url_externa: Mapped[str] = mapped_column(
        String(500), nullable=False, unique=True, index=True
    )
    # 2048: las URLs de imagen de CDNs (Facebook fbcdn, etc.) traen muchos parámetros
    # firmados y superan los 500 con facilidad.
    imagen_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    # ── Referencias ricas (M2.8, migración 0019) ──
    # El aportante puede copiar los detalles del anuncio original (FB/OLX) para que la
    # tarjeta sea útil sin salir del feed. Sigue siendo dato NO verificado.
    descripcion: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    ciudad: Mapped[str | None] = mapped_column(String(80), nullable=True)
    kilometraje: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Lista de URLs (máx. 5, validado en Pydantic). JSONB para no crear otra tabla por
    # algo que siempre se lee entero y nunca se consulta por elemento.
    fotos: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb"), default=list
    )
    estado_moderacion: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        server_default=EstadoModeracion.PENDIENTE.value,
        default=EstadoModeracion.PENDIENTE.value,
        index=True,
    )
    activa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
