"""Estado VERIFICADO del sistema — no el declarado (TASK-007).

Imprime cinco bloques mirando el sistema real, no la documentación. Su salida es
**precondición de cada entrada de bitácora**: antes de escribir "esto quedó hecho",
se corre y se mira.

  1. Migraciones — head del repo vs `alembic_version` de Neon (y en qué dirección).
  2. Git — commits sin pushear y ramas sin mergear, en ambos repos.
  3. Proveedor vehicular — sus capacidades, observadas desde el endpoint público
     anónimo (sin gastar tokens, sin nombrar cuál es).
  4. Fuentes con consultas en los últimos 7 días — y las que NO tienen (la ausencia
     es la señal).
  5. Cola del worker — pendientes y `en_proceso` atascados, con su antigüedad.

**Solo lectura.** Jamás escribe en ninguna BD ni en ningún repo. La única operación
de red sobre los repos es `git fetch` (sin `--prune`). Si una fuente no responde, ese
bloque lo dice y los otros cuatro se imprimen igual; el exit siempre es 0.

Uso:
    python -m scripts.estado
    ESTADO_PLACA=XYZ1234 python -m scripts.estado   # placa para el bloque 3
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REPO_FRONT = RAIZ.parent / "consulta-placas-web"

# Overridable para probar el modo de fallo (spec §criterio: "apuntando a un puerto muerto").
BACKEND_PROD = os.getenv("ESTADO_BACKEND", "https://consulta-placas-ec.onrender.com")
# Placa solo para observar el array `productos` del perfil (viene aunque el perfil
# esté vacío). No importa que tenga datos; sí que el formato sea válido.
PLACA_SONDA = os.getenv("ESTADO_PLACA", "ABC1234")

ANCHO = 72


# ── utilidades de presentación ──────────────────────────────────────────────

def titulo(n: int, texto: str) -> None:
    print()
    print(f"{n}. {texto.upper()}")
    print("-" * ANCHO)


def linea(texto: str = "") -> None:
    print(texto)


def alineado(ok: bool, si: str, no: str) -> str:
    return f"  [OK] {si}" if ok else f"  [!!] {no}"


def _antiguedad(ts: datetime | None) -> str:
    if ts is None:
        return "nunca"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - ts
    dias = delta.days
    horas = delta.seconds // 3600
    if dias > 0:
        return f"hace {dias} d {horas} h"
    minutos = (delta.seconds % 3600) // 60
    if horas > 0:
        return f"hace {horas} h {minutos} min"
    return f"hace {minutos} min"


# ── conexión a Neon (explícita, desde .env, NO desde src.core.database) ──────

def dsn_neon() -> str | None:
    """DSN de producción leído directo de `.env`.

    NO se importa `src.core.database`: desde TASK-010 esa capa resuelve con
    precedencia entorno real > `.env.local` > `.env`, así que en una máquina de
    desarrollo daría la BD local en silencio. Acá se quiere producción, sí o sí.
    """
    try:
        from dotenv import dotenv_values
    except Exception as e:  # pragma: no cover - dependencia ya instalada
        raise RuntimeError(f"no se pudo importar python-dotenv: {e!r}") from e

    vals = dotenv_values(RAIZ / ".env")
    dsn = vals.get("DATABASE_URL")
    if not dsn:
        return None
    # psycopg 3 no entiende el prefijo +psycopg del DSN de SQLAlchemy.
    return dsn.replace("postgresql+psycopg://", "postgresql://")


def abrir_neon():
    """Devuelve (conexion, None) o (None, motivo). Nunca lanza."""
    try:
        import psycopg
    except Exception as e:
        return None, f"no se pudo importar psycopg: {e!r}"
    try:
        dsn = dsn_neon()
    except Exception as e:
        return None, str(e)
    if dsn is None:
        return None, ".env no tiene DATABASE_URL (configuración faltante)"
    try:
        conn = psycopg.connect(dsn, connect_timeout=15)
        conn.autocommit = True  # solo SELECT; evita dejar transacciones abiertas
        return conn, None
    except Exception as e:
        return None, f"Neon inalcanzable: {e!r}"


# ── bloque 1: migraciones ──────────────────────────────────────────────────

def bloque_migraciones(conn) -> None:
    titulo(1, "Migraciones — head local vs Neon")

    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(RAIZ / "alembic.ini"))
        cfg.set_main_option("script_location", str(RAIZ / "alembic"))
        script = ScriptDirectory.from_config(cfg)
        # Orden real de las migraciones, de la más nueva a la más vieja.
        revisiones = [s.revision for s in script.walk_revisions()]
        heads = list(script.get_heads())
    except Exception as e:
        linea(f"  no se pudo leer el head local: {e!r}")
        revisiones, heads = [], []

    if len(heads) == 1:
        linea(f"  head del repo:  {heads[0]}")
    elif len(heads) > 1:
        linea(f"  [!!] el repo tiene VARIOS heads: {', '.join(heads)}")
    # (0 heads → ya se reportó el fallo arriba)

    if conn is None:
        linea("  head de Neon:   no se pudo consultar (ver arriba)")
        return

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM alembic_version")
            filas = cur.fetchall()
        neon = filas[0][0] if filas else None
    except Exception as e:
        linea(f"  head de Neon:   no se pudo consultar: {e!r}")
        return

    linea(f"  head de Neon:   {neon or '(sin fila en alembic_version)'}")

    if not revisiones or not heads:
        return
    head_local = heads[0]
    if neon == head_local:
        linea(alineado(True, "alineados", ""))
    elif neon in revisiones:
        # neon es un ancestro del head local → faltan migraciones por aplicar.
        faltan = revisiones.index(neon)  # cuántas hay por encima de neon
        linea(alineado(
            False, "", f"faltan {faltan} migración(es) por aplicar en Neon "
                       f"(neon={neon} < repo={head_local})"
        ))
    else:
        # neon NO está en el historial del repo → la base fue por delante, o divergen.
        linea("  [!!] Neon apunta a una revisión que el repo NO conoce.")
        linea("       O la base fue por delante del código (ya pasó dos veces y es")
        linea("       lo peor), o las historias divergieron. Revisar a mano.")


# ── bloque 2: git ─────────────────────────────────────────────────────────

def _git(repo: Path, *args: str, timeout: int = 30) -> tuple[int, str, str]:
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, timeout=timeout,
    )
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def _estado_repo(nombre: str, repo: Path) -> None:
    linea(f"  {nombre}  ({repo})")
    if not repo.exists():
        linea("    [!!] el repositorio no está en esta máquina — bloque omitido")
        return
    if not (repo / ".git").exists():
        linea("    [!!] la carpeta existe pero no es un repo git")
        return

    # fetch sin --prune: única operación de red permitida sobre los repos.
    rc, _, err = _git(repo, "fetch", "--quiet")
    if rc != 0:
        linea(f"    [..] git fetch falló ({err or 'sin detalle'}); los datos son")
        linea("         de la última vez que alguien hizo fetch")

    rc, out, err = _git(repo, "rev-list", "--count", "origin/main..main")
    if rc == 0 and out.isdigit():
        n = int(out)
        linea(alineado(
            n == 0,
            "main está al día con origin/main",
            f"main tiene {n} commit(s) SIN pushear a origin/main",
        ))
    else:
        linea(f"    [..] no se pudo comparar con origin/main ({err or out or 'sin detalle'})")

    rc, out, _ = _git(repo, "branch", "--no-merged", "main", "--format=%(refname:short)")
    if rc == 0:
        ramas = [b for b in out.splitlines() if b.strip()]
        if ramas:
            linea(f"    [!!] {len(ramas)} rama(s) local(es) SIN mergear a main:")
            for b in ramas:
                linea(f"         - {b}")
        else:
            linea("  [OK] no hay ramas locales sin mergear a main")
    else:
        linea("    [..] no se pudieron listar las ramas")


def bloque_git() -> None:
    titulo(2, "Git — commits sin pushear y ramas sin mergear")
    try:
        _estado_repo("backend ", RAIZ)
    except Exception as e:
        linea(f"  backend: no se pudo revisar: {e!r}")
    linea()
    try:
        _estado_repo("frontend", REPO_FRONT)
    except Exception as e:
        linea(f"  frontend: no se pudo revisar: {e!r}")


# ── bloque 3: proveedor vehicular ─────────────────────────────────────────

def bloque_proveedor() -> None:
    titulo(3, "Proveedor vehicular — capacidades observadas en producción")

    try:
        import httpx
    except Exception as e:
        linea(f"  no se pudo importar httpx: {e!r}")
        return

    url = f"{BACKEND_PROD}/consultar/{PLACA_SONDA}/perfil"
    linea(f"  GET {url}?solo_cache=true  (anónimo, sin gastar tokens)")
    t0 = time.monotonic()
    try:
        # Render free duerme: el primer request puede tardar 20-30 s. No es un fallo.
        r = httpx.get(url, params={"solo_cache": "true"}, timeout=75)
    except Exception as e:
        linea(f"  [!!] no respondió: {e!r}")
        return
    tardo = time.monotonic() - t0
    if tardo > 15:
        linea(f"  (tardó {tardo:.0f} s — arranque en frío de Render, no es un fallo)")
    if r.status_code != 200:
        linea(f"  [!!] respondió HTTP {r.status_code} (se esperaba 200 anónimo)")
        return

    try:
        productos = {p["codigo"]: p for p in r.json().get("productos", [])}
    except Exception as e:
        linea(f"  [!!] respuesta ilegible: {e!r}")
        return

    if not productos:
        linea("  [!!] el perfil no trajo `productos` — no se puede observar el proveedor")
        return

    con_capacidad = [
        c for c in ("identificadores_tecnicos", "titular_validado")
        if productos.get(c, {}).get("disponible") is True
    ]
    if con_capacidad:
        linea(f"  [!!] HAY un proveedor con capacidades activo: {', '.join(con_capacidad)}")
        linea("       con `disponible: true`. Si NO hay credenciales reales cargadas,")
        linea("       eso es el `mock` fabricando VIN y titular — revisar el dashboard")
        linea("       de Render (PROVEEDOR_VEHICULAR_ACTIVO).")
    else:
        linea(alineado(
            True,
            "ningún proveedor ofrece datos (identificadores/titular en "
            "`disponible: false`) — estado correcto hoy",
            "",
        ))


# ── bloque 4: fuentes con consultas recientes ────────────────────────────

def bloque_fuentes(conn) -> None:
    titulo(4, "Fuentes — consultas en los últimos 7 días")
    if conn is None:
        linea("  no se pudo consultar Neon (ver bloque 1)")
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT fuente,
                       count(*) FILTER (WHERE creado_en > now() - interval '7 days') AS recientes,
                       max(creado_en) AS ultima
                FROM consultas
                GROUP BY fuente
                ORDER BY fuente
                """
            )
            filas = cur.fetchall()
    except Exception as e:
        linea(f"  no se pudo leer `consultas`: {e!r}")
        return

    if not filas:
        linea("  la tabla `consultas` está vacía")
        return

    sin_recientes = []
    for fuente, recientes, ultima in filas:
        marca = "[OK]" if recientes else "[!!]"
        linea(f"  {marca} {fuente:<10} {recientes:>4} en 7 d   última: {_antiguedad(ultima)}")
        if not recientes:
            sin_recientes.append(fuente)
    if sin_recientes:
        linea()
        linea(f"  [!!] sin actividad en 7 días: {', '.join(sin_recientes)}")
        linea("       (la ausencia es la señal — así se habría visto lo de FGE)")


