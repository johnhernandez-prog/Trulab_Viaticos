"""Viático unificado (ADR-029, docs/database-design.md §2.6, §2.7 y §2.9).

- `viaticos`: un registro con folio `VT-000001` recorre la etapa `SOLICITUD` (solo
  `CON_SOLICITUD`) y la `LEGALIZACION` con el mismo id y folio. `valor_transferido` es una
  columna **generada** (`recursos_propios ? 0 : valor_asignado`, RN-14): nunca se escribe.
- `viatico_trayectos`: 1 a 5 tramos de la solicitud, con la **instantánea** de las tarifas
  aplicadas (un cambio de tarifa no altera solicitudes existentes).
- `viatico_eventos`: historial de **solo inserción** (sin `UPDATE`/`DELETE` para `trulab_app`
  y un trigger que lo impide también al dueño del esquema).

Los `CHECK` aseguran la coherencia que no depende del flujo; la obligatoriedad de una solicitud
completa (RN-06) y las transiciones las valida el service, porque la solicitud se guarda como
borrador `PENDIENTE` antes de estar completa.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Computed,
    ForeignKey,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    AccionViatico,
    DimensionEvento,
    EstadoFinanciero,
    EstadoOperativo,
    Etapa,
    Modalidad,
    valores_sql,
)
from app.core.models import (
    Base,
    ConAutores,
    ConBorradoLogico,
    ConId,
    ConMarcasDeTiempo,
    ConMigradoDe,
)

# Folio legible VT-000001 (RN-04, docs/database-design.md §11). La secuencia la crea la migración.
SECUENCIA_FOLIO = "seq_folio_viaticos"
PROYECTO_OTRO_MAXIMO = 150
Dinero = Numeric(14, 2)

_SOLICITUD_VACIA = (
    "proyecto_id IS NULL AND proyecto_otro IS NULL AND lider_proyecto IS NULL "
    "AND presupuesto_solicitado IS NULL AND firma_archivo_id IS NULL "
    "AND formato_adjunto_id IS NULL AND solicitud_aprobada_at IS NULL "
    "AND legalizacion_habilitada_at IS NULL "
    "AND NOT requiere_tiquete AND NOT requiere_gastos_viaje"
)


class Viatico(ConId, ConMarcasDeTiempo, ConAutores, ConBorradoLogico, ConMigradoDe, Base):
    __tablename__ = "viaticos"

    folio: Mapped[str] = mapped_column(
        Text,
        unique=True,
        server_default=text(f"'VT-' || lpad(nextval('{SECUENCIA_FOLIO}')::text, 6, '0')"),
    )
    modalidad: Mapped[str] = mapped_column(Text)
    etapa: Mapped[str] = mapped_column(Text)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    motivo_viaje: Mapped[str] = mapped_column(Text)
    fecha_legalizacion: Mapped[date] = mapped_column(server_default=func.current_date())

    # --- Instantánea del colaborador al crear (RN-17, ADR-020) ---
    colaborador_nombre: Mapped[str] = mapped_column(Text)
    colaborador_cargo: Mapped[str | None] = mapped_column(Text)
    colaborador_cedula: Mapped[str | None] = mapped_column(Text)  # dato personal (RNF-09)
    colaborador_celula: Mapped[str | None] = mapped_column(Text)
    colaborador_es_prestador: Mapped[bool]
    colaborador_fecha_nacimiento: Mapped[date | None]

    # --- Solicitud (solo CON_SOLICITUD; nulos en LEGALIZACION_DIRECTA) ---
    proyecto_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proyectos.id", ondelete="RESTRICT"), index=True
    )
    proyecto_otro: Mapped[str | None] = mapped_column(String(PROYECTO_OTRO_MAXIMO))
    lider_proyecto: Mapped[str | None] = mapped_column(Text)
    empresa: Mapped[str | None] = mapped_column(Text)
    requiere_tiquete: Mapped[bool] = mapped_column(server_default=text("false"))
    requiere_gastos_viaje: Mapped[bool] = mapped_column(server_default=text("false"))
    presupuesto_solicitado: Mapped[Decimal | None] = mapped_column(Dinero)
    comentarios: Mapped[str | None] = mapped_column(Text)
    firma_archivo_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("archivos.id", ondelete="RESTRICT"), index=True
    )
    formato_adjunto_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("archivos.id", ondelete="RESTRICT"), index=True
    )
    solicitud_aprobada_at: Mapped[datetime | None]
    legalizacion_habilitada_at: Mapped[datetime | None]

    # --- Estados y dinero ---
    recursos_propios: Mapped[bool] = mapped_column(server_default=text("false"))
    valor_asignado: Mapped[Decimal] = mapped_column(Dinero, server_default=text("0"))
    valor_transferido: Mapped[Decimal] = mapped_column(
        Dinero,
        Computed(
            # Tal como PostgreSQL la normaliza: así `alembic check` no la ve distinta.
            "CASE WHEN recursos_propios THEN (0)::numeric ELSE valor_asignado END",
            persisted=True,
        ),
    )
    estado: Mapped[str] = mapped_column(Text, server_default=text("'PENDIENTE'"))
    estado_financiero: Mapped[str] = mapped_column(Text, server_default=text("'PENDIENTE'"))
    aprobada_at: Mapped[datetime | None]
    devuelta_at: Mapped[datetime | None]
    estado_financiero_at: Mapped[datetime | None]
    observaciones: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(f"modalidad IN ({valores_sql(Modalidad)})", name="modalidad"),
        CheckConstraint(f"etapa IN ({valores_sql(Etapa)})", name="etapa"),
        CheckConstraint(f"estado IN ({valores_sql(EstadoOperativo)})", name="estado"),
        CheckConstraint(
            f"estado_financiero IN ({valores_sql(EstadoFinanciero)})", name="estado_financiero"
        ),
        # La legalización directa nace (y se queda) en LEGALIZACION.
        CheckConstraint(
            "modalidad = 'CON_SOLICITUD' OR etapa = 'LEGALIZACION'", name="etapa_segun_modalidad"
        ),
        CheckConstraint(
            "char_length(btrim(motivo_viaje)) BETWEEN 3 AND 500", name="motivo_viaje_longitud"
        ),
        CheckConstraint("btrim(colaborador_nombre) <> ''", name="colaborador_nombre_no_vacio"),
        CheckConstraint(
            "proyecto_otro IS NULL OR char_length(btrim(proyecto_otro)) >= 3",
            name="proyecto_otro_longitud",
        ),
        CheckConstraint(
            "presupuesto_solicitado IS NULL OR presupuesto_solicitado >= 0",
            name="presupuesto_no_negativo",
        ),
        CheckConstraint("valor_asignado >= 0", name="valor_asignado_no_negativo"),
        # DP-17: recursos propios solo en legalización directa.
        CheckConstraint(
            "NOT recursos_propios OR modalidad = 'LEGALIZACION_DIRECTA'",
            name="recursos_propios_directa",
        ),
        # RN-03: pagar o procesar exige la legalización aprobada.
        CheckConstraint(
            "estado_financiero NOT IN ('PAGADO', 'PROCESADO') "
            "OR (estado = 'APROBADO' AND etapa = 'LEGALIZACION')",
            name="liquidacion_requiere_aprobado",
        ),
        # RN-16, ADR-031: exactamente uno de proyecto del catálogo o "Otro", solo en la solicitud.
        CheckConstraint(
            "(modalidad = 'CON_SOLICITUD' AND ("
            "(proyecto_id IS NOT NULL AND proyecto_otro IS NULL) "
            "OR (proyecto_id IS NULL AND proyecto_otro IS NOT NULL))) "
            "OR (modalidad = 'LEGALIZACION_DIRECTA' "
            "AND proyecto_id IS NULL AND proyecto_otro IS NULL)",
            name="proyecto_exclusivo",
        ),
        CheckConstraint(
            "modalidad <> 'CON_SOLICITUD' "
            "OR (lider_proyecto IS NOT NULL AND btrim(lider_proyecto) <> '')",
            name="lider_en_solicitud",
        ),
        CheckConstraint(
            f"modalidad <> 'LEGALIZACION_DIRECTA' OR ({_SOLICITUD_VACIA})",
            name="solicitud_solo_con_solicitud",
        ),
        CheckConstraint(
            "NOT (etapa = 'LEGALIZACION' AND modalidad = 'CON_SOLICITUD') "
            "OR legalizacion_habilitada_at IS NOT NULL",
            name="legalizacion_habilitada",
        ),
        Index(
            "ix_viaticos__usuario_etapa_estado",
            "usuario_id",
            "etapa",
            "estado",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_viaticos__bandeja",
            "estado",
            "estado_financiero",
            "etapa",
            text("fecha_legalizacion DESC"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_viaticos__proyecto_otro",
            func.lower(text("proyecto_otro")),
            postgresql_where=text("proyecto_otro IS NOT NULL"),
        ),
        Index(
            "uq_viaticos__migrado_de",
            "migrado_de",
            unique=True,
            postgresql_where=text("migrado_de IS NOT NULL"),
        ),
    )


# Conceptos de la instantánea tarifaria de un trayecto (`trans_interno` ya resuelto por días).
CONCEPTOS_INSTANTANEA = (
    "vr_alimentacion",
    "otros_gastos",
    "trans_interno",
    "transporte_aeropuerto",
    "transporte_intermunicipal",
    "subtotal_estadia",
)


class ViaticoTrayecto(ConId, ConMarcasDeTiempo, ConAutores, Base):
    """Tramo de la solicitud. Sin `deleted_at`: se reemplazan en bloque mientras es editable."""

    __tablename__ = "viatico_trayectos"

    viatico_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("viaticos.id", ondelete="CASCADE"))
    orden: Mapped[int] = mapped_column(SmallInteger)
    ciudad_origen: Mapped[str] = mapped_column(Text)
    ciudad_destino: Mapped[str] = mapped_column(Text)
    fecha_ida: Mapped[datetime]
    fecha_regreso: Mapped[datetime]
    requiere_hospedaje: Mapped[bool] = mapped_column(server_default=text("false"))
    dias_estadia: Mapped[int] = mapped_column(SmallInteger)
    # Tarifa aplicada; NULL si no se calculó (RN-33 o sin gastos de viaje).
    tarifa_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tarifas_viaticos.id", ondelete="RESTRICT"), index=True
    )
    vr_alimentacion: Mapped[Decimal | None] = mapped_column(Dinero)
    otros_gastos: Mapped[Decimal | None] = mapped_column(Dinero)
    trans_interno: Mapped[Decimal | None] = mapped_column(Dinero)
    transporte_aeropuerto: Mapped[Decimal | None] = mapped_column(Dinero)
    transporte_intermunicipal: Mapped[Decimal | None] = mapped_column(Dinero)
    subtotal_estadia: Mapped[Decimal | None] = mapped_column(Dinero)

    __table_args__ = (
        CheckConstraint("orden BETWEEN 1 AND 5", name="orden_rango"),
        CheckConstraint("btrim(ciudad_origen) <> ''", name="ciudad_origen_no_vacia"),
        CheckConstraint("btrim(ciudad_destino) <> ''", name="ciudad_destino_no_vacia"),
        # RN-30: origen y destino distintos, salvo el destino "Otro".
        CheckConstraint(
            "ciudad_destino <> ciudad_origen OR ciudad_destino = 'Otro'",
            name="destino_distinto_de_origen",
        ),
        CheckConstraint("fecha_regreso >= fecha_ida", name="regreso_despues_de_ida"),
        CheckConstraint("dias_estadia >= 1", name="dias_estadia_minimo"),
        *(
            CheckConstraint(
                f"{concepto} IS NULL OR {concepto} >= 0", name=f"{concepto}_no_negativo"
            )
            for concepto in CONCEPTOS_INSTANTANEA
        ),
        Index("uq_viatico_trayectos__viatico_orden", "viatico_id", "orden", unique=True),
    )


class ViaticoEvento(ConId, Base):
    """Historial funcional de las tres dimensiones (etapa, operativo, financiero)."""

    __tablename__ = "viatico_eventos"

    viatico_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("viaticos.id", ondelete="RESTRICT"))
    etapa: Mapped[str] = mapped_column(Text)
    accion: Mapped[str] = mapped_column(Text)
    dimension: Mapped[str | None] = mapped_column(Text)
    estado_anterior: Mapped[str | None] = mapped_column(Text)
    estado_nuevo: Mapped[str | None] = mapped_column(Text)
    comentario: Mapped[str | None] = mapped_column(Text)
    datos: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (
        CheckConstraint(f"etapa IN ({valores_sql(Etapa)})", name="etapa"),
        CheckConstraint(f"accion IN ({valores_sql(AccionViatico)})", name="accion"),
        CheckConstraint(
            f"dimension IS NULL OR dimension IN ({valores_sql(DimensionEvento)})",
            name="dimension",
        ),
        CheckConstraint("datos IS NULL OR jsonb_typeof(datos) = 'object'", name="datos_objeto"),
        Index("ix_viatico_eventos__viatico_created_at", "viatico_id", "created_at"),
    )
