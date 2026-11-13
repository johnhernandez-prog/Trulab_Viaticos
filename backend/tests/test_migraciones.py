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
from sqlalchemy.exc import DBAPIError

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


# --- auditoría de solo inserción, incluso para el dueño (S1-07) ---------------------------------


def _insertar_evento(owner: Connection, usuario_id: object = None) -> int:
    evento_id = owner.execute(
        text(
            "INSERT INTO auditoria (accion, entidad, usuario_id) "
            "VALUES ('PRUEBA', 'pruebas', :u) RETURNING id"
        ),
        {"u": usuario_id},
    ).scalar_one()
    return int(evento_id)


@requiere_owner
@pytest.mark.parametrize(
    "sentencia",
    [
        "UPDATE auditoria SET accion = 'ALTERADA' WHERE id = :id",
        "DELETE FROM auditoria WHERE id = :id",
    ],
)
def test_trigger_impide_modificar_auditoria_al_owner(owner: Connection, sentencia: str) -> None:
    evento_id = _insertar_evento(owner)

    with pytest.raises(DBAPIError, match="solo inserción"):
        owner.execute(text(sentencia), {"id": evento_id})


@requiere_owner
def test_trigger_impide_truncate_de_auditoria(owner: Connection) -> None:
    with pytest.raises(DBAPIError, match="solo inserción"):
        owner.execute(text("TRUNCATE auditoria"))


@requiere_owner
def test_purga_de_usuario_deja_la_auditoria_sin_actor(owner: Connection) -> None:
    # Purga física (manual, fuera del MVP): la FK hace SET NULL y el trigger lo admite.
    usuario_id = owner.execute(
        text(
            # SUPERADMIN: no necesita username ni contraseña (ADR-027).
            "INSERT INTO usuarios (nombre_completo, correo, rol) "
            "VALUES ('Purga', 'purga-prueba@trulab.co', 'SUPERADMIN') RETURNING id"
        )
    ).scalar_one()
    evento_id = _insertar_evento(owner, usuario_id)

    owner.execute(text("DELETE FROM usuarios WHERE id = :id"), {"id": usuario_id})

    fila = owner.execute(
        text("SELECT usuario_id, accion FROM auditoria WHERE id = :id"), {"id": evento_id}
    ).one()
    assert tuple(fila) == (None, "PRUEBA")


@requiere_owner
def test_privilegios_de_trulab_app_en_tablas_de_identidad(owner: Connection) -> None:
    filas = owner.execute(
        text(
            "SELECT table_name, string_agg(privilege_type, ',' ORDER BY privilege_type) "
            "FROM information_schema.role_table_grants "
            "WHERE grantee = 'trulab_app' AND table_name IN "
            "('usuarios', 'cargos', 'celulas', 'sesiones', 'auditoria', "
            "'tokens_recuperacion_password') "
            "GROUP BY table_name"
        )
    ).all()

    assert dict(tuple(f) for f in filas) == {
        "usuarios": "INSERT,SELECT,UPDATE",
        "cargos": "INSERT,SELECT,UPDATE",
        "celulas": "INSERT,SELECT,UPDATE",
        "sesiones": "DELETE,INSERT,SELECT,UPDATE",
        "auditoria": "INSERT,SELECT",
        # Se invalidan con `used_at`, no se borran (S1-07b).
        "tokens_recuperacion_password": "INSERT,SELECT,UPDATE",
    }


# --- modelo unificado (S2-02) --------------------------------------------------------------------


@requiere_owner
def test_privilegios_de_trulab_app_en_el_modelo_de_viaticos(owner: Connection) -> None:
    tablas = (
        "proyectos",
        "rubros",
        "tarifas_viaticos",
        "archivos",
        "viaticos",
        "viatico_trayectos",
        "viatico_eventos",
        "gastos",
        "v_viatico_saldos",
    )
    filas = owner.execute(
        text(
            "SELECT table_name, string_agg(privilege_type, ',' ORDER BY privilege_type) "
            "FROM information_schema.role_table_grants "
            "WHERE grantee = 'trulab_app' AND table_name = ANY(:tablas) "
            "GROUP BY table_name"
        ),
        {"tablas": list(tablas)},
    ).all()

    assert dict(tuple(f) for f in filas) == {
        # Se desactivan o se eliminan lógicamente (§8).
        "proyectos": "INSERT,SELECT,UPDATE",
        "rubros": "INSERT,SELECT,UPDATE",
        "tarifas_viaticos": "INSERT,SELECT,UPDATE",
        "viaticos": "INSERT,SELECT,UPDATE",
        "gastos": "INSERT,SELECT,UPDATE",
        # Se reemplazan en bloque mientras la solicitud es editable.
        "viatico_trayectos": "DELETE,INSERT,SELECT,UPDATE",
        # Inmutables.
        "archivos": "INSERT,SELECT",
        "viatico_eventos": "INSERT,SELECT",
        "v_viatico_saldos": "SELECT",
    }


@requiere_owner
@pytest.mark.parametrize(
    "sentencia",
    [
        "UPDATE viatico_eventos SET comentario = 'x' WHERE false",
        "DELETE FROM viatico_eventos WHERE false",
        "TRUNCATE viatico_eventos",
    ],
)
def test_trigger_impide_modificar_eventos_al_owner(owner: Connection, sentencia: str) -> None:
    # `WHERE false`: el trigger de fila no se dispara sin filas; se inserta una antes.
    usuario_id = owner.execute(
        text(
            "INSERT INTO usuarios (nombre_completo, correo, rol) "
            "VALUES ('Eventos', 'eventos-prueba@trulab.co', 'SUPERADMIN') RETURNING id"
        )
    ).scalar_one()
    viatico_id = owner.execute(
        text(
            "INSERT INTO viaticos (modalidad, etapa, usuario_id, motivo_viaje, "
            "colaborador_nombre, colaborador_es_prestador) "
            "VALUES ('LEGALIZACION_DIRECTA', 'LEGALIZACION', :u, 'Prueba', 'Eventos', false) "
            "RETURNING id"
        ),
        {"u": usuario_id},
    ).scalar_one()
    owner.execute(
        text(
            "INSERT INTO viatico_eventos (viatico_id, etapa, accion, usuario_id) "
            "VALUES (:v, 'LEGALIZACION', 'CREAR', :u)"
        ),
        {"v": viatico_id, "u": usuario_id},
    )

    with pytest.raises(DBAPIError, match="solo inserción"):
        owner.execute(
            text(sentencia.replace("WHERE false", "WHERE viatico_id = :v")), {"v": viatico_id}
        )


@requiere_owner
def test_vista_de_saldos_respeta_el_rls_de_quien_consulta(owner: Connection) -> None:
    opciones = owner.execute(
        text("SELECT reloptions FROM pg_class WHERE relname = 'v_viatico_saldos'")
    ).scalar_one()

    assert "security_invoker=true" in (opciones or [])


@requiere_owner
def test_folio_de_viaticos_usa_su_secuencia_propia(owner: Connection) -> None:
    duena = owner.execute(
        text(
            "SELECT d.refobjid::regclass::text FROM pg_depend d "
            "JOIN pg_class s ON s.oid = d.objid "
            "WHERE s.relname = 'seq_folio_viaticos' AND d.deptype = 'a'"
        )
    ).scalar_one()

    assert duena == "viaticos"
