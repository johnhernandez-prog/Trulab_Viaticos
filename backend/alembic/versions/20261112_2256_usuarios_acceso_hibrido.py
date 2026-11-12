"""Acceso híbrido: credenciales de operativos en `usuarios` y tokens de recuperación (S1-07b).

ADR-027 (reemplaza ADR-006): VIAJERO, ADMIN y FINANCIERO entran con `username` + contraseña
(Argon2id); SUPERADMIN, solo con Google. docs/database-design.md §2.2 y §2.12.

- `usuarios`: `username` (CITEXT único), `password_hash`, `debe_cambiar_password`,
  `password_cambiada_at`, `intentos_fallidos`, `bloqueado_hasta`, `es_prestador_servicios`,
  `fecha_nacimiento`, y los `CHECK` que atan las credenciales al rol. `firma_archivo_id` llega con
  la tabla `archivos` (S2-02).
- `tokens_recuperacion_password`: solo el SHA-256 del token, de un solo uso. `trulab_app` no
  tiene `DELETE` (los tokens se invalidan con `used_at`).

Guarda: si ya hay usuarios operativos (sin contraseña, porque antes no existía), la migración se
niega a correr con un mensaje claro en lugar de fallar en un `CHECK`. Hasta S1-07b solo el seed
creaba usuarios, y solo SUPERADMIN.

Revision ID: f7a1a890a1d3
Revises: a154d56e054d
Create Date: 2026-11-12 22:56:57.721058
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f7a1a890a1d3"
down_revision: str | None = "a154d56e054d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (nombre sin prefijo, condición) en el orden en que se crean.
_CHECKS_USUARIOS: list[tuple[str, str]] = [
    (
        "password_segun_rol",
        "(rol <> 'SUPERADMIN' AND password_hash IS NOT NULL) "
        "OR (rol = 'SUPERADMIN' AND password_hash IS NULL)",
    ),
    ("password_argon2id", "password_hash ~ '^\\$argon2id\\$'"),
    ("username_operativo", "rol = 'SUPERADMIN' OR username IS NOT NULL"),
    ("username_formato", "username::text ~ '^[a-z0-9._-]{3,40}$'"),
    ("google_solo_superadmin", "rol = 'SUPERADMIN' OR google_sub IS NULL"),
    ("superadmin_sin_cambio_password", "rol <> 'SUPERADMIN' OR NOT debe_cambiar_password"),
    ("intentos_fallidos_no_negativos", "intentos_fallidos >= 0"),
]


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM usuarios WHERE rol <> 'SUPERADMIN') THEN
                RAISE EXCEPTION 'Hay usuarios operativos sin credenciales: asígneles username y '
                    'contraseña antes de aplicar S1-07b (ADR-027)';
            END IF;
        END
        $$
        """
    )

    # --- usuarios (§2.2) --------------------------------------------------------------------------
    op.add_column("usuarios", sa.Column("username", postgresql.CITEXT(), nullable=True))
    op.add_column("usuarios", sa.Column("password_hash", sa.String(length=255), nullable=True))
    op.add_column(
        "usuarios",
        sa.Column(
            "debe_cambiar_password", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column(
        "usuarios", sa.Column("password_cambiada_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "usuarios",
        sa.Column(
            "intentos_fallidos", sa.SmallInteger(), server_default=sa.text("0"), nullable=False
        ),
    )
    op.add_column(
        "usuarios", sa.Column("bloqueado_hasta", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "usuarios",
        sa.Column(
            "es_prestador_servicios", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column("usuarios", sa.Column("fecha_nacimiento", sa.Date(), nullable=True))
    op.create_unique_constraint(op.f("uq_usuarios__username"), "usuarios", ["username"])
    for nombre, condicion in _CHECKS_USUARIOS:
        op.create_check_constraint(op.f(f"ck_usuarios__{nombre}"), "usuarios", condicion)

    # --- tokens_recuperacion_password (§2.12) -----------------------------------------------------
    op.create_table(
        "tokens_recuperacion_password",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_tokens_recuperacion_password__token_hash_sha256"),
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name=op.f("ck_tokens_recuperacion_password__expira_despues_de_crear"),
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"],
            ["usuarios.id"],
            name=op.f("fk_tokens_recuperacion_password__usuario_id__usuarios"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tokens_recuperacion_password")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_tokens_recuperacion_password__token_hash")),
    )
    op.create_index(
        op.f("ix_tokens_recuperacion_password__expires_at"),
        "tokens_recuperacion_password",
        ["expires_at"],
    )
    op.create_index(
        op.f("ix_tokens_recuperacion_password__usuario_id"),
        "tokens_recuperacion_password",
        ["usuario_id"],
    )
    # Se invalidan con `used_at`; no se borran (trazabilidad de la recuperación).
    op.execute("REVOKE DELETE ON tokens_recuperacion_password FROM trulab_app")


def downgrade() -> None:
    op.drop_table("tokens_recuperacion_password")
    for nombre, _ in reversed(_CHECKS_USUARIOS):
        op.drop_constraint(op.f(f"ck_usuarios__{nombre}"), "usuarios", type_="check")
    op.drop_constraint(op.f("uq_usuarios__username"), "usuarios", type_="unique")
    for columna in (
        "fecha_nacimiento",
        "es_prestador_servicios",
        "bloqueado_hasta",
        "intentos_fallidos",
        "password_cambiada_at",
        "debe_cambiar_password",
        "password_hash",
        "username",
    ):
        op.drop_column("usuarios", columna)
