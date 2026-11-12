"""Modelo `cargos` (docs/database-design.md §2.1)."""

from sqlalchemy import CheckConstraint, Index, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import (
    Base,
    ConAutores,
    ConBorradoLogico,
    ConId,
    ConMarcasDeTiempo,
    ConMigradoDe,
)

# Folio legible CA-000001 desde una secuencia propia (RN-04, docs/database-design.md §11).
# La secuencia la crea la migración; puede dejar huecos (rollback) y se acepta.
SECUENCIA_FOLIO = "seq_folio_cargos"


class Cargo(ConId, ConMarcasDeTiempo, ConAutores, ConBorradoLogico, ConMigradoDe, Base):
    __tablename__ = "cargos"

    folio: Mapped[str] = mapped_column(
        Text,
        unique=True,
        server_default=text(f"'CA-' || lpad(nextval('{SECUENCIA_FOLIO}')::text, 6, '0')"),
    )
    nombre: Mapped[str] = mapped_column(Text)
    descripcion: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("btrim(nombre) <> ''", name="nombre_no_vacio"),
        # Nombre único sin distinguir mayúsculas entre los no eliminados (se puede recrear).
        Index(
            "uq_cargos__nombre",
            func.lower(text("nombre")),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "uq_cargos__migrado_de",
            "migrado_de",
            unique=True,
            postgresql_where=text("migrado_de IS NOT NULL"),
        ),
    )
