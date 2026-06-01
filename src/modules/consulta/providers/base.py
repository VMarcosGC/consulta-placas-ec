"""Contrato normalizado de la capa de proveedores vehiculares.

`ResultadoVehicular` es el shape ÚNICO que todo proveedor devuelve, sin importar la API
externa subyacente. Así el resto del backend (consolidador, desbloqueos) no sabe ni le importa
qué proveedor respondió. `ProveedorVehicular` es la interfaz que cada proveedor implementa.

Reglas (AGENTS.md §6 y scraping-respetuoso):
- Un proveedor NUNCA propaga excepciones: captura todo y devuelve `estado="error"`.
- `estado` cacheable: `consulta_realizada` / `sin_resultados` (ver services/proveedor.py).
- `capacidades`: códigos del catálogo (`productos_consulta`) que el proveedor PUEDE entregar.
  Se consulta SIN llamar al proveedor (para pintar las tarjetas de desbloqueo en el preview
  gratis). Un proveedor sin credenciales declara `capacidades` vacío.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from decimal import Decimal

# Estados del resultado del proveedor (alineados con el contrato §6).
ESTADO_OK = "consulta_realizada"
ESTADO_SIN_DATOS = "sin_resultados"
ESTADO_SIN_CREDENCIALES = "sin_credenciales"
ESTADO_ERROR = "error"


@dataclass
class ResultadoVehicular:
    """Resultado normalizado de un proveedor para una placa.

    Los campos sensibles (`titular`, `chasis`, `motor`, `vin`) vienen en CLARO desde el
    proveedor; el consolidador decide cómo exponerlos (ofuscados/validados) según el
    desbloqueo del usuario. NUNCA se exponen crudos en una respuesta pública.
    """

    placa: str
    proveedor: str
    estado: str = ESTADO_SIN_DATOS
    # Características (pueden enriquecer o confirmar lo que ya trae el scraping público).
    marca: str | None = None
    modelo: str | None = None
    anio: int | None = None
    color: str | None = None
    tipo: str | None = None
    clase: str | None = None
    servicio: str | None = None
    # Identificadores sensibles (en claro; se ofuscan aguas abajo).
    chasis: str | None = None
    motor: str | None = None
    vin: str | None = None
    # Titular (PII): nombre crudo. Se valida/ofusca aguas abajo, NUNCA se expone crudo.
    titular: str | None = None
    # Transaccional (informativo; las multas "oficiales" siguen viniendo del scraping).
    multas: list[dict] = field(default_factory=list)
    valores_pendientes: float | None = None
    # Auditoría comercial.
    costo_estimado_usd: Decimal | None = None
    # Respuesta cruda del proveedor (para depurar/auditar; no se expone al usuario final).
    raw_response: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serializa a dict (cacheable). `Decimal` → str para JSON."""
        d = asdict(self)
        if self.costo_estimado_usd is not None:
            d["costo_estimado_usd"] = str(self.costo_estimado_usd)
        return d

    @property
    def tiene_identificadores(self) -> bool:
        return bool(self.vin or self.motor or self.chasis)

    @property
    def tiene_titular(self) -> bool:
        return bool(self.titular)


class ProveedorVehicular(ABC):
    """Interfaz de un proveedor de datos vehiculares.

    `nombre` identifica al proveedor (auditoría). `capacidades` son los códigos de producto
    que puede entregar (vacío si no está configurado/credenciado). `consultar` devuelve el
    contrato normalizado y NUNCA lanza (captura todo → estado de error).
    """

    nombre: str = "base"

    @property
    def capacidades(self) -> frozenset[str]:
        """Códigos del catálogo que este proveedor puede entregar (sin llamarlo)."""
        return frozenset()

    @abstractmethod
    async def consultar(self, placa: str) -> ResultadoVehicular:
        """Consulta el proveedor para una placa y devuelve el contrato normalizado."""
        raise NotImplementedError
