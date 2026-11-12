"""La API se conecta como `trulab_app`, con privilegios mínimos (S1-04, docs/database-design.md §6).

Usa la conexión real de la app (`DATABASE_URL`) contra la BD migrada.
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import ProgrammingError

from app.core.db import get_engine


@pytest.fixture
def conexion() -> Iterator[Connection]:
    with get_engine().connect() as con:
        yield con
        con.rollback()


def test_la_api_se_conecta_como_trulab_app(conexion: Connection) -> None:
    assert conexion.execute(text("SELECT current_user")).scalar_one() == "trulab_app"


def test_trulab_app_no_tiene_atributos_privilegiados(conexion: Connection) -> None:
    fila = conexion.execute(
        text(
            "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcreatedb, rolreplication "
            "FROM pg_roles WHERE rolname = current_user"
        )
    ).one()

    assert tuple(fila) == (False, False, False, False, False)


def test_trulab_app_no_es_duena_de_la_bd_ni_del_esquema(conexion: Connection) -> None:
    dueno_bd = conexion.execute(
        text("SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = current_database()")
    ).scalar_one()
    es_duena_esquema = conexion.execute(
        text("SELECT pg_has_role(nspowner, 'USAGE') FROM pg_namespace WHERE nspname = 'public'")
    ).scalar_one()

    assert dueno_bd == "trulab_owner"
    assert es_duena_esquema is False


def test_trulab_app_no_puede_crear_objetos(conexion: Connection) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        conexion.execute(text("CREATE TABLE intento_ddl (id int)"))


def test_trulab_app_no_lee_alembic_version(conexion: Connection) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        conexion.execute(text("SELECT version_num FROM alembic_version"))


@pytest.mark.parametrize("extension", ["citext", "pgcrypto"])
def test_extension_instalada(conexion: Connection, extension: str) -> None:
    instalada = conexion.execute(
        text("SELECT count(*) FROM pg_extension WHERE extname = :nombre"), {"nombre": extension}
    ).scalar_one()

    assert instalada == 1


def test_trulab_app_usa_citext_y_pgcrypto(conexion: Connection) -> None:
    iguales = conexion.execute(
        text("SELECT 'Ana@Trulab.co'::citext = 'ana@trulab.co'::citext")
    ).scalar_one()
    hash_hex = conexion.execute(text("SELECT encode(digest('x', 'sha256'), 'hex')")).scalar_one()
    uuid = conexion.execute(text("SELECT gen_random_uuid()")).scalar_one()

    assert iguales is True
    assert len(hash_hex) == 64
    assert uuid is not None
