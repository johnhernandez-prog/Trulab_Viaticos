"""Auditoría (S1-07, docs/database-design.md §2.8 y §7)."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.audit import (
    AccionAuditoria,
    Auditoria,
    DatoProhibidoError,
    enmascarar_cedula,
    registrar,
    sanear,
)
from tests.fabricas import crear_usuario

# --- saneamiento de `datos` (sin BD) ------------------------------------------------------------


@pytest.mark.parametrize(
    ("cedula", "esperado"),
    [("1020304050", "******4050"), ("1234", "1234"), ("", ""), (None, None)],
)
def test_enmascarar_cedula(cedula: str | None, esperado: str | None) -> None:
    assert enmascarar_cedula(cedula) == esperado


def test_sanear_enmascara_la_cedula_en_cualquier_nivel() -> None:
    datos = {
        "antes": {"cedula": "1020304050", "rol": "VIAJERO"},
        "despues": [{"Cedula": "99887766"}],
    }

    assert sanear(datos) == {
        "antes": {"cedula": "******4050", "rol": "VIAJERO"},
        "despues": [{"Cedula": "****7766"}],
    }


@pytest.mark.parametrize(
    "datos",
    [
        {"refresh_token": "x"},
        {"ID_TOKEN": "x"},
        {"cambios": {"password": "x"}},
        {"lista": [{"token_hash": "x"}]},
        {"Authorization": "Bearer x"},
        {"cookie": "trulab_refresh=x"},
        # Acceso híbrido (ADR-027): nunca contraseñas, hashes ni tokens de recuperación.
        {"antes": {"password_hash": "$argon2id$..."}},
        {"nueva_password": "x"},
        {"password_actual": "x"},
        {"password_temporal": "x"},
        {"reset_token": "x"},
    ],
)
def test_sanear_rechaza_secretos(datos: dict[str, object]) -> None:
    with pytest.raises(DatoProhibidoError):
        sanear(datos)


# --- registro en la BD (trulab_app) -------------------------------------------------------------


def test_registrar_inserta_en_la_misma_transaccion(sesion: Session) -> None:
    actor = crear_usuario(sesion)
    afectado = crear_usuario(sesion, cedula="1020304050")

    evento = registrar(
        sesion,
        AccionAuditoria.ROL_CAMBIAR,
        "usuarios",
        afectado.id,
        usuario_id=actor.id,
        datos={"antes": {"rol": "VIAJERO"}, "despues": {"rol": "ADMIN"}, "cedula": "1020304050"},
        ip="192.0.2.1",
        user_agent="pytest",
    )
    sesion.flush()

    guardado = sesion.scalars(select(Auditoria).where(Auditoria.id == evento.id)).one()
    assert guardado.accion == "ROL_CAMBIAR"
    assert guardado.entidad_id == afectado.id
    assert guardado.datos["cedula"] == "******4050"
    assert guardado.created_at is not None


def test_registrar_sin_actor_es_del_sistema(sesion: Session) -> None:
    evento = registrar(sesion, AccionAuditoria.ACCESO_DENEGADO, "auth", datos={"motivo": "DOMINIO"})
    sesion.flush()

    assert evento.usuario_id is None
    assert evento.id > 0


def test_accion_con_formato_invalido_se_rechaza(sesion: Session) -> None:
    sesion.add(Auditoria(accion="rol-cambiar", entidad="usuarios", datos={}))

    with pytest.raises(IntegrityError, match="ck_auditoria__accion_formato"):
        sesion.flush()


@pytest.mark.parametrize(
    "sentencia",
    ["UPDATE auditoria SET accion = 'X' WHERE false", "DELETE FROM auditoria WHERE false"],
)
def test_trulab_app_no_modifica_ni_borra_auditoria(sesion: Session, sentencia: str) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        sesion.execute(text(sentencia))
