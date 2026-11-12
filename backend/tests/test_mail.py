"""Correo transaccional (S1-08, ADR-028): `LogMailer` (local) y `SesMailer` (Amazon SES)."""

import logging
from typing import Any

import pytest

from app.core.config import Settings
from app.core.mail import (
    Correo,
    ErrorEnvioCorreo,
    LogMailer,
    SesMailer,
    crear_mailer,
    enmascarar_correo,
)

CORREO = Correo("ana.perez@gmail.com", "Asunto", "Texto con enlace", "<p>HTML</p>")


class ClienteSesFalso:
    def __init__(self, falla: bool = False) -> None:
        self.falla = falla
        self.enviados: list[dict[str, Any]] = []

    def send_email(self, **kwargs: Any) -> dict[str, str]:
        if self.falla:
            raise RuntimeError("MessageRejected")
        self.enviados.append(kwargs)
        return {"MessageId": "1"}


def _ses(cliente: ClienteSesFalso) -> SesMailer:
    mailer = SesMailer("viaticos@trulab.co", "us-east-1")  # crear el cliente no usa la red
    mailer._cliente = cliente
    return mailer


def test_ses_envia_texto_y_html_desde_el_remitente_verificado() -> None:
    cliente = ClienteSesFalso()

    _ses(cliente).enviar(CORREO)

    [envio] = cliente.enviados
    assert envio["FromEmailAddress"] == "viaticos@trulab.co"
    assert envio["Destination"] == {"ToAddresses": ["ana.perez@gmail.com"]}
    cuerpo = envio["Content"]["Simple"]["Body"]
    assert cuerpo["Text"]["Data"] == "Texto con enlace" and cuerpo["Html"]["Data"] == "<p>HTML</p>"


def test_ses_rechazado_lanza_error_sin_registrar_el_destinatario_completo(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.ERROR), pytest.raises(ErrorEnvioCorreo):
        _ses(ClienteSesFalso(falla=True)).enviar(CORREO)

    assert "ana.perez@gmail.com" not in caplog.text


def test_log_mailer_escribe_el_correo_completo(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app.mail"):
        LogMailer().enviar(CORREO)

    [registro] = caplog.records
    assert registro.getMessage() == "correo_local"
    assert registro.__dict__["cuerpo"] == "Texto con enlace"


def test_crear_mailer_segun_configuracion() -> None:
    base = {"database_url": "postgresql+psycopg://u:p@db/x", "jwt_secret": "x" * 32}

    local = crear_mailer(Settings.model_validate(base))
    ses = crear_mailer(
        Settings.model_validate({**base, "mail_backend": "ses", "aws_ses_sender": "v@trulab.co"})
    )

    assert isinstance(local, LogMailer) and isinstance(ses, SesMailer)


def test_enmascarar_correo() -> None:
    assert enmascarar_correo("ana.perez@trulab.co") == "a***@trulab.co"
    assert enmascarar_correo("sin-arroba") == "***"
