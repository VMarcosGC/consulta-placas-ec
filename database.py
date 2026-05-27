import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@localhost:5432/consulta_placas"
)

CACHE_TTL_MINUTOS = int(os.getenv("CACHE_TTL_MINUTOS", "30"))

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRA_MINUTOS = int(os.getenv("JWT_EXPIRA_MINUTOS", "1440"))

# Orígenes permitidos por CORS (frontend Next.js en dev/prod).
# Coma-separados. Default: localhost:3000 (Next.js dev por defecto).
CORS_ORIGINS = [
    origen.strip()
    for origen in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
    if origen.strip()
]

if not JWT_SECRET_KEY:
    raise RuntimeError(
        "JWT_SECRET_KEY no configurada. Generala con: "
        "python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    )

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def obtener_sesion():
    sesion = SessionLocal()
    try:
        yield sesion
    finally:
        sesion.close()
