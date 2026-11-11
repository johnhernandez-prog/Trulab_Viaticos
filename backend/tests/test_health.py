import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import __version__
from app.core.config import get_settings
from app.core.db import bd_disponible
from app.main import create_app


def test_health_con_bd_real_responde_ok(client: TestClient) -> None:
    respuesta = client.get("/api/v1/health")

    assert respuesta.status_code == 200
    assert respuesta.json() == {"status": "ok", "version": __version__, "db": "ok"}


def test_health_sin_bd_responde_503(app: FastAPI, client: TestClient) -> None:
    app.dependency_overrides[bd_disponible] = lambda: False

    respuesta = client.get("/api/v1/health")

    assert respuesta.status_code == 503
    assert respuesta.json() == {"status": "error", "version": __version__, "db": "error"}


def test_documentacion_bajo_prefijo_versionado(client: TestClient) -> None:
    openapi = client.get("/api/v1/openapi.json")

    assert openapi.status_code == 200
    assert "/api/v1/health" in openapi.json()["paths"]
    assert client.get("/api/v1/docs").status_code == 200


def test_documentacion_deshabilitada_en_produccion(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "production")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as cliente:
            assert cliente.get("/api/v1/openapi.json").status_code == 404
            assert cliente.get("/api/v1/docs").status_code == 404
    finally:
        get_settings.cache_clear()
