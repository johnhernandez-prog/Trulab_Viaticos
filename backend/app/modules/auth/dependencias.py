"""Dependencias de FastAPI para identificar al usuario de cada petición (ADR-005, ADR-027).

- El rol, el estado activo y `debe_cambiar_password` se leen **de la BD en cada petición**, no del
  JWT: un cambio de rol, una desactivación o un cierre de sesión surten efecto de inmediato.
- La sesión (`sid` del JWT) debe seguir vigente: el logout y la rotación revocan el access token.
- `UsuarioActual` exige además que no haya un cambio de contraseña pendiente; solo `/me`,
  `/auth/logout` y `/auth/password/change` usan `UsuarioActualPermitiendoCambio`.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security import TokenExpiradoError, TokenInvalidoError, decodificar_access_token
from app.modules.auth.errores import CambioPasswordRequerido, NoAutenticado, TokenExpirado
from app.modules.auth.models import Sesion
from app.modules.auth.service import Contexto
from app.modules.usuarios.models import Usuario

_bearer = HTTPBearer(auto_error=False, description="Access token de /auth/login o /auth/google")

DB = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]


@dataclass(frozen=True)
class Autenticado:
    usuario: Usuario
    sesion_id: uuid.UUID


def contexto(request: Request) -> Contexto:
    ip = request.client.host if request.client else None
    return Contexto.crear(ip, request.headers.get("user-agent"))


Ctx = Annotated[Contexto, Depends(contexto)]


def _autenticado(
    session: DB,
    settings: Config,
    credenciales: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Autenticado:
    if credenciales is None:
        raise NoAutenticado()
    try:
        claims = decodificar_access_token(credenciales.credentials, secreto=settings.jwt_secret)
    except TokenExpiradoError as error:
        raise TokenExpirado() from error
    except TokenInvalidoError as error:
        raise NoAutenticado() from error
    fila = session.execute(
        select(Usuario, Sesion.revoked_at)
        .join(Sesion, Sesion.usuario_id == Usuario.id)
        .where(Usuario.id == claims.usuario_id, Sesion.id == claims.sesion_id)
    ).first()
    if fila is None:
        raise NoAutenticado()
    usuario, revocada = fila
    if revocada is not None or not usuario.activo or usuario.deleted_at is not None:
        raise NoAutenticado()
    return Autenticado(usuario=usuario, sesion_id=claims.sesion_id)


UsuarioActualPermitiendoCambio = Annotated[Autenticado, Depends(_autenticado)]


def _sin_cambio_pendiente(autenticado: UsuarioActualPermitiendoCambio) -> Autenticado:
    if autenticado.usuario.debe_cambiar_password:
        raise CambioPasswordRequerido()
    return autenticado


UsuarioActual = Annotated[Autenticado, Depends(_sin_cambio_pendiente)]
