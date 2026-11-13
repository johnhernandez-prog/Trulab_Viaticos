"""Catálogos, tarifas, archivos, viáticos, trayectos, eventos, gastos y saldos (S2-02).

Modelo unificado de docs/database-design.md §2.3–§2.9 y §2.14 (ADR-029, ADR-030, ADR-031):

- `proyectos` y `rubros` (catálogos de SUPERADMIN, se desactivan) y `tarifas_viaticos`, con el
  **seed inicial de las 44 tarifas** leído de `app/modules/catalogos/datos/tarifas_viaticos.csv`
  (los valores viven en ese archivo validado por el dueño del producto, no en el código).
- `archivos` (metadatos de S3, inmutables) y `usuarios.firma_archivo_id`.
- `viaticos` con folio `VT-000001` (secuencia propia), `valor_transferido` **generado** y los
  `CHECK` de coherencia entre modalidad, etapa, proyecto y estados; `viatico_trayectos` (1–5 con
  instantánea tarifaria) y `viatico_eventos` (**solo inserción**, también para el dueño).
- `gastos` (proyecto híbrido, soporte imagen / archivo PDF) y la vista `v_viatico_saldos`
  (`security_invoker`, para que respete el RLS de S2-03).

Privilegios de `trulab_app` más estrictos que los por defecto:
- Sin `DELETE` en `proyectos`, `rubros`, `tarifas_viaticos` (se desactivan) ni en `viaticos` y
  `gastos` (borrado lógico). `viatico_trayectos` sí: se reemplazan en bloque.
- `archivos` y `viatico_eventos`: solo `INSERT` y `SELECT`.
- `v_viatico_saldos`: solo `SELECT`.

Revision ID: 2c36be2a3312
Revises: f7a1a890a1d3
Create Date: 2026-11-13 13:49:09.138724
"""

import csv
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2c36be2a3312"
down_revision: str | None = "f7a1a890a1d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CSV_TARIFAS = (
    Path(__file__).resolve().parents[2] / "app/modules/catalogos/datos/tarifas_viaticos.csv"
)
CONCEPTOS = (
    "vr_alimentacion",
    "otros_gastos",
    "transporte_aeropuerto",
    "transporte_intermunicipal",
    "trans_interno_dia_1",
    "trans_interno_varios_dias",
)

VISTA_SALDOS = """
CREATE VIEW v_viatico_saldos WITH (security_invoker = true) AS
SELECT
    v.id AS viatico_id,
    v.folio,
    v.usuario_id,
    v.modalidad,
    v.etapa,
    v.estado,
    v.estado_financiero,
    v.fecha_legalizacion,
    v.recursos_propios,
    v.valor_asignado,
    v.valor_transferido,
    v.presupuesto_solicitado,
    COALESCE(SUM(g.valor), 0)::numeric(14, 2) AS total_gastos,
    COUNT(g.id) AS cantidad_gastos,
    COUNT(g.id) FILTER (WHERE g.soporte_id IS NULL AND g.archivo_id IS NULL)
        AS gastos_sin_comprobante,
    (v.valor_transferido - COALESCE(SUM(g.valor), 0))::numeric(14, 2) AS saldo
FROM viaticos v
LEFT JOIN gastos g ON g.viatico_id = v.id AND g.deleted_at IS NULL
WHERE v.deleted_at IS NULL
GROUP BY v.id
"""


def _sembrar_tarifas() -> None:
    """Las 44 tarifas oficiales (22 destinos × empleado/prestador). `migrado_de` = clave legada."""
    tabla = sa.table(
        "tarifas_viaticos",
        sa.column("ciudad", sa.Text()),
        sa.column("es_prestador_servicios", sa.Boolean()),
        sa.column("orden", sa.SmallInteger()),
        sa.column("migrado_de", sa.Text()),
        *(sa.column(concepto, sa.Numeric(14, 2)) for concepto in CONCEPTOS),
    )
    with CSV_TARIFAS.open(encoding="utf-8", newline="") as archivo:
        filas = [
            {
                "ciudad": fila["ciudad"],
                "es_prestador_servicios": fila["es_prestador_servicios"] == "true",
                "orden": int(fila["orden"]),
                "migrado_de": fila["clave_legado"],
                **{concepto: Decimal(fila[concepto]) for concepto in CONCEPTOS},
            }
            for fila in csv.DictReader(archivo)
        ]
    op.bulk_insert(tabla, filas)