# ── bloque 5: cola del worker ───────────────────────────────────────────

def bloque_cola(conn) -> None:
    titulo(5, "Cola del worker — pendientes y atascados")
    if conn is None:
        linea("  no se pudo consultar Neon (ver bloque 1)")
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT estado,
                       count(*),
                       min(creado_en)  AS mas_viejo_creado,
                       min(tomado_en)  AS mas_viejo_tomado
                FROM cola_scraping
                WHERE estado IN ('pendiente', 'en_proceso')
                GROUP BY estado
                ORDER BY estado
                """
            )
            filas = {e: (n, c, t) for e, n, c, t in cur.fetchall()}
    except Exception as e:
        linea(f"  no se pudo leer `cola_scraping`: {e!r}")
        return

    if not filas:
        linea(alineado(True, "sin trabajos pendientes ni en proceso", ""))
        return

    pend = filas.get("pendiente")
    if pend:
        n, creado, _ = pend
        viejo = _antiguedad(creado)
        marca = "[!!]" if ("d " in viejo) else "[OK]"
        linea(f"  {marca} pendiente:   {n:>3}   el más viejo, {viejo}")
        if marca == "[!!]":
            linea("       pendientes de hace días = el worker no está drenando la cola")

    enp = filas.get("en_proceso")
    if enp:
        n, _, tomado = enp
        viejo = _antiguedad(tomado)
        # Un en_proceso de más de unos minutos es un lock colgado, no trabajo en curso.
        colgado = ("d " in viejo) or ("h " in viejo)
        marca = "[!!]" if colgado else "[OK]"
        linea(f"  {marca} en_proceso:  {n:>3}   el más viejo tomado {viejo}")
        if colgado:
            linea("       en_proceso de hace horas/días = lock colgado, no trabajo vivo")


# ── main ──────────────────────────────────────────────────────────────────

def main() -> int:
    # La copy lleva acentos es-EC; en la consola legacy de Windows (CP1252) se
    # mojibakean. Forzar UTF-8 en stdout donde se pueda (no rompe si no se puede).
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * ANCHO)
    print("  ESTADO VERIFICADO DEL SISTEMA")
    print(f"  {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}")
    print("=" * ANCHO)

    conn, motivo = abrir_neon()
    if motivo:
        print()
        print(f"  Neon: {motivo}")
        print("  (los bloques que no dependen de la BD se imprimen igual)")

    try:
        bloque_migraciones(conn)
        bloque_git()
        bloque_proveedor()
        bloque_fuentes(conn)
        bloque_cola(conn)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    print()
    print("=" * ANCHO)
    print("  Fin. Este script solo informa — no arregla nada.")
    print("=" * ANCHO)
    return 0


if __name__ == "__main__":
    sys.exit(main())
