"""Tablas maestras de catálogo (docs/database-design.md §2.3).

Las tres (`celulas`, `proyectos`, `rubros`) tienen la misma estructura: `ConCatalogo`.
Sin `deleted_at`: un valor se desactiva (`activo = false`) y, si está en uso, la FK `RESTRICT`
impide borrarlo (RN-24).
"""

from sqlalchemy import CheckConstraint, Index, SmallInteger, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, ConAutores, ConId, ConMarcasDeTiempo, ConMigradoDe


class ConCatalogo(ConId, ConMarcasDeTiempo, ConAutores, ConMigradoDe):
    # Valor EXACTO de AppSheet (por ejemplo 'Conexión Agro'); único sin distinguir mayúsculas.
    nombre: Mapped[str] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(server_default=text("true"))
    # Orden opcional en los selectores (si es NULL, alfabético).
    orden: Mapped[int | None] = mapped_column(SmallInteger)


class Celula(ConCatalogo, Base):
    __tablename__ = "celulas"

    __table_args__ = (
        CheckConstraint("btrim(nombre) <> ''", name="nombre_no_vacio"),
        Index("uq_celulas__nombre", func.lower(text("nombre")), unique=True),
        Index(
            "uq_celulas__migrado_de",
            "migrado_de",
            unique=True,
            postgresql_where=text("migrado_de IS NOT NULL"),
        ),
    )
