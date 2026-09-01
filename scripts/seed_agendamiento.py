"""Siembra negocios que ACEPTAN AGENDAMIENTO + algunas citas demo (migración 0034).

Para qué: probar el flujo de agendamiento de servicios de punta a punta sin datos
reales todavía.

- 8 `servicios` `aprobada`/`activo` con `acepta_agendamiento=True`, atribuidos a la
  cuenta de `--dueno` (default `mrkitov@gmail.com`) para que ESE usuario los vea como
  "sus negocios" y reciba las solicitudes. Si esa cuenta no existe → cuenta demo, con
  aviso (entonces la bandeja "recibidas" no será visible al loguearse).
- 4 `citas_servicio` `solicitada` con solicitante = cuenta demo, contra 2 de esos
  negocios, para que la bandeja del dueño tenga contenido.

Idempotente (por nombre de servicio / por trío servicio+fecha+solicitante). `--borrar`
quita SOLO lo que sembró este script.

    python -m scripts.seed_agendamiento
    python -m scripts.seed_agendamiento --dueno otro@correo.com
    python -m scripts.seed_agendamiento --borrar
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, delete, insert, select
from sqlalchemy.orm import Session, sessionmaker

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

import src.registry  # noqa: E402,F401

from src.modules.auth.models import Usuario  # noqa: E402
from src.modules.marketplace.models import (  # noqa: E402
    CitaServicio,
    EstadoCita,
    EstadoModeracion,
    Servicio,
)

_T_USUARIO = Usuario.__table__
_T_SERV = Servicio.__table__
_T_CITA = CitaServicio.__table__

EMAIL_DEMO = "demo-seed@carstore.local"
DUENO_DEFAULT = "mrkitov@gmail.com"

# (nombre, categoria, provincia, ciudad, horario)
_NEGOCIOS = [
    ("Tecnicentro Andrade", "mecanica", "Pichincha", "Quito",
     "Lun a Vie 8:00–18:00 · Sáb 8:00–13:00"),
    ("Mecánica Total Vera · Certificada", "mecanica_certificada", "Guayas", "Guayaquil",
     "Lun a Sáb 8:30–17:30"),
    ("AutoService Cuenca", "centro_servicio", "Azuay", "Cuenca",
     "Lun a Vie 9:00–19:00"),
    ("Lavadero Express La Y", "lavadero", "Pichincha", "Quito",
     "Todos los días 7:00–20:00"),
    ("AutoLuces Ambato", "luces", "Tungurahua", "Ambato",
     "Lun a Vie 9:00–18:00 · Sáb 9:00–14:00"),
    ("Accesorios y Lujos Manta", "accesorios", "Manabí", "Manta",
     "Lun a Sáb 10:00–19:00"),
    ("Servifrenos Loja", "mecanica", "Loja", "Loja",
     "Lun a Vie 8:00–17:00"),
    ("MultiMarcas Guerrero · Certificada", "mecanica_certificada", "Pichincha", "Quito",
     "Lun a Vie 8:00–18:00"),
]

_MOTIVOS = ["mantenimiento", "revision", "diagnostico", "lavado"]
_FRANJAS = ["manana", "tarde", "noche", "todo_el_dia"]
_NOTAS = [
    "El auto tiene un ruido al frenar en frío.",
    "Vengo por el ABC de motor y revisión de suspensión.",
    "Quiero cotizar láminas de seguridad y polarizado.",
    None,
]


def _dsn_neon() -> str:
    valores = dotenv_values(RAIZ / ".env")
    crudo = (valores.get("DATABASE_URL") or "").strip()
    if not crudo:
        print("ERROR: `.env` no tiene DATABASE_URL.")
        raise SystemExit(2)
    for pre in ("postgresql+", "postgresql://", "postgres://"):
        if crudo.startswith(pre):
            if pre == "postgresql+":
                return crudo
            return "postgresql+psycopg://" + crudo[len(pre):]
    return crudo


def _abrir_sesion() -> tuple[Session, object]:
    engine = create_engine(_dsn_neon(), pool_pre_ping=True, future=True)
    fabrica = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return fabrica(), engine


def _uid(sesion: Session, email: str) -> int | None:
    fila = sesion.execute(select(_T_USUARIO.c.id).where(_T_USUARIO.c.email == email)).first()
    return fila[0] if fila else None


def sembrar(sesion: Session, email_dueno: str) -> dict:
    dueno_id = _uid(sesion, email_dueno)
    demo_id = _uid(sesion, EMAIL_DEMO)
    if dueno_id is None:
        print(f"  AVISO: no existe {email_dueno}; los negocios quedan en la cuenta demo.")
        dueno_id = demo_id
    if demo_id is None:
        print("  ERROR: falta la cuenta demo (corré `python -m scripts.seed_demo`).")
        raise SystemExit(2)

    nombres = [n[0] for n in _NEGOCIOS]
    existentes = {
        nombre: sid
        for sid, nombre in sesion.execute(
            select(_T_SERV.c.id, _T_SERV.c.nombre).where(_T_SERV.c.nombre.in_(nombres))
        )
    }

    creados = 0
    ids_negocios: list[int] = []
    for nombre, cat, prov, ciudad, horario in _NEGOCIOS:
        if nombre in existentes:
            sid = existentes[nombre]
            sesion.execute(
                _T_SERV.update().where(_T_SERV.c.id == sid).values(
                    acepta_agendamiento=True,
                    estado_moderacion=EstadoModeracion.APROBADA.value,
                    activo=True,
                )
            )
        else:
            sid = sesion.execute(
                insert(_T_SERV).values(
                    nombre=nombre, categoria=cat, provincia=prov, ciudad=ciudad,
                    descripcion="Negocio de demostración para probar el agendamiento en línea.",
                    horario=horario, certificado=cat == "mecanica_certificada",
                    acepta_agendamiento=True,
                    estado_moderacion=EstadoModeracion.APROBADA.value, activo=True,
                    aportado_por_usuario_id=dueno_id,
                ).returning(_T_SERV.c.id)
            ).scalar_one()
            creados += 1
        ids_negocios.append(sid)

    # Citas demo contra los 2 primeros negocios.
    citas_existentes = {
        (s, f, u)
        for s, f, u in sesion.execute(
            select(_T_CITA.c.servicio_id, _T_CITA.c.fecha, _T_CITA.c.solicitante_usuario_id)
            .where(_T_CITA.c.servicio_id.in_(ids_negocios[:2]))
        )
    }
    hoy = date.today()
    citas_creadas = 0
    for i in range(4):
        sid = ids_negocios[i % 2]
        fecha = hoy + timedelta(days=2 + i * 2)
        if (sid, fecha, demo_id) in citas_existentes:
            continue
        sesion.execute(
            insert(_T_CITA).values(
                servicio_id=sid, solicitante_usuario_id=demo_id,
                nombre_contacto="Cliente Demo", telefono_contacto="0999000111",
                vehiculo=["Chevrolet Sail 2016", "Kia Sportage 2019",
                          "Hyundai Tucson 2015", "Mazda 3 2018"][i],
                motivo=_MOTIVOS[i % len(_MOTIVOS)], fecha=fecha,
                franja=_FRANJAS[i % len(_FRANJAS)], nota=_NOTAS[i % len(_NOTAS)],
                estado=EstadoCita.SOLICITADA.value,
            )
        )
        citas_creadas += 1

    sesion.commit()
    return {"negocios_creados": creados, "negocios_total": len(ids_negocios),
            "citas_creadas": citas_creadas, "dueno_id": dueno_id}


def borrar(sesion: Session) -> dict:
    nombres = [n[0] for n in _NEGOCIOS]
    ids = list(
        sesion.execute(select(_T_SERV.c.id).where(_T_SERV.c.nombre.in_(nombres))).scalars()
    )
    n_citas = 0
    if ids:
        n_citas = sesion.execute(
            delete(_T_CITA).where(_T_CITA.c.servicio_id.in_(ids))
        ).rowcount
    n_serv = sesion.execute(
        delete(_T_SERV).where(_T_SERV.c.nombre.in_(nombres))
    ).rowcount
    sesion.commit()
    return {"citas": n_citas, "servicios": n_serv}


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    args = argv[1:]
    modo_borrar = "--borrar" in args
    email_dueno = DUENO_DEFAULT
    if "--dueno" in args:
        i = args.index("--dueno")
        if i + 1 < len(args):
            email_dueno = args[i + 1]
    if set(args) - {"--borrar", "--dueno", email_dueno}:
        print(__doc__)
        return 2

    sesion, engine = _abrir_sesion()
    try:
        print("=" * 60)
        print("  SEED — AGENDAMIENTO DE SERVICIOS")
        print("=" * 60)
        if modo_borrar:
            r = borrar(sesion)
            print(f"\n  Citas eliminadas ...... {r['citas']}")
            print(f"  Servicios eliminados .. {r['servicios']}")
            return 0
        r = sembrar(sesion, email_dueno)
        print(f"\n  Dueño de los negocios . usuario_id={r['dueno_id']} ({email_dueno})")
        print(f"  Negocios creados ...... {r['negocios_creados']}")
        print(f"  Negocios (total) ...... {r['negocios_total']}  (todos con acepta_agendamiento=True)")
        print(f"  Citas demo creadas .... {r['citas_creadas']}")
        print("\n  Deshacer: python -m scripts.seed_agendamiento --borrar")
        return 0
    finally:
        sesion.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
