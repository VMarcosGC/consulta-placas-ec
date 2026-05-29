"""Schemas Pydantic para los enlaces de compra-venta (Fase 4).

El dueño genera un enlace temporal de solo lectura. El `scope` es opt-in: por
defecto el portador solo ve las características del auto (ofuscadas, vía
`VehiculoSalidaCompartida`); cada flag adicional habilita una sección del
historial privado en la vista compartida (`VehiculoCompartidoSalida`).
"""

from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.ofuscacion import ofuscar_identificador
from src.modules.vehiculos.schemas.vehiculo import VehiculoSalidaCompartida

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
