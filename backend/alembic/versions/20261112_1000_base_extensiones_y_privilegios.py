"""Base de la BD: extensiones citext y pgcrypto, y privilegios mínimos de trulab_app.

No crea tablas de negocio (llegan desde S1-07). Prepara la BD para que cada tabla que cree
`trulab_owner` en migraciones futuras quede accesible para `trulab_app` solo con DML.

Requisitos (los cumple infra/db/init/10-roles.sh):
- el rol `trulab_app` existe;
- la migración la ejecuta el dueño de la BD (`trulab_owner`), no un superusuario. Así los
  privilegios por defecto se aplican a los objetos que crean las migraciones.

El rol `trulab_app` va literal (docs/database-design.md §6): una migración es una foto fija y no
depende de constantes que puedan cambiar después.

Revision ID: 3f1c9a7e5b20
Revises:
Create Date: 2026-11-12 10:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "3f1c9a7e5b20"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Falla pronto y con un mensaje claro si el entorno no está preparado.
    op.execute(
        """
        DO $$
        DECLARE
            dueno text;
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'trulab_app') THEN
                RAISE EXCEPTION 'No existe el rol trulab_app: ejecute infra/db/init/10-roles.sh';
            END IF;
            SELECT pg_get_userbyid(datdba) INTO dueno
              FROM pg_database WHERE datname = current_database();
            IF dueno <> current_user THEN
                RAISE EXCEPTION
                    'Las migraciones las ejecuta el dueño de la BD (%), no %', dueno, current_user;
            END IF;
        END
        $$;
        """
    )

    # Extensiones (docs/database-design.md §10). Ambas son "trusted" desde PostgreSQL 13: las crea
    # el dueño de la BD sin ser superusuario. citext: correos sin distinguir mayúsculas.
    # pgcrypto: digest() para hashes; gen_random_uuid() también es nativa desde PG 13.
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # Esquema: nadie más que el dueño crea objetos; trulab_app solo puede usarlo.
    op.execute("REVOKE ALL ON SCHEMA public FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA public TO trulab_app")

    # Privilegios por defecto sobre lo que cree trulab_owner en adelante: solo DML, nunca DDL,
    # TRUNCATE, REFERENCES ni TRIGGER. Las tablas de solo inserción (auditoría, eventos) revocan
    # UPDATE y DELETE en su propia migración (docs/database-design.md §7).
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO trulab_app"
    )
    # Secuencias: USAGE para nextval() de los folios (RN-04); sin UPDATE (setval) para la API.
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO trulab_app"
    )

    # alembic_version se creó antes que estos privilegios por defecto; se deja explícito que la
    # API no la lee ni la modifica.
    op.execute("REVOKE ALL ON TABLE alembic_version FROM trulab_app")


def downgrade() -> None:
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE USAGE, SELECT ON SEQUENCES FROM trulab_app"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM trulab_app"
    )
    op.execute("REVOKE USAGE ON SCHEMA public FROM trulab_app")
    # Deja el esquema como lo crea PostgreSQL 16 (USAGE para PUBLIC, sin CREATE).
    op.execute("GRANT USAGE ON SCHEMA public TO PUBLIC")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
    op.execute("DROP EXTENSION IF EXISTS citext")
