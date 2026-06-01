"""Harness de evaluación del proveedor vehicular activo (POC Fase 3).

Corre un lote CONTROLADO de placas contra el proveedor activo (`PROVEEDOR_VEHICULAR_ACTIVO`)
y mide lo necesario para decidir si activarlo en producción:
  - % de éxito (estado=consulta_realizada)
  - latencia (promedio / mínimo / máximo / p95)
  - cobertura de campos del contrato (qué % de resultados trae cada campo)
  - costo estimado (suma y promedio por consulta)
  - errores frecuentes (por estado y mensaje)

NO toca la BD ni cachea: llama directo al proveedor para medir su comportamiento crudo.
Secuencial (no paraleliza contra la misma fuente, ver skill scraping-respetuoso); usa
`--delay` para espaciar las llamadas si el proveedor tiene límite de tasa.

Uso:
  python -m scripts.evaluar_proveedor                 # 60 placas de demo, proveedor activo
  python -m scripts.evaluar_proveedor --n 100         # 100 placas
  python -m scripts.evaluar_proveedor --placas mis_placas.txt --delay 0.5
  python -m scripts.evaluar_proveedor --json reporte.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from collections import Counter
from dataclasses import asdict

from src.core.validators import validar_placa
from src.modules.consulta.providers import obtener_proveedor
from src.modules.consulta.providers.base import ESTADO_OK
from src.modules.consulta.providers.selector import nombre_proveedor_activo

# Campos del contrato cuya cobertura medimos.
CAMPOS = [
    "marca", "modelo", "anio", "color", "tipo", "clase", "servicio",
    "chasis", "motor", "vin", "titular", "valores_pendientes",
]

# Prefijos de provincia (letra inicial real) para generar placas de formato válido.
_PREFIJOS = ["ABA", "GSA", "PCT", "PBX", "AAB", "GTC", "PDD", "MAB", "TBA", "LBC",
             "IAA", "OBB", "USA", "ECC", "SAD", "XBA"]


def _placas_demo(n: int) -> list[str]:
    """Genera n placas de FORMATO válido (no necesariamente reales) de forma determinista.

    Para un POC con datos reales, reemplazar por una lista de placas conocidas vía --placas.
    """
    placas: list[str] = []
    i = 0
    while len(placas) < n:
        pref = _PREFIJOS[i % len(_PREFIJOS)]
        num = 1000 + (i * 37) % 9000
        try:
            placas.append(validar_placa(f"{pref}{num}"))
        except ValueError:
            pass
        i += 1
    return placas


def _cargar_placas(ruta: str) -> list[str]:
    placas = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            t = linea.strip()
            if not t:
                continue
            try:
                placas.append(validar_placa(t))
            except ValueError:
                print(f"  (placa inválida ignorada: {t!r})")
    return placas


async def evaluar(placas: list[str], delay: float) -> dict:
    proveedor = obtener_proveedor()
    nombre = nombre_proveedor_activo()
    filas = []
    latencias = []
    for placa in placas:
        t0 = time.perf_counter()
        res = await proveedor.consultar(placa)
        ms = (time.perf_counter() - t0) * 1000
        latencias.append(ms)
        filas.append({"placa": placa, "ms": ms, "resultado": asdict(res)})
        if delay:
            await asyncio.sleep(delay)

    total = len(filas)
    exitos = [f for f in filas if f["resultado"]["estado"] == ESTADO_OK]
    estados = Counter(f["resultado"]["estado"] for f in filas)
    errores = Counter(
        (f["resultado"].get("raw_response") or {}).get("error")
        or (f["resultado"].get("raw_response") or {}).get("http_status")
        or f["resultado"]["estado"]
        for f in filas
        if f["resultado"]["estado"] != ESTADO_OK
    )
    cobertura = {
        c: round(100 * sum(1 for f in exitos if f["resultado"].get(c) not in (None, "", [])) / len(exitos), 1)
        if exitos else 0.0
        for c in CAMPOS
    }
    costos = [
        float(f["resultado"]["costo_estimado_usd"])
        for f in exitos
        if f["resultado"].get("costo_estimado_usd") is not None
    ]

    def _p95(xs):
        if not xs:
            return 0.0
        xs = sorted(xs)
        return round(xs[min(len(xs) - 1, int(len(xs) * 0.95))], 1)

    return {
        "proveedor": nombre,
        "total_placas": total,
        "exito_pct": round(100 * len(exitos) / total, 1) if total else 0.0,
        "estados": dict(estados),
        "latencia_ms": {
            "promedio": round(statistics.mean(latencias), 1) if latencias else 0.0,
            "min": round(min(latencias), 1) if latencias else 0.0,
            "max": round(max(latencias), 1) if latencias else 0.0,
            "p95": _p95(latencias),
        },
        "cobertura_campos_pct": cobertura,
        "costo_usd": {
            "total": round(sum(costos), 4),
            "promedio_por_consulta": round(sum(costos) / len(costos), 4) if costos else 0.0,
        },
        "errores_frecuentes": dict(errores.most_common(5)),
    }


def _imprimir(rep: dict) -> None:
    print("\n" + "=" * 60)
    print(f"  EVALUACIÓN PROVEEDOR · {rep['proveedor']}")
    print("=" * 60)
    print(f"  Placas probadas      : {rep['total_placas']}")
    print(f"  % éxito              : {rep['exito_pct']}%   {rep['estados']}")
    lat = rep["latencia_ms"]
    print(f"  Latencia (ms)        : prom {lat['promedio']} · min {lat['min']} · max {lat['max']} · p95 {lat['p95']}")
    print(f"  Costo USD            : total {rep['costo_usd']['total']} · prom/consulta {rep['costo_usd']['promedio_por_consulta']}")
    print("  Cobertura de campos  :")
    for c, pct in rep["cobertura_campos_pct"].items():
        print(f"      {c:<20} {pct}%")
    if rep["errores_frecuentes"]:
        print(f"  Errores frecuentes   : {rep['errores_frecuentes']}")
    print("=" * 60 + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Evalúa el proveedor vehicular activo.")
    ap.add_argument("--n", type=int, default=60, help="cantidad de placas demo (default 60)")
    ap.add_argument("--placas", help="archivo con placas reales (una por línea)")
    ap.add_argument("--delay", type=float, default=0.0, help="segundos entre llamadas")
    ap.add_argument("--json", dest="salida_json", help="guarda el reporte en este archivo JSON")
    args = ap.parse_args()

    placas = _cargar_placas(args.placas) if args.placas else _placas_demo(args.n)
    if not placas:
        print("No hay placas para evaluar.")
        return

    reporte = asyncio.run(evaluar(placas, args.delay))
    _imprimir(reporte)
    if args.salida_json:
        with open(args.salida_json, "w", encoding="utf-8") as f:
            json.dump(reporte, f, ensure_ascii=False, indent=2)
        print(f"Reporte guardado en {args.salida_json}")


if __name__ == "__main__":
    main()
