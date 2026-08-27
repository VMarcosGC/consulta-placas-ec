"""Pruebas de la ciudad de las publicaciones internas (migración 0023).

`publicaciones_referenciadas` ya tenía `ciudad`; las internas no, así que un comprador
veía dónde está un auto copiado de OLX pero no uno publicado en la plataforma. Aquí se
cubre el ciclo completo del campo: alta, catálogo cerrado, ausencia, edición y salida
pública (feed y detalle).

No requieren PostgreSQL ni red: la sesión se aísla con `Mock` y las dependencias de
FastAPI se sustituyen con `app.dependency_overrides` (mismo patrón que
`tests/test_contacto_vendedor.py`). Los modelos usan JSONB, así que SQLite no serviría.

Se usa `unittest` de la stdlib (el repo no tiene pytest y no se agrega una dependencia
por esto, §4):

    python -m unittest tests.test_ciudad_publicacion -v
"""

import unittest
from datetime import datetime, timezone
from typing import get_args
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
    Vendedor,
)
from src.modules.marketplace.schemas import (
    CiudadPublicacion,
    PublicacionInternaSalida,
)


# Las 12 acordadas al abrir el catálogo. Se listan aquí a mano (no derivadas de
# `CiudadPublicacion`) para que agregar una ciudad sea una decisión consciente: si el
# catálogo cambia sin querer, esta prueba lo dice.
CIUDADES_ESPERADAS = (
    "Quito", "Guayaquil", "Cuenca", "Ambato", "Manta", "Loja", "Machala",
    "Santo Domingo", "Portoviejo", "Ibarra", "Riobamba", "Esmeraldas",
)


def _sesion_falsa(resultados_execute):
    """Sesión mockeada: cada `execute()` devuelve el siguiente valor de la lista.

    Cada resultado se expone por las dos vías que usan los endpoints:
    `scalar_one_or_none()` (lecturas de una fila) y `scalars().all()` (listados). Un
    resultado que sea lista solo tiene sentido por la segunda.
    """
    sesion = Mock()

    def _resultado(r):
        return Mock(
            scalar_one_or_none=Mock(return_value=r),
            scalars=Mock(return_value=Mock(all=Mock(return_value=r if isinstance(r, list) else [r]))),
        )

    sesion.execute.side_effect = [_resultado(r) for r in resultados_execute]

    def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1
        if getattr(obj, "creado_en", None) is None:
            obj.creado_en = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)

    sesion.refresh.side_effect = _refresh
    return sesion


def _usuario(id_=7):
    return Usuario(id=id_, email="vendedor@example.com", password_hash="x", nombre="Marcos G.")


def _publicacion(ciudad=None, estado=EstadoPublicacion.BORRADOR.value):
    """Publicación interna mínima pero serializable por `PublicacionInternaSalida`."""
    return PublicacionInterna(
        id=10,
        usuario_id=7,
        vendedor_id=3,
        placa="ABC1234",
        titulo="Mazda 3 2016",
        ciudad=ciudad,
        precio_usd=12000,
        estado=estado,
        plan=PlanPublicacion.LIGHT.value,
        estado_verificacion=EstadoVerificacion.NO_VERIFICADO.value,
        destacado=False,
        creado_en=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
    )


class CatalogoCiudadesTests(unittest.TestCase):
    """El catálogo vive en el CÓDIGO (un `Literal`), no en una tabla de la BD."""

    def test_contiene_exactamente_las_doce_acordadas(self):
        self.assertEqual(get_args(CiudadPublicacion), CIUDADES_ESPERADAS)

    def test_los_valores_van_listos_para_mostrar(self):
        """Sin `snake_case`: `PublicacionReferenciada.ciudad` es texto libre, así que la
        tarjeta del feed pinta ambos campos tal cual, sin embellecer uno y el otro no."""
        for ciudad in get_args(CiudadPublicacion):
            with self.subTest(ciudad=ciudad):
                self.assertEqual(ciudad, ciudad.strip())
                self.assertTrue(ciudad[0].isupper())


