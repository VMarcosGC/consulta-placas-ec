"""Pruebas de la renovación / antigüedad de las publicaciones internas (migración 0026).

Decisión de producto (Marcos, 2026-08-27): un anuncio con
`SEMANAS_VIGENCIA_PUBLICACION` semanas sin renovar pierde vigencia → cae al final del
feed y de `/buscar`, y el dueño ve "Renovar" mientras el anuncio siga `activa`. Renovar
(`POST /marketplace/publicaciones/{id}/renovar`) pone `renovada_en = now()` y lo vuelve
a subir. No cobra (§1.0.3) y no toca `creado_en`.

Cubre: los helpers puros, la derivación en `PublicacionInternaSalida`, la degradación en
el feed, y el endpoint de renovación (happy path + los tres 422/404).

No requieren PostgreSQL ni red (mismo patrón que `tests/test_kilometraje_publicacion.py`):
sesión con `Mock`, dependencias de FastAPI sustituidas con `app.dependency_overrides`.

    python -m unittest tests.test_renovacion_publicacion -v
"""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from fastapi.testclient import TestClient

import main
from src.core.database import obtener_sesion
from src.modules.auth.dependencies import usuario_actual
from src.modules.auth.models import Usuario
from src.modules.marketplace.models import (
    EstadoPublicacion,
    EstadoVerificacion,
    PlanPublicacion,
    PublicacionInterna,
)
from src.modules.marketplace.routers.publicaciones import (
    _codificar_cursor,
    _decodificar_cursor,
)
from src.modules.marketplace.schemas import (
    SEMANAS_VIGENCIA_PUBLICACION,
    PublicacionInternaSalida,
    publicacion_vigente,
    semanas_desde_publicacion,
)

AHORA = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)


def _sesion_falsa(resultados_execute):
    sesion = Mock()

    def _resultado(r):
        filas = r if isinstance(r, list) else [r]
        return Mock(
            scalar_one_or_none=Mock(return_value=r),
            all=Mock(return_value=filas),
            scalars=Mock(return_value=Mock(all=Mock(return_value=filas))),
        )

    sesion.execute.side_effect = [_resultado(r) for r in resultados_execute]
    return sesion


def _usuario(id_=7):
    return Usuario(id=id_, email="vendedor@example.com", password_hash="x", nombre="Marcos G.")


def _publicacion(
    *,
    semanas_sin_renovar=0,
    estado=EstadoPublicacion.ACTIVA.value,
    plan=PlanPublicacion.LIGHT.value,
):
    """Publicación interna serializable, con `renovada_en` a N semanas atrás."""
    renovada_en = datetime.now(timezone.utc) - timedelta(weeks=semanas_sin_renovar)
    pub = PublicacionInterna(
        id=10,
        usuario_id=7,
        vendedor_id=3,
        placa="ABC1234",
        titulo="Mazda 3 2016",
        precio_usd=12000,
        estado=estado,
        plan=plan,
        estado_verificacion=EstadoVerificacion.NO_VERIFICADO.value,
        destacado=(plan == PlanPublicacion.PREMIUM.value),
        creado_en=datetime.now(timezone.utc) - timedelta(weeks=semanas_sin_renovar),
        renovada_en=renovada_en,
    )
    pub.ficha = None
    pub.fotos = []
    pub.vehiculo = None
    return pub


class HelpersDeAntiguedadTests(unittest.TestCase):
    def test_semanas_desde_publicacion_cuenta_semanas_completas(self):
        self.assertEqual(semanas_desde_publicacion(datetime.now(timezone.utc)), 0)
        hace_tres = datetime.now(timezone.utc) - timedelta(weeks=3, hours=1)
        self.assertEqual(semanas_desde_publicacion(hace_tres), 3)

    def test_semanas_desde_publicacion_tolera_naive(self):
        naive = (datetime.now(timezone.utc) - timedelta(weeks=2)).replace(tzinfo=None)
        self.assertEqual(semanas_desde_publicacion(naive), 2)

    def test_publicacion_vigente_usa_el_umbral(self):
        self.assertTrue(publicacion_vigente(datetime.now(timezone.utc)))
        justo_en_el_umbral = datetime.now(timezone.utc) - timedelta(
            weeks=SEMANAS_VIGENCIA_PUBLICACION, hours=1
        )
        self.assertFalse(publicacion_vigente(justo_en_el_umbral))


class DerivacionEnLaSalidaTests(unittest.TestCase):
    """`PublicacionInternaSalida.desde_modelo` deriva vigencia y `puede_renovar`."""

    def test_anuncio_fresco_es_vigente_y_no_se_puede_renovar(self):
        salida = PublicacionInternaSalida.desde_modelo(_publicacion(semanas_sin_renovar=0))
        self.assertTrue(salida.vigente)
        self.assertEqual(salida.semanas_publicada, 0)
        self.assertFalse(salida.puede_renovar)

    def test_anuncio_viejo_y_activo_no_es_vigente_y_se_puede_renovar(self):
        salida = PublicacionInternaSalida.desde_modelo(_publicacion(semanas_sin_renovar=5))
        self.assertFalse(salida.vigente)
        self.assertGreaterEqual(salida.semanas_publicada, SEMANAS_VIGENCIA_PUBLICACION)
        self.assertTrue(salida.puede_renovar)

    def test_anuncio_viejo_pero_pausado_no_se_puede_renovar(self):
        salida = PublicacionInternaSalida.desde_modelo(
            _publicacion(semanas_sin_renovar=5, estado=EstadoPublicacion.PAUSADA.value)
        )
        self.assertFalse(salida.vigente)
        self.assertFalse(salida.puede_renovar)  # primero se reactiva

    def test_renovada_en_ausente_cae_a_creado_en_sin_romper(self):
        """Filas anteriores a 0026 o modelos de prueba sin `renovada_en`: no revienta."""
        pub = _publicacion(semanas_sin_renovar=0)
        pub.renovada_en = None
        salida = PublicacionInternaSalida.desde_modelo(pub)
        self.assertTrue(salida.vigente)


