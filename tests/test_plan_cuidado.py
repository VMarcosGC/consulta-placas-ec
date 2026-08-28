"""Plan de cuidado por reglas (`services/plan_cuidado.py`). Función pura, sin BD.

    python -m unittest tests.test_plan_cuidado -v
"""

import unittest
from datetime import date

from src.modules.vehiculos.services.plan_cuidado import REGLAS, generar_plan

HOY = date(2026, 8, 28)


def _item(plan, clave):
    return next(i for i in plan.items if i.clave == clave)


class PlanCuidadoTests(unittest.TestCase):
    def test_sin_datos_todo_en_sin_datos(self):
        plan = generar_plan(km_referencia=None, registros=[], hoy=HOY)
        self.assertEqual(len(plan.items), len(REGLAS))
        self.assertTrue(all(i.estado == "sin_datos" for i in plan.items))
        self.assertEqual(plan.vencidos, 0)

    def test_aceite_vencido_por_km(self):
        # Último cambio de aceite a 40.000 km; hoy el auto va en 50.000 → vencido
        # (intervalo 5.000 km).
        registros = [("Cambio de aceite y filtro", date(2026, 1, 10), 40_000)]
        plan = generar_plan(km_referencia=50_000, registros=registros, hoy=HOY)
        self.assertEqual(_item(plan, "aceite_motor").estado, "vencido")
        self.assertGreaterEqual(plan.vencidos, 1)
        # El primer item de la lista es un vencido (orden por severidad).
        self.assertEqual(plan.items[0].estado, "vencido")

    def test_aceite_al_dia_tras_registro_reciente(self):
        registros = [("Cambio de aceite", date(2026, 8, 1), 49_500)]
        plan = generar_plan(km_referencia=50_000, registros=registros, hoy=HOY)
        self.assertEqual(_item(plan, "aceite_motor").estado, "al_dia")

    def test_matricula_vencida_por_tiempo(self):
        registros = [("Matrícula anual", date(2025, 1, 15), None)]
        plan = generar_plan(km_referencia=None, registros=registros, hoy=HOY)
        self.assertEqual(_item(plan, "matricula").estado, "vencido")

    def test_proximo_km_cerca_del_intervalo(self):
        # Aceite a 47.000; intervalo 5.000 → próximo a 52.000. Hoy 51.500 → dentro del
        # 15% (750 km) del intervalo → "proximo".
        registros = [("aceite motor", date(2026, 7, 1), 47_000)]
        plan = generar_plan(km_referencia=51_500, registros=registros, hoy=HOY)
        self.assertEqual(_item(plan, "aceite_motor").estado, "proximo")

    def test_km_referencia_se_refleja(self):
        plan = generar_plan(km_referencia=123_000, registros=[], hoy=HOY)
        self.assertEqual(plan.km_referencia, 123_000)


if __name__ == "__main__":
    unittest.main()