class AltaConCiudadTests(unittest.TestCase):
    """`POST /marketplace/publicaciones` — la ciudad se acepta del cliente y se persiste."""

    def setUp(self):
        self.usuario = _usuario()
        main.app.dependency_overrides[usuario_actual] = lambda: self.usuario
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def _con_sesion(self, creada):
        """El alta ejecuta 2 consultas: el perfil de vendedor y la recarga de la salida."""
        sesion = _sesion_falsa([None, creada])

        def _flush():
            for llamada in sesion.add.call_args_list:
                obj = llamada.args[0]
                if isinstance(obj, Vendedor) and obj.id is None:
                    obj.id = 3

        sesion.flush.side_effect = _flush
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        return sesion

    def _publicacion_agregada(self, sesion):
        return next(
            ll.args[0]
            for ll in sesion.add.call_args_list
            if isinstance(ll.args[0], PublicacionInterna)
        )

    def test_ciudad_del_catalogo_se_persiste_y_sale_en_la_respuesta(self):
        sesion = self._con_sesion(_publicacion(ciudad="Cuenca"))

        respuesta = self.cliente.post(
            "/marketplace/publicaciones",
            json={"placa": "ABC1234", "precio_usd": 12000, "ciudad": "Cuenca"},
        )

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.json()["ciudad"], "Cuenca")
        self.assertEqual(self._publicacion_agregada(sesion).ciudad, "Cuenca")

    def test_ciudad_con_espacio_del_catalogo_se_acepta(self):
        """`Santo Domingo` lleva espacio: se guarda tal cual, sin normalizar."""
        sesion = self._con_sesion(_publicacion(ciudad="Santo Domingo"))

        respuesta = self.cliente.post(
            "/marketplace/publicaciones",
            json={"placa": "ABC1234", "precio_usd": 12000, "ciudad": "Santo Domingo"},
        )

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(self._publicacion_agregada(sesion).ciudad, "Santo Domingo")

    def test_ciudad_fuera_del_catalogo_devuelve_422_sin_tocar_la_bd(self):
        """Contrato §10.2: validación → 422, nunca 500. Lo da el `Literal` gratis."""
        sesion = self._con_sesion(_publicacion())

        respuesta = self.cliente.post(
            "/marketplace/publicaciones",
            json={"placa": "ABC1234", "precio_usd": 12000, "ciudad": "Tulcán"},
        )

        self.assertEqual(respuesta.status_code, 422)
        sesion.add.assert_not_called()
        sesion.commit.assert_not_called()

    def test_ciudad_con_otra_capitalizacion_tambien_es_422(self):
        """El catálogo es exacto: no hay normalización silenciosa de mayúsculas."""
        sesion = self._con_sesion(_publicacion())

        respuesta = self.cliente.post(
            "/marketplace/publicaciones",
            json={"placa": "ABC1234", "precio_usd": 12000, "ciudad": "quito"},
        )

        self.assertEqual(respuesta.status_code, 422)
        sesion.commit.assert_not_called()

    def test_ciudad_omitida_queda_en_null_y_el_alta_funciona_igual(self):
        """Sin backfill ni derivación: NULL significa 'el vendedor no la indicó'."""
        sesion = self._con_sesion(_publicacion(ciudad=None))

        respuesta = self.cliente.post(
            "/marketplace/publicaciones",
            json={"placa": "ABC1234", "precio_usd": 12000},
        )

        self.assertEqual(respuesta.status_code, 201)
        self.assertIsNone(respuesta.json()["ciudad"])
        self.assertIsNone(self._publicacion_agregada(sesion).ciudad)


