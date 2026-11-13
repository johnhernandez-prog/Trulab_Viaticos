"""Almacenamiento de archivos (ADR-028): `local` (desarrollo) y `s3` (staging y producción).

Las dos implementaciones cumplen el mismo protocolo `Almacenamiento`:

- `guardar(clave, contenido, mime_type)`: escribe una vez; las claves no se reutilizan (los
  archivos son inmutables, como sus filas en `archivos`).
- `url_lectura(...)`: URL temporal de lectura (5 min por defecto).
  - **S3:** URL **prefirmada** de `get_object` sobre un bucket privado, con el tipo y el nombre
    forzados en la respuesta (`ResponseContentType`, `ResponseContentDisposition`).
  - **Local:** imita la URL prefirmada: un token firmado (JWT HS256 con una clave derivada de
    `JWT_SECRET` y audiencia propia) con la clave, el tipo, el nombre y la expiración, que sirve
    `GET /api/v1/archivos/contenido`. Así un `<img src>` funciona sin el encabezado
    `Authorization`, igual que con S3, y el token no sirve como access token.
"""

import hashlib
import hmac
import urllib.parse
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import jwt

from app.core.config import Settings, get_settings

AUDIENCIA_LOCAL = "trulab:archivo-local"
RUTA_CONTENIDO_LOCAL = "/api/v1/archivos/contenido"


class Almacenamiento(Protocol):
    def guardar(self, clave: str, contenido: bytes, mime_type: str) -> None: ...

    def url_lectura(self, clave: str, *, mime_type: str, nombre: str, expira_en: int) -> str: ...


def content_disposition(nombre: str, *, inline: bool = True) -> str:
    """`inline; filename="..."; filename*=UTF-8''...` (RFC 6266) con una versión ASCII segura."""
    ascii_seguro = "".join(
        c if c.isascii() and c.isprintable() and c not in '"\\' else "_" for c in nombre
    )
    tipo = "inline" if inline else "attachment"
    return (
        f'{tipo}; filename="{ascii_seguro}"; '
        f"filename*=UTF-8''{urllib.parse.quote(nombre, safe='')}"
    )


# --- local --------------------------------------------------------------------------------------


class ClaveInvalidaError(ValueError):
    """La clave saldría de la carpeta del almacenamiento (`..`, rutas absolutas)."""


class TokenArchivoInvalidoError(ValueError):
    """Token de lectura local alterado, vencido o de otro tipo."""


class AlmacenamientoLocal:
    def __init__(self, raiz: Path, secreto: str) -> None:
        self.raiz = raiz.resolve()
        # Clave propia (derivada), para que un token de archivo nunca valga como access token.
        self._clave_firma = hmac.new(
            secreto.encode(), b"trulab:archivos-local", hashlib.sha256
        ).hexdigest()

    def _ruta(self, clave: str) -> Path:
        ruta = (self.raiz / clave).resolve()
        if not ruta.is_relative_to(self.raiz) or ruta == self.raiz:
            raise ClaveInvalidaError(clave)
        return ruta

    def guardar(self, clave: str, contenido: bytes, mime_type: str) -> None:
        ruta = self._ruta(clave)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        # "x": falla si ya existe; un archivo guardado no se sobrescribe nunca.
        with ruta.open("xb") as destino:
            destino.write(contenido)

    def leer(self, clave: str) -> bytes:
        return self._ruta(clave).read_bytes()

    def url_lectura(self, clave: str, *, mime_type: str, nombre: str, expira_en: int) -> str:
        token = jwt.encode(
            {
                "k": clave,
                "m": mime_type,
                "n": nombre,
                "aud": AUDIENCIA_LOCAL,
                "exp": datetime.now(UTC) + timedelta(seconds=expira_en),
            },
            self._clave_firma,
            algorithm="HS256",
        )
        return f"{RUTA_CONTENIDO_LOCAL}?token={token}"

    def verificar_token(self, token: str) -> dict[str, Any]:
        try:
            datos: dict[str, Any] = jwt.decode(
                token,
                self._clave_firma,
                algorithms=["HS256"],
                audience=AUDIENCIA_LOCAL,
                options={"require": ["exp", "aud", "k", "m", "n"]},
            )
        except jwt.PyJWTError as error:
            raise TokenArchivoInvalidoError(str(error)) from error
        return datos


# --- Amazon S3 ----------------------------------------------------------------------------------


class AlmacenamientoS3:
    """Bucket **privado**; el cliente `boto3` toma las credenciales del rol de IAM de la tarea."""

    def __init__(self, bucket: str, cliente: Any) -> None:
        self.bucket = bucket
        self.cliente = cliente

    def guardar(self, clave: str, contenido: bytes, mime_type: str) -> None:
        self.cliente.put_object(
            Bucket=self.bucket,
            Key=clave,
            Body=contenido,
            ContentType=mime_type,
            ServerSideEncryption="AES256",
        )

    def url_lectura(self, clave: str, *, mime_type: str, nombre: str, expira_en: int) -> str:
        url: str = self.cliente.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": clave,
                "ResponseContentType": mime_type,
                "ResponseContentDisposition": content_disposition(nombre),
            },
            ExpiresIn=expira_en,
        )
        return url


def crear_almacenamiento(settings: Settings) -> Almacenamiento:
    if settings.storage_backend == "s3":
        import boto3
        from botocore.config import Config

        cliente = boto3.client(
            "s3", region_name=settings.aws_region, config=Config(signature_version="s3v4")
        )
        return AlmacenamientoS3(settings.aws_s3_bucket, cliente)
    return AlmacenamientoLocal(Path(settings.storage_local_path), settings.jwt_secret)


@lru_cache
def _almacenamiento_por_defecto() -> Almacenamiento:
    return crear_almacenamiento(get_settings())


def get_almacenamiento() -> Almacenamiento:
    """Dependencia de FastAPI (las pruebas la reemplazan con `dependency_overrides`)."""
    return _almacenamiento_por_defecto()
