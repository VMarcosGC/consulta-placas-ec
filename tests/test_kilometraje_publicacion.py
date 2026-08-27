"""Pruebas del kilometraje de las publicaciones internas (migración 0024).

`publicaciones_referenciadas` ya tenía `kilometraje`; las internas no, así que el
comprador veía el recorrido de un auto copiado de OLX pero no el de uno publicado aquí.
Aquí se cubre el ciclo completo del campo: alta, rango, ausencia, edición y salida
pública (feed, detalle y búsqueda), más la **convivencia** con el otro kilometraje que ya
exponía el schema (`ResumenMantenimientos.ultimo_kilometraje`), que son hechos distintos.

No requieren PostgreSQL ni red: la sesión se aísla con `Mock` y las dependencias de
FastAPI se sustituyen con `app.dependency_overrides` (mismo patrón que
`tests/test_ciudad_publicacion.py`). Los modelos usan JSONB, así que SQLite no serviría.

Se usa `unittest` de la stdlib (el repo no tiene pytest y no se agrega una dependencia
por esto, §4):

    python -m unittest tests.test_kilometraje_publicacion -v
"""

import unittest
from datetime import date, datetime, timezone
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
    PublicacionInternaCrear,
    PublicacionInternaSalida,
    PublicacionReferenciadaCrear,
)


# Tope declarado en los `Field` de ambos schemas. Se escribe a mano (no derivado) para
# que cambiar el límite sea una decisión consciente y esta prueba lo diga.
KILOMETRAJE_MAXIMO = 2_000_000


