"""Auditoría de seguridad y administración (docs/database-design.md §2.8 y §7, RF-014).

- Tabla `auditoria` de **solo inserción**: `trulab_app` no tiene `UPDATE` ni `DELETE`, y un
  trigger rechaza `UPDATE`, `DELETE` y `TRUNCATE` incluso para el dueño del esquema.
- `registrar()` agrega la fila a la sesión del llamador: se guarda en la **misma transacción**
  que el cambio auditado (si el cambio se revierte, su auditoría también).
- `datos` nunca lleva secretos (tokens, contraseñas y sus hashes, cookies) ni la cédula
  completa: `registrar()` rechaza las claves prohibidas y enmascara la cédula.

Solo la consulta SUPERADMIN (endpoint en S1-10).
"""

import uuid
from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Any, cast

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, Index, Text, func, text
from sqlalchemy.dialects.postgresql import INET, JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.models import Base


class AccionAuditoria(StrEnum):
    """Acciones auditadas. Se agregan aquí; la BD solo exige el formato (`MAYUSCULAS_CON_GUION`)."""

    USUARIO_CREAR = "USUARIO_CREAR"
    USUARIO_EDITAR = "USUARIO_EDITAR"
    ROL_CAMBIAR = "ROL_CAMBIAR"
    USUARIO_ACTIVAR = "USUARIO_ACTIVAR"
    USUARIO_DESACTIVAR = "USUARIO_DESACTIVAR"
    CARGO_CREAR = "CARGO_CREAR"
    CARGO_EDITAR = "CARGO_EDITAR"
    CARGO_ELIMINAR = "CARGO_ELIMINAR"
    CATALOGO_CREAR = "CATALOGO_CREAR"
    CATALOGO_EDITAR = "CATALOGO_EDITAR"
    CATALOGO_DESACTIVAR = "CATALOGO_DESACTIVAR"
    ACCESO_DENEGADO = "ACCESO_DENEGADO"
    # Acceso híbrido (ADR-027).
    LOGIN_EXITOSO = "LOGIN_EXITOSO"
    LOGIN_FALLIDO = "LOGIN_FALLIDO"
    PASSWORD_CAMBIADA = "PASSWORD_CAMBIADA"  # noqa: S105 (nombre de acción, no un secreto)
    PASSWORD_RECUPERACION_SOLICITADA = "PASSWORD_RECUPERACION_SOLICITADA"  # noqa: S105
    SUPERADMIN_ASIGNADO = "SUPERADMIN_ASIGNADO"


class Auditoria(Base):
    __tablename__ = "auditoria"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # Actor; NULL = el sistema (seed, ETL) o un intento de acceso sin usuario.
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), index=True
    )
    accion: Mapped[str] = mapped_column(Text)
    entidad: Mapped[str] = mapped_column(Text)
    entidad_id: Mapped[uuid.UUID | None]
    datos: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint("accion ~ '^[A-Z][A-Z_]*$'", name="accion_formato"),
        CheckConstraint("jsonb_typeof(datos) = 'object'", name="datos_objeto"),
        Index("ix_auditoria__entidad_entidad_id", "entidad", "entidad_id"),
        Index("ix_auditoria__created_at", "created_at"),
    )


# Claves que nunca pueden aparecer en `datos` (en ningún nivel, sin distinguir mayúsculas).
CLAVES_PROHIBIDAS = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "token_hash",
        "password",
        "password_hash",
        "password_actual",
        "nueva_password",
        "password_temporal",
        "reset_token",
        "contrasena",
        "contraseña",
        "secret",
        "secreto",
        "cookie",
        "authorization",
    }
)
CLAVES_CEDULA = frozenset({"cedula", "cédula"})


class DatoProhibidoError(ValueError):
    """Se intentó auditar un secreto. Es un error de programación, no de usuario."""


def enmascarar_cedula(valor: object) -> object:
    """Deja visibles solo los últimos 4 caracteres: `1234567890` → `******7890`."""
    if not isinstance(valor, str) or not valor:
        return valor
    visibles = valor[-4:]
    return "*" * max(len(valor) - 4, 0) + visibles


def sanear(datos: object) -> object:
    """Copia de `datos` sin secretos y con la cédula enmascarada (recursivo)."""
    if isinstance(datos, Mapping):
        limpio: dict[str, object] = {}
        for clave, valor in datos.items():
            nombre = str(clave).lower()
            if nombre in CLAVES_PROHIBIDAS:
                raise DatoProhibidoError(f"La auditoría no puede guardar '{clave}'")
            if nombre in CLAVES_CEDULA:
                limpio[str(clave)] = enmascarar_cedula(sanear(valor))
            else:
                limpio[str(clave)] = sanear(valor)
        return limpio
    if isinstance(datos, list | tuple):
        return [sanear(valor) for valor in datos]
    return datos


def registrar(
    session: Session,
    accion: AccionAuditoria,
    entidad: str,
    entidad_id: uuid.UUID | None = None,
    *,
    usuario_id: uuid.UUID | None = None,
    datos: Mapping[str, object] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> Auditoria:
    """Agrega un evento de auditoría a la transacción en curso (no hace commit)."""
    # `sanear` devuelve un dict cuando recibe un dict.
    limpio = cast(dict[str, Any], sanear(dict(datos or {})))
    evento = Auditoria(
        accion=accion.value,
        entidad=entidad,
        entidad_id=entidad_id,
        usuario_id=usuario_id,
        datos=limpio,
        ip=ip,
        user_agent=user_agent,
    )
    session.add(evento)
    return evento
