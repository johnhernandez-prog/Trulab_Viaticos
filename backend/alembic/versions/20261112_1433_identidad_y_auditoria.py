"""Identidad y auditoría: usuarios, cargos, células, sesiones y auditoría (S1-07).

Tablas de docs/database-design.md §2.1, §2.2, §2.3 (solo `celulas`, que `usuarios` necesita),
§2.8 y §2.9, con los índices de §5 y la nomenclatura de §9.

Orden: `usuarios` primero (las demás tablas la referencian en `created_by`/`updated_by`); las FK
`usuarios.cargo_id` y `usuarios.celula_id` se agregan al final para cerrar el ciclo.

Privilegios de `trulab_app` además de los por defecto (solo DML, migración inicial):
- `usuarios`, `cargos`, `celulas`: sin `DELETE`. Se desactivan o se eliminan lógicamente (§8).
- `auditoria`: solo `INSERT` y `SELECT` (§7). Además, un trigger rechaza `UPDATE`, `DELETE` y
  `TRUNCATE` para cualquier rol; solo deja pasar el `SET NULL` de `usuario_id` que hace la FK
  cuando se purga un usuario (proceso manual, fuera del MVP).
- `sesiones`: DML completo (S1-08 revoca y limpia sesiones).

Revision ID: a154d56e054d
Revises: 3f1c9a7e5b20
Create Date: 2026-11-12 14:33:20.086030
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a154d56e054d"
down_revision: str | None = "3f1c9a7e5b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columnas_base(*, borrado_logico: bool = True) -> list[sa.Column[Any]]:
    """Columnas base de docs/database-design.md §2 (`id`, marcas de tiempo, autores, ETL)."""
    tz = sa.DateTime(timezone=True)
    columnas: list[sa.Column[Any]] = [
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("created_at", tz, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", tz, server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
    ]
    if borrado_logico:
        columnas.append(sa.Column("deleted_at", tz, nullable=True))
    columnas.append(sa.Column("migrado_de", sa.Text(), nullable=True))
    return columnas


def _autores(tabla: str) -> list[sa.ForeignKeyConstraint]:
    return [
        sa.ForeignKeyConstraint(
            [columna],
            ["usuarios.id"],
            name=op.f(f"fk_{tabla}__{columna}__usuarios"),
            ondelete="RESTRICT",
        )
        for columna in ("created_by", "updated_by")
    ]


def _indices_base(tabla: str) -> None:
    """Índices de las FK de autores y `UNIQUE (migrado_de)` parcial para el ETL."""
    for columna in ("created_by", "updated_by"):
        op.create_index(op.f(f"ix_{tabla}__{columna}"), tabla, [columna])
    op.create_index(
        f"uq_{tabla}__migrado_de",
        tabla,
        ["migrado_de"],
        unique=True,
        postgresql_where=sa.text("migrado_de IS NOT NULL"),
    )


def upgrade() -> None:
    # --- usuarios (§2.2). Sin contraseña (DP-01, RN-15). ---------------------------------------
    op.create_table(
        "usuarios",
        *_columnas_base(),
        sa.Column("nombre_completo", sa.Text(), nullable=False),
        sa.Column("correo", postgresql.CITEXT(), nullable=False),
        sa.Column("cedula", sa.Text(), nullable=True),
        sa.Column("celula_id", sa.Uuid(), nullable=True),
        sa.Column("rol", sa.Text(), nullable=False),
        sa.Column("cargo_id", sa.Uuid(), nullable=True),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("google_sub", sa.Text(), nullable=True),
        sa.Column("ultimo_acceso", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "rol IN ('VIAJERO', 'FINANCIERO', 'ADMIN', 'SUPERADMIN')", name=op.f("ck_usuarios__rol")
        ),
        sa.CheckConstraint(
            "btrim(nombre_completo) <> ''", name=op.f("ck_usuarios__nombre_completo_no_vacio")
        ),
        sa.CheckConstraint(
            "correo ~ '^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$'", name=op.f("ck_usuarios__correo_formato")
        ),
        *_autores("usuarios"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usuarios")),
        sa.UniqueConstraint("correo", name=op.f("uq_usuarios__correo")),
        sa.UniqueConstraint("google_sub", name=op.f("uq_usuarios__google_sub")),
    )
    _indices_base("usuarios")
    op.create_index(op.f("ix_usuarios__cargo_id"), "usuarios", ["cargo_id"])
    op.create_index(op.f("ix_usuarios__celula_id"), "usuarios", ["celula_id"])
    op.create_index("ix_usuarios__rol", "usuarios", ["rol"], postgresql_where=sa.text("activo"))
    op.create_index(
        "uq_usuarios__cedula",
        "usuarios",
        ["cedula"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND cedula IS NOT NULL"),
    )

    # --- cargos (§2.1), con folio CA-000001 desde su secuencia (RN-04, §11). -------------------
    op.execute("CREATE SEQUENCE seq_folio_cargos")
    op.create_table(
        "cargos",
        *_columnas_base(),
        sa.Column(
            "folio",
            sa.Text(),
            server_default=sa.text("'CA-' || lpad(nextval('seq_folio_cargos')::text, 6, '0')"),
            nullable=False,
        ),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("descripcion", sa.Text(), nullable=True),
        sa.CheckConstraint("btrim(nombre) <> ''", name=op.f("ck_cargos__nombre_no_vacio")),
        *_autores("cargos"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cargos")),
        sa.UniqueConstraint("folio", name=op.f("uq_cargos__folio")),
    )
    # La secuencia pertenece a la columna: se borra con la tabla.
    op.execute("ALTER SEQUENCE seq_folio_cargos OWNED BY cargos.folio")
    _indices_base("cargos")
    op.create_index(
        "uq_cargos__nombre",
        "cargos",
        [sa.text("lower(nombre)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # --- celulas (§2.3): catálogo; sin deleted_at (se desactiva). ------------------------------
    op.create_table(
        "celulas",
        *_columnas_base(borrado_logico=False),
        sa.Column("nombre", sa.Text(), nullable=False),
        sa.Column("activo", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("orden", sa.SmallInteger(), nullable=True),
        sa.CheckConstraint("btrim(nombre) <> ''", name=op.f("ck_celulas__nombre_no_vacio")),
        *_autores("celulas"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_celulas")),
    )
    _indices_base("celulas")
    op.create_index("uq_celulas__nombre", "celulas", [sa.text("lower(nombre)")], unique=True)

    # --- FK que cierran el ciclo usuarios ↔ cargos/celulas (§3: RESTRICT). ----------------------
    op.create_foreign_key(
        op.f("fk_usuarios__cargo_id__cargos"),
        "usuarios",
        "cargos",
        ["cargo_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_usuarios__celula_id__celulas"),
        "usuarios",
        "celulas",
        ["celula_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # --- auditoria (§2.8, §7): solo inserción. ------------------------------------------------
    op.create_table(
        "auditoria",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("accion", sa.Text(), nullable=False),
        sa.Column("entidad", sa.Text(), nullable=False),
        sa.Column("entidad_id", sa.Uuid(), nullable=True),
        sa.Column(
            "datos",
            postgresql.JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("accion ~ '^[A-Z][A-Z_]*$'", name=op.f("ck_auditoria__accion_formato")),
        sa.CheckConstraint(
            "jsonb_typeof(datos) = 'object'", name=op.f("ck_auditoria__datos_objeto")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_auditoria__usuario_id__usuarios"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auditoria")),
    )
    op.create_index(op.f("ix_auditoria__usuario_id"), "auditoria", ["usuario_id"])
    op.create_index("ix_auditoria__entidad_entidad_id", "auditoria", ["entidad", "entidad_id"])
    op.create_index("ix_auditoria__created_at", "auditoria", ["created_at"])
    op.execute(
        """
        CREATE FUNCTION fn_auditoria_solo_insercion() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            -- Única modificación admitida: el SET NULL de la FK al purgar un usuario.
            IF TG_OP = 'UPDATE'
               AND OLD.usuario_id IS NOT NULL AND NEW.usuario_id IS NULL
               AND (to_jsonb(NEW) - 'usuario_id') = (to_jsonb(OLD) - 'usuario_id') THEN
                RETURN NEW;
            END IF;
            RAISE EXCEPTION 'auditoria es de solo inserción: % no permitido', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER tg_auditoria__solo_insercion BEFORE UPDATE OR DELETE ON auditoria "
        "FOR EACH ROW EXECUTE FUNCTION fn_auditoria_solo_insercion()"
    )
    op.execute(
        "CREATE TRIGGER tg_auditoria__sin_truncate BEFORE TRUNCATE ON auditoria "
        "FOR EACH STATEMENT EXECUTE FUNCTION fn_auditoria_solo_insercion()"
    )

    # --- sesiones (§2.9): solo el hash SHA-256 del refresh token. ------------------------------
    op.create_table(
        "sesiones",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'", name=op.f("ck_sesiones__token_hash_sha256")
        ),
        sa.CheckConstraint(
            "expires_at > created_at", name=op.f("ck_sesiones__expira_despues_de_crear")
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_sesiones__usuario_id__usuarios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sesiones")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sesiones__token_hash")),
    )
    op.create_index(op.f("ix_sesiones__usuario_id"), "sesiones", ["usuario_id"])

    # --- Privilegios de trulab_app más estrictos que los por defecto. ---------------------------
    op.execute("REVOKE DELETE ON usuarios, cargos, celulas FROM trulab_app")
    op.execute("REVOKE UPDATE, DELETE ON auditoria FROM trulab_app")


def downgrade() -> None:
    op.drop_table("sesiones")
    op.drop_table("auditoria")
    op.execute("DROP FUNCTION fn_auditoria_solo_insercion()")
    op.drop_constraint(op.f("fk_usuarios__celula_id__celulas"), "usuarios", type_="foreignkey")
    op.drop_constraint(op.f("fk_usuarios__cargo_id__cargos"), "usuarios", type_="foreignkey")
    op.drop_table("celulas")
    op.drop_table("cargos")  # borra también seq_folio_cargos (OWNED BY)
    op.drop_table("usuarios")
