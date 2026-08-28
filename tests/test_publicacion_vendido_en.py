"""`vendido_en` (migración 0031): se sella al pasar a `vendida` y se limpia al salir.

La transición de estado la resuelve `_aplicar_transicion_estado` (función casi pura:
toma la publicación y el estado nuevo). No requiere BD.

    python -m unittest tests.test_publicacion_vendido_en -v
"""

import unittest
from datetime import datetime, timezone

from src.modules.marketplace.models import (
    EstadoPublicacion,
    EstadoVerificacion,
    PlanPublicacion,
    PublicacionInterna,
)
from src.modules.marketplace.routers.publicaciones import _aplicar_transicion_estado
from src.modules.marketplace.schemas import PublicacionInternaSalida

AHORA = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)


def _pub(estado: str, vendido_en=None) -> PublicacionInterna:
    return PublicacionInterna(
        id=1,
        usuario_id=1,
        placa="ABC1234",
        precio_usd=9000,
        plan=PlanPublicacion.LIGHT.value,
        estado=estado,
        estado_verificacion=EstadoVerificacion.NO_VERIFICADO.value,
        destacado=False,
        creado_en=AHORA,
        renovada_en=AHORA,
        vendido_en=vendido_en,
    )


class TransicionVendida(unittest.TestCase):
    def test_activa_a_vendida_sella_fecha(self):
        p = _pub(EstadoPublicacion.ACTIVA.value)
        _aplicar_transicion_estado(p, EstadoPublicacion.VENDIDA)
        self.assertEqual(p.estado, "vendida")
        self.assertIsNotNone(p.vendido_en)

    def test_salir_de_vendida_limpia_fecha(self):
        p = _pub(EstadoPublicacion.VENDIDA.value, vendido_en=AHORA)
        _aplicar_transicion_estado(p, EstadoPublicacion.ACTIVA)
        self.assertEqual(p.estado, "activa")
        self.assertIsNone(p.vendido_en)

    def test_vendida_a_vendida_no_pisa_fecha(self):
        p = _pub(EstadoPublicacion.VENDIDA.value, vendido_en=AHORA)
        _aplicar_transicion_estado(p, EstadoPublicacion.VENDIDA)
        self.assertEqual(p.vendido_en, AHORA)

    def test_pausada_no_toca_vendido_en(self):
        p = _pub(EstadoPublicacion.ACTIVA.value)
        _aplicar_transicion_estado(p, EstadoPublicacion.PAUSADA)
        self.assertIsNone(p.vendido_en)

    def test_salida_expone_vendido_en(self):
        p = _pub(EstadoPublicacion.VENDIDA.value, vendido_en=AHORA)
        salida = PublicacionInternaSalida.desde_modelo(p)
        self.assertEqual(salida.vendido_en, AHORA)


if __name__ == "__main__":
    unittest.main()
