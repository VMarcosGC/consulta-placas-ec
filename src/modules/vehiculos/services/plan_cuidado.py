"""Plan de cuidado del vehículo: qué mantenimientos tocan, según reglas simples.

ESTO ES UNA APROXIMACIÓN POR REGLAS, no un plan de fabricante. Toma intervalos
genéricos de uso común en Ecuador (aceite cada 5.000 km, frenos cada 20.000, etc.) y
los cruza con lo que el dueño YA registró en `mantenimientos` para decir, por ítem, si
está `al_dia`, `proximo`, `vencido` o `sin_datos`.

Función pura y sin I/O: el router le pasa los datos ya leídos de la BD. Más adelante
un plan generado con IA (según modelo/año/estado real) puede reemplazar `generar_plan`
manteniendo la forma de `ItemPlan` — por eso la respuesta lleva `fuente`.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from datetime import date

# ── Catálogo de reglas ────────────────────────────────────────────────────────
# `cada_km` / `cada_meses`: el que se cumpla primero manda. `claves` se comparan
# (normalizadas: minúsculas sin tildes) por substring contra `Mantenimiento.tipo`,
# que es texto libre.


@dataclass(frozen=True)
class Regla:
    clave: str
    titulo: str
    cada_km: int | None
    cada_meses: int | None
    claves: tuple[str, ...]


REGLAS: tuple[Regla, ...] = (
    Regla("aceite_motor", "Cambio de aceite y filtro de motor", 5_000, 6,
          ("aceite", "filtro de aceite", "lubricante")),
    Regla("filtro_aire", "Filtro de aire", 15_000, 12, ("filtro de aire", "filtro aire")),
    Regla("filtro_combustible", "Filtro de combustible", 20_000, 24,
          ("filtro de combustible", "filtro gasolina", "filtro diesel")),
    Regla("frenos", "Revisión de frenos (pastillas y discos)", 20_000, 12,
          ("freno", "pastilla", "disco de freno")),
    Regla("liquido_frenos", "Cambio de líquido de frenos", 40_000, 24,
          ("liquido de freno", "líquido de freno")),
    Regla("refrigerante", "Cambio de refrigerante", 40_000, 24,
          ("refrigerante", "anticongelante", "coolant")),
    Regla("bujias", "Cambio de bujías", 40_000, 36, ("bujia", "bujía")),
    Regla("alineacion_balanceo", "Alineación y balanceo", 10_000, 12,
          ("alineacion", "alineación", "balanceo")),
    Regla("llantas", "Revisión / cambio de llantas", 50_000, 60,
          ("llanta", "neumatico", "neumático", "caucho")),
    Regla("bateria", "Revisión / cambio de batería", None, 36, ("bateria", "batería")),
    Regla("distribucion", "Correa o cadena de distribución", 80_000, 96,
          ("distribucion", "distribución", "correa de tiempo", "cadenilla")),
    Regla("amortiguadores", "Amortiguadores y suspensión", 60_000, 72,
          ("amortiguador", "suspension", "suspensión")),
    Regla("matricula", "Matrícula anual y revisión vehicular", None, 12,
          ("matricula", "matrícula", "revision vehicular", "revisión vehicular", "rtv")),
)

Estado = str  # "al_dia" | "proximo" | "vencido" | "sin_datos"


@dataclass
class ItemPlan:
    clave: str
    titulo: str
    estado: Estado
    detalle: str
    cada_km: int | None = None
    cada_meses: int | None = None
    ultimo_km: int | None = None
    ultima_fecha: date | None = None
    proximo_km: int | None = None


@dataclass
class Plan:
    fuente: str = "reglas"
    km_referencia: int | None = None
    items: list[ItemPlan] = field(default_factory=list)
    vencidos: int = 0
    proximos: int = 0
    nota_ia: str = (
        "Estimación por reglas generales. Un plan a la medida del modelo, año y estado "
        "del auto llegará más adelante con IA."
    )


def _normalizar(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return sin_tildes.lower().strip()


_ORDEN_ESTADO = {"vencido": 0, "proximo": 1, "sin_datos": 2, "al_dia": 3}


def _fmt_km(n: int) -> str:
    return f"{n:,.0f} km".replace(",", ".")


def _meses_desde(f: date, hoy: date) -> int:
    return (hoy.year - f.year) * 12 + (hoy.month - f.month)


def generar_plan(
    *,
    km_referencia: int | None,
    registros: list[tuple[str, date, int | None]],
    hoy: date | None = None,
) -> Plan:
    """`registros` = [(tipo_texto_libre, fecha, kilometraje_o_None), ...].

    Devuelve el plan con un `ItemPlan` por regla, ordenado vencido → próximo →
    sin datos → al día.
    """
    hoy = hoy or date.today()
    plan = Plan(km_referencia=km_referencia)

    for regla in REGLAS:
        # Último registro que matchea esta regla por substring.
        matches = [
            (fecha, km)
            for (tipo, fecha, km) in registros
            if any(c in _normalizar(tipo) for c in regla.claves)
        ]
        ultima_fecha = max((f for f, _ in matches), default=None)
        ultimo_km = None
        if matches:
            # km del registro más reciente por fecha (si lo tiene).
            ultimo_km = max(matches, key=lambda t: t[0])[1]

        vencido_km = False
        proximo_km = False
        proximo_km_valor: int | None = None
        if regla.cada_km is not None:
            base = ultimo_km if ultimo_km is not None else 0
            proximo_km_valor = base + regla.cada_km
            if km_referencia is not None:
                restante = proximo_km_valor - km_referencia
                vencido_km = restante <= 0
                proximo_km = 0 < restante <= max(1_000, regla.cada_km * 0.15)

        vencido_tiempo = False
        proximo_tiempo = False
        if regla.cada_meses is not None and ultima_fecha is not None:
            transcurridos = _meses_desde(ultima_fecha, hoy)
            vencido_tiempo = transcurridos >= regla.cada_meses
            proximo_tiempo = regla.cada_meses - 1 <= transcurridos < regla.cada_meses

        tiene_senal = (km_referencia is not None) or (ultima_fecha is not None)
        if not tiene_senal and not matches:
            estado = "sin_datos"
        elif vencido_km or vencido_tiempo:
            estado = "vencido"
        elif proximo_km or proximo_tiempo:
            estado = "proximo"
        elif not matches and regla.cada_meses is not None and km_referencia is None:
            # Sin historial y sin km: solo sabemos que "algún día toca".
            estado = "sin_datos"
        else:
            estado = "al_dia"

        # Detalle legible.
        partes: list[str] = []
        if regla.cada_km and regla.cada_meses:
            partes.append(f"Cada {_fmt_km(regla.cada_km)} o {regla.cada_meses} meses")
        elif regla.cada_km:
            partes.append(f"Cada {_fmt_km(regla.cada_km)}")
        elif regla.cada_meses:
            partes.append(f"Cada {regla.cada_meses} meses")
        if ultima_fecha is not None:
            hace = _meses_desde(ultima_fecha, hoy)
            trozo = f"último registro {ultima_fecha.isoformat()}"
            if ultimo_km is not None:
                trozo += f" ({_fmt_km(ultimo_km)})"
            trozo += f", hace {hace} mes{'es' if hace != 1 else ''}"
            partes.append(trozo)
        else:
            partes.append("sin registro previo — hazlo y regístralo")
        detalle = ". ".join(partes) + "."

        item = ItemPlan(
            clave=regla.clave,
            titulo=regla.titulo,
            estado=estado,
            detalle=detalle,
            cada_km=regla.cada_km,
            cada_meses=regla.cada_meses,
            ultimo_km=ultimo_km,
            ultima_fecha=ultima_fecha,
            proximo_km=proximo_km_valor,
        )
        plan.items.append(item)

    plan.items.sort(key=lambda i: (_ORDEN_ESTADO[i.estado], i.titulo))
    plan.vencidos = sum(1 for i in plan.items if i.estado == "vencido")
    plan.proximos = sum(1 for i in plan.items if i.estado == "proximo")
    return plan
