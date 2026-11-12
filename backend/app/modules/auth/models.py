"""Modelos de autenticación (docs/database-design.md §2.11 y §2.12).

- `sesiones`: una fila por refresh token emitido.
- `tokens_recuperacion_password`: una fila por enlace de restablecimiento (ADR-027, RN-15); de un
  solo uso (`used_at`) y de vida corta (`PASSWORD_RESET_TTL_MINUTES`, 15–30 min).

En ambas se guarda solo el **hash SHA-256** del token (64 caracteres hexadecimales), nunca el
token: un `CHECK` lo exige, así que un token en claro no puede guardarse ni por error. La
emisión, rotación, revocación y consumo de tokens son de S1-08.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base


class Sesion(Base):
    __tablename__ = "sesiones"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Al borrar un usuario (solo en una purga manual) se borran sus sesiones.
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip: Mapped[str | None] = mapped_column(INET)

    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_sha256"),
        CheckConstraint("expires_at > created_at", name="expira_despues_de_crear"),
    )


class TokenRecuperacionPassword(Base):
    __tablename__ = "tokens_recuperacion_password"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    expires_at: Mapped[datetime] = mapped_column(index=True)
    # Marca el uso (o la invalidación al pedir uno nuevo): un token usado no vuelve a servir.
    used_at: Mapped[datetime | None]
    # IP de quien pidió el restablecimiento.
    ip: Mapped[str | None] = mapped_column(INET)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="token_hash_sha256"),
        CheckConstraint("expires_at > created_at", name="expira_despues_de_crear"),
    )
