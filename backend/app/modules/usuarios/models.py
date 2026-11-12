"""Modelo `usuarios` (docs/database-design.md §2.2).

- Sin contraseña (DP-01, RN-15): el acceso es solo con Google Workspace (S1-08).
- `correo` (CITEXT) es la clave de acceso: se compara sin distinguir mayúsculas.
- `google_sub` (el `sub` estable del ID token de Google) se fija en el primer login.
- Ciclo de vida con `activo` (RN-11), no con `deleted_at`: un inactivo sigue en el historial.
- `cargo_id` y `celula_id` usan `use_alter`: `cargos` y `celulas` referencian a `usuarios`
  (`created_by`), así que esas FK se crean después de las tres tablas (ciclo de dependencias).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Rol
from app.core.models import (
    Base,
    ConAutores,
    ConBorradoLogico,
    ConId,
    ConMarcasDeTiempo,
    ConMigradoDe,
)

_ROLES_SQL = ", ".join(f"'{rol.value}'" for rol in Rol)


class Usuario(ConId, ConMarcasDeTiempo, ConAutores, ConBorradoLogico, ConMigradoDe, Base):
    __tablename__ = "usuarios"

    nombre_completo: Mapped[str] = mapped_column(Text)
    correo: Mapped[str] = mapped_column(CITEXT, unique=True)
    # Dato personal (RNF-09): nunca en logs ni completo en auditoría.
    cedula: Mapped[str | None] = mapped_column(Text)
    celula_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("celulas.id", ondelete="RESTRICT", use_alter=True), index=True
    )
    rol: Mapped[str] = mapped_column(Text)
    cargo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cargos.id", ondelete="RESTRICT", use_alter=True), index=True
    )
    activo: Mapped[bool] = mapped_column(server_default=text("true"))
    google_sub: Mapped[str | None] = mapped_column(Text, unique=True)
    ultimo_acceso: Mapped[datetime | None]

    __table_args__ = (
        CheckConstraint(f"rol IN ({_ROLES_SQL})", name="rol"),
        CheckConstraint("btrim(nombre_completo) <> ''", name="nombre_completo_no_vacio"),
        # Formato mínimo; el dominio de Google Workspace (RN-12) lo valida la app (configurable).
        CheckConstraint(r"correo ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'", name="correo_formato"),
        Index(
            "uq_usuarios__cedula",
            "cedula",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND cedula IS NOT NULL"),
        ),
        Index("ix_usuarios__rol", "rol", postgresql_where=text("activo")),
        Index(
            "uq_usuarios__migrado_de",
            "migrado_de",
            unique=True,
            postgresql_where=text("migrado_de IS NOT NULL"),
        ),
    )
