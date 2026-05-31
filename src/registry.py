"""Registro central de modelos ORM.

Importar este módulo garantiza que TODAS las clases mapeadas queden registradas en
`Base.metadata`. Es el único punto que Alembic necesita importar (`alembic/env.py`)
para que `--autogenerate` y los `target_metadata` vean todas las tablas.

Tras la mudanza a `src/modules/`, los modelos viven repartidos por dominio; este
archivo es la lista única que hay que actualizar al agregar un modelo nuevo.
"""

from src.core.database import Base  # noqa: F401

# auth
from src.modules.auth.models import Usuario, TransaccionToken  # noqa: F401

# vehiculos
from src.modules.vehiculos.models.vehiculo import Vehiculo  # noqa: F401
from src.modules.vehiculos.models.dueno_historico import DuenoHistorico  # noqa: F401
from src.modules.vehiculos.models.kilometraje_lectura import KilometrajeLectura  # noqa: F401
from src.modules.vehiculos.models.mantenimiento import Mantenimiento  # noqa: F401
from src.modules.vehiculos.models.vehiculo_favorito import VehiculoFavorito  # noqa: F401

# consulta
from src.modules.consulta.models.consulta import Consulta  # noqa: F401
from src.modules.consulta.models.cola_scraping import ColaScraping  # noqa: F401

# marketplace
from src.modules.marketplace.models import (  # noqa: F401
    EnlaceCompartido,
    EstadoModeracion,
    PublicacionInterna,
    PublicacionReferenciada,
)
