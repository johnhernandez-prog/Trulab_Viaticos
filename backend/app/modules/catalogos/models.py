"""Tablas maestras de catálogo (docs/database-design.md §2.3 y §2.5).

- `celulas`, `proyectos` y `rubros` comparten la estructura `ConCatalogo`; `proyectos` agrega
  `codigo` y `exige_formato_prestador` (RN-33).
- `tarifas_viaticos` (ADR-030): una fila por ciudad de destino y tipo de vinculación, con los 6
  conceptos tarifarios. Sus valores iniciales vienen de `datos/tarifas_viaticos.csv`.
- Sin `deleted_at`: un valor se desactiva (`activo = false`) y, si está en uso, la FK `RESTRICT`
  impide borrarlo (RN-24).
"""

from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Index, Numeric, SmallInteger, Text, func, text
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


def _indices_catalogo(tabla: str) -> tuple[Index, Index]:
    return (
        Index(f"uq_{tabla}__nombre", func.lower(text("nombre")), unique=True),
        Index(
            f"uq_{tabla}__migrado_de",
            "migrado_de",
            unique=True,
            postgresql_where=text("migrado_de IS NOT NULL"),
        ),
    )


class Proyecto(ConCatalogo, Base):
    __tablename__ = "proyectos"

    # Código corto de la hoja PROYECTOS (p. ej. `P-CONEXI-002`).
    codigo: Mapped[str | None] = mapped_column(Text)
    # Prestador + proyecto con esta marca: adjunta formato en vez de calcular (RN-33).
    exige_formato_prestador: Mapped[bool] = mapped_column(server_default=text("false"))

    __table_args__ = (
        CheckConstraint("btrim(nombre) <> ''", name="nombre_no_vacio"),
        CheckConstraint("codigo IS NULL OR btrim(codigo) <> ''", name="codigo_no_vacio"),
        *_indices_catalogo("proyectos"),
        Index(
            "uq_proyectos__codigo",
            "codigo",
            unique=True,
            postgresql_where=text("codigo IS NOT NULL"),
        ),
    )


class Rubro(ConCatalogo, Base):
    __tablename__ = "rubros"

    __table_args__ = (
        CheckConstraint("btrim(nombre) <> ''", name="nombre_no_vacio"),
        *_indices_catalogo("rubros"),
    )


# Los 6 conceptos tarifarios, en COP (NUMERIC(14,2), ADR-012).
CONCEPTOS_TARIFA = (
    "vr_alimentacion",
    "otros_gastos",
    "transporte_aeropuerto",
    "transporte_intermunicipal",
    "trans_interno_dia_1",
    "trans_interno_varios_dias",
)

Dinero = Numeric(14, 2)


class TarifaViatico(ConId, ConMarcasDeTiempo, ConAutores, ConMigradoDe, Base):
    __tablename__ = "tarifas_viaticos"

    # Destino tal como se ve en el selector (`Bogotá`, `Otro`). `migrado_de` = clave legada.
    ciudad: Mapped[str] = mapped_column(Text)
    es_prestador_servicios: Mapped[bool] = mapped_column(Boolean)
    vr_alimentacion: Mapped[Decimal] = mapped_column(Dinero)  # por día
    otros_gastos: Mapped[Decimal] = mapped_column(Dinero)  # por día
    transporte_aeropuerto: Mapped[Decimal] = mapped_column(Dinero)  # por trayecto
    transporte_intermunicipal: Mapped[Decimal] = mapped_column(Dinero)  # por trayecto
    trans_interno_dia_1: Mapped[Decimal] = mapped_column(Dinero)  # si dias_estadia = 1
    trans_interno_varios_dias: Mapped[Decimal] = mapped_column(Dinero)  # si dias_estadia > 1
    activo: Mapped[bool] = mapped_column(server_default=text("true"))
    orden: Mapped[int | None] = mapped_column(SmallInteger)

    __table_args__ = (
        CheckConstraint("btrim(ciudad) <> ''", name="ciudad_no_vacia"),
        *(
            CheckConstraint(f"{concepto} >= 0", name=f"{concepto}_no_negativo")
            for concepto in CONCEPTOS_TARIFA
        ),
        Index(
            "uq_tarifas_viaticos__ciudad_tipo",
            func.lower(text("ciudad")),
            "es_prestador_servicios",
            unique=True,
        ),
        Index(
            "uq_tarifas_viaticos__migrado_de_tipo",
            "migrado_de",
            "es_prestador_servicios",
            unique=True,
            postgresql_where=text("migrado_de IS NOT NULL"),
        ),
    )
