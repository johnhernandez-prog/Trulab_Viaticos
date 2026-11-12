"""Entorno de Alembic de Trulab Viajes (S1-04).

- Se conecta con `DATABASE_URL_MIGRATIONS` (rol `trulab_owner`, dueño del esquema). Nunca con
  `DATABASE_URL` (rol `trulab_app`), que a propósito no puede crear ni alterar objetos.
- `target_metadata` es la metadata de `app.core.models.Base`, con la `naming_convention` del
  proyecto. Los modelos de cada dominio (`app/modules/<dominio>/models.py`) se importan solos,
  así que una tabla nueva aparece en `--autogenerate` sin tocar este archivo.
- Cada migración corre en su propia transacción (PostgreSQL admite DDL transaccional).
"""

import importlib
import importlib.util
import os
import pkgutil
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import create_engine, pool

import app.modules
from app.core.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _importar_modelos() -> None:
    """Importa `app.modules.<dominio>.models` de cada dominio que lo tenga."""
    for modulo in pkgutil.iter_modules(app.modules.__path__, prefix="app.modules."):
        if modulo.ispkg and importlib.util.find_spec(f"{modulo.name}.models") is not None:
            importlib.import_module(f"{modulo.name}.models")


_importar_modelos()
target_metadata = Base.metadata


def _configurar(**destino: Any) -> None:
    """Opciones comunes a los modos online y offline; `destino` es la conexión o la URL."""
    context.configure(
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        transaction_per_migration=True,
        **destino,
    )


def _url_migraciones() -> str:
    url = os.environ.get("DATABASE_URL_MIGRATIONS", "").strip()
    if not url:
        raise RuntimeError(
            "Falta DATABASE_URL_MIGRATIONS (rol trulab_owner). Las migraciones no se ejecutan con "
            "DATABASE_URL: el rol trulab_app no puede crear ni modificar el esquema. "
            "Use el servicio `migrate` de Docker Compose (ver backend/README.md)."
        )
    return url


def run_migrations_offline() -> None:
    """`alembic upgrade head --sql`: genera el SQL sin conectarse, para revisarlo antes."""
    # Sin URL basta el dialecto para generar SQL.
    url = os.environ.get("DATABASE_URL_MIGRATIONS", "").strip() or "postgresql+psycopg://"
    _configurar(url=url, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url_migraciones(), poolclass=pool.NullPool)
    with engine.connect() as conexion:
        _configurar(connection=conexion)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
