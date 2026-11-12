"""Migraciones y privilegios por defecto vistos desde `trulab_owner` (S1-04).

Necesitan `DATABASE_URL_MIGRATIONS`, que la API no recibe a propósito (mínimo privilegio).
Se ejecutan en el servicio `migrate`:
    docker compose run --rm migrate python -m pytest
Con solo `DATABASE_URL` (contenedor `api`) se omiten.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, create_engine, pool, text

URL_MIGRACIONES = os.environ.get("DATABASE_URL_MIGRATIONS", "").strip()
BACKEND = Path(__file__).resolve().parents[1]

requiere_owner = pytest.mark.skipif(
    not URL_MIGRACIONES, reason="sin DATABASE_URL_MIGRATIONS (use el servicio migrate)"
)


@pytest.fixture
def owner() -> Iterator[Connection]:
    engine = create_engine(URL_MIGRACIONES, poolclass=pool.NullPool)
    with engine.connect() as con:
        yield con
        # Nada de lo que hagan las pruebas queda en la BD.
        con.rollback()
    engine.dispose()


def _scripts() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))


def test_historial_de_migraciones_lineal() -> None:
    # Una sola cabeza: dos migraciones creadas en paralelo exigen `alembic merge`.
    assert len(_scripts().get_heads()) == 1


@requiere_owner
def test_bd_en_la_ultima_migracion(owner: Connection) -> None:
    version = owner.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    assert version == _scripts().get_current_head()


@requiere_owner
def test_migraciones_las_ejecuta_trulab_owner_sin_ser_superusuario(owner: Connection) -> None:
    fila = owner.execute(
        text(
            "SELECT current_user, rolsuper, rolbypassrls, rolcreaterole, rolcreatedb "
            "FROM pg_roles WHERE rolname = current_user"
        )
    ).one()

    assert tuple(fila) == ("trulab_owner", False, False, False, False)


@requiere_owner
def test_tablas_nuevas_del_owner_quedan_con_solo_dml_para_trulab_app(owner: Connection) -> None:
    owner.execute(text("CREATE TABLE prueba_privilegios (id bigserial PRIMARY KEY)"))

    privilegios = {
        privilegio: owner.execute(
            text("SELECT has_table_privilege('trulab_app', 'prueba_privilegios', :p)"),
            {"p": privilegio},
        ).scalar_one()
        for privilegio in (
            "SELECT",
            "INSERT",
            "UPDATE",
            "DELETE",
            "TRUNCATE",
            "REFERENCES",
            "TRIGGER",
        )
    }
    secuencia = owner.execute(
        text(
            "SELECT has_sequence_privilege('trulab_app', 'prueba_privilegios_id_seq', 'USAGE'), "
            "has_sequence_privilege('trulab_app', 'prueba_privilegios_id_seq', 'UPDATE')"
        )
    ).one()

    assert privilegios == {
        "SELECT": True,
        "INSERT": True,
        "UPDATE": True,
        "DELETE": True,
        "TRUNCATE": False,
        "REFERENCES": False,
        "TRIGGER": False,
    }
    assert tuple(secuencia) == (True, False)


@requiere_owner
def test_public_no_concede_nada_a_public(owner: Connection) -> None:
    acceso_public = owner.execute(
        text(
            "SELECT has_schema_privilege('public', 'public', 'USAGE'), "
            "has_schema_privilege('public', 'public', 'CREATE'), "
            "has_database_privilege('public', current_database(), 'CONNECT')"
        )
    ).one()

    assert tuple(acceso_public) == (False, False, False)