def upgrade() -> None:
    op.create_table(
        "archivos",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("nombre_original", sa.Text(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("tamano_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("proposito", sa.Text(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "btrim(nombre_original) <> ''", name=op.f("ck_archivos__nombre_original_no_vacio")
        ),
        sa.CheckConstraint(
            "btrim(storage_key) <> ''", name=op.f("ck_archivos__storage_key_no_vacia")
        ),
        sa.CheckConstraint(
            "mime_type ~ '^[a-z]+/[a-z0-9.+-]+$'", name=op.f("ck_archivos__mime_type_formato")
        ),
        sa.CheckConstraint(
            "proposito IN ('SOPORTE', 'ARCHIVO', 'FIRMA', 'FORMATO_PRESTADOR')",
            name=op.f("ck_archivos__proposito"),
        ),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_archivos__sha256_hex")),
        sa.CheckConstraint(
            "tamano_bytes > 0 AND tamano_bytes <= 10485760", name=op.f("ck_archivos__tamano_maximo")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["usuarios.id"],
            name=op.f("fk_archivos__created_by__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_archivos")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_archivos__storage_key")),
    )
    op.create_index(op.f("ix_archivos__created_by"), "archivos", ["created_by"], unique=False)
    op.create_index("ix_archivos__sha256", "archivos", ["sha256"], unique=False)
    op.create_table(
        "proyectos",
        sa.Column("codigo", sa.Text(), nullable=True),
        sa.Column(
            "exige_formato_prestador", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("migrado_de", sa.Text(), nullable=True),
        sa.CheckConstraint("btrim(nombre) <> ''", name=op.f("ck_proyectos__nombre_no_vacio")),
        sa.CheckConstraint(
            "codigo IS NULL OR btrim(codigo) <> ''", name=op.f("ck_proyectos__codigo_no_vacio")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["usuarios.id"],
            name=op.f("fk_proyectos__created_by__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["usuarios.id"],
            name=op.f("fk_proyectos__updated_by__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proyectos")),
    )
    op.create_index(op.f("ix_proyectos__created_by"), "proyectos", ["created_by"], unique=False)
    op.create_index(op.f("ix_proyectos__updated_by"), "proyectos", ["updated_by"], unique=False)
    op.create_index(
        "uq_proyectos__codigo",
        "proyectos",
        ["codigo"],
        unique=True,
        postgresql_where=sa.text("codigo IS NOT NULL"),
    )
    op.create_index(
        "uq_proyectos__migrado_de",
        "proyectos",
        ["migrado_de"],
        unique=True,
        postgresql_where=sa.text("migrado_de IS NOT NULL"),
    )
    op.create_index("uq_proyectos__nombre", "proyectos", [sa.text("lower(nombre)")], unique=True)
    op.create_table(
        "rubros",
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("migrado_de", sa.Text(), nullable=True),
        sa.CheckConstraint("btrim(nombre) <> ''", name=op.f("ck_rubros__nombre_no_vacio")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["usuarios.id"],
            name=op.f("fk_rubros__created_by__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["usuarios.id"],
            name=op.f("fk_rubros__updated_by__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rubros")),
    )
    op.create_index(op.f("ix_rubros__created_by"), "rubros", ["created_by"], unique=False)
    op.create_index(op.f("ix_rubros__updated_by"), "rubros", ["updated_by"], unique=False)
    op.create_index(
        "uq_rubros__migrado_de",
        "rubros",
        ["migrado_de"],
        unique=True,
        postgresql_where=sa.text("migrado_de IS NOT NULL"),
    )
    op.create_index("uq_rubros__nombre", "rubros", [sa.text("lower(nombre)")], unique=True)
    op.create_table(
        "tarifas_viaticos",
        sa.Column("ciudad", sa.Text(), nullable=False),
        sa.Column("es_prestador_servicios", sa.Boolean(), nullable=False),
        sa.Column("vr_alimentacion", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("otros_gastos", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("transporte_aeropuerto", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("transporte_intermunicipal", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("trans_interno_dia_1", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("trans_interno_varios_dias", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("migrado_de", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "btrim(ciudad) <> ''", name=op.f("ck_tarifas_viaticos__ciudad_no_vacia")
        ),
        sa.CheckConstraint(
            "otros_gastos >= 0", name=op.f("ck_tarifas_viaticos__otros_gastos_no_negativo")
        ),
        sa.CheckConstraint(
            "trans_interno_dia_1 >= 0",
            name=op.f("ck_tarifas_viaticos__trans_interno_dia_1_no_negativo"),
        ),
        sa.CheckConstraint(
            "trans_interno_varios_dias >= 0",
            name=op.f("ck_tarifas_viaticos__trans_interno_varios_dias_no_negativo"),
        ),
        sa.CheckConstraint(
            "transporte_aeropuerto >= 0",
            name=op.f("ck_tarifas_viaticos__transporte_aeropuerto_no_negativo"),
        ),
        sa.CheckConstraint(
            "transporte_intermunicipal >= 0",
            name=op.f("ck_tarifas_viaticos__transporte_intermunicipal_no_negativo"),
        ),
        sa.CheckConstraint(
            "vr_alimentacion >= 0", name=op.f("ck_tarifas_viaticos__vr_alimentacion_no_negativo")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["usuarios.id"],
            name=op.f("fk_tarifas_viaticos__created_by__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["usuarios.id"],
            name=op.f("fk_tarifas_viaticos__updated_by__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tarifas_viaticos")),
    )
    op.create_index(
        op.f("ix_tarifas_viaticos__created_by"), "tarifas_viaticos", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_tarifas_viaticos__updated_by"), "tarifas_viaticos", ["updated_by"], unique=False
    )
    op.create_index(
        "uq_tarifas_viaticos__ciudad_tipo",
        "tarifas_viaticos",
        [sa.text("lower(ciudad)"), "es_prestador_servicios"],
        unique=True,
    )
    op.create_index(
        "uq_tarifas_viaticos__migrado_de_tipo",
        "tarifas_viaticos",
        ["migrado_de", "es_prestador_servicios"],
        unique=True,
        postgresql_where=sa.text("migrado_de IS NOT NULL"),
    )
    op.execute("CREATE SEQUENCE seq_folio_viaticos")
    op.create_table(
        "viaticos",
        sa.Column(
            "folio",
            sa.Text(),
            server_default=sa.text("'VT-' || lpad(nextval('seq_folio_viaticos')::text, 6, '0')"),
            nullable=False,
        ),
        sa.Column("modalidad", sa.Text(), nullable=False),
        sa.Column("etapa", sa.Text(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("motivo_viaje", sa.Text(), nullable=False),
        sa.Column(
            "fecha_legalizacion", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False
        ),
        sa.Column("colaborador_nombre", sa.Text(), nullable=False),
        sa.Column("colaborador_cargo", sa.Text(), nullable=True),
        sa.Column("colaborador_cedula", sa.Text(), nullable=True),
        sa.Column("colaborador_celula", sa.Text(), nullable=True),
        sa.Column("colaborador_es_prestador", sa.Boolean(), nullable=False),
        sa.Column("colaborador_fecha_nacimiento", sa.Date(), nullable=True),
        sa.Column("proyecto_id", sa.Uuid(), nullable=True),
        sa.Column("proyecto_otro", sa.String(length=150), nullable=True),
        sa.Column("lider_proyecto", sa.Text(), nullable=True),
        sa.Column("empresa", sa.Text(), nullable=True),
        sa.Column(
            "requiere_tiquete", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "requiere_gastos_viaje", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("presupuesto_solicitado", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("comentarios", sa.Text(), nullable=True),
        sa.Column("firma_archivo_id", sa.Uuid(), nullable=True),
        sa.Column("formato_adjunto_id", sa.Uuid(), nullable=True),
        sa.Column("solicitud_aprobada_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legalizacion_habilitada_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "recursos_propios", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "valor_asignado",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "valor_transferido",
            sa.Numeric(precision=14, scale=2),
            sa.Computed(
                "CASE WHEN recursos_propios THEN (0)::numeric ELSE valor_asignado END",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("estado", sa.Text(), server_default=sa.text("'PENDIENTE'"), nullable=False),
        sa.Column(
            "estado_financiero", sa.Text(), server_default=sa.text("'PENDIENTE'"), nullable=False
        ),
        sa.Column("aprobada_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("devuelta_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("estado_financiero_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("migrado_de", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "(modalidad = 'CON_SOLICITUD' AND ((proyecto_id IS NOT NULL AND proyecto_otro IS "
            "NULL) OR (proyecto_id IS NULL AND proyecto_otro IS NOT NULL))) OR (modalidad = "
            "'LEGALIZACION_DIRECTA' AND proyecto_id IS NULL AND proyecto_otro IS NULL)",
            name=op.f("ck_viaticos__proyecto_exclusivo"),
        ),
        sa.CheckConstraint(
            "NOT (etapa = 'LEGALIZACION' AND modalidad = 'CON_SOLICITUD') OR "
            "legalizacion_habilitada_at IS NOT NULL",
            name=op.f("ck_viaticos__legalizacion_habilitada"),
        ),
        sa.CheckConstraint(
            "NOT recursos_propios OR modalidad = 'LEGALIZACION_DIRECTA'",
            name=op.f("ck_viaticos__recursos_propios_directa"),
        ),
        sa.CheckConstraint(
            "btrim(colaborador_nombre) <> ''", name=op.f("ck_viaticos__colaborador_nombre_no_vacio")
        ),
        sa.CheckConstraint(
            "estado IN ('PENDIENTE', 'APROBADO', 'RECHAZADO')", name=op.f("ck_viaticos__estado")
        ),
        sa.CheckConstraint(
            "estado_financiero IN ('PENDIENTE', 'TRANSFERIDO', 'PAGADO', 'PROCESADO')",
            name=op.f("ck_viaticos__estado_financiero"),
        ),
        sa.CheckConstraint(
            "estado_financiero NOT IN ('PAGADO', 'PROCESADO') OR (estado = 'APROBADO' AND etapa = "
            "'LEGALIZACION')",
            name=op.f("ck_viaticos__liquidacion_requiere_aprobado"),
        ),
        sa.CheckConstraint(
            "etapa IN ('SOLICITUD', 'LEGALIZACION')", name=op.f("ck_viaticos__etapa")
        ),
        sa.CheckConstraint(
            "modalidad <> 'CON_SOLICITUD' OR (lider_proyecto IS NOT NULL AND "
            "btrim(lider_proyecto) <> '')",
            name=op.f("ck_viaticos__lider_en_solicitud"),
        ),
        sa.CheckConstraint(
            "modalidad <> 'LEGALIZACION_DIRECTA' OR (proyecto_id IS NULL AND proyecto_otro IS "
            "NULL AND lider_proyecto IS NULL AND presupuesto_solicitado IS NULL AND "
            "firma_archivo_id IS NULL AND formato_adjunto_id IS NULL AND solicitud_aprobada_at IS "
            "NULL AND legalizacion_habilitada_at IS NULL AND NOT requiere_tiquete AND NOT "
            "requiere_gastos_viaje)",
            name=op.f("ck_viaticos__solicitud_solo_con_solicitud"),
        ),
        sa.CheckConstraint(
            "modalidad = 'CON_SOLICITUD' OR etapa = 'LEGALIZACION'",
            name=op.f("ck_viaticos__etapa_segun_modalidad"),
        ),
        sa.CheckConstraint(
            "modalidad IN ('CON_SOLICITUD', 'LEGALIZACION_DIRECTA')",
            name=op.f("ck_viaticos__modalidad"),
        ),
        sa.CheckConstraint(
            "char_length(btrim(motivo_viaje)) BETWEEN 3 AND 500",
            name=op.f("ck_viaticos__motivo_viaje_longitud"),
        ),
        sa.CheckConstraint(
            "presupuesto_solicitado IS NULL OR presupuesto_solicitado >= 0",
            name=op.f("ck_viaticos__presupuesto_no_negativo"),
        ),
        sa.CheckConstraint(
            "proyecto_otro IS NULL OR char_length(btrim(proyecto_otro)) >= 3",
            name=op.f("ck_viaticos__proyecto_otro_longitud"),
        ),
        sa.CheckConstraint(
            "valor_asignado >= 0", name=op.f("ck_viaticos__valor_asignado_no_negativo")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["usuarios.id"],
            name=op.f("fk_viaticos__created_by__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["firma_archivo_id"],
            ["archivos.id"],
            name=op.f("fk_viaticos__firma_archivo_id__archivos"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["formato_adjunto_id"],
            ["archivos.id"],
            name=op.f("fk_viaticos__formato_adjunto_id__archivos"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["proyecto_id"],
            ["proyectos.id"],
            name=op.f("fk_viaticos__proyecto_id__proyectos"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["usuarios.id"],
            name=op.f("fk_viaticos__updated_by__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_viaticos__usuario_id__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_viaticos")),
        sa.UniqueConstraint("folio", name=op.f("uq_viaticos__folio")),
    )
    op.create_index(
        "ix_viaticos__bandeja",
        "viaticos",
        ["estado", "estado_financiero", "etapa", sa.text("fecha_legalizacion DESC")],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(op.f("ix_viaticos__created_by"), "viaticos", ["created_by"], unique=False)
    op.create_index(
        op.f("ix_viaticos__firma_archivo_id"), "viaticos", ["firma_archivo_id"], unique=False
    )
    op.create_index(
        op.f("ix_viaticos__formato_adjunto_id"), "viaticos", ["formato_adjunto_id"], unique=False
    )
    op.create_index(op.f("ix_viaticos__proyecto_id"), "viaticos", ["proyecto_id"], unique=False)
    op.create_index(
        "ix_viaticos__proyecto_otro",
        "viaticos",
        [sa.text("lower(proyecto_otro)")],
        unique=False,
        postgresql_where=sa.text("proyecto_otro IS NOT NULL"),
    )
    op.create_index(op.f("ix_viaticos__updated_by"), "viaticos", ["updated_by"], unique=False)
    op.create_index(
        "ix_viaticos__usuario_etapa_estado",
        "viaticos",
        ["usuario_id", "etapa", "estado"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(op.f("ix_viaticos__usuario_id"), "viaticos", ["usuario_id"], unique=False)
    op.create_index(
        "uq_viaticos__migrado_de",
        "viaticos",
        ["migrado_de"],
        unique=True,
        postgresql_where=sa.text("migrado_de IS NOT NULL"),
    )
    op.create_table(
        "gastos",
        sa.Column("viatico_id", sa.Uuid(), nullable=False),
        sa.Column("fecha_factura", sa.Date(), nullable=False),
        sa.Column("rubro_id", sa.Uuid(), nullable=False),
        sa.Column("proyecto_id", sa.Uuid(), nullable=True),
        sa.Column("proyecto_otro", sa.String(length=150), nullable=True),
        sa.Column("concepto", sa.Text(), nullable=False),
        sa.Column("cc_nit", sa.Text(), nullable=True),
        sa.Column("empresa", sa.Text(), nullable=True),
        sa.Column("valor", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("soporte_id", sa.Uuid(), nullable=True),
        sa.Column("archivo_id", sa.Uuid(), nullable=True),
        sa.Column("observaciones", sa.Text(), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("migrado_de", sa.Text(), nullable=True),
        sa.CheckConstraint("btrim(concepto) <> ''", name=op.f("ck_gastos__concepto_no_vacio")),
        sa.CheckConstraint(
            "(proyecto_id IS NOT NULL AND proyecto_otro IS NULL) OR (proyecto_id IS NULL AND "
            "proyecto_otro IS NOT NULL)",
            name=op.f("ck_gastos__proyecto_exclusivo"),
        ),
        sa.CheckConstraint(
            "proyecto_otro IS NULL OR char_length(btrim(proyecto_otro)) >= 3",
            name=op.f("ck_gastos__proyecto_otro_longitud"),
        ),
        sa.CheckConstraint(
            "soporte_id IS NULL OR archivo_id IS NULL OR soporte_id <> archivo_id",
            name=op.f("ck_gastos__soporte_y_archivo_distintos"),
        ),
        sa.CheckConstraint("valor > 0", name=op.f("ck_gastos__valor_positivo")),
        sa.ForeignKeyConstraint(
            ["archivo_id"],
            ["archivos.id"],
            name=op.f("fk_gastos__archivo_id__archivos"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["usuarios.id"],
            name=op.f("fk_gastos__created_by__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["proyecto_id"],
            ["proyectos.id"],
            name=op.f("fk_gastos__proyecto_id__proyectos"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["rubro_id"],
            ["rubros.id"],
            name=op.f("fk_gastos__rubro_id__rubros"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["soporte_id"],
            ["archivos.id"],
            name=op.f("fk_gastos__soporte_id__archivos"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["usuarios.id"],
            name=op.f("fk_gastos__updated_by__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["viatico_id"],
            ["viaticos.id"],
            name=op.f("fk_gastos__viatico_id__viaticos"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gastos")),
        sa.UniqueConstraint("archivo_id", name=op.f("uq_gastos__archivo_id")),
        sa.UniqueConstraint("soporte_id", name=op.f("uq_gastos__soporte_id")),
    )
    op.create_index(op.f("ix_gastos__created_by"), "gastos", ["created_by"], unique=False)
    op.create_index(
        "ix_gastos__fecha_factura_proyecto",
        "gastos",
        ["fecha_factura", "proyecto_id"],
        unique=False,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(op.f("ix_gastos__proyecto_id"), "gastos", ["proyecto_id"], unique=False)
    op.create_index(
        "ix_gastos__proyecto_otro",
        "gastos",
        [sa.text("lower(proyecto_otro)")],
        unique=False,
        postgresql_where=sa.text("proyecto_otro IS NOT NULL"),
    )
    op.create_index(op.f("ix_gastos__rubro_id"), "gastos", ["rubro_id"], unique=False)
    op.create_index(op.f("ix_gastos__updated_by"), "gastos", ["updated_by"], unique=False)
    op.create_index(op.f("ix_gastos__viatico_id"), "gastos", ["viatico_id"], unique=False)
    op.create_index(
        "uq_gastos__migrado_de",
        "gastos",
        ["migrado_de"],
        unique=True,
        postgresql_where=sa.text("migrado_de IS NOT NULL"),
    )
    op.create_table(
        "viatico_eventos",
        sa.Column("viatico_id", sa.Uuid(), nullable=False),
        sa.Column("etapa", sa.Text(), nullable=False),
        sa.Column("accion", sa.Text(), nullable=False),
        sa.Column("dimension", sa.Text(), nullable=True),
        sa.Column("estado_anterior", sa.Text(), nullable=True),
        sa.Column("estado_nuevo", sa.Text(), nullable=True),
        sa.Column("comentario", sa.Text(), nullable=True),
        sa.Column("datos", postgresql.JSONB, nullable=True),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.CheckConstraint(
            "accion IN ('CREAR', 'EDITAR_SOLICITUD', 'APROBAR', 'RECHAZAR', 'DEVOLVER', "
            "'GESTIONAR_TIQUETES', 'HABILITAR_LEGALIZACION', 'CAMBIAR_ESTADO_FINANCIERO', "
            "'EDITAR_VALOR_ASIGNADO', 'CAMBIAR_RECURSOS_PROPIOS', 'LIQUIDAR', 'ELIMINAR')",
            name=op.f("ck_viatico_eventos__accion"),
        ),
        sa.CheckConstraint(
            "datos IS NULL OR jsonb_typeof(datos) = 'object'",
            name=op.f("ck_viatico_eventos__datos_objeto"),
        ),
        sa.CheckConstraint(
            "dimension IS NULL OR dimension IN ('OPERATIVO', 'FINANCIERO', 'ETAPA')",
            name=op.f("ck_viatico_eventos__dimension"),
        ),
        sa.CheckConstraint(
            "etapa IN ('SOLICITUD', 'LEGALIZACION')", name=op.f("ck_viatico_eventos__etapa")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_viatico_eventos__usuario_id__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["viatico_id"],
            ["viaticos.id"],
            name=op.f("fk_viatico_eventos__viatico_id__viaticos"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_viatico_eventos")),
    )
    op.create_index(
        op.f("ix_viatico_eventos__usuario_id"), "viatico_eventos", ["usuario_id"], unique=False
    )
    op.create_index(
        "ix_viatico_eventos__viatico_created_at",
        "viatico_eventos",
        ["viatico_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "viatico_trayectos",
        sa.Column("viatico_id", sa.Uuid(), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=False),
        sa.Column("ciudad_origen", sa.Text(), nullable=False),
        sa.Column("ciudad_destino", sa.Text(), nullable=False),
        sa.Column("fecha_ida", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fecha_regreso", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "requiere_hospedaje", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("dias_estadia", sa.SmallInteger(), nullable=False),
        sa.Column("tarifa_id", sa.Uuid(), nullable=True),
        sa.Column("vr_alimentacion", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("otros_gastos", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("trans_interno", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("transporte_aeropuerto", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("transporte_intermunicipal", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("subtotal_estadia", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "btrim(ciudad_destino) <> ''",
            name=op.f("ck_viatico_trayectos__ciudad_destino_no_vacia"),
        ),
        sa.CheckConstraint(
            "btrim(ciudad_origen) <> ''", name=op.f("ck_viatico_trayectos__ciudad_origen_no_vacia")
        ),
        sa.CheckConstraint(
            "ciudad_destino <> ciudad_origen OR ciudad_destino = 'Otro'",
            name=op.f("ck_viatico_trayectos__destino_distinto_de_origen"),
        ),
        sa.CheckConstraint(
            "dias_estadia >= 1", name=op.f("ck_viatico_trayectos__dias_estadia_minimo")
        ),
        sa.CheckConstraint(
            "fecha_regreso >= fecha_ida", name=op.f("ck_viatico_trayectos__regreso_despues_de_ida")
        ),
        sa.CheckConstraint("orden BETWEEN 1 AND 5", name=op.f("ck_viatico_trayectos__orden_rango")),
        sa.CheckConstraint(
            "otros_gastos IS NULL OR otros_gastos >= 0",
            name=op.f("ck_viatico_trayectos__otros_gastos_no_negativo"),
        ),
        sa.CheckConstraint(
            "subtotal_estadia IS NULL OR subtotal_estadia >= 0",
            name=op.f("ck_viatico_trayectos__subtotal_estadia_no_negativo"),
        ),
        sa.CheckConstraint(
            "trans_interno IS NULL OR trans_interno >= 0",
            name=op.f("ck_viatico_trayectos__trans_interno_no_negativo"),
        ),
        sa.CheckConstraint(
            "transporte_aeropuerto IS NULL OR transporte_aeropuerto >= 0",
            name=op.f("ck_viatico_trayectos__transporte_aeropuerto_no_negativo"),
        ),
        sa.CheckConstraint(
            "transporte_intermunicipal IS NULL OR transporte_intermunicipal >= 0",
            name=op.f("ck_viatico_trayectos__transporte_intermunicipal_no_negativo"),
        ),
        sa.CheckConstraint(
            "vr_alimentacion IS NULL OR vr_alimentacion >= 0",
            name=op.f("ck_viatico_trayectos__vr_alimentacion_no_negativo"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["usuarios.id"],
            name=op.f("fk_viatico_trayectos__created_by__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tarifa_id"],
            ["tarifas_viaticos.id"],
            name=op.f("fk_viatico_trayectos__tarifa_id__tarifas_viaticos"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["usuarios.id"],
            name=op.f("fk_viatico_trayectos__updated_by__usuarios"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["viatico_id"],
            ["viaticos.id"],
            name=op.f("fk_viatico_trayectos__viatico_id__viaticos"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_viatico_trayectos")),
    )
    op.create_index(
        op.f("ix_viatico_trayectos__created_by"), "viatico_trayectos", ["created_by"], unique=False
    )
    op.create_index(
        op.f("ix_viatico_trayectos__tarifa_id"), "viatico_trayectos", ["tarifa_id"], unique=False
    )
    op.create_index(
        op.f("ix_viatico_trayectos__updated_by"), "viatico_trayectos", ["updated_by"], unique=False
    )
    op.create_index(
        "uq_viatico_trayectos__viatico_orden",
        "viatico_trayectos",
        ["viatico_id", "orden"],
        unique=True,
    )
    op.add_column("usuarios", sa.Column("firma_archivo_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_usuarios__firma_archivo_id"), "usuarios", ["firma_archivo_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_usuarios__firma_archivo_id__archivos"),
        "usuarios",
        "archivos",
        ["firma_archivo_id"],
        ["id"],
        ondelete="RESTRICT",
        use_alter=True,
    )

    # --- A mano: lo que autogenerate no ve. ----------------------------------------------------
    # La secuencia del folio pertenece a la columna: se borra con la tabla (RN-04, §11).
    op.execute("ALTER SEQUENCE seq_folio_viaticos OWNED BY viaticos.folio")

    # Historial de solo inserción, también para el dueño del esquema (§7).
    op.execute(
        """
        CREATE FUNCTION fn_solo_insercion() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% es de solo inserción: % no permitido', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER tg_viatico_eventos__solo_insercion BEFORE UPDATE OR DELETE "
        "ON viatico_eventos FOR EACH ROW EXECUTE FUNCTION fn_solo_insercion()"
    )
    op.execute(
        "CREATE TRIGGER tg_viatico_eventos__sin_truncate BEFORE TRUNCATE ON viatico_eventos "
        "FOR EACH STATEMENT EXECUTE FUNCTION fn_solo_insercion()"
    )

    # Fuente única del saldo (ADR-008): nunca se almacena.
    op.execute(VISTA_SALDOS)

    op.execute(
        "REVOKE DELETE ON proyectos, rubros, tarifas_viaticos, viaticos, gastos FROM trulab_app"
    )
    op.execute("REVOKE UPDATE, DELETE ON archivos, viatico_eventos FROM trulab_app")
    op.execute("REVOKE INSERT, UPDATE, DELETE ON v_viatico_saldos FROM trulab_app")

    _sembrar_tarifas()


def downgrade() -> None:
    op.execute("DROP VIEW v_viatico_saldos")
    op.drop_constraint(
        op.f("fk_usuarios__firma_archivo_id__archivos"), "usuarios", type_="foreignkey"
    )
    op.drop_index(op.f("ix_usuarios__firma_archivo_id"), table_name="usuarios")
    op.drop_column("usuarios", "firma_archivo_id")
    op.drop_index("uq_viatico_trayectos__viatico_orden", table_name="viatico_trayectos")
    op.drop_index(op.f("ix_viatico_trayectos__updated_by"), table_name="viatico_trayectos")
    op.drop_index(op.f("ix_viatico_trayectos__tarifa_id"), table_name="viatico_trayectos")
    op.drop_index(op.f("ix_viatico_trayectos__created_by"), table_name="viatico_trayectos")
    op.drop_table("viatico_trayectos")
    op.drop_index("ix_viatico_eventos__viatico_created_at", table_name="viatico_eventos")
    op.drop_index(op.f("ix_viatico_eventos__usuario_id"), table_name="viatico_eventos")
    op.drop_table("viatico_eventos")
    op.execute("DROP FUNCTION fn_solo_insercion()")
    op.drop_index(
        "uq_gastos__migrado_de",
        table_name="gastos",
        postgresql_where=sa.text("migrado_de IS NOT NULL"),
    )
    op.drop_index(op.f("ix_gastos__viatico_id"), table_name="gastos")
    op.drop_index(op.f("ix_gastos__updated_by"), table_name="gastos")
    op.drop_index(op.f("ix_gastos__rubro_id"), table_name="gastos")
    op.drop_index(
        "ix_gastos__proyecto_otro",
        table_name="gastos",
        postgresql_where=sa.text("proyecto_otro IS NOT NULL"),
    )
    op.drop_index(op.f("ix_gastos__proyecto_id"), table_name="gastos")
    op.drop_index(
        "ix_gastos__fecha_factura_proyecto",
        table_name="gastos",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(op.f("ix_gastos__created_by"), table_name="gastos")
    op.drop_table("gastos")
    op.drop_index(
        "uq_viaticos__migrado_de",
        table_name="viaticos",
        postgresql_where=sa.text("migrado_de IS NOT NULL"),
    )
    op.drop_index(op.f("ix_viaticos__usuario_id"), table_name="viaticos")
    op.drop_index(
        "ix_viaticos__usuario_etapa_estado",
        table_name="viaticos",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_index(op.f("ix_viaticos__updated_by"), table_name="viaticos")
    op.drop_index(
        "ix_viaticos__proyecto_otro",
        table_name="viaticos",
        postgresql_where=sa.text("proyecto_otro IS NOT NULL"),
    )
    op.drop_index(op.f("ix_viaticos__proyecto_id"), table_name="viaticos")
    op.drop_index(op.f("ix_viaticos__formato_adjunto_id"), table_name="viaticos")
    op.drop_index(op.f("ix_viaticos__firma_archivo_id"), table_name="viaticos")
    op.drop_index(op.f("ix_viaticos__created_by"), table_name="viaticos")
    op.drop_index(
        "ix_viaticos__bandeja",
        table_name="viaticos",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.drop_table("viaticos")
    op.drop_index(
        "uq_tarifas_viaticos__migrado_de_tipo",
        table_name="tarifas_viaticos",
        postgresql_where=sa.text("migrado_de IS NOT NULL"),
    )
    op.drop_index("uq_tarifas_viaticos__ciudad_tipo", table_name="tarifas_viaticos")
    op.drop_index(op.f("ix_tarifas_viaticos__updated_by"), table_name="tarifas_viaticos")
    op.drop_index(op.f("ix_tarifas_viaticos__created_by"), table_name="tarifas_viaticos")
    op.drop_table("tarifas_viaticos")
    op.drop_index("uq_rubros__nombre", table_name="rubros")
    op.drop_index(
        "uq_rubros__migrado_de",
        table_name="rubros",
        postgresql_where=sa.text("migrado_de IS NOT NULL"),
    )
    op.drop_index(op.f("ix_rubros__updated_by"), table_name="rubros")
    op.drop_index(op.f("ix_rubros__created_by"), table_name="rubros")
    op.drop_table("rubros")
    op.drop_index("uq_proyectos__nombre", table_name="proyectos")
    op.drop_index(
        "uq_proyectos__migrado_de",
        table_name="proyectos",
        postgresql_where=sa.text("migrado_de IS NOT NULL"),
    )
    op.drop_index(
        "uq_proyectos__codigo",
        table_name="proyectos",
        postgresql_where=sa.text("codigo IS NOT NULL"),
    )
    op.drop_index(op.f("ix_proyectos__updated_by"), table_name="proyectos")
    op.drop_index(op.f("ix_proyectos__created_by"), table_name="proyectos")
    op.drop_table("proyectos")
    op.drop_index("ix_archivos__sha256", table_name="archivos")
    op.drop_index(op.f("ix_archivos__created_by"), table_name="archivos")
    op.drop_table("archivos")
