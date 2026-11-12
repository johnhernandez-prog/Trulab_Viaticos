"""Modelo `usuarios` (docs/database-design.md §2.2).

- Acceso híbrido (ADR-027, RN-12, RN-15):
  - VIAJERO, ADMIN y FINANCIERO entran con `username` + contraseña: ambos son obligatorios y
    `password_hash` solo admite el formato PHC de Argon2id (nunca una contraseña en claro).
  - SUPERADMIN entra solo con Google: sin contraseña, y es el único que puede tener `google_sub`
    (el `sub` estable del ID token, que se fija en el primer login).
  - Los `CHECK` por rol obligan a ajustar las credenciales en la misma operación que cambia el
    rol (promover a SUPERADMIN borra la contraseña; degradar exige una temporal).
- `correo` (CITEXT, sin distinguir mayúsculas) es el contacto y el destino de la recuperación de
  contraseña; para SUPERADMIN, además, la identidad de Google (el dominio lo valida la app).
- Ciclo de vida con `activo` (RN-11), no con `deleted_at`: un inactivo sigue en el historial.
- `cargo_id` y `celula_id` usan `use_alter`: `cargos` y `celulas` referencian a `usuarios`
  (`created_by`), así que esas FK se crean después de las tres tablas (ciclo de dependencias).
"""

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String, Text, text
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
    # Credenciales de los operativos (ADR-027). NULL en un SUPERADMIN.
    username: Mapped[str | None] = mapped_column(CITEXT, unique=True)
    # Hash Argon2id (formato PHC). Nunca en logs, auditoría ni respuestas de la API.
    password_hash: Mapped[str | None] = mapped_column(String(255))
    debe_cambiar_password: Mapped[bool] = mapped_column(server_default=text("false"))
    password_cambiada_at: Mapped[datetime | None]
    # Bloqueo temporal por intentos fallidos (S-14).
    intentos_fallidos: Mapped[int] = mapped_column(SmallInteger, server_default=text("0"))
    bloqueado_hasta: Mapped[datetime | None]
    # Prestador de servicios externo: define la tabla tarifaria y el formato adjunto (RN-29, RN-33).
    es_prestador_servicios: Mapped[bool] = mapped_column(server_default=text("false"))
    # Para la emisión de tiquetes (RN-31). Dato personal (RNF-09).
    fecha_nacimiento: Mapped[date | None]
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
        # --- Acceso híbrido (ADR-027) ---
        CheckConstraint(
            "(rol <> 'SUPERADMIN' AND password_hash IS NOT NULL) "
            "OR (rol = 'SUPERADMIN' AND password_hash IS NULL)",
            name="password_segun_rol",
        ),
        CheckConstraint(r"password_hash ~ '^\$argon2id\$'", name="password_argon2id"),
        CheckConstraint("rol = 'SUPERADMIN' OR username IS NOT NULL", name="username_operativo"),
        # `::text`: sobre CITEXT el operador `~` no distingue mayúsculas; se exigen minúsculas.
        CheckConstraint(r"username::text ~ '^[a-z0-9._-]{3,40}$'", name="username_formato"),
        CheckConstraint("rol = 'SUPERADMIN' OR google_sub IS NULL", name="google_solo_superadmin"),
        CheckConstraint(
            "rol <> 'SUPERADMIN' OR NOT debe_cambiar_password",
            name="superadmin_sin_cambio_password",
        ),
        CheckConstraint("intentos_fallidos >= 0", name="intentos_fallidos_no_negativos"),
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
