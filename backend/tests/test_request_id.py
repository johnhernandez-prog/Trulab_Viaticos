import re

from fastapi.testclient import TestClient


def test_genera_request_id_si_no_viene(client: TestClient) -> None:
    respuesta = client.get("/api/v1/health")

    assert re.fullmatch(r"[0-9a-f]{32}", respuesta.headers["X-Request-ID"])


def test_conserva_request_id_valido_del_cliente(client: TestClient) -> None:
    respuesta = client.get("/api/v1/health", headers={"X-Request-ID": "01JC-abc_9.x"})

    assert respuesta.headers["X-Request-ID"] == "01JC-abc_9.x"


def test_reemplaza_request_id_inseguro(client: TestClient) -> None:
    respuesta = client.get("/api/v1/health", headers={"X-Request-ID": "<script>alert(1)</script>"})

    assert respuesta.headers["X-Request-ID"] != "<script>alert(1)</script>"
    assert re.fullmatch(r"[0-9a-f]{32}", respuesta.headers["X-Request-ID"])
