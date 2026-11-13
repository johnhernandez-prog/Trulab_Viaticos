"""Almacenamiento local y S3 (S2-06, ADR-028). S3 con `botocore.stub.Stubber` (sin red)."""

import urllib.parse
from datetime import UTC, datetime, timedelta
from pathlib import Path

import boto3
import jwt
import pytest
from botocore.config import Config
from botocore.stub import Stubber

from app.core.config import get_settings
from app.modules.archivos.storage import (
    AUDIENCIA_LOCAL,
    AlmacenamientoLocal,
    AlmacenamientoS3,
    ClaveInvalidaError,
    TokenArchivoInvalidoError,
    content_disposition,
    crear_almacenamiento,
)

SECRETO = "x" * 40


def _local(tmp_path: Path) -> AlmacenamientoLocal:
    return AlmacenamientoLocal(tmp_path, SECRETO)


# --- local ----------------------------------------------------------------------------------------


def test_local_guarda_y_lee(tmp_path: Path) -> None:
    almacen = _local(tmp_path)

    almacen.guardar("soporte/2026/11/a.jpg", b"contenido", "image/jpeg")

    assert almacen.leer("soporte/2026/11/a.jpg") == b"contenido"
    assert (tmp_path / "soporte/2026/11/a.jpg").read_bytes() == b"contenido"


def test_local_no_sobrescribe_un_archivo_existente(tmp_path: Path) -> None:
    almacen = _local(tmp_path)
    almacen.guardar("a.pdf", b"uno", "application/pdf")

    with pytest.raises(FileExistsError):
        almacen.guardar("a.pdf", b"dos", "application/pdf")

    assert almacen.leer("a.pdf") == b"uno"


@pytest.mark.parametrize("clave", ["../fuera.txt", "a/../../fuera.txt", "/etc/passwd", ""])
def test_local_rechaza_claves_fuera_de_la_carpeta(tmp_path: Path, clave: str) -> None:
    almacen = _local(tmp_path / "almacen")

    with pytest.raises(ClaveInvalidaError):
        almacen.guardar(clave, b"x", "image/png")


def test_local_url_con_token_verificable(tmp_path: Path) -> None:
    almacen = _local(tmp_path)

    url = almacen.url_lectura("a.pdf", mime_type="application/pdf", nombre="f.pdf", expira_en=300)

    assert url.startswith("/api/v1/archivos/contenido?token=")
    token = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["token"][0]
    datos = almacen.verificar_token(token)
    assert (datos["k"], datos["m"], datos["n"]) == ("a.pdf", "application/pdf", "f.pdf")


def test_local_token_alterado_o_vencido_no_vale(tmp_path: Path) -> None:
    almacen = _local(tmp_path)
    url = almacen.url_lectura("a.pdf", mime_type="application/pdf", nombre="f.pdf", expira_en=300)
    token = url.split("token=")[1]
    vencido = almacen.url_lectura(
        "a.pdf", mime_type="application/pdf", nombre="f.pdf", expira_en=-10
    ).split("token=")[1]

    with pytest.raises(TokenArchivoInvalidoError):
        almacen.verificar_token(token[:-2] + ("AA" if not token.endswith("AA") else "BB"))
    with pytest.raises(TokenArchivoInvalidoError):
        almacen.verificar_token(vencido)
    # Otro secreto (otra instalación) no valida el token.
    with pytest.raises(TokenArchivoInvalidoError):
        AlmacenamientoLocal(tmp_path, "y" * 40).verificar_token(token)


def test_local_un_jwt_firmado_con_el_secreto_de_sesion_no_vale(tmp_path: Path) -> None:
    """La clave del token de archivo es derivada: un JWT firmado directamente con `JWT_SECRET`
    (como los access tokens) no abre archivos."""
    almacen = _local(tmp_path)
    falso = jwt.encode(
        {
            "k": "a.pdf",
            "m": "application/pdf",
            "n": "f.pdf",
            "aud": AUDIENCIA_LOCAL,
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        SECRETO,
        algorithm="HS256",
    )

    with pytest.raises(TokenArchivoInvalidoError):
        almacen.verificar_token(falso)


def test_content_disposition_con_nombre_no_ascii() -> None:
    cabecera = content_disposition('Factura "café".pdf')

    assert cabecera.startswith('inline; filename="Factura _caf__.pdf"')
    assert "filename*=UTF-8''Factura%20%22caf%C3%A9%22.pdf" in cabecera


# --- S3 -------------------------------------------------------------------------------------------


def _cliente_s3() -> object:
    return boto3.client(
        "s3",
        region_name="us-east-1",
        aws_access_key_id="AKIAPRUEBA",
        aws_secret_access_key="secreto-de-prueba",  # noqa: S106
        config=Config(signature_version="s3v4"),
    )


def test_s3_guarda_cifrado_con_el_tipo_detectado() -> None:
    cliente = _cliente_s3()
    almacen = AlmacenamientoS3("trulab-bucket", cliente)
    with Stubber(cliente) as stub:
        stub.add_response(
            "put_object",
            {"ETag": '"abc"'},
            {
                "Bucket": "trulab-bucket",
                "Key": "archivo/2026/11/x.pdf",
                "Body": b"%PDF-1.7",
                "ContentType": "application/pdf",
                "ServerSideEncryption": "AES256",
            },
        )

        almacen.guardar("archivo/2026/11/x.pdf", b"%PDF-1.7", "application/pdf")

        stub.assert_no_pending_responses()


def test_s3_url_prefirmada_de_cinco_minutos() -> None:
    almacen = AlmacenamientoS3("trulab-bucket", _cliente_s3())

    url = almacen.url_lectura(
        "soporte/2026/11/x.jpg", mime_type="image/jpeg", nombre="factura.jpg", expira_en=300
    )

    partes = urllib.parse.urlparse(url)
    consulta = urllib.parse.parse_qs(partes.query)
    assert "trulab-bucket" in partes.netloc + partes.path
    assert partes.path.endswith("/soporte/2026/11/x.jpg")
    assert consulta["X-Amz-Expires"] == ["300"]
    assert consulta["response-content-type"] == ["image/jpeg"]
    assert consulta["response-content-disposition"][0].startswith('inline; filename="factura.jpg"')
    assert "X-Amz-Signature" in consulta


def test_fabrica_segun_storage_backend(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = get_settings()
    local = base.model_copy(
        update={"storage_backend": "local", "storage_local_path": str(tmp_path)}
    )
    assert isinstance(crear_almacenamiento(local), AlmacenamientoLocal)

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAPRUEBA")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secreto-de-prueba")
    s3 = base.model_copy(update={"storage_backend": "s3", "aws_s3_bucket": "trulab-bucket"})
    almacen = crear_almacenamiento(s3)
    assert isinstance(almacen, AlmacenamientoS3)
    assert almacen.bucket == "trulab-bucket"


def test_max_upload_mb_no_supera_el_check_de_la_bd() -> None:
    from pydantic import ValidationError

    from app.core.config import Settings

    base = get_settings().model_dump()
    with pytest.raises(ValidationError):
        Settings(**{**base, "max_upload_mb": 11})
    with pytest.raises(ValidationError):
        Settings(**{**base, "signed_url_ttl_seconds": 3600})
