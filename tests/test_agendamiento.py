"""Agendamiento de citas para servicios (migración 0034).

Cliente pide → negocio responde. Sin PostgreSQL: sesión con `Mock`.

    python -m unittest tests.test_agendamiento -v
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
    CitaServicio,
    EstadoCita,
    EstadoModeracion,
    Servicio,
)
from src.modules.marketplace.schemas import CitaCrear, RespuestaNegocio

AHORA = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
MANANA = date.today()


def _res(v):
    filas = v if isinstance(v, list) else [v]
    return Mock(
        scalar_one_or_none=Mock(return_value=v),
        scalar_one=Mock(return_value=v),
        scalars=Mock(return_value=Mock(all=Mock(return_value=filas))),
    )


def _sesion(*resultados):
    s = Mock()
    s.execute.side_effect = [_res(r) for r in resultados]
    s.add = Mock()
    s.commit = Mock()

    def _refresh(obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1
        if getattr(obj, "creado_en", None) is None:
            obj.creado_en = AHORA
        if getattr(obj, "estado", None) is None:
            obj.estado = EstadoCita.SOLICITADA.value

    s.refresh.side_effect = _refresh
    return s


def _usuario(id_=7, email="u@example.com"):
    return Usuario(id=id_, email=email, password_hash="x", nombre="Ana")


def _servicio(id_=3, agenda=True, dueno_id=99):
    return Servicio(
        id=id_, nombre="Taller Vera", categoria="mecanica", provincia="Pichincha",
        ciudad="Quito", certificado=False, acepta_agendamiento=agenda,
        estado_moderacion=EstadoModeracion.APROBADA.value, activo=True,
        aportado_por_usuario_id=dueno_id, creado_en=AHORA,
    )


def _cita(estado=EstadoCita.SOLICITADA.value, servicio=None):
    c = CitaServicio(
        id=5, servicio_id=3, solicitante_usuario_id=7, nombre_contacto="Ana",
        telefono_contacto=None, vehiculo=None, motivo="mantenimiento",
        fecha=MANANA, franja="tarde", nota=None, estado=estado,
        respuesta_negocio=None, fecha_propuesta=None, franja_propuesta=None,
        creado_en=AHORA,
    )
    c.servicio = servicio or _servicio()
    return c


BASE = {"nombre_contacto": "Ana", "motivo": "mantenimiento",
        "fecha": str(MANANA), "franja": "tarde"}


class SchemaTests(unittest.TestCase):
    def test_fecha_pasada_no_valida(self):
        with self.assertRaises(Exception):
            CitaCrear(**{**BASE, "fecha": "2000-01-01"})

    def test_motivo_fuera_de_catalogo(self):
        with self.assertRaises(Exception):
            CitaCrear(**{**BASE, "motivo": "nave"})

    def test_alta_minima_valida(self):
        c = CitaCrear(**BASE)
        self.assertEqual(c.motivo, "mantenimiento")

    def test_reprogramar_sin_fecha_no_valida_en_router(self):
        # el schema lo permite; el router lo rechaza (test aparte abajo)
        r = RespuestaNegocio(decision="reprogramada")
        self.assertIsNone(r.fecha_propuesta)


class PedirCitaTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario()

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_pide_cita_en_servicio_que_agenda(self):
        sesion = _sesion(_servicio(agenda=True))
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post("/marketplace/servicios/3/citas", json=BASE)
        self.assertEqual(r.status_code, 201)
        creada = sesion.add.call_args.args[0]
        self.assertIsInstance(creada, CitaServicio)
        self.assertEqual(creada.solicitante_usuario_id, 7)
        self.assertEqual(r.json()["estado"], "solicitada")

    def test_servicio_sin_agendamiento_da_422(self):
        sesion = _sesion(_servicio(agenda=False))
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post("/marketplace/servicios/3/citas", json=BASE)
        self.assertEqual(r.status_code, 422)

    def test_servicio_inexistente_da_404(self):
        sesion = _sesion(None)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post("/marketplace/servicios/999/citas", json=BASE)
        self.assertEqual(r.status_code, 404)

    def test_sin_sesion_da_401(self):
        main.app.dependency_overrides.clear()
        main.app.dependency_overrides[obtener_sesion] = lambda: Mock()
        r = self.cliente.post("/marketplace/servicios/3/citas", json=BASE)
        self.assertEqual(r.status_code, 401)


class ActualizarCitaTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario()

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_cancela_propia(self):
        cita = _cita()
        sesion = _sesion(cita, cita)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.patch("/marketplace/citas/5", json={"estado": "cancelada"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(cita.estado, "cancelada")

    def test_ajena_da_404(self):
        sesion = _sesion(None)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.patch("/marketplace/citas/5", json={"estado": "cancelada"})
        self.assertEqual(r.status_code, 404)

    def test_confirmar_solo_si_reprogramada(self):
        cita = _cita(estado=EstadoCita.SOLICITADA.value)
        sesion = _sesion(cita)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.patch("/marketplace/citas/5", json={"estado": "confirmada"})
        self.assertEqual(r.status_code, 422)


class ResponderCitaTests(unittest.TestCase):
    def setUp(self):
        self.cliente = TestClient(main.app)

    def tearDown(self):
        main.app.dependency_overrides.clear()

    def test_solo_el_negocio_responde(self):
        # usuario 7 no es dueño (dueño=99) ni admin
        cita = _cita(servicio=_servicio(dueno_id=99))
        sesion = _sesion(cita)
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=7)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/citas/5/responder", json={"decision": "confirmada"}
        )
        self.assertEqual(r.status_code, 404)

    def test_negocio_confirma(self):
        cita = _cita(servicio=_servicio(dueno_id=7))
        sesion = _sesion(cita)
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=7)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/citas/5/responder",
            json={"decision": "confirmada", "respuesta": "Te esperamos 3pm"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(cita.estado, "confirmada")
        self.assertEqual(cita.respuesta_negocio, "Te esperamos 3pm")

    def test_reprogramar_sin_fecha_da_422(self):
        cita = _cita(servicio=_servicio(dueno_id=7))
        sesion = _sesion(cita)
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=7)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/citas/5/responder", json={"decision": "reprogramada"}
        )
        self.assertEqual(r.status_code, 422)

    def test_reprogramar_guarda_propuesta(self):
        cita = _cita(servicio=_servicio(dueno_id=7))
        sesion = _sesion(cita)
        main.app.dependency_overrides[usuario_actual] = lambda: _usuario(id_=7)
        main.app.dependency_overrides[obtener_sesion] = lambda: sesion
        r = self.cliente.post(
            "/marketplace/citas/5/responder",
            json={"decision": "reprogramada", "fecha_propuesta": str(MANANA),
                  "franja_propuesta": "manana"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(cita.estado, "reprogramada")
        self.assertEqual(str(cita.fecha_propuesta), str(MANANA))
        self.assertEqual(cita.franja_propuesta, "manana")


if __name__ == "__main__":
    unittest.main()
