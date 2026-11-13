"""Gastos de un viático en etapa LEGALIZACION (docs/database-design.md §2.8; AppSheet
`Registro_Gastos`).

- Proyecto híbrido (RN-16, ADR-031): exactamente uno de `proyecto_id` (catálogo) o
  `proyecto_otro` (texto de la opción "Otro").
- `soporte_id` es la **imagen** y `archivo_id` el **PDF** (DP-15, RN-13); cada archivo pertenece
  a un solo gasto. Al menos uno de los dos es obligatorio para aprobar y liquidar, no para
  guardar (RN-21): lo valida `transicionar()` y la vista expone `gastos_sin_comprobante`.
- "Sin fecha futura" (RN-07) y "solo en etapa LEGALIZACION" las valida el service.
- Borrado lógico (`deleted_at`): el saldo los excluye.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import (
    Base,
    ConAutores,
    ConBorradoLogico,
    ConId,
    ConMarcasDeTiempo,
    ConMigradoDe,
)
from app.modules.viaticos.models import PROYECTO_OTRO_MAXIMO


class Gasto(ConId, ConMarcasDeTiempo, ConAutores, ConBorradoLogico, ConMigradoDe, Base):
    __tablename__ = "gastos"

    viatico_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("viaticos.id", ondelete="RESTRICT"), index=True
    )
    fecha_factura: Mapped[date]
    rubro_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("rubros.id", ondelete="RESTRICT"), index=True
    )
    proyecto_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True
    )
    proyecto_otro: Mapped[str | None] = mapped_column(String(PROYECTO_OTRO_MAXIMO))
    concepto: Mapped[str] = mapped_column(Text)
    cc_nit: Mapped[str | None] = mapped_column(Text)
    empresa: Mapped[str | None] = mapped_column(Text)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    soporte_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("archivos.id", ondelete="RESTRICT"), unique=True
    )
    archivo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("archivos.id", ondelete="RESTRICT"), unique=True
    )
    observaciones: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("valor > 0", name="valor_positivo"),
        CheckConstraint("btrim(concepto) <> ''", name="concepto_no_vacio"),
        CheckConstraint(
            "(proyecto_id IS NOT NULL AND proyecto_otro IS NULL) "
            "OR (proyecto_id IS NULL AND proyecto_otro IS NOT NULL)",
            name="proyecto_exclusivo",
        ),
        CheckConstraint(
            "proyecto_otro IS NULL OR char_length(btrim(proyecto_otro)) >= 3",
            name="proyecto_otro_longitud",
        ),
        CheckConstraint(
            "soporte_id IS NULL OR archivo_id IS NULL OR soporte_id <> archivo_id",
            name="soporte_y_archivo_distintos",
        ),
        Index(
            "ix_gastos__fecha_factura_proyecto",
            "fecha_factura",
            "proyecto_id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_gastos__proyecto_otro",
            func.lower(text("proyecto_otro")),
            postgresql_where=text("proyecto_otro IS NOT NULL"),
        ),
        Index(
            "uq_gastos__migrado_de",
            "migrado_de",
            unique=True,
            postgresql_where=text("migrado_de IS NOT NULL"),
        ),
    )
