from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # raise_server_exceptions=False: se prueba la respuesta 500 que recibe el cliente.
    with TestClient(app, raise_server_exceptions=False) as cliente:
        yield cliente
