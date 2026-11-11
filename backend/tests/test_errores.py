from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import MEDIA_TYPE, ErrorDominio


class ErrorDePrueba(ErrorDominio):
    status = 409
    code = "TRANSICION_INVALIDA"
    title = "La transición no es válida"


def _agregar_rutas_de_prueba(app: FastAPI) -> None:
    @app.get("/prueba/dominio")
    def dominio() -> None:
        raise ErrorDePrueba("La legalización ya cambió de estado.")

    @app.get("/prueba/falla")
    def falla() -> None:
        raise RuntimeError("detalle interno que no debe filtrarse")

    @app.get("/prueba/validacion")
    def validacion(cantidad: int) -> int:
        return cantidad


def test_ruta_inexistente_responde_problem_json(client: TestClient) -> None:
    respuesta = client.get("/api/v1/no-existe")

    assert respuesta.status_code == 404
    assert respuesta.headers["content-type"] == MEDIA_TYPE
    cuerpo = respuesta.json()
    assert cuerpo["code"] == "NO_ENCONTRADO"
    assert cuerpo["status"] == 404
    assert cuerpo["request_id"] == respuesta.headers["X-Request-ID"]


def test_metodo_no_permitido(client: TestClient) -> None:
    respuesta = client.post("/api/v1/health")

    assert respuesta.status_code == 405
    assert respuesta.json()["code"] == "METODO_NO_PERMITIDO"


def test_error_de_dominio(app: FastAPI, client: TestClient) -> None:
    _agregar_rutas_de_prueba(app)

    respuesta = client.get("/prueba/dominio")

    assert respuesta.status_code == 409
    cuerpo = respuesta.json()
    assert cuerpo["code"] == "TRANSICION_INVALIDA"
    assert cuerpo["title"] == "La transición no es válida"
    assert cuerpo["detail"] == "La legalización ya cambió de estado."
    assert cuerpo["type"] == "https://trulab.co/errores/transicion-invalida"


def test_error_de_validacion_lista_campos(app: FastAPI, client: TestClient) -> None:
    _agregar_rutas_de_prueba(app)

    respuesta = client.get("/prueba/validacion", params={"cantidad": "muchos"})

    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["code"] == "VALIDACION"
    assert cuerpo["errors"][0]["field"] == "cantidad"


def test_error_interno_no_filtra_detalles(app: FastAPI, client: TestClient) -> None:
    _agregar_rutas_de_prueba(app)

    respuesta = client.get("/prueba/falla", headers={"X-Request-ID": "abc-123"})

    assert respuesta.status_code == 500
    assert respuesta.headers["X-Request-ID"] == "abc-123"
    cuerpo = respuesta.json()
    assert cuerpo["code"] == "ERROR_INTERNO"
    assert cuerpo["request_id"] == "abc-123"
    assert "detalle interno" not in respuesta.text
