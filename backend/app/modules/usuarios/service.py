"""Reglas de negocio de usuarios. En S1-07 solo el SUPERADMIN inicial; el CRUD llega en S1-10."""

import re
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import AccionAuditoria, registrar
from app.core.enums import Rol
from app.modules.usuarios.models import Usuario

_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ErrorConfiguracion(ValueError):
    """Valor de configuración inválido (por ejemplo, `SUPERADMIN_EMAIL` de otro dominio)."""


class ResultadoSuperadmin(StrEnum):
    OMITIDO_SIN_CORREO = "OMITIDO_SIN_CORREO"
    YA_HAY_SUPERADMIN = "YA_HAY_SUPERADMIN"
    CREADO = "CREADO"
    PROMOVIDO = "PROMOVIDO"


def validar_correo_corporativo(correo: str, dominio: str) -> str:
    """Devuelve el correo normalizado si es del dominio de Google Workspace (RN-12)."""
    normalizado = correo.strip().lower()
    if not _CORREO.match(normalizado):
        raise ErrorConfiguracion("El correo no tiene un formato válido")
    if normalizado.rsplit("@", 1)[1] != dominio.strip().lower():
        raise ErrorConfiguracion(f"El correo debe ser del dominio @{dominio}")
    return normalizado


def asegurar_superadmin_inicial(
    session: Session, correo: str, nombre: str, dominio: str
) -> ResultadoSuperadmin:
    """Garantiza que exista al menos un SUPERADMIN activo (idempotente; no hace commit).

    - Sin correo configurado: no hace nada.
    - Si ya hay un SUPERADMIN activo: no hace nada. Así la variable de entorno no sirve para
      crear superadministradores adicionales; los siguientes se gestionan desde la app (S1-10).
    - Si no lo hay: crea el usuario o, si el correo ya existe, lo promueve y reactiva
      (recuperación de acceso). Ambos casos quedan en `auditoria` con `origen = seed`.
    """
    if not correo.strip():
        return ResultadoSuperadmin.OMITIDO_SIN_CORREO
    correo = validar_correo_corporativo(correo, dominio)

    hay_superadmin = session.scalar(
        select(Usuario.id)
        .where(Usuario.rol == Rol.SUPERADMIN, Usuario.activo, Usuario.deleted_at.is_(None))
        .limit(1)
    )
    if hay_superadmin is not None:
        return ResultadoSuperadmin.YA_HAY_SUPERADMIN

    existente = session.scalar(select(Usuario).where(Usuario.correo == correo))
    if existente is None:
        usuario = Usuario(
            nombre_completo=nombre.strip() or "Superadministrador",
            correo=correo,
            rol=Rol.SUPERADMIN,
        )
        session.add(usuario)
        session.flush()
        registrar(
            session,
            AccionAuditoria.USUARIO_CREAR,
            "usuarios",
            usuario.id,
            datos={"origen": "seed", "correo": correo, "rol": Rol.SUPERADMIN.value},
        )
        return ResultadoSuperadmin.CREADO

    antes = {"rol": existente.rol, "activo": existente.activo}
    existente.rol = Rol.SUPERADMIN
    existente.activo = True
    existente.deleted_at = None
    session.flush()
    registrar(
        session,
        AccionAuditoria.ROL_CAMBIAR,
        "usuarios",
        existente.id,
        datos={
            "origen": "seed",
            "antes": antes,
            "despues": {"rol": Rol.SUPERADMIN.value, "activo": True},
        },
    )
    return ResultadoSuperadmin.PROMOVIDO