class FeedDegradaLasRezagadasTests(unittest.TestCase):
    """En el feed, las publicaciones sin vigencia van al final de su nivel."""

    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_una_light_vieja_queda_despues_de_una_light_nueva(self):
        vieja = _publicacion(semanas_sin_renovar=6)
        vieja.id = 1
        nueva = _publicacion(semanas_sin_renovar=0)
        nueva.id = 2
        # El feed hace 3 queries: [internas activas], [favoritos por placa], [referenciadas].
        # La query de internas ordena por creado_en desc; acá la vieja llega primero para
        # probar que el sort la baja.
        main.app.dependency_overrides[obtener_sesion] = lambda: _sesion_falsa(
            [[vieja, nueva], [], []]
        )

        respuesta = self.cliente.get("/marketplace/feed")

        self.assertEqual(respuesta.status_code, 200)
        estandar = respuesta.json()["estandar"]
        self.assertEqual([p["id"] for p in estandar], [2, 1])
        self.assertTrue(estandar[0]["vigente"])
        self.assertFalse(estandar[1]["vigente"])


class RenovarEndpointTests(unittest.TestCase):
    def setUp(self):
        self.usuario = _usuario()
        main.app.dependency_overrides[usuario_actual] = lambda: self.usuario
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def _con_sesion(self, resultados):
        sesion = _sesion_falsa(resultados)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        return sesion

    def test_renovar_un_anuncio_viejo_y_activo_bumpea_renovada_en(self):
        pub = _publicacion(semanas_sin_renovar=5)
        antes = pub.renovada_en
        sesion = self._con_sesion([pub, pub])  # entrada + recarga para la salida

        respuesta = self.cliente.post("/marketplace/publicaciones/10/renovar")

        self.assertEqual(respuesta.status_code, 200)
        self.assertGreater(pub.renovada_en, antes)
        sesion.commit.assert_called_once()
        cuerpo = respuesta.json()
        self.assertTrue(cuerpo["vigente"])
        self.assertEqual(cuerpo["semanas_publicada"], 0)
        self.assertFalse(cuerpo["puede_renovar"])

    def test_renovar_un_anuncio_todavia_vigente_da_422(self):
        pub = _publicacion(semanas_sin_renovar=1)
        sesion = self._con_sesion([pub])

        respuesta = self.cliente.post("/marketplace/publicaciones/10/renovar")

        self.assertEqual(respuesta.status_code, 422)
        self.assertIn("vigente", respuesta.json()["detail"].lower())
        sesion.commit.assert_not_called()

    def test_renovar_un_anuncio_pausado_da_422(self):
        pub = _publicacion(semanas_sin_renovar=5, estado=EstadoPublicacion.PAUSADA.value)
        sesion = self._con_sesion([pub])

        respuesta = self.cliente.post("/marketplace/publicaciones/10/renovar")

        self.assertEqual(respuesta.status_code, 422)
        self.assertIn("activo", respuesta.json()["detail"].lower())
        sesion.commit.assert_not_called()

    def test_renovar_una_publicacion_ajena_da_404(self):
        self._con_sesion([None])  # _mi_publicacion no la encuentra

        respuesta = self.cliente.post("/marketplace/publicaciones/999/renovar")

        self.assertEqual(respuesta.status_code, 404)

    def test_renovar_sin_sesion_da_401(self):
        main.app.dependency_overrides.pop(usuario_actual, None)
        self._con_sesion([])

        respuesta = self.cliente.post("/marketplace/publicaciones/10/renovar")

        self.assertEqual(respuesta.status_code, 401)


class CursorConVigenciaTests(unittest.TestCase):
    """El cursor keyset de `/buscar` gana la clave `vigente` como nivel de más peso."""

    def test_round_trip_incluye_vigente(self):
        token = _codificar_cursor(False, True, AHORA, 0, 42)
        self.assertEqual(_decodificar_cursor(token), (False, True, AHORA, 0, 42))

    def test_cursor_viejo_sin_v_se_asume_vigente(self):
        import base64
        import json

        crudo = json.dumps(
            {"d": True, "c": AHORA.isoformat(), "f": 0, "i": 7}, separators=(",", ":")
        )
        viejo = base64.urlsafe_b64encode(crudo.encode("utf-8")).decode("ascii")
        self.assertEqual(_decodificar_cursor(viejo), (True, True, AHORA, 0, 7))


if __name__ == "__main__":
    unittest.main()
