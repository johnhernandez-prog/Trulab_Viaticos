"""Base declarativa de SQLAlchemy compartida por los modelos de todos los módulos.

La `naming_convention` aplica la nomenclatura de docs/database-design.md §9 para que Alembic
genere nombres de constraints e índices estables y predecibles:

- PK: `pk_<tabla>`
- índices: `ix_<tabla>__<columnas>`
- únicos: `uq_<tabla>__<columnas>`
- FK: `fk_<tabla>__<columna>__<tabla_ref>`
- checks: `ck_<tabla>__<regla>` (la regla es el `name` que se da al `CheckConstraint`)

Cada módulo de dominio define sus modelos en `app/modules/<dominio>/models.py` heredando de
`Base`; `alembic/env.py` los descubre e importa solo.

Los mixins de este archivo implementan las "columnas base" de docs/database-design.md §2.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, Text, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "ix": "ix_%(table_name)s__%(column_0_N_name)s",
    "uq": "uq_%(table_name)s__%(column_0_N_name)s",
    "fk": "fk_%(table_name)s__%(column_0_N_name)s__%(referred_table_name)s",
    "ck": "ck_%(table_name)s__%(constraint_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    # Toda marca de tiempo es TIMESTAMPTZ (UTC), nunca `timestamp without time zone`.
    type_annotation_map = {datetime: DateTime(timezone=True)}


class ConId:
    """PK UUID generada por la BD (ADR-011): no enumerable."""

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )


class ConMarcasDeTiempo:
    """`created_at` y `updated_at` (este lo actualiza el ORM en cada UPDATE)."""

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class ConAutores:
    """Quién creó y quién modificó por última vez (`NULL` = registro del sistema o del ETL).

    Los fija el service con el usuario autenticado (desde S1-10). Los usuarios no se borran,
    así que la FK es `RESTRICT`. Todas las FK llevan índice (docs/database-design.md §5).
    """

    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )


class ConBorradoLogico:
    """Eliminación lógica (ADR-013, docs/database-design.md §8)."""

    deleted_at: Mapped[datetime | None]


class ConMigradoDe:
    """ID o valor original de AppSheet, para trazabilidad e idempotencia del ETL (F10).

    Cada tabla declara su índice `UNIQUE (migrado_de) WHERE migrado_de IS NOT NULL`.
    """

    migrado_de: Mapped[str | None] = mapped_column(Text)
