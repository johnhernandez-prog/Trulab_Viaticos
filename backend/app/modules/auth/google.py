"""Verificación del ID token de Google (solo login de SUPERADMIN, ADR-027).

`google-auth` comprueba la firma con las claves públicas de Google, el emisor
(`accounts.google.com`), la audiencia (`GOOGLE_CLIENT_ID`) y el vencimiento. Las reglas de negocio
(dominio, usuario registrado, rol) las aplica `service.iniciar_sesion_google`.
"""

from collections.abc import Callable
from functools import lru_cache
from typing import Any

from app.core.config import get_settings
from app.modules.auth.errores import LoginGoogleNoDisponible, NoAutenticado

VerificadorGoogle = Callable[[str], dict[str, Any]]


@lru_cache
def _transporte() -> Any:
    from google.auth.transport import requests as google_requests

    return google_requests.Request()  # type: ignore[no-untyped-call]


def verificar_id_token(id_token: str) -> dict[str, Any]:
    client_id = get_settings().google_client_id
    if not client_id:
        raise LoginGoogleNoDisponible()
    from google.oauth2 import id_token as google_id_token

    try:
        claims: dict[str, Any] = google_id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
            id_token, _transporte(), client_id
        )
    except ValueError as error:  # firma, audiencia, emisor o vencimiento inválidos
        raise NoAutenticado("El token de Google no es válido") from error
    return claims


def get_verificador_google() -> VerificadorGoogle:
    """Dependencia de FastAPI (las pruebas la reemplazan por un verificador falso)."""
    return verificar_id_token