def _sesion_falsa(resultados_execute):
    """Sesión mockeada: cada `execute()` devuelve el siguiente valor de la lista.

    Cada resultado se expone por las dos vías que usan los endpoints:
    `scalar_one_or_none()` (lecturas de una fila) y `scalars().all()` (listados).
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


def _publicacion(kilometraje=None, estado=EstadoPublicacion.BORRADOR.value,
                 plan=PlanPublicacion.LIGHT.value, vehiculo=None):
    """Publicación interna mínima pero serializable por `PublicacionInternaSalida`."""
    pub = PublicacionInterna(
        id=10,
        usuario_id=7,
        vendedor_id=3,
        placa="ABC1234",
        titulo="Mazda 3 2016",
        ciudad="Quito",
        kilometraje=kilometraje,
        precio_usd=12000,
        estado=estado,
        plan=plan,
        estado_verificacion=EstadoVerificacion.NO_VERIFICADO.value,
        destacado=False,
        creado_en=datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc),
    )
    if vehiculo is not None:
        pub.vehiculo = vehiculo
    return pub


class RangoDelKilometrajeTests(unittest.TestCase):
    """El rango se declara en el schema (`Field`), no en la BD: el 422 sale gratis."""

    @staticmethod
    def _restricciones(schema):
        """`[('Ge', 0), ('Le', 2000000)]` — los `annotated_types` que puso el `Field`."""
        campo = schema.model_fields["kilometraje"]
        return [
            (type(m).__name__, getattr(m, "ge", getattr(m, "le", None)))
            for m in campo.metadata
        ]

    def test_los_limites_son_los_esperados(self):
        self.assertEqual(
            self._restricciones(PublicacionInternaCrear),
            [("Ge", 0), ("Le", KILOMETRAJE_MAXIMO)],
        )
        self.assertIsNone(PublicacionInternaCrear.model_fields["kilometraje"].default)

    def test_los_limites_son_los_mismos_que_en_la_referenciada(self):
        """Mismo nombre y mismo contrato en ambas entidades, para que la tarjeta del feed
        lea un solo campo y no necesite dos ramas (misma regla que la ciudad)."""
        self.assertEqual(
            self._restricciones(PublicacionInternaCrear),
            self._restricciones(PublicacionReferenciadaCrear),
        )


class AltaConKilometrajeTests(unittest.TestCase):
    """`POST /marketplace/publicaciones` — se acepta del cliente y se persiste."""

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

    def test_kilometraje_se_persiste_y_sale_en_la_respuesta(self):
        sesion = self._con_sesion(_publicacion(kilometraje=87_500))

        respuesta = self.cliente.post(
            "/marketplace/publicaciones",
            json={"placa": "ABC1234", "precio_usd": 12000, "kilometraje": 87500},
        )

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.json()["kilometraje"], 87500)
        self.assertEqual(self._publicacion_agregada(sesion).kilometraje, 87_500)

    def test_cero_kilometros_es_valido_y_no_se_confunde_con_ausente(self):
        """Un 0 km (auto nuevo) es un dato declarado; NULL es "no lo declaró"."""
        sesion = self._con_sesion(_publicacion(kilometraje=0))

        respuesta = self.cliente.post(
            "/marketplace/publicaciones",
            json={"placa": "ABC1234", "precio_usd": 12000, "kilometraje": 0},
        )

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.json()["kilometraje"], 0)
        self.assertEqual(self._publicacion_agregada(sesion).kilometraje, 0)

    def test_kilometraje_negativo_devuelve_422_sin_tocar_la_bd(self):
        """Contrato §10.2: validación → 422, nunca 500. Lo da el `Field` gratis."""
        sesion = self._con_sesion(_publicacion())

        respuesta = self.cliente.post(
            "/marketplace/publicaciones",
            json={"placa": "ABC1234", "precio_usd": 12000, "kilometraje": -1},
        )

        self.assertEqual(respuesta.status_code, 422)
        sesion.add.assert_not_called()
        sesion.commit.assert_not_called()

    def test_kilometraje_por_encima_del_tope_devuelve_422(self):
        sesion = self._con_sesion(_publicacion())

        respuesta = self.cliente.post(
            "/marketplace/publicaciones",
            json={
                "placa": "ABC1234",
                "precio_usd": 12000,
                "kilometraje": KILOMETRAJE_MAXIMO + 1,
            },
        )

        self.assertEqual(respuesta.status_code, 422)
        sesion.commit.assert_not_called()

    def test_el_tope_exacto_se_acepta(self):
        """`le` es inclusivo: el límite es válido, el siguiente no."""
        self._con_sesion(_publicacion(kilometraje=KILOMETRAJE_MAXIMO))

        respuesta = self.cliente.post(
            "/marketplace/publicaciones",
            json={"placa": "ABC1234", "precio_usd": 12000, "kilometraje": KILOMETRAJE_MAXIMO},
        )

        self.assertEqual(respuesta.status_code, 201)

    def test_kilometraje_omitido_queda_en_null_y_el_alta_funciona_igual(self):
        """No es obligatorio para publicar: sin backfill ni derivación del garage."""
        sesion = self._con_sesion(_publicacion(kilometraje=None))

        respuesta = self.cliente.post(
            "/marketplace/publicaciones",
            json={"placa": "ABC1234", "precio_usd": 12000},
        )

        self.assertEqual(respuesta.status_code, 201)
        self.assertIsNone(respuesta.json()["kilometraje"])
        self.assertIsNone(self._publicacion_agregada(sesion).kilometraje)


class EdicionKilometrajeTests(unittest.TestCase):
    """`PATCH /marketplace/publicaciones/{id}` — el auto sigue rodando mientras se vende."""

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

    def test_actualizar_el_kilometraje_lo_cambia_en_el_modelo_y_en_la_salida(self):
        pub = _publicacion(kilometraje=87_500, estado=EstadoPublicacion.ACTIVA.value)
        sesion = self._con_sesion(pub)

        respuesta = self.cliente.patch(
            "/marketplace/publicaciones/10", json={"kilometraje": 91_200}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(pub.kilometraje, 91_200)
        self.assertEqual(respuesta.json()["kilometraje"], 91_200)
        sesion.commit.assert_called_once()

    def test_registrar_el_kilometraje_que_faltaba_tambien_funciona(self):
        """Publicar sin kilometraje y completarlo después es un camino válido."""
        pub = _publicacion(kilometraje=None, estado=EstadoPublicacion.ACTIVA.value)
        self._con_sesion(pub)

        respuesta = self.cliente.patch(
            "/marketplace/publicaciones/10", json={"kilometraje": 45_000}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(pub.kilometraje, 45_000)

    def test_kilometraje_fuera_de_rango_en_la_edicion_devuelve_422(self):
        pub = _publicacion(kilometraje=87_500, estado=EstadoPublicacion.ACTIVA.value)
        sesion = self._con_sesion(pub)

        respuesta = self.cliente.patch(
            "/marketplace/publicaciones/10", json={"kilometraje": -5}
        )

        self.assertEqual(respuesta.status_code, 422)
        self.assertEqual(pub.kilometraje, 87_500)  # intacto
        sesion.commit.assert_not_called()

    def test_no_enviar_kilometraje_deja_el_anterior_intacto(self):
        """Omitir un campo = no tocarlo (el router mira `model_fields_set`)."""
        pub = _publicacion(kilometraje=87_500, estado=EstadoPublicacion.ACTIVA.value)
        self._con_sesion(pub)

        respuesta = self.cliente.patch(
            "/marketplace/publicaciones/10", json={"titulo": "Mazda 3 2016 full"}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(pub.kilometraje, 87_500)
        self.assertEqual(respuesta.json()["kilometraje"], 87_500)

    def test_enviar_kilometraje_null_lo_vacia(self):
        """`null` EXPLÍCITO borra el recorrido (M2.11): el vendedor lo tecleó mal y lo
        quiere dejar en blanco. Distinto de omitir el campo (test de arriba)."""
        pub = _publicacion(kilometraje=87_500, estado=EstadoPublicacion.ACTIVA.value)
        sesion = self._con_sesion(pub)

        respuesta = self.cliente.patch(
            "/marketplace/publicaciones/10", json={"kilometraje": None}
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNone(pub.kilometraje)
        self.assertIsNone(respuesta.json()["kilometraje"])
        sesion.commit.assert_called_once()


class KilometrajeEnLasVistasPublicasTests(unittest.TestCase):
    """Tiene que llegar al comprador: feed, detalle y búsqueda."""

    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def _con_sesion(self, resultados):
        main.app.dependency_overrides[obtener_sesion] = lambda: _sesion_falsa(resultados)

    def test_el_feed_publico_expone_el_kilometraje(self):
        pub = _publicacion(kilometraje=87_500, estado=EstadoPublicacion.ACTIVA.value)
        self._con_sesion([[pub], []])  # internas activas, referenciadas

        respuesta = self.cliente.get("/marketplace/feed")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["estandar"][0]["kilometraje"], 87_500)

    def test_el_detalle_publico_expone_el_kilometraje(self):
        pub = _publicacion(kilometraje=87_500, estado=EstadoPublicacion.ACTIVA.value)
        self._con_sesion([pub])

        respuesta = self.cliente.get("/marketplace/publicaciones/10")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json()["kilometraje"], 87_500)

    def test_una_publicacion_sin_kilometraje_se_lee_sin_romper(self):
        """NULL es el estado normal de las filas anteriores a la migración 0024: un GET
        público no puede volverse 500 por un campo que nadie llenó (§10.2)."""
        pub = _publicacion(kilometraje=None, estado=EstadoPublicacion.ACTIVA.value)
        self._con_sesion([[pub], []])

        respuesta = self.cliente.get("/marketplace/feed")

        self.assertEqual(respuesta.status_code, 200)
        self.assertIsNone(respuesta.json()["estandar"][0]["kilometraje"])

    def test_el_item_de_busqueda_reusa_el_schema_con_kilometraje(self):
        """`GET /marketplace/buscar` no filtra por kilometraje (fuera de alcance), pero
        sus items son `PublicacionInternaSalida`, así que ya lo traen."""
        self.assertIn("kilometraje", PublicacionInternaSalida.model_fields)


class ConvivenciaDeLosDosKilometrajesTests(unittest.TestCase):
    """`kilometraje` y `mantenimientos.ultimo_kilometraje` son hechos DISTINTOS.

    El primero es "el odómetro hoy, según el vendedor" (declarado, cualquier plan). El
    segundo es "el odómetro en el último service" (derivado del garage, solo premium).
    Conviven a propósito: el segundo respalda al primero. Estas pruebas fijan esa
    decisión para que nadie borre uno creyendo que duplica al otro.
    """

    def _vehiculo_con_service(self, km_service):
        """Vehículo mockeado con un mantenimiento; evita construir el modelo real."""
        return Mock(
            marca="Mazda",
            modelo="3",
            anio=2016,
            mantenimientos=[
                Mock(fecha=date(2026, 5, 1), kilometraje_relacionado=km_service)
            ],
        )

    def test_ambos_conviven_en_la_misma_salida_con_valores_distintos(self):
        pub = _publicacion(
            kilometraje=91_200,
            estado=EstadoPublicacion.ACTIVA.value,
            plan=PlanPublicacion.PREMIUM.value,
            vehiculo=self._vehiculo_con_service(78_000),
        )
        pub.ficha = None
        pub.fotos = []

        salida = PublicacionInternaSalida.desde_modelo(pub)

        self.assertEqual(salida.kilometraje, 91_200)          # declarado hoy
        self.assertEqual(salida.mantenimientos.ultimo_kilometraje, 78_000)  # último service

    def test_el_declarado_no_depende_del_plan_ni_del_garage(self):
        """Una light sin vehículo vinculado igual publica su kilometraje; lo que no
        tiene es el resumen de mantenimientos."""
        pub = _publicacion(kilometraje=91_200, estado=EstadoPublicacion.ACTIVA.value)
        pub.ficha = None
        pub.fotos = []

        salida = PublicacionInternaSalida.desde_modelo(pub)

        self.assertEqual(salida.kilometraje, 91_200)
        self.assertIsNone(salida.mantenimientos)

    def test_el_resumen_premium_no_rellena_el_declarado(self):
        """Sin declaración del vendedor, el campo queda en NULL aunque el garage tenga
        un service cargado: no se deriva (el garage es privado y opt-in, `SCOPE_PERMITIDO`)."""
        pub = _publicacion(
            kilometraje=None,
            estado=EstadoPublicacion.ACTIVA.value,
            plan=PlanPublicacion.PREMIUM.value,
            vehiculo=self._vehiculo_con_service(78_000),
        )
        pub.ficha = None
        pub.fotos = []

        salida = PublicacionInternaSalida.desde_modelo(pub)

        self.assertIsNone(salida.kilometraje)
        self.assertEqual(salida.mantenimientos.ultimo_kilometraje, 78_000)


if __name__ == "__main__":
    unittest.main()
