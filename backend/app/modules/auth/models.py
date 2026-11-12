"""Modelo `sesiones` (docs/database-design.md §2.9): una fila por refresh token emitido.

Solo se guarda el **hash SHA-256** del refresh token (64 caracteres hexadecimales), nunca el
token: un `CHECK` lo exige, así que un token en claro no puede guardarse ni por error. La
rotación, la revocación y la emisión de tokens son de S1-08.
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
