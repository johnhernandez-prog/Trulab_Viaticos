import uuid
from collections.abc import Iterator
from contextlib import nullcontext
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import rate_limit
from app.core.db import fijar_contexto_rls, get_db, get_engine, get_fabrica_sesion
from app.core.enums import Rol
from app.core.mail import Correo, get_mailer
from app.main import create_app
from app.modules.auth.errores import NoAutenticado
from app.modules.auth.google import get_verificador_google

if TYPE_CHECKING:
    from app.modules.archivos.storage import AlmacenamientoLocal

# Contexto de RLS por defecto de `sesion` (S2-03): privilegiado (SUPERADMIN), para que las
# fábricas de `tests/fabricas.py` puedan insertar sin pasar antes por una petición autenticada.
# Las pruebas de aislamiento (RN-01) lo sobrescriben con `fijar_contexto_rls(sesion, ...)` antes
# de afirmar lo que ve un VIAJERO.
_USUARIO_CONFTEST = uuid.UUID("00000000-0000-0000-0000-000000000000")


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # raise_server_exceptions=False: se prueba la respuesta 500 que recibe el cliente.
    with TestClient(app, raise_server_exceptions=False) as cliente:
        yield cliente


@pytest.fixture
def sesion() -> Iterator[Session]:
    """Sesión ORM como `trulab_app` (la conexión de la API) dentro de una transacción.

    Todo se revierte al terminar: las pruebas no dejan datos en la BD. Los `commit()` del código
    bajo prueba se convierten en savepoints (`join_transaction_mode="create_savepoint"`).
    """
    conexion = get_engine().connect()
    transaccion = conexion.begin()
    session = Session(bind=conexion, join_transaction_mode="create_savepoint")
    fijar_contexto_rls(session, _USUARIO_CONFTEST, Rol.SUPERADMIN)
    try:
        yield session
    finally:
        session.close()
        transaccion.rollback()
        conexion.close()


class Buzon:
    """`Mailer` de pruebas: guarda los correos en memoria."""

    def __init__(self) -> None:
        self.correos: list[Correo] = []

    def enviar(self, correo: Correo) -> None:
        self.correos.append(correo)


@pytest.fixture
def buzon() -> Buzon:
    return Buzon()


@pytest.fixture
def tokens_google() -> dict[str, dict[str, Any]]:
    """ID tokens de Google aceptados por el verificador falso: `{token: claims}`."""
    return {}


@pytest.fixture
def api(
    app: FastAPI, sesion: Session, buzon: Buzon, tokens_google: dict[str, dict[str, Any]]
) -> Iterator[TestClient]:
    """Cliente HTTP cuya API usa la sesión de prueba (revertida), el buzón y Google falso."""

    def verificador(id_token: str) -> dict[str, Any]:
        if id_token not in tokens_google:
            raise NoAutenticado("El token de Google no es válido")
        return tokens_google[id_token]

    app.dependency_overrides[get_db] = lambda: sesion
    # Las respuestas en streaming abren su propia sesión en producción; en pruebas reutilizan la
    # sesión revertida (con su contexto de RLS ya fijado por la autenticación de la petición).
    app.dependency_overrides[get_fabrica_sesion] = lambda: lambda _usuario_id, _rol: nullcontext(
        sesion
    )
    app.dependency_overrides[get_mailer] = lambda: buzon
    app.dependency_overrides[get_verificador_google] = lambda: verificador
    rate_limit.contador.reiniciar()
    with TestClient(app, raise_server_exceptions=False) as cliente:
        yield cliente
    rate_limit.contador.reiniciar()


@pytest.fixture
def almacen(app: FastAPI, tmp_path: Path) -> "AlmacenamientoLocal":
    """Almacenamiento local en una carpeta temporal para las pruebas HTTP de archivos (S2-06)."""
    from app.core.config import get_settings
    from app.modules.archivos.storage import AlmacenamientoLocal, get_almacenamiento

    almacenamiento = AlmacenamientoLocal(tmp_path / "almacen", get_settings().jwt_secret)
    app.dependency_overrides[get_almacenamiento] = lambda: almacenamiento
    return almacenamiento
