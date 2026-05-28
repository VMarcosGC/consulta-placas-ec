"""Schemas Pydantic del Vehículo con tres niveles de visibilidad.

Niveles:
  - Completo:   datos sin ofuscar. Solo para el dueño autenticado.
  - Compartido: ofuscado pero útil. VIN/motor/chasis muestran solo los primeros
                3 caracteres + país de origen del VIN.
  - Publico:    datos mínimos (placa, marca, modelo, color, año). Sin VIN/motor/chasis.

`from_attributes=True` permite que FastAPI los devuelva pasándole directamente
una instancia del modelo SQLAlchemy.
"""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator

from utils.validators import validar_placa, validar_vin
from utils.ofuscacion import ofuscar_vin, ofuscar_identificador, decodificar_origen_vin


# ─────────────────────────── Entrada ───────────────────────────

class VehiculoCrear(BaseModel):
    placa: str = Field(min_length=6, max_length=10)
    vin: str | None = Field(default=None, min_length=17, max_length=17)
    numero_motor: str | None = Field(default=None, max_length=50)
    numero_chasis: str | None = Field(default=None, max_length=50)
    marca: str | None = Field(default=None, max_length=100)
    modelo: str | None = Field(default=None, max_length=100)
    anio: int | None = Field(default=None, ge=1900, le=2100)
    color: str | None = Field(default=None, max_length=50)
    transmision: str | None = Field(default=None, max_length=30)
    tipo_motor: str | None = Field(default=None, max_length=50)
    ciudad_registro: str | None = Field(default=None, max_length=100)

    @field_validator("placa")
    @classmethod
    def _placa_valida(cls, v: str) -> str:
        return validar_placa(v)

    @field_validator("vin")
    @classmethod
    def _vin_valido(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validar_vin(v)


class VehiculoActualizar(BaseModel):
    """Campos opcionales para PATCH/PUT parcial. La placa no se cambia."""
    vin: str | None = Field(default=None, min_length=17, max_length=17)
    numero_motor: str | None = Field(default=None, max_length=50)
    numero_chasis: str | None = Field(default=None, max_length=50)
    marca: str | None = Field(default=None, max_length=100)
    modelo: str | None = Field(default=None, max_length=100)
    anio: int | None = Field(default=None, ge=1900, le=2100)
    color: str | None = Field(default=None, max_length=50)
    transmision: str | None = Field(default=None, max_length=30)
    tipo_motor: str | None = Field(default=None, max_length=50)
    ciudad_registro: str | None = Field(default=None, max_length=100)

    @field_validator("vin")
    @classmethod
    def _vin_valido(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validar_vin(v)


# ─────────────────────────── Salida ───────────────────────────

class _VehiculoBase(BaseModel):
    """Atributos comunes a todas las vistas (no sensibles)."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    placa: str
    marca: str | None
    modelo: str | None
    anio: int | None
    color: str | None
    transmision: str | None
    tipo_motor: str | None
    ciudad_registro: str | None
    creado_en: datetime


class IdentificadorOfuscado(BaseModel):
    """Wrapper para mostrar un identificador ofuscado con metadatos opcionales."""
    valor_mostrado: str | None
    pais: str | None = None
    descripcion: str | None = None
    nivel: str


class VehiculoSalidaCompleta(_VehiculoBase):
    """Vista del dueño autenticado: todo visible."""
    vin: str | None
    numero_motor: str | None
    numero_chasis: str | None
    actualizado_en: datetime


class VehiculoSalidaCompartida(_VehiculoBase):
    """Vista para comprador con token: VIN/motor/chasis ofuscados a `origen`."""
    vin: IdentificadorOfuscado
    numero_motor: IdentificadorOfuscado
    numero_chasis: IdentificadorOfuscado

    @classmethod
    def desde_modelo(cls, vehiculo) -> "VehiculoSalidaCompartida":
        """Construye la vista compartida desde una instancia del modelo Vehiculo."""
        return cls(
            id=vehiculo.id,
            placa=vehiculo.placa,
            marca=vehiculo.marca,
            modelo=vehiculo.modelo,
            anio=vehiculo.anio,
            color=vehiculo.color,
            transmision=vehiculo.transmision,
            tipo_motor=vehiculo.tipo_motor,
            ciudad_registro=vehiculo.ciudad_registro,
            creado_en=vehiculo.creado_en,
            vin=IdentificadorOfuscado(**ofuscar_vin(vehiculo.vin, nivel="origen")),
            numero_motor=IdentificadorOfuscado(
                valor_mostrado=ofuscar_identificador(vehiculo.numero_motor, 3),
                nivel="origen",
            ),
            numero_chasis=IdentificadorOfuscado(
                valor_mostrado=ofuscar_identificador(vehiculo.numero_chasis, 3),
                pais=decodificar_origen_vin(vehiculo.numero_chasis)["pais"],
                descripcion=decodificar_origen_vin(vehiculo.numero_chasis)["descripcion"],
                nivel="origen",
            ),
        )


class VehiculoSalidaPublica(_VehiculoBase):
    """Vista mínima: sin VIN/motor/chasis. Para listados anónimos o resúmenes."""
    pass
