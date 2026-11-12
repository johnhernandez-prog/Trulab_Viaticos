"""Base declarativa de SQLAlchemy compartida por los modelos de todos los módulos.

La `naming_convention` aplica la nomenclatura de docs/database-design.md §9 para que Alembic
genere nombres de constraints e índices estables y predecibles:

- PK: `pk_<tabla>`
- índices: `ix_<tabla>__<columnas>`
- únicos: `uq_<tabla>__<columnas>`
- FK: `fk_<tabla>__<columna>__<tabla_ref>`
- checks: `ck_<tabla>__<regla>` (la regla es el `name` que se da al `CheckConstraint`)

Cada módulo de dominio define sus modelos en `app/modules/<dominio>/models.py` heredando de
`Base`; `alembic/env.py` los descubre e importa solo (desde S1-07).
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "pk": "pk_%(table_name)s",
    "ix": "ix_%(table_name)s__%(column_0_N_name)s",
    "uq": "uq_%(table_name)s__%(column_0_N_name)s",
    "fk": "fk_%(table_name)s__%(column_0_N_name)s__%(referred_table_name)s",
    "ck": "ck_%(table_name)s__%(constraint_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
