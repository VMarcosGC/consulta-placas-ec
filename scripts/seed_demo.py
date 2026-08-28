"""Datos DEMO para poblar el marketplace con volumen realista.

**Para qué sirve.** Marcos necesita navegar el feed del market con ~100 publicaciones
(fotos, fichas técnicas de completitud variada, planes light/premium, verificaciones)
para probar diseño, paginación y rendimiento en gama baja. Este script SIEMBRA esos
datos ficticios y sabe LIMPIARLOS.

**Esto es data de demo, no de producción.** Crea una cuenta ficticia
(`demo-seed@carstore.local`) y cuelga TODO de ella: un `Vendedor`, ~100
`PublicacionInterna` `activa`, sus `FichaPublicacion` y sus `FotoPublicacion`. Borrar la
cuenta borra todo lo sembrado (FKs `ON DELETE CASCADE`), pero `--borrar` lo hace en orden
explícito para poder contarlo. Nunca toca filas que no cuelguen de esa cuenta: las ~6
publicaciones reales/de prueba que ya existan se quedan intactas.

**Uso**

    python -m scripts.seed_demo            # crea o asegura los datos demo (idempotente)
    python -m scripts.seed_demo --borrar   # elimina TODO lo que sembró y sale

Correrlo dos veces no duplica: las publicaciones se identifican por su placa (generada
de forma determinista con una semilla fija) y sólo se crea lo que falta.

**Conexión.** Explícita a Neon leyendo `DATABASE_URL` de `.env` (NO vía
`src.core.database`, que en una máquina de dev resuelve la BD local por `.env.local`,
TASK-010). Mismo criterio que `scripts/estado.py`; la única diferencia con su snippet es
que aquí se conserva/repone el driver `postgresql+psycopg://` porque este script usa
SQLAlchemy (estado.py usa psycopg "crudo", que no entiende ese prefijo). El engine es
aparte; los enums, los schemas de ficha y las **tablas** (`Model.__table__`) salen de
`src/modules/...`.

**Escrituras por SQLAlchemy Core, no por el ORM.** Se usa `insert()/delete()` contra
`Model.__table__` en vez de instanciar los modelos, para que el script sea inmune a que
un modelo declare una columna que Neon todavía no tiene (p. ej. una migración pendiente
de aplicar): el ORM mete esa columna en cada SELECT/RETURNING y revienta; Core sólo toca
las columnas que nombras.

Sin dependencias nuevas: SQLAlchemy, psycopg y python-dotenv ya están en requirements;
los datos se generan con `random` de la stdlib y listas propias.
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, delete, func, insert, select, update
from sqlalchemy.orm import Session, sessionmaker

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from passlib.context import CryptContext  # noqa: E402  (dep ya instalada, no abre red)

# Registra TODOS los modelos ORM en `Base.metadata`: sin esto, configurar el mapper de
# `Usuario` falla al resolver `relationship("Vehiculo")` y demás clases no importadas.
import src.registry  # noqa: E402,F401

from src.modules.auth.models import Usuario, TransaccionToken  # noqa: E402
from src.modules.marketplace.models import (  # noqa: E402
    ContactoRevelado,
    EstadoPublicacion,
    EstadoVerificacion,
    FichaPublicacion,
    FotoPublicacion,
    PlanPublicacion,
    PublicacionInterna,
    TipoVendedor,
    Vendedor,
)
from src.modules.marketplace.schemas import (  # noqa: E402
    BloqueCarroceria,
    BloqueInteriores,
    BloqueMotorSuspension,
    ExtraVehiculo,
)

# Tablas Core (no las clases): las escrituras van por `insert()/delete()` sobre estos
# objetos, así el script no arrastra columnas que el modelo declare y Neon no tenga.
_T_USUARIO = Usuario.__table__
_T_TX = TransaccionToken.__table__
_T_VENDEDOR = Vendedor.__table__
_T_PUB = PublicacionInterna.__table__
_T_FICHA = FichaPublicacion.__table__
_T_FOTO = FotoPublicacion.__table__
_T_CONTACTO = ContactoRevelado.__table__


# ═══════════════════════ Constantes de la siembra ═══════════════════════

# Ancla de todo lo sembrado. Todo cuelga de esta cuenta → borrarla = borrar la demo.
EMAIL_DEMO = "demo-seed@carstore.local"
NOMBRE_CUENTA_DEMO = "Cuenta Demo (seed)"
NOMBRE_PUBLICO_VENDEDOR = "Autos Demo"
# E.164 sin `+` (formato que consume wa.me), para que "Ver teléfono" funcione en la demo.
TELEFONO_VENDEDOR = "593999000111"

# Cantidad objetivo de publicaciones internas.
N_PUBLICACIONES = 100
# Cuántas llevan ficha técnica (completitud variada).
N_CON_FICHA = 65
# Cuántas son premium (destacadas).
N_PREMIUM = 20
# Cuántas de las premium quedan "verificado por la plataforma".
N_VERIFICADAS = 6
# Cuántas llevan el sello "revisado por mecánica" (migración 0028). Simula el ejercicio
# del código de un solo uso que la mecánica le entrega al vendedor: acá se aplica directo.
N_CON_SELLO_MECANICA = 12

# Semilla fija: la misma corrida produce las mismas placas y datos → idempotencia real.
SEMILLA = 20260827

# Saldo de cortesía (mismo valor que `auth.models.SALDO_INICIAL_TOKENS`; se replica aquí
# para no acoplar el seed a esa constante). Monetización suspendida (§1.0.3): no se gasta.
SALDO_DEMO = 5

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ─────────────────── Catálogo de autos comunes en Ecuador ───────────────────
# (marca, modelo, segmento, anio_min). El segmento gobierna precio, kilometraje,
# carrocería y tracción. anio_min recorta modelos que no existían en 2008.

CATALOGO: list[tuple[str, str, str, int]] = [
    ("Chevrolet", "Sail", "sedan", 2010),
    ("Chevrolet", "Aveo", "sedan", 2008),
    ("Chevrolet", "Spark GT", "hatchback", 2010),
    ("Chevrolet", "Onix", "sedan", 2016),
    ("Chevrolet", "Tracker", "suv", 2014),
    ("Kia", "Rio", "sedan", 2008),
    ("Kia", "Sportage", "suv", 2008),
    ("Kia", "Picanto", "hatchback", 2008),
    ("Kia", "Soul", "suv", 2012),
    ("Hyundai", "Accent", "sedan", 2008),
    ("Hyundai", "Tucson", "suv", 2008),
    ("Hyundai", "Creta", "suv", 2017),
    ("Toyota", "Corolla", "sedan", 2008),
    ("Toyota", "Hilux", "camioneta", 2008),
    ("Toyota", "RAV4", "suv", 2008),
    ("Toyota", "Yaris", "sedan", 2008),
    ("Toyota", "Corolla Cross", "suv", 2021),
    ("Mazda", "3", "sedan", 2008),
    ("Mazda", "CX-5", "suv", 2013),
    ("Mazda", "BT-50", "camioneta", 2008),
    ("Nissan", "Sentra", "sedan", 2008),
    ("Nissan", "Frontier", "camioneta", 2008),
    ("Nissan", "Versa", "sedan", 2012),
    ("Renault", "Duster", "suv", 2012),
    ("Renault", "Logan", "sedan", 2008),
    ("Renault", "Sandero", "hatchback", 2008),
    ("Volkswagen", "Gol", "hatchback", 2008),
    ("Volkswagen", "Golf", "hatchback", 2008),
    ("Suzuki", "Grand Vitara", "suv", 2008),
    ("Great Wall", "Wingle 5", "camioneta", 2011),
    ("Chery", "Tiggo 2", "suv", 2017),
    ("Hino", "300", "camion", 2008),
]

# Banda de precio USD del mercado de usados: (piso ~2008, techo ~2024).
BANDA_PRECIO = {
    "hatchback": (4000, 17000),
    "sedan": (5000, 24000),
    "suv": (9000, 39000),
    "camioneta": (11000, 44000),
    "camion": (18000, 46000),
}
PRECIO_MIN, PRECIO_MAX = 2500, 45000

CILINDRAJE = {
    "hatchback": [1000, 1200, 1400],
    "sedan": [1400, 1500, 1600, 1800, 2000],
    "suv": [1600, 2000, 2400, 2500],
    "camioneta": [2400, 2500, 2800, 3000],
    "camion": [4000, 5000],
}

# Catálogo cerrado de `CiudadPublicacion` (schemas.py), con pesos ~población/actividad.
CIUDADES = [
    "Quito", "Guayaquil", "Cuenca", "Ambato", "Manta", "Loja",
    "Machala", "Santo Domingo", "Portoviejo", "Ibarra", "Riobamba", "Esmeraldas",
]
PESOS_CIUDAD = [26, 24, 11, 8, 7, 4, 4, 5, 4, 3, 2.5, 2]

SELLOS_TITULO = [
    "único dueño", "full extras", "poco kilometraje", "recién importado",
    "mantenimiento al día", "precio conversable",
]

# Mecánicas ficticias para el sello "revisado por mecánica". (nombre, ciudad).
MECANICAS_SELLO = [
    ("Tecnicentro Andrade", "Quito"),
    ("Mecánica Total Vera", "Guayaquil"),
    ("AutoDiagnóstico Cedeño", "Manta"),
    ("Taller El Motorista", "Cuenca"),
    ("Servifrenos Loja", "Loja"),
    ("MultiMarcas Guerrero", "Ambato"),
]

APERTURAS = [
    "Vendo mi {modelo}, siempre guardado en garaje.",
    "Se vende {marca} {modelo} en muy buen estado.",
    "Auto familiar, bien cuidado y sin apuros de venta.",
    "Cambio de vehículo, por eso lo dejo ir.",
]
CUERPOS = [
    "Mantenimientos al día en taller autorizado.",
    "Llantas en buen estado y batería nueva.",
    "Matrícula al día y sin multas pendientes.",
    "Motor y caja funcionan sin novedad.",
]
CIERRES = [
    "Se acepta revisión mecánica de tu confianza.",
    "Recibo auto de menor valor como parte de pago.",
    "Escríbeme para coordinar una prueba de manejo.",
    "Trato directo con el dueño, sin intermediarios.",
]

COLORES = [
    "Blanco", "Plata", "Gris", "Negro", "Rojo", "Azul marino", "Beige", "Verde militar",
]
AUDIO = [
    'Pantalla táctil 7" con Bluetooth',
    "Radio original con USB y auxiliar",
    "Android Auto y Apple CarPlay",
    "Equipo Pioneer con parlantes nuevos",
]
CAMBIOS_RECIENTES = [
    "Amortiguadores delanteros nuevos (2025).",
    "Correa de distribución cambiada hace 10.000 km.",
    "Frenos y discos nuevos hace 5.000 km.",
    "Rótulas y terminales cambiados en el último control.",
]
OBS_MOTOR = [
    "Motor no fuma, arranque en frío normal.",
    "Mantenimiento cada 5.000 km, facturas a la vista.",
    "Sin ruidos ni testigos en el tablero.",
]
OBS_CARRO = [
    "Pintura conserva el brillo de fábrica.",
    "Detalles menores de uso en el parachoques.",
    "Sin masilla, latonería original.",
]
OBS_INT = [
    "Interior limpio, sin olores.",
    "Tapicería sin roturas ni quemaduras.",
    "Aire acondicionado enfría bien.",
]

EXTRAS_POOL = [
    ("Láminas de seguridad", "Polarizado legal en todas las ventanas."),
    ("Llantas nuevas", "Juego completo cambiado en 2025."),
    ("Alarma con localizador GPS", None),
    ("Aros de aleación", None),
    ("Cámara de retroceso", None),
    ("Sensores de parqueo", None),
    ("Neblineros", None),
    ("Asientos con forros de cuerina", None),
    ("Batería nueva", "Instalada hace 3 meses."),
]

# Pool de imágenes de autos: URLs directas de Unsplash (cargan en un <img> sin auth).
# Verificadas el 2026-08-27: las 18 devuelven HTTP 200 con bytes de imagen (image/jpeg).
# El endpoint normal exige que la URL sea de nuestro Cloudinary; este script inserta
# directo en BD y se salta esa validación A PROPÓSITO (son datos demo).
_UNSPLASH_IDS = [
    "photo-1503376780353-7e6692767b70",  # Porsche Panamera negro
    "photo-1552519507-da3b142c6e3d",      # Chevrolet Camaro azul
    "photo-1494976388531-d1058494cdd8",   # Ford Mustang negro
    "photo-1583121274602-3e2820c69888",   # deportivo rojo
    "photo-1541899481282-d53bffe3c35d",   # hatchback turquesa
    "photo-1568605117036-5fe5e7bab0b7",   # coupé plateado en carretera
    "photo-1502877338535-766e1452684a",   # coupé azul de perfil
    "photo-1549317661-bd32c8ce0db2",      # Fiat 500 celeste
    "photo-1550355291-bbee04a92027",      # hot-hatch rojo de frente
    "photo-1494905998402-395d579af36f",   # coupé oscuro al atardecer
    "photo-1471479917193-f00955256257",   # auto de noche en ciudad
    "photo-1544636331-e26879cd4d9b",      # deportivo blanco de frente
    "photo-1533106418989-88406c7cc8ca",   # faros encendidos en garaje
    "photo-1605559424843-9e4c228bf1c2",   # coupé amarillo
    "photo-1489824904134-891ab64532f1",   # Volkswagen Escarabajo naranja
    "photo-1553440569-bcc63803a83d",      # deportivo rojo en bosque
    "photo-1542362567-b07e54358753",      # deportivo blanco
    "photo-1511919884226-fd3cad34687c",   # deportivo amarillo
]
POOL_FOTOS = [
    f"https://images.unsplash.com/{pid}?auto=format&fit=crop&w=900&q=70"
    for pid in _UNSPLASH_IDS
]

CAMPOS_FICHA: list[tuple[str, str]] = [
    ("motor_suspension", "combustible"),
    ("motor_suspension", "cilindraje_cc"),
    ("motor_suspension", "transmision"),
    ("motor_suspension", "traccion"),
    ("motor_suspension", "estado_motor"),
    ("motor_suspension", "estado_suspension"),
    ("motor_suspension", "fugas_visibles"),
    ("motor_suspension", "cambios_recientes"),
    ("motor_suspension", "observaciones"),
    ("carroceria", "tipo"),
    ("carroceria", "numero_puertas"),
    ("carroceria", "color"),
    ("carroceria", "estado_pintura"),
    ("carroceria", "choques_reparados"),
    ("carroceria", "oxido_visible"),
    ("carroceria", "estado_general"),
    ("carroceria", "observaciones"),
    ("interiores", "material_asientos"),
    ("interiores", "estado_asientos"),
    ("interiores", "aire_acondicionado"),
    ("interiores", "sistema_audio"),
    ("interiores", "estado_tablero"),
    ("interiores", "observaciones"),
]

_SCHEMA_BLOQUE = {
    "motor_suspension": BloqueMotorSuspension,
    "carroceria": BloqueCarroceria,
    "interiores": BloqueInteriores,
}


# ═══════════════════════ Conexión explícita a Neon ═══════════════════════

def _dsn_neon() -> str:
    """DSN de producción leído directo de `.env` (nunca `src.core.database`).

    Conserva/repone el driver `postgresql+psycopg://` que SQLAlchemy necesita para
    hablar con psycopg 3 (Render/Neon a veces emiten `postgresql://` a secas).
    """
    valores = dotenv_values(RAIZ / ".env")
    crudo = (valores.get("DATABASE_URL") or "").strip()
    if not crudo:
        print(
            "ERROR: `.env` no tiene DATABASE_URL. Este script siembra contra Neon y "
            "necesita esa cadena. Configúrala en `.env` (no en `.env.local`) y reintenta."
        )
        raise SystemExit(2)
    if crudo.startswith("postgresql+"):
        return crudo
    if crudo.startswith("postgresql://"):
        return "postgresql+psycopg://" + crudo[len("postgresql://"):]
    if crudo.startswith("postgres://"):
        return "postgresql+psycopg://" + crudo[len("postgres://"):]
    return crudo


def _abrir_sesion() -> tuple[Session, object]:
    engine = create_engine(_dsn_neon(), pool_pre_ping=True, future=True)
    fabrica = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return fabrica(), engine


# ═══════════════════════ Generadores deterministas ═══════════════════════

def _placa(rng: random.Random, usadas: set[str]) -> str:
    """Placa ecuatoriana válida para `validar_placa`: 3 letras + 3 o 4 dígitos."""
    provincias = "ABCEGHILMOPSTUXZ"
    while True:
        letras = rng.choice(provincias) + "".join(rng.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(2))
        digitos = str(rng.randint(100, 9999)) if rng.random() < 0.65 else f"{rng.randint(0, 999):03d}"
        placa = letras + digitos
        if placa not in usadas:
            usadas.add(placa)
            return placa


def _estado_componente(rng: random.Random) -> str:
    return rng.choices(
        ["excelente", "bueno", "regular", "requiere_atencion"],
        weights=[25, 50, 20, 5],
    )[0]


def _valor_campo(bloque: str, campo: str, rng: random.Random, seg: str) -> object:
    if bloque == "motor_suspension":
        if campo == "combustible":
            if seg in ("camioneta", "camion"):
                return rng.choice(["diesel", "diesel", "gasolina"])
            return rng.choice(["gasolina"] * 6 + ["glp", "hibrido", "diesel"])
        if campo == "cilindraje_cc":
            return rng.choice(CILINDRAJE[seg])
        if campo == "transmision":
            return rng.choice(["manual", "manual", "automatica", "automatica", "cvt"])
        if campo == "traccion":
            if seg == "suv":
                return rng.choice(["4x2", "4x2", "awd", "4x4"])
            if seg in ("camioneta", "camion"):
                return rng.choice(["4x2", "4x4", "4x4"])
            return "4x2"
        if campo in ("estado_motor", "estado_suspension"):
            return _estado_componente(rng)
        if campo == "fugas_visibles":
            return rng.random() < 0.12
        if campo == "cambios_recientes":
            return rng.choice(CAMBIOS_RECIENTES)
        if campo == "observaciones":
            return rng.choice(OBS_MOTOR)
    elif bloque == "carroceria":
        if campo == "tipo":
            return seg  # sedan/hatchback/suv/camioneta/camion ∈ TipoCarroceria
        if campo == "numero_puertas":
            return {
                "sedan": 4, "suv": 5, "hatchback": rng.choice([5, 5, 3]),
                "camioneta": rng.choice([2, 4]), "camion": 2,
            }[seg]
        if campo == "color":
            return rng.choice(COLORES)
        if campo == "estado_pintura":
            return rng.choice(
                ["original", "original", "retoques", "repintado_parcial", "repintado_total"]
            )
        if campo == "choques_reparados":
            return rng.random() < 0.18
        if campo == "oxido_visible":
            return rng.random() < 0.10
        if campo == "estado_general":
            return _estado_componente(rng)
        if campo == "observaciones":
            return rng.choice(OBS_CARRO)
    elif bloque == "interiores":
        if campo == "material_asientos":
            return rng.choice(["tela", "tela", "cuerina", "cuero", "mixto"])
        if campo == "estado_asientos":
            return _estado_componente(rng)
        if campo == "aire_acondicionado":
            return rng.random() < 0.90
        if campo == "sistema_audio":
            return rng.choice(AUDIO)
        if campo == "estado_tablero":
            return _estado_componente(rng)
        if campo == "observaciones":
            return rng.choice(OBS_INT)
    raise KeyError((bloque, campo))


def _construir_ficha(
    rng: random.Random, seg: str, objetivo: float
) -> tuple[dict | None, dict | None, dict | None, list[dict]]:
    """Devuelve (motor_suspension, carroceria, interiores, extras) ya validados por
    los schemas Pydantic. Un bloque sin campos llenos queda en `None`."""
    prob = min(0.98, max(0.05, objetivo + rng.uniform(-0.06, 0.06)))
    crudos: dict[str, dict] = {"motor_suspension": {}, "carroceria": {}, "interiores": {}}
    for bloque, campo in CAMPOS_FICHA:
        if rng.random() < prob:
            crudos[bloque][campo] = _valor_campo(bloque, campo, rng, seg)

    def _norm(bloque: str) -> dict | None:
        raw = crudos[bloque]
        if not raw:
            return None
        # Valida catálogos y `extra="forbid"`; normaliza a dict sin claves None.
        return _SCHEMA_BLOQUE[bloque](**raw).model_dump(exclude_none=True)

    if objetivo >= 0.5:
        n_extras = rng.choice([0, 1, 1, 2, 3])
    else:
        n_extras = 1 if rng.random() < 0.15 else 0
    extras: list[dict] = []
    for nombre, detalle in rng.sample(EXTRAS_POOL, n_extras):
        datos = {"nombre": nombre}
        if detalle:
            datos["detalle"] = detalle
        extras.append(ExtraVehiculo(**datos).model_dump(exclude_none=True))

    return _norm("motor_suspension"), _norm("carroceria"), _norm("interiores"), extras


def _fotos_para(idx: int, rng: random.Random) -> list[tuple[str, int, str | None]]:
    """1 a 4 fotos por publicación, cicladas sobre el pool con offset por índice."""
    n = rng.choice([1, 1, 2, 2, 2, 3, 3, 4])
    inicio = (idx * 3) % len(POOL_FOTOS)
    salida: list[tuple[str, int, str | None]] = []
    for orden in range(n):
        url = POOL_FOTOS[(inicio + orden) % len(POOL_FOTOS)]
        bloque = None if orden == 0 else rng.choice(
            [None, None, "carroceria", "interiores", "motor_suspension", "general"]
        )
        salida.append((url, orden, bloque))
    return salida


def _construir_specs() -> list[dict]:
    """Las 100 publicaciones como dicts puros y deterministas (semilla fija)."""
    rng = random.Random(SEMILLA)
    ahora = datetime.now(timezone.utc)

    premium_idx = set(rng.sample(range(N_PUBLICACIONES), N_PREMIUM))
    verificadas_idx = set(rng.sample(sorted(premium_idx), N_VERIFICADAS))
    ficha_idx = set(rng.sample(range(N_PUBLICACIONES), N_CON_FICHA))
    # El sello de mecánica solo tiene sentido en anuncios con ficha (la revisión
    # respalda lo declarado): se eligen de entre esos.
    sello_idx = set(rng.sample(sorted(ficha_idx), N_CON_SELLO_MECANICA))

    usadas: set[str] = set()
    specs: list[dict] = []
    for idx in range(N_PUBLICACIONES):
        marca, modelo, seg, anio_min = CATALOGO[idx % len(CATALOGO)]
        # Re-mezcla para que no salgan en bloques del mismo modelo.
        marca, modelo, seg, anio_min = rng.choice(CATALOGO)
        anio = rng.randint(max(2008, anio_min), 2024)

        frac = (anio - 2008) / (2024 - 2008)
        piso, techo = BANDA_PRECIO[seg]
        precio = (piso + frac * (techo - piso)) * rng.uniform(0.82, 1.12)
        precio = max(PRECIO_MIN, min(PRECIO_MAX, precio))
        paso = 500 if precio < 12000 else 1000
        precio_usd = Decimal(int(round(precio / paso) * paso))

        edad = 2026 - anio
        km = edad * rng.randint(7000, 21000) + rng.randint(-4000, 4000)
        km = max(0, min(360000, km))
        km = int(round(km / 1000) * 1000)
        kilometraje = None if rng.random() < 0.06 else km

        ciudad = rng.choices(CIUDADES, weights=PESOS_CIUDAD)[0]

        r = rng.random()
        if r < 0.55:
            titulo = None
        elif r < 0.85:
            titulo = f"{marca} {modelo} {anio}"
        else:
            titulo = f"{marca} {modelo} {anio} · {rng.choice(SELLOS_TITULO)}"

        if rng.random() < 0.72:
            descripcion = " ".join([
                rng.choice(APERTURAS).format(marca=marca, modelo=modelo),
                rng.choice(CUERPOS),
                rng.choice(CIERRES),
            ])
        else:
            descripcion = None

        es_premium = idx in premium_idx
        es_verificada = idx in verificadas_idx
        creado_en = ahora - timedelta(
            days=rng.randint(0, 75), hours=rng.randint(0, 23), minutes=rng.randint(0, 59)
        )
        verificado_en = None
        if es_verificada:
            verificado_en = min(ahora, creado_en + timedelta(days=rng.randint(1, 10)))

        ficha = None
        if idx in ficha_idx:
            b = rng.random()
            objetivo = 0.18 if b < 0.20 else (0.50 if b < 0.65 else 0.90)
            ficha = _construir_ficha(rng, seg, objetivo)

        # Sello "revisado por mecánica": nombre + ciudad de una mecánica ficticia y una
        # fecha posterior a la publicación (la revisión ocurre con el auto ya en venta).
        mecanica_nombre = mecanica_ciudad = certificado_mecanica_en = None
        if idx in sello_idx:
            mecanica_nombre, mecanica_ciudad = rng.choice(MECANICAS_SELLO)
            certificado_mecanica_en = min(
                ahora, creado_en + timedelta(days=rng.randint(1, 14))
            )

        fotos = _fotos_para(idx, rng)

        specs.append({
            "placa": _placa(rng, usadas),
            "marca": marca,
            "modelo": modelo,
            "segmento": seg,
            "anio": anio,
            "titulo": titulo,
            "descripcion": descripcion,
            "ciudad": ciudad,
            "kilometraje": kilometraje,
            "precio_usd": precio_usd,
            "plan": PlanPublicacion.PREMIUM.value if es_premium else PlanPublicacion.LIGHT.value,
            "destacado": es_premium,
            "estado_verificacion": (
                EstadoVerificacion.VERIFICADO.value if es_verificada
                else EstadoVerificacion.NO_VERIFICADO.value
            ),
            "verificado_en": verificado_en,
            "creado_en": creado_en,
            "mecanica_nombre": mecanica_nombre,
            "mecanica_ciudad": mecanica_ciudad,
            "certificado_mecanica_en": certificado_mecanica_en,
            "ficha": ficha,
            "fotos": fotos,
        })
    return specs


# ═══════════════════════ Alta / aseguramiento ═══════════════════════

def _ensure_usuario(sesion: Session) -> tuple[int, bool]:
    fila = sesion.execute(
        select(_T_USUARIO.c.id).where(_T_USUARIO.c.email == EMAIL_DEMO)
    ).first()
    if fila is not None:
        return fila[0], False
    uid = sesion.execute(
        insert(_T_USUARIO).values(
            email=EMAIL_DEMO,
            password_hash=_pwd.hash("demo-seed-sin-login"),
            nombre=NOMBRE_CUENTA_DEMO,
            # El CHECK de `usuarios` sólo admite 'local' o 'google' (migración 0025); la
            # tarea pedía 'password', que violaría la constraint. 'local' es el equivalente.
            proveedor_autenticacion="local",
            email_verificado=True,
            saldo_tokens=SALDO_DEMO,
        ).returning(_T_USUARIO.c.id)
    ).scalar_one()
    # Auditoría del crédito inicial (§10.3): el saldo nace en 5, queda registrado.
    sesion.execute(insert(_T_TX).values(
        usuario_id=uid, monto=SALDO_DEMO, motivo="saldo_inicial",
    ))
    return uid, True


def _ensure_vendedor(sesion: Session, usuario_id: int) -> tuple[int, bool]:
    valores = dict(
        tipo=TipoVendedor.PARTICULAR.value,
        nombre_publico=NOMBRE_PUBLICO_VENDEDOR,
        telefono=TELEFONO_VENDEDOR,
        telefono_verificado=False,
    )
    fila = sesion.execute(
        select(_T_VENDEDOR.c.id).where(_T_VENDEDOR.c.usuario_id == usuario_id)
    ).first()
    if fila is not None:
        vid = fila[0]
        sesion.execute(update(_T_VENDEDOR).where(_T_VENDEDOR.c.id == vid).values(**valores))
        return vid, False
    vid = sesion.execute(
        insert(_T_VENDEDOR).values(usuario_id=usuario_id, **valores)
        .returning(_T_VENDEDOR.c.id)
    ).scalar_one()
    return vid, True


def _filas_fotos(publicacion_id: int, spec_fotos: list[tuple[str, int, str | None]]) -> list[dict]:
    return [
        {"publicacion_id": publicacion_id, "url": url, "orden": orden, "bloque": bloque}
        for url, orden, bloque in spec_fotos
    ]


def sembrar(sesion: Session) -> dict:
    specs = _construir_specs()
    usuario_id, usuario_creado = _ensure_usuario(sesion)
    vendedor_id, vendedor_creado = _ensure_vendedor(sesion, usuario_id)

    id_por_placa = {
        placa: pid
        for pid, placa in sesion.execute(
            select(_T_PUB.c.id, _T_PUB.c.placa)
            .where(_T_PUB.c.usuario_id == usuario_id)
        )
    }
    ids_existentes = list(id_por_placa.values())

    con_ficha: set[int] = set()
    con_fotos: set[int] = set()
    if ids_existentes:
        con_ficha = set(sesion.scalars(
            select(_T_FICHA.c.publicacion_id)
            .where(_T_FICHA.c.publicacion_id.in_(ids_existentes))
        ))
        con_fotos = set(sesion.scalars(
            select(_T_FOTO.c.publicacion_id)
            .where(_T_FOTO.c.publicacion_id.in_(ids_existentes)).distinct()
        ))

    pubs_creadas = pubs_existentes = fichas_creadas = fotos_creadas = 0
    sellos_creados = 0

    for spec in specs:
        pid = id_por_placa.get(spec["placa"])
        if pid is None:
            # `premium_cobrado_en` queda NULL (monetización suspendida, §1.0.3). Las
            # columnas con server_default que no se nombran (timestamps, y `renovada_en`
            # cuando la 0026 se aplique) las pone la BD.
            pid = sesion.execute(
                insert(_T_PUB).values(
                    usuario_id=usuario_id,
                    vendedor_id=vendedor_id,
                    vehiculo_id=None,
                    placa=spec["placa"],
                    titulo=spec["titulo"],
                    descripcion=spec["descripcion"],
                    ciudad=spec["ciudad"],
                    kilometraje=spec["kilometraje"],
                    precio_usd=spec["precio_usd"],
                    plan=spec["plan"],
                    estado=EstadoPublicacion.ACTIVA.value,
                    estado_verificacion=spec["estado_verificacion"],
                    verificado_en=spec["verificado_en"],
                    destacado=spec["destacado"],
                    creado_en=spec["creado_en"],
                    mecanica_nombre=spec["mecanica_nombre"],
                    mecanica_ciudad=spec["mecanica_ciudad"],
                    certificado_mecanica_en=spec["certificado_mecanica_en"],
                ).returning(_T_PUB.c.id)
            ).scalar_one()
            pubs_creadas += 1
            if spec["mecanica_nombre"]:
                sellos_creados += 1
        else:
            pubs_existentes += 1
            # Top-up idempotente: si la fila ya existía sin sello y a este spec le
            # toca uno, se agrega (no pisa un sello puesto a mano).
            if spec["mecanica_nombre"]:
                n = sesion.execute(
                    update(_T_PUB)
                    .where(_T_PUB.c.id == pid, _T_PUB.c.mecanica_nombre.is_(None))
                    .values(
                        mecanica_nombre=spec["mecanica_nombre"],
                        mecanica_ciudad=spec["mecanica_ciudad"],
                        certificado_mecanica_en=spec["certificado_mecanica_en"],
                    )
                ).rowcount
                sellos_creados += n

        # Ficha y fotos: se crean si la publicación es nueva o si le faltan (p. ej.
        # alguien borró sólo las fotos y se vuelve a correr el seed).
        if spec["ficha"] is not None and pid not in con_ficha:
            ms, ca, it, extras = spec["ficha"]
            sesion.execute(insert(_T_FICHA).values(
                publicacion_id=pid, motor_suspension=ms, carroceria=ca,
                interiores=it, extras=extras,
            ))
            fichas_creadas += 1
        if spec["fotos"] and pid not in con_fotos:
            sesion.execute(insert(_T_FOTO), _filas_fotos(pid, spec["fotos"]))
            fotos_creadas += len(spec["fotos"])

    sesion.commit()

    total_demo = sesion.scalar(
        select(func.count()).select_from(_T_PUB)
        .where(_T_PUB.c.usuario_id == usuario_id)
    )
    total_tabla = sesion.scalar(select(func.count()).select_from(_T_PUB))

    return {
        "usuario_id": usuario_id,
        "usuario_creado": usuario_creado,
        "vendedor_id": vendedor_id,
        "vendedor_creado": vendedor_creado,
        "pubs_creadas": pubs_creadas,
        "pubs_existentes": pubs_existentes,
        "fichas_creadas": fichas_creadas,
        "fotos_creadas": fotos_creadas,
        "sellos_creados": sellos_creados,
        "total_demo": total_demo,
        "total_tabla": total_tabla,
    }


# ═══════════════════════ Limpieza ═══════════════════════

def borrar(sesion: Session) -> dict:
    fila = sesion.execute(
        select(_T_USUARIO.c.id).where(_T_USUARIO.c.email == EMAIL_DEMO)
    ).first()
    if fila is None:
        return {"vacio": True}
    usuario_id = fila[0]

    pub_ids = list(sesion.scalars(
        select(_T_PUB.c.id).where(_T_PUB.c.usuario_id == usuario_id)
    ))

    n_fotos = n_fichas = n_contactos = n_pubs = 0
    if pub_ids:
        n_fotos = sesion.execute(
            delete(_T_FOTO).where(_T_FOTO.c.publicacion_id.in_(pub_ids))
        ).rowcount
        n_fichas = sesion.execute(
            delete(_T_FICHA).where(_T_FICHA.c.publicacion_id.in_(pub_ids))
        ).rowcount
        # Defensivo: el seed no crea contactos revelados, pero si una demo previa los
        # dejó (o el frontend los generó al probar), se van con la publicación.
        n_contactos = sesion.execute(
            delete(_T_CONTACTO).where(_T_CONTACTO.c.publicacion_interna_id.in_(pub_ids))
        ).rowcount
        n_pubs = sesion.execute(
            delete(_T_PUB).where(_T_PUB.c.usuario_id == usuario_id)
        ).rowcount

    n_vendedores = sesion.execute(
        delete(_T_VENDEDOR).where(_T_VENDEDOR.c.usuario_id == usuario_id)
    ).rowcount
    n_tx = sesion.execute(
        delete(_T_TX).where(_T_TX.c.usuario_id == usuario_id)
    ).rowcount
    n_user = sesion.execute(
        delete(_T_USUARIO).where(_T_USUARIO.c.id == usuario_id)
    ).rowcount

    sesion.commit()
    return {
        "vacio": False,
        "fotos": n_fotos,
        "fichas": n_fichas,
        "contactos": n_contactos,
        "publicaciones": n_pubs,
        "vendedores": n_vendedores,
        "transacciones": n_tx,
        "usuarios": n_user,
    }


# ═══════════════════════ main ═══════════════════════

def _uso() -> None:
    print(__doc__)


def main(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    args = set(argv[1:])
    if args - {"--borrar"}:
        _uso()
        return 2
    modo_borrar = "--borrar" in args

    sesion, engine = _abrir_sesion()
    try:
        if modo_borrar:
            print("=" * 64)
            print("  SEED DEMO — LIMPIEZA")
            print("=" * 64)
            r = borrar(sesion)
            if r.get("vacio"):
                print(f"\n  No existe la cuenta {EMAIL_DEMO}: nada que borrar.")
                return 0
            print(f"\n  Cuenta demo: {EMAIL_DEMO}")
            print(f"  Filas eliminadas:")
            print(f"    fotos_publicacion .......... {r['fotos']}")
            print(f"    fichas_publicacion ......... {r['fichas']}")
            print(f"    contactos_revelados ........ {r['contactos']}")
            print(f"    publicaciones_internas ..... {r['publicaciones']}")
            print(f"    vendedores ................. {r['vendedores']}")
            print(f"    transacciones_tokens ....... {r['transacciones']}")
            print(f"    usuarios .................... {r['usuarios']}")
            print("\n  BD de vuelta a como estaba antes de la siembra.")
            return 0

        print("=" * 64)
        print("  SEED DEMO — SIEMBRA")
        print("=" * 64)
        r = sembrar(sesion)
        print(f"\n  Usuario demo: id={r['usuario_id']} ({EMAIL_DEMO}) "
              f"[{'creado' if r['usuario_creado'] else 'reutilizado'}]")
        print(f"  Vendedor:     id={r['vendedor_id']} ('{NOMBRE_PUBLICO_VENDEDOR}', "
              f"tel {TELEFONO_VENDEDOR}) [{'creado' if r['vendedor_creado'] else 'reutilizado'}]")
        print()
        print(f"  Publicaciones internas creadas ... {r['pubs_creadas']}")
        print(f"  Publicaciones que ya existían .... {r['pubs_existentes']}")
        print(f"  Fichas técnicas creadas .......... {r['fichas_creadas']}")
        print(f"  Fotos creadas ................... {r['fotos_creadas']}")
        print(f"  Sellos de mecánica aplicados ..... {r['sellos_creados']}")
        print()
        print(f"  publicaciones_internas de la demo . {r['total_demo']}")
        print(f"  publicaciones_internas EN TOTAL ... {r['total_tabla']}")
        print("\n  Listo. Limpieza: python -m scripts.seed_demo --borrar")
        return 0
    finally:
        sesion.close()
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
