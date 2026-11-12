"""La `naming_convention` de `Base` produce los nombres de docs/database-design.md §9."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Table,
    UniqueConstraint,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.core.models import NAMING_CONVENTION, Base


def test_base_usa_la_naming_convention_del_proyecto() -> None:
    assert Base.metadata.naming_convention == NAMING_CONVENTION


def test_nombres_de_constraints_e_indices() -> None:
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    Table("proyectos", metadata, Column("id", Integer, primary_key=True))
    gastos = Table(
        "gastos",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("proyecto_id", Integer, ForeignKey("proyectos.id")),
        Column("fecha_factura", Integer),
        Column("valor", Integer),
        UniqueConstraint("proyecto_id", "fecha_factura"),
        CheckConstraint("valor > 0", name="valor_positivo"),
    )
    indice = Index(None, gastos.c.fecha_factura, gastos.c.proyecto_id)

    dialecto = postgresql.dialect()  # type: ignore[no-untyped-call]
    ddl = str(CreateTable(gastos).compile(dialect=dialecto))

    assert "CONSTRAINT pk_gastos PRIMARY KEY" in ddl
    assert "CONSTRAINT uq_gastos__proyecto_id_fecha_factura UNIQUE" in ddl
    assert "CONSTRAINT ck_gastos__valor_positivo CHECK" in ddl
    assert "CONSTRAINT fk_gastos__proyecto_id__proyectos FOREIGN KEY" in ddl
    ddl_indice = str(CreateIndex(indice).compile(dialect=dialecto))  # type: ignore[no-untyped-call]
    assert "ix_gastos__fecha_factura_proyecto_id" in ddl_indice
