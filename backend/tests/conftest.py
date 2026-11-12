from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.db import get_engine
from app.main import create_app


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
    try:
        yield session
    finally:
        session.close()
        transaccion.rollback()
        conexion.close()
