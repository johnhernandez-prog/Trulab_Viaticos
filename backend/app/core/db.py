"""Conexión a PostgreSQL con SQLAlchemy 2 en modo síncrono (ADR-003).

Contexto de RLS (S1-09, base de las políticas de S2-03): `fijar_contexto_rls()` guarda el usuario
y el rol en la sesión ORM y los fija con `set_config(..., is_local => true)` (equivale a
`SET LOCAL`) en la transacción actual y, mediante el evento `after_begin`, en cada transacción
nueva de esa sesión. Por ser local a la transacción, el valor nunca sobrevive en una conexión
devuelta al pool.
"""

import uuid
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Connection, Engine, create_engine, event, text
from sqlalchemy.orm import Session, SessionTransaction, sessionmaker

from app.core.config import get_settings
from app.core.enums import Rol

_CLAVE_RLS = "trulab_rls"
_SQL_RLS = text(
    "SELECT set_config('app.usuario_id', :usuario_id, true), set_config('app.rol', :rol, true)"
)


def _aplicar_rls(conexion: Connection, valores: dict[str, str]) -> None:
    conexion.execute(_SQL_RLS, valores)


def fijar_contexto_rls(session: Session, usuario_id: uuid.UUID, rol: Rol | str) -> None:
    """Fija `app.usuario_id` y `app.rol` para las políticas RLS en esta sesión ORM."""
    valores = {"usuario_id": str(usuario_id), "rol": str(Rol(rol))}
    session.info[_CLAVE_RLS] = valores
    _aplicar_rls(session.connection(), valores)


@event.listens_for(Session, "after_begin")
def _reaplicar_rls(session: Session, _transaccion: SessionTransaction, conexion: Connection) -> Any:
    valores = session.info.get(_CLAVE_RLS)
    if valores is not None:
        _aplicar_rls(conexion, valores)


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