class EdicionCiudadTests(unittest.TestCase):
    """`PATCH /marketplace/publicaciones/{id}` — el vendedor corrige o muda la ciudad."""

    def setUp(self):
        self.usuario = _usuario()
        main.app.dependency_overrides[usuario_actual] = lambda: self.usuario
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def _con_sesion(self, pub):
        # El PATCH resuelve la publicación al entrar y la recarga para la salida.
        sesion = _sesion_falsa([pub, pub])
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        return sesion

    def test_cambiar_la_ciudad_la_actualiza_en_el_modelo_y_en_la_salida(self):
        pub = _publicacion(ciudad="Quito", estado=EstadoPublicacion.ACTIVA.value)
        sesion = self._con_sesion(pub)

        respuesta = self.cliente.patch(
            "/marketplace/publicaciones/10", json={"ciudad": "Manta"}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(pub.ciudad, "Manta")
        self.assertEqual(respuesta.json()["ciudad"], "Manta")
        sesion.commit.assert_called_once()

    def test_ciudad_fuera_del_catalogo_en_la_edicion_devuelve_422(self):
        pub = _publicacion(ciudad="Quito", estado=EstadoPublicacion.ACTIVA.value)
        sesion = self._con_sesion(pub)

        respuesta = self.cliente.patch(
            "/marketplace/publicaciones/10", json={"ciudad": "Latacunga"}
        )

        self.assertEqual(respuesta.status_code, 422)
        self.assertEqual(pub.ciudad, "Quito")  # intacta
        sesion.commit.assert_not_called()

    def test_no_enviar_ciudad_deja_la_anterior_intacta(self):
        """Omitir un campo = no tocarlo (se mira `model_fields_set` en el router)."""
        pub = _publicacion(ciudad="Ibarra", estado=EstadoPublicacion.ACTIVA.value)
        self._con_sesion(pub)

        respuesta = self.cliente.patch(
            "/marketplace/publicaciones/10", json={"titulo": "Mazda 3 2016 full"}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(pub.ciudad, "Ibarra")
        self.assertEqual(respuesta.json()["ciudad"], "Ibarra")

    def test_enviar_ciudad_null_la_vacia(self):
        """`null` EXPLÍCITO borra la ciudad (M2.11): el vendedor la eligió por error y la
        quiere dejar en blanco. Distinto de omitir el campo (test de arriba)."""
        pub = _publicacion(ciudad="Ibarra", estado=EstadoPublicacion.ACTIVA.value)
        sesion = self._con_sesion(pub)

        respuesta = self.cliente.patch(
            "/marketplace/publicaciones/10", json={"ciudad": None}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNone(pub.ciudad)
        self.assertIsNone(respuesta.json()["ciudad"])
        sesion.commit.assert_called_once()


class CiudadEnLasVistasPublicasTests(unittest.TestCase):
    """La ciudad tiene que llegar al comprador: feed, detalle y búsqueda."""

    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def _con_sesion(self, resultados):
        main.app.dependency_overrides[obtener_sesion] = lambda: _sesion_falsa(resultados)

    def test_el_feed_publico_expone_la_ciudad(self):
        pub = _publicacion(ciudad="Guayaquil", estado=EstadoPublicacion.ACTIVA.value)
        self._con_sesion([[pub], []])  # internas activas, referenciadas

        respuesta = self.cliente.get("/marketplace/feed")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["estandar"][0]["ciudad"], "Guayaquil")

    def test_el_detalle_publico_expone_la_ciudad(self):
        pub = _publicacion(ciudad="Loja", estado=EstadoPublicacion.ACTIVA.value)
        self._con_sesion([pub])

        respuesta = self.cliente.get("/marketplace/publicaciones/10")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["ciudad"], "Loja")

    def test_una_ciudad_fuera_del_catalogo_se_lee_sin_romper(self):
        """La salida es `str | None` a propósito: si mañana se retira una ciudad del
        catálogo, las filas viejas deben poder LEERSE. Un GET público no puede volverse
        500 por un cambio de catálogo (§10.2)."""
        pub = _publicacion(ciudad="Tena", estado=EstadoPublicacion.ACTIVA.value)
        salida = PublicacionInternaSalida.desde_modelo(pub)
        self.assertEqual(salida.ciudad, "Tena")

    def test_el_item_de_busqueda_reusa_el_schema_con_ciudad(self):
        """`GET /marketplace/buscar` no filtra por ciudad (fuera de alcance), pero sus
        items son `PublicacionInternaSalida`, así que ya la traen."""
        self.assertIn("ciudad", PublicacionInternaSalida.model_fields)


if __name__ == "__main__":
    unittest.main()
