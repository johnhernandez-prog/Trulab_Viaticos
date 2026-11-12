"""Correo transaccional (ADR-028): interfaz `Mailer` con Amazon SES o el log local.

- `MAIL_BACKEND=ses`: Amazon SES con `boto3`. Credenciales del rol de IAM de la tarea (nunca en
  variables en producción). Remitente: `AWS_SES_SENDER`, identidad verificada en SES.
- `MAIL_BACKEND=log`: escribe el correo en el log, **incluido el cuerpo** (con el enlace de
  restablecimiento) para poder probar en local. `Settings` impide usarlo fuera de `ENV=local`.

Un fallo de envío se registra y se propaga como `ErrorEnvioCorreo`; quien llama decide si se
oculta al usuario (en la recuperación de contraseña se oculta, para no revelar cuentas).
"""

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from app.core.config import Settings, get_settings

logger = logging.getLogger("app.mail")


@dataclass(frozen=True)
class Correo:
    destinatario: str
    asunto: str
    texto: str
    html: str | None = None


class ErrorEnvioCorreo(Exception):
    """El proveedor no aceptó el correo."""


class Mailer(Protocol):
    def enviar(self, correo: Correo) -> None: ...


def enmascarar_correo(correo: str) -> str:
    """`ana.perez@trulab.co` → `a***@trulab.co` (para logs)."""
    local, _, dominio = correo.partition("@")
    return f"{local[:1]}***@{dominio}" if dominio else "***"


class LogMailer:
    """Solo para `ENV=local`: el correo completo va al log del backend."""

    def enviar(self, correo: Correo) -> None:
        logger.info(
            "correo_local",
            extra={
                "destinatario": correo.destinatario,
                "asunto": correo.asunto,
                "cuerpo": correo.texto,
            },
        )


class SesMailer:
    def __init__(self, remitente: str, region: str) -> None:
        import boto3  # importación diferida: en local no hace falta cargar botocore

        self._remitente = remitente
        self._cliente: Any = boto3.client("sesv2", region_name=region)

    def enviar(self, correo: Correo) -> None:
        cuerpo: dict[str, Any] = {"Text": {"Data": correo.texto, "Charset": "UTF-8"}}
        if correo.html:
            cuerpo["Html"] = {"Data": correo.html, "Charset": "UTF-8"}
        try:
            self._cliente.send_email(
                FromEmailAddress=self._remitente,
                Destination={"ToAddresses": [correo.destinatario]},
                Content={
                    "Simple": {
                        "Subject": {"Data": correo.asunto, "Charset": "UTF-8"},
                        "Body": cuerpo,
                    }
                },
            )
        except Exception as error:  # botocore lanza varias clases; todas significan "no salió"
            logger.error(
                "correo_no_enviado",
                extra={"destinatario": enmascarar_correo(correo.destinatario)},
                exc_info=error,
            )
            raise ErrorEnvioCorreo from error
        logger.info(
            "correo_enviado", extra={"destinatario": enmascarar_correo(correo.destinatario)}
        )


def crear_mailer(settings: Settings) -> Mailer:
    if settings.mail_backend == "ses":
        return SesMailer(settings.aws_ses_sender, settings.aws_region)
    return LogMailer()


@lru_cache
def get_mailer() -> Mailer:
    """Dependencia de FastAPI (las pruebas la reemplazan por un buzón en memoria)."""
    return crear_mailer(get_settings())
