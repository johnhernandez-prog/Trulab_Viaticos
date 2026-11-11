"""Conexión a PostgreSQL con SQLAlchemy 2 en modo síncrono (ADR-003).

El `SET LOCAL` de las variables de RLS por transacción se agrega con la autorización (S1-09).
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    # El engine se crea al primer uso: importar la app no exige una BD disponible.
    return create_engine(
        get_settings().database_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )


@lru_cache
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición, cerrada siempre al terminar."""
    session = _session_factory()()
    try:
        yield session
    finally:
        session.close()


def bd_disponible() -> bool:
    """`SELECT 1` contra la BD. No lanza excepciones: devuelve False si no hay conexión."""
    try:
        with get_engine().connect() as conexion:
            conexion.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
