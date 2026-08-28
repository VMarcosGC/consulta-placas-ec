"""'Me gusta' público = conteo de favoritos por placa, y su efecto en el feed.

No hay tabla nueva: el "me gusta" de una publicación es cuántos usuarios tienen su
PLACA en `vehiculos_favoritos`. En el feed, más "me gusta" empuja la publicación hacia
arriba dentro de su nivel (relevancia), antes de la vigencia.

Sin PostgreSQL: sesión con `Mock` (mismo patrón que el resto de tests del market).

    python -m unittest tests.test_favoritos_relevancia -v
"""

import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from fastapi.testclient import TestClient

import main
from src.core.database import obtener_sesion
from src.modules.marketplace.models import (
    EstadoPublicacion,
    EstadoVerificacion,
    PlanPublicacion,
    PublicacionInterna,
)
from src.modules.marketplace.schemas import PublicacionInternaSalida


def _resultado(r):
    filas = r if isinstance(r, list) else [r]
    return Mock(
        scalar_one_or_none=Mock(return_value=r),
        all=Mock(return_value=filas),
        scalars=Mock(return_value=Mock(all=Mock(return_value=filas))),
    )


def _sesion(*resultados):
    s = Mock()
    s.execute.side_effect = [_resultado(r) for r in resultados]
    return s


def _pub(id_, placa, *, semanas=0):
    p = PublicacionInterna(
        id=id_,
        usuario_id=1,
        placa=placa,
        titulo=f"Auto {id_}",
        precio_usd=10000,
        estado=EstadoPublicacion.ACTIVA.value,
        plan=PlanPublicacion.LIGHT.value,
        estado_verificacion=EstadoVerificacion.NO_VERIFICADO.value,
        destacado=False,
        creado_en=datetime(2026, 8, 1, tzinfo=timezone.utc),
        renovada_en=datetime.now(timezone.utc),
    )
    p.ficha = None
    p.fotos = []
    p.vehiculo = None
    return p


class SalidaExponeMeGustaTests(unittest.TestCase):
    def test_desde_modelo_toma_el_conteo_que_le_pasan(self):
        s = PublicacionInternaSalida.desde_modelo(_pub(1, "ABC1234"), 7)
        self.assertEqual(s.total_favoritos, 7)

    def test_por_defecto_es_cero(self):
        s = PublicacionInternaSalida.desde_modelo(_pub(1, "ABC1234"))
        self.assertEqual(s.total_favoritos, 0)


class FeedOrdenaPorMeGustaTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_la_publicacion_con_mas_me_gusta_va_arriba(self):
        poca = _pub(1, "AAA1111")
        mucha = _pub(2, "BBB2222")
        # feed: [internas], [favoritos (placa, conteo)], [referenciadas]
        main.app.dependency_overrides[obtener_sesion] = lambda: _sesion(
            [poca, mucha], [("AAA1111", 1), ("BBB2222", 9)], []
        )

        r = self.cliente.get("/marketplace/feed")

        self.assertEqual(r.status_code, 200)
        estandar = r.json()["estandar"]
        self.assertEqual([p["id"] for p in estandar], [2, 1])
        self.assertEqual(estandar[0]["total_favoritos"], 9)
        self.assertEqual(estandar[1]["total_favoritos"], 1)

    def test_sin_favoritos_el_feed_no_se_rompe(self):
        main.app.dependency_overrides[obtener_sesion] = lambda: _sesion(
            [_pub(1, "AAA1111")], [], []
        )
        r = self.cliente.get("/marketplace/feed")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["estandar"][0]["total_favoritos"], 0)


if __name__ == "__main__":
    unittest.main()
