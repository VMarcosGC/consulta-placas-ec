"""Siembra presencias DEMO en los puntos de encuentro (migración 0033).

Para qué: que `/puntos-encuentro` no se vea vacío mientras no hay uso real. Toma
publicaciones internas `activa` (las de la cuenta demo de `seed_demo.py`) y las
"anuncia" repartidas entre los 6 puntos de Quito, con fechas en los próximos días y
franjas variadas. Todas quedan `anunciada`.

Idempotente por la UK `(punto_id, publicacion_interna_id, fecha)`: reejecutar no
duplica. `--borrar` quita SOLO las presencias de las publicaciones de la cuenta demo.

Conexión explícita a Neon leyendo `.env` (mismo criterio que `scripts/seed_demo.py`);
escrituras por SQLAlchemy Core.

    python -m scripts.seed_puntos_encuentro
    python -m scripts.seed_puntos_encuentro --borrar
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, delete, func, insert, select
from sqlalchemy.orm import Session, sessionmaker

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import src.registry  # noqa: E402,F401

from src.modules.auth.models import Usuario  # noqa: E402
from src.modules.marketplace.models import (  # noqa: E402
    EstadoPresencia,
    EstadoPublicacion,
    PresenciaPunto,
    PublicacionInterna,
    PuntoEncuentro,
)

_T_USUARIO = Usuario.__table__
_T_PUB = PublicacionInterna.__table__
_T_PUNTO = PuntoEncuentro.__table__
_T_PRES = PresenciaPunto.__table__

EMAIL_DEMO = "demo-seed@carstore.local"
N_PRESENCIAS = 22
_FRANJAS = ["manana", "tarde", "noche", "todo_el_dia"]
_NOTAS = [
    "Llevo matrícula, historial y segunda llave.",
    "Puedo llegar 10 minutos antes.",
    "Acepto revisión mecánica de tu confianza en el sitio.",
    "Vengo con el auto lavado y con tanque lleno.",
    None,
    None,
]


def _dsn_neon() -> str:
    valores = dotenv_values(RAIZ / ".env")
    crudo = (valores.get("DATABASE_URL") or "").strip()
    if not crudo:
        print("ERROR: `.env` no tiene DATABASE_URL.")
        raise SystemExit(2)
    if crudo.startswith("postgresql+"):
        return crudo
    if crudo.startswith("postgresql://"):
        return "postgresql+psycopg://" + crudo[len("postgresql://") :]
    if crudo.startswith("postgres://"):
        return "postgresql+psycopg://" + crudo[len("postgres://") :]
    return crudo


def _abrir_sesion() -> tuple[Session, object]:
    engine = create_engine(_dsn_neon(), pool_pre_ping=True, future=True)
    fabrica = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return fabrica(), engine


def _usuario_demo_id(sesion: Session) -> int | None:
    fila = sesion.execute(
        select(_T_USUARIO.c.id).where(_T_USUARIO.c.email == EMAIL_DEMO)
    ).first()
    return fila[0] if fila else None


def sembrar(sesion: Session) -> dict:
    uid = _usuario_demo_id(sesion)
    if uid is None:
        print(f"  ERROR: no existe la cuenta {EMAIL_DEMO}. Corré `python -m scripts.seed_demo`.")
        raise SystemExit(2)

    puntos = list(
        sesion.execute(
            select(_T_PUNTO.c.id).where(_T_PUNTO.c.activo.is_(True)).order_by(_T_PUNTO.c.orden)
        ).scalars()
    )
    if not puntos:
        print("  ERROR: no hay puntos de encuentro. ¿Aplicaste la migración 0033?")
        raise SystemExit(2)

    pubs = list(
        sesion.execute(
            select(_T_PUB.c.id)
            .where(
                _T_PUB.c.usuario_id == uid,
                _T_PUB.c.estado == EstadoPublicacion.ACTIVA.value,
            )
            .order_by(_T_PUB.c.id)
            .limit(N_PRESENCIAS)
        ).scalars()
    )
    if not pubs:
        print("  ERROR: la cuenta demo no tiene publicaciones activas.")
        raise SystemExit(2)

    existentes = {
        (p, b, f)
        for p, b, f in sesion.execute(
            select(_T_PRES.c.punto_id, _T_PRES.c.publicacion_interna_id, _T_PRES.c.fecha).where(
                _T_PRES.c.publicacion_interna_id.in_(pubs)
            )
        )
    }

    hoy = date.today()
    creadas = 0
    for i, pub_id in enumerate(pubs):
        punto_id = puntos[i % len(puntos)]
        fecha = hoy + timedelta(days=1 + (i % 12))  # próximos 12 días
        if (punto_id, pub_id, fecha) in existentes:
            continue
        sesion.execute(
            insert(_T_PRES).values(
                punto_id=punto_id,
                publicacion_interna_id=pub_id,
                usuario_id=uid,
                fecha=fecha,
                franja=_FRANJAS[i % len(_FRANJAS)],
                estado=EstadoPresencia.ANUNCIADA.value,
                nota=_NOTAS[i % len(_NOTAS)],
            )
        )
        creadas += 1

    sesion.commit()
    total = sesion.scalar(
        select(func.count()).select_from(_T_PRES).where(_T_PRES.c.usuario_id == uid)
    )
    return {"creadas": creadas, "total_demo": total, "puntos": len(puntos), "pubs": len(pubs)}


def borrar(sesion: Session) -> int:
    uid = _usuario_demo_id(sesion)
    if uid is None:
        return 0
    n = sesion.execute(
        delete(_T_PRES).where(_T_PRES.c.usuario_id == uid)
    ).rowcount
    sesion.commit()
    return n


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    modo_borrar = "--borrar" in argv[1:]
    if set(argv[1:]) - {"--borrar"}:
        print(__doc__)
        return 2

    sesion, engine = _abrir_sesion()
    try:
        print("=" * 60)
        print("  SEED — PRESENCIAS EN PUNTOS DE ENCUENTRO")
        print("=" * 60)
        if modo_borrar:
            n = borrar(sesion)
            print(f"\n  Eliminadas {n} presencias de la cuenta demo.")
            return 0
        r = sembrar(sesion)
        print(f"\n  Puntos activos ......... {r['puntos']}")
        print(f"  Publicaciones usadas ... {r['pubs']}")
        print(f"  Presencias creadas ..... {r['creadas']}")
        print(f"  Presencias demo (total)  {r['total_demo']}")
        print("\n  Deshacer: python -m scripts.seed_puntos_encuentro --borrar")
        return 0
    finally:
        sesion.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
