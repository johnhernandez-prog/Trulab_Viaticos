"""`/archivos` y `/me/firma` (S2-06, docs/api-design.md §5.1 y §5.9; RN-13, RN-32)."""

import hashlib
import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import PropositoArchivo, Rol
from app.modules.archivos import router as archivos_router
from app.modules.archivos.models import Archivo
from app.modules.archivos.storage import AlmacenamientoLocal
from app.modules.usuarios.models import Usuario
from tests import muestras
from tests.fabricas import bearer, crear_archivo, crear_usuario

URL = "/api/v1/archivos"


def _actor(sesion: Session, rol: Rol = Rol.VIAJERO) -> tuple[Usuario, dict[str, str]]:
    usuario = crear_usuario(sesion, rol=rol)
    return usuario, bearer(sesion, usuario)


def _subir(
    api: TestClient,
    encabezados: dict[str, str],
    contenido: bytes,
    proposito: str = "SOPORTE",
    nombre: str = "factura.jpg",
    content_type: str = "image/jpeg",
) -> httpx.Response:
    return api.post(
        URL,
        files={"archivo": (nombre, contenido, content_type)},
        data={"proposito": proposito},
        headers=encabezados,
    )


# =================================================================================================
# POST /archivos
# =================================================================================================


@pytest.mark.usefixtures("almacen")
@pytest.mark.parametrize(
    ("contenido", "proposito", "mime"),
    [
        (muestras.JPEG, "SOPORTE", "image/jpeg"),
        (muestras.PNG, "SOPORTE", "image/png"),
        (muestras.WEBP, "SOPORTE", "image/webp"),
        (muestras.PDF, "ARCHIVO", "application/pdf"),
        (muestras.PNG, "FIRMA", "image/png"),
        (muestras.PDF, "FORMATO_PRESTADOR", "application/pdf"),
        (
            muestras.XLSX,
            "FORMATO_PRESTADOR",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (muestras.XLS, "FORMATO_PRESTADOR", "application/vnd.ms-excel"),
    ],
)
def test_sube_un_archivo_valido(
    api: TestClient, sesion: Session, contenido: bytes, proposito: str, mime: str
) -> None:
    usuario, encabezados = _actor(sesion)

    respuesta = _subir(api, encabezados, contenido, proposito, content_type="text/plain")

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    # El tipo sale del contenido, no del Content-Type que mandó el cliente.
    assert cuerpo["mime_type"] == mime
    assert cuerpo["proposito"] == proposito
    assert cuerpo["tamano_bytes"] == len(contenido)
    assert cuerpo["sha256"] == hashlib.sha256(contenido).hexdigest()
    assert "storage_key" not in cuerpo
    assert respuesta.headers["Location"] == f"{URL}/{cuerpo['id']}"
    archivo = sesion.get(Archivo, uuid.UUID(cuerpo["id"]))
    assert archivo is not None and archivo.created_by == usuario.id


def test_el_contenido_queda_en_el_almacenamiento(
    api: TestClient, sesion: Session, almacen: AlmacenamientoLocal
) -> None:
    _, encabezados = _actor(sesion)

    cuerpo = _subir(api, encabezados, muestras.JPEG).json()

    archivo = sesion.get(Archivo, uuid.UUID(cuerpo["id"]))
    assert archivo is not None
    assert archivo.storage_key.startswith("soporte/") and archivo.storage_key.endswith(".jpg")
    assert "factura" not in archivo.storage_key  # la clave nunca usa el nombre del cliente
    assert almacen.leer(archivo.storage_key) == muestras.JPEG


@pytest.mark.usefixtures("almacen")
@pytest.mark.parametrize(
    ("contenido", "proposito", "nombre", "content_type"),
    [
        # Ejecutables y contenido activo disfrazados (extensión y Content-Type mienten).
        (muestras.EXE, "ARCHIVO", "factura.pdf", "application/pdf"),
        (muestras.EXE, "SOPORTE", "foto.jpg", "image/jpeg"),
        (muestras.HTML, "SOPORTE", "foto.jpg", "image/jpeg"),
        (muestras.SVG, "FIRMA", "firma.svg", "image/svg+xml"),
        (muestras.DOCX, "FORMATO_PRESTADOR", "formato.xlsx", "application/vnd.ms-excel"),
        # Tipo válido, propósito equivocado (RN-13).
        (muestras.PDF, "SOPORTE", "factura.pdf", "application/pdf"),
        (muestras.JPEG, "ARCHIVO", "factura.jpg", "image/jpeg"),
        (muestras.XLSX, "ARCHIVO", "formato.xlsx", "application/octet-stream"),
        (muestras.HEIC, "FIRMA", "firma.heic", "image/heic"),
    ],
)
def test_rechaza_tipos_no_permitidos(
    api: TestClient,
    sesion: Session,
    contenido: bytes,
    proposito: str,
    nombre: str,
    content_type: str,
) -> None:
    usuario, encabezados = _actor(sesion)

    respuesta = _subir(api, encabezados, contenido, proposito, nombre, content_type)

    assert respuesta.status_code == 415, respuesta.text
    assert respuesta.json()["code"] == "TIPO_ARCHIVO_NO_PERMITIDO"
    # No quedó ninguna fila del archivo rechazado.
    assert sesion.scalar(select(func.count()).where(Archivo.created_by == usuario.id)) == 0


@pytest.mark.usefixtures("almacen")
def test_archivo_vacio_es_422(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = _subir(api, encabezados, b"")

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "VALOR_NO_PERMITIDO"


@pytest.mark.usefixtures("almacen")
def test_archivo_mas_grande_que_el_limite_es_413(
    api: TestClient, sesion: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, encabezados = _actor(sesion)
    monkeypatch.setattr(archivos_router, "_limite_bytes", lambda: 1024)

    respuesta = _subir(api, encabezados, muestras.JPEG + b"\x00" * 2048)

    assert respuesta.status_code == 413
    assert respuesta.json()["code"] == "ARCHIVO_MUY_GRANDE"


@pytest.mark.usefixtures("almacen")
def test_content_length_excesivo_se_corta_antes_de_leer(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(
        URL,
        content=b"x",
        headers={
            **encabezados,
            "Content-Type": "multipart/form-data; boundary=x",
            "Content-Length": str(50 * 1024 * 1024),
        },
    )

    assert respuesta.status_code == 413


@pytest.mark.usefixtures("almacen")
def test_proposito_invalido_es_422(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = _subir(api, encabezados, muestras.JPEG, "OTRO")

    assert respuesta.status_code == 422


@pytest.mark.usefixtures("almacen")
def test_subir_sin_sesion_es_401(api: TestClient) -> None:
    assert _subir(api, {}, muestras.JPEG).status_code == 401


# =================================================================================================
# GET /archivos/{id}/url y /archivos/contenido (local)
# =================================================================================================


@pytest.mark.usefixtures("almacen")
def test_dueno_obtiene_url_temporal_y_descarga(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    archivo_id = _subir(api, encabezados, muestras.PDF, "ARCHIVO", "Factura café.pdf").json()["id"]

    respuesta = api.get(f"{URL}/{archivo_id}/url", headers=encabezados)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["mime_type"] == "application/pdf"
    assert cuerpo["nombre"] == "Factura café.pdf"
    assert cuerpo["url"].startswith("/api/v1/archivos/contenido?token=")
    # La URL funciona sin Authorization (como una prefirmada de S3).
    descarga = api.get(cuerpo["url"])
    assert descarga.status_code == 200
    assert descarga.content == muestras.PDF
    assert descarga.headers["content-type"] == "application/pdf"
    assert descarga.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in descarga.headers["content-security-policy"]
    assert "filename*=UTF-8''Factura%20caf%C3%A9.pdf" in descarga.headers["content-disposition"]


@pytest.mark.usefixtures("almacen")
@pytest.mark.parametrize("token", ["", "basura", "a.b.c"])
def test_contenido_con_token_invalido_es_404(api: TestClient, token: str) -> None:
    assert api.get(f"{URL}/contenido", params={"token": token}).status_code == 404


def test_contenido_no_existe_con_s3(api: TestClient, app: FastAPI) -> None:
    from app.modules.archivos.storage import AlmacenamientoS3, get_almacenamiento

    app.dependency_overrides[get_almacenamiento] = lambda: AlmacenamientoS3("b", object())

    assert api.get(f"{URL}/contenido", params={"token": "x"}).status_code == 404


@pytest.mark.usefixtures("almacen")
def test_otro_viajero_no_ve_el_archivo(api: TestClient, sesion: Session) -> None:
    dueno, encabezados_dueno = _actor(sesion)
    archivo = crear_archivo(sesion, created_by=dueno.id)
    _, encabezados_otro = _actor(sesion)

    assert api.get(f"{URL}/{archivo.id}/url", headers=encabezados_otro).status_code == 404
    assert api.get(f"{URL}/{archivo.id}", headers=encabezados_otro).status_code == 404
    assert api.get(f"{URL}/{archivo.id}", headers=encabezados_dueno).status_code == 200


@pytest.mark.usefixtures("almacen")
@pytest.mark.parametrize("rol", [Rol.ADMIN, Rol.FINANCIERO, Rol.SUPERADMIN])
def test_roles_privilegiados_ven_el_archivo_ajeno(
    api: TestClient, sesion: Session, rol: Rol
) -> None:
    dueno = crear_usuario(sesion)
    archivo = crear_archivo(sesion, created_by=dueno.id)
    _, encabezados = _actor(sesion, rol)

    respuesta = api.get(f"{URL}/{archivo.id}/url", headers=encabezados)

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "factura.jpg"


@pytest.mark.usefixtures("almacen")
def test_url_de_archivo_inexistente_es_404(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)

    assert api.get(f"{URL}/{uuid.uuid4()}/url", headers=encabezados).status_code == 404


# =================================================================================================
# /me/firma (RN-32)
# =================================================================================================

FIRMA = "/api/v1/me/firma"


@pytest.mark.usefixtures("almacen")
def test_ciclo_de_la_firma_del_perfil(api: TestClient, sesion: Session) -> None:
    usuario, encabezados = _actor(sesion)
    assert api.get(FIRMA, headers=encabezados).status_code == 404

    archivo_id = _subir(api, encabezados, muestras.PNG, "FIRMA", "firma.png").json()["id"]
    guardada = api.put(FIRMA, json={"archivo_id": archivo_id}, headers=encabezados)

    assert guardada.status_code == 200, guardada.text
    assert guardada.json()["archivo_id"] == archivo_id
    assert guardada.json()["mime_type"] == "image/png"
    sesion.refresh(usuario)
    assert str(usuario.firma_archivo_id) == archivo_id
    consulta = api.get(FIRMA, headers=encabezados)
    assert consulta.status_code == 200 and consulta.json()["archivo_id"] == archivo_id

    assert api.delete(FIRMA, headers=encabezados).status_code == 204
    sesion.refresh(usuario)
    assert usuario.firma_archivo_id is None
    # El archivo no se borra (inmutable).
    assert sesion.get(Archivo, uuid.UUID(archivo_id)) is not None


@pytest.mark.usefixtures("almacen")
def test_firma_exige_un_archivo_con_proposito_firma(api: TestClient, sesion: Session) -> None:
    usuario, encabezados = _actor(sesion)
    soporte = crear_archivo(sesion, created_by=usuario.id, proposito=PropositoArchivo.SOPORTE)

    respuesta = api.put(FIRMA, json={"archivo_id": str(soporte.id)}, headers=encabezados)

    assert respuesta.status_code == 415
    assert respuesta.json()["code"] == "TIPO_ARCHIVO_NO_PERMITIDO"


@pytest.mark.usefixtures("almacen")
def test_firma_con_archivo_ajeno_es_422(api: TestClient, sesion: Session) -> None:
    otro = crear_usuario(sesion)
    ajeno = crear_archivo(
        sesion, created_by=otro.id, proposito=PropositoArchivo.FIRMA, mime_type="image/png"
    )
    _, encabezados = _actor(sesion, Rol.ADMIN)  # aunque ADMIN lo vea por RLS, no es suyo

    respuesta = api.put(FIRMA, json={"archivo_id": str(ajeno.id)}, headers=encabezados)

    assert respuesta.status_code == 422
    assert respuesta.json()["errors"][0]["field"] == "archivo_id"
