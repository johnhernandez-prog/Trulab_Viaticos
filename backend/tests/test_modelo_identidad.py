"""Modelo de identidad (S1-07): restricciones de `usuarios`, `cargos`, `celulas` y `sesiones`.

Corre como `trulab_app` (la conexión de la API) y todo se revierte al terminar.
"""

import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.modules.auth.models import Sesion
from app.modules.cargos.models import Cargo
from app.modules.catalogos.models import Celula
from app.modules.usuarios.models import Usuario
from tests.fabricas import correo_unico, crear_cargo, crear_celula, crear_usuario

# --- cargos -------------------------------------------------------------------------------------


def test_cargo_recibe_folio_legible_de_la_secuencia(sesion: Session) -> None:
    primero = crear_cargo(sesion)
    segundo = crear_cargo(sesion)
    sesion.refresh(primero)
    sesion.refresh(segundo)

    assert re.fullmatch(r"CA-\d{6,}", primero.folio)
    assert int(segundo.folio[3:]) > int(primero.folio[3:])


def test_cargo_nombre_unico_sin_distinguir_mayusculas(sesion: Session) -> None:
    crear_cargo(sesion, "Analista de Campo")

    with pytest.raises(IntegrityError, match="uq_cargos__nombre"):
        crear_cargo(sesion, "ANALISTA DE CAMPO")


def test_cargo_eliminado_permite_recrear_el_nombre(sesion: Session) -> None:
    cargo = crear_cargo(sesion, "Coordinador")
    cargo.deleted_at = datetime.now(UTC)
    sesion.flush()

    assert crear_cargo(sesion, "coordinador").id != cargo.id


def test_cargo_nombre_no_puede_estar_vacio(sesion: Session) -> None:
    with pytest.raises(IntegrityError, match="ck_cargos__nombre_no_vacio"):
        crear_cargo(sesion, "   ")


# --- celulas ------------------------------------------------------------------------------------


def test_celula_activa_por_defecto_y_nombre_unico(sesion: Session) -> None:
    celula = crear_celula(sesion, "Laboratorio")
    sesion.refresh(celula)

    assert celula.activo is True
    with pytest.raises(IntegrityError, match="uq_celulas__nombre"):
        crear_celula(sesion, "laboratorio")


# --- usuarios -----------------------------------------------------------------------------------


def test_usuario_con_valores_por_defecto(sesion: Session) -> None:
    usuario = crear_usuario(sesion)
    sesion.refresh(usuario)

    assert usuario.activo is True
    assert usuario.google_sub is None
    assert usuario.created_at is not None and usuario.created_at.tzinfo is not None


def test_correo_unico_y_buscable_sin_distinguir_mayusculas(sesion: Session) -> None:
    correo = correo_unico()
    usuario = crear_usuario(sesion, correo=correo)

    encontrado = sesion.scalar(select(Usuario).where(Usuario.correo == correo.upper()))
    assert encontrado is not None and encontrado.id == usuario.id
    with pytest.raises(IntegrityError, match="uq_usuarios__correo"):
        crear_usuario(sesion, correo=correo.upper())


@pytest.mark.parametrize("rol", ["ROOT", "viajero", ""])
def test_rol_fuera_del_enum_se_rechaza(sesion: Session, rol: str) -> None:
    with pytest.raises(IntegrityError, match="ck_usuarios__rol"):
        crear_usuario(sesion, rol=rol)


@pytest.mark.parametrize("correo", ["sin-arroba", "a@b", "con espacio@trulab.co"])
def test_correo_con_formato_invalido_se_rechaza(sesion: Session, correo: str) -> None:
    with pytest.raises(IntegrityError, match="ck_usuarios__correo_formato"):
        crear_usuario(sesion, correo=correo)


def test_cedula_unica_entre_no_eliminados(sesion: Session) -> None:
    crear_usuario(sesion, cedula="1020304050")
    crear_usuario(sesion, cedula=None)
    crear_usuario(sesion, cedula=None)

    with pytest.raises(IntegrityError, match="uq_usuarios__cedula"):
        crear_usuario(sesion, cedula="1020304050")


def test_google_sub_unico(sesion: Session) -> None:
    crear_usuario(sesion, google_sub="108234567890123456789")

    with pytest.raises(IntegrityError, match="uq_usuarios__google_sub"):
        crear_usuario(sesion, google_sub="108234567890123456789")


def test_usuario_con_cargo_y_celula(sesion: Session) -> None:
    cargo = crear_cargo(sesion)
    celula = crear_celula(sesion)
    usuario = crear_usuario(sesion, cargo_id=cargo.id, celula_id=celula.id)

    assert (usuario.cargo_id, usuario.celula_id) == (cargo.id, celula.id)


def test_autores_referencian_a_usuarios(sesion: Session) -> None:
    admin = crear_usuario(sesion)
    cargo = Cargo(nombre="Auditor", created_by=admin.id, updated_by=admin.id)
    sesion.add(cargo)
    sesion.flush()

    assert cargo.created_by == admin.id


# --- privilegios de trulab_app ------------------------------------------------------------------


@pytest.mark.parametrize("tabla", ["usuarios", "cargos", "celulas"])
def test_trulab_app_no_borra_fisicamente(sesion: Session, tabla: str) -> None:
    # Se desactivan o se eliminan lógicamente (docs/database-design.md §8).
    with pytest.raises(ProgrammingError, match="permission denied"):
        sesion.execute(text(f"DELETE FROM {tabla} WHERE false"))  # noqa: S608 (tabla fija)


def test_trulab_app_desactiva_usuarios(sesion: Session) -> None:
    usuario = crear_usuario(sesion)

    sesion.execute(update(Usuario).where(Usuario.id == usuario.id).values(activo=False))
    sesion.refresh(usuario)

    assert usuario.activo is False


# --- sesiones -----------------------------------------------------------------------------------


def _hash_token() -> str:
    return hashlib.sha256(secrets.token_bytes(32)).hexdigest()


def test_sesion_guarda_solo_el_hash_y_se_revoca(sesion: Session) -> None:
    usuario = crear_usuario(sesion)
    registro = Sesion(
        usuario_id=usuario.id,
        token_hash=_hash_token(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
        ip="192.0.2.10",
        user_agent="pytest",
    )
    sesion.add(registro)
    sesion.flush()

    registro.revoked_at = datetime.now(UTC)
    sesion.flush()
    sesion.refresh(registro)
    assert registro.revoked_at is not None

    # S1-08 limpia sesiones vencidas: trulab_app puede borrarlas.
    sesion.execute(text("DELETE FROM sesiones WHERE id = :id"), {"id": registro.id})
    restantes = sesion.scalar(
        select(func.count()).select_from(Sesion).where(Sesion.id == registro.id)
    )
    assert restantes == 0


@pytest.mark.parametrize(
    "token_hash",
    ["token-en-claro", "A" * 64, "0" * 63, secrets.token_urlsafe(48)],
)
def test_sesion_rechaza_lo_que_no_sea_un_sha256_hex(sesion: Session, token_hash: str) -> None:
    usuario = crear_usuario(sesion)
    sesion.add(
        Sesion(
            usuario_id=usuario.id,
            token_hash=token_hash,
            expires_at=datetime.now(UTC) + timedelta(days=7),
        )
    )

    with pytest.raises(IntegrityError, match="ck_sesiones__token_hash_sha256"):
        sesion.flush()


def test_sesion_debe_expirar_despues_de_crearse(sesion: Session) -> None:
    usuario = crear_usuario(sesion)
    sesion.add(
        Sesion(
            usuario_id=usuario.id,
            token_hash=_hash_token(),
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
    )

    with pytest.raises(IntegrityError, match="ck_sesiones__expira_despues_de_crear"):
        sesion.flush()


def test_celula_inexistente_viola_la_fk(sesion: Session) -> None:
    with pytest.raises(IntegrityError, match="fk_usuarios__celula_id__celulas"):
        crear_usuario(sesion, celula_id=uuid.uuid4())


def test_catalogo_se_desactiva_sin_borrarse(sesion: Session) -> None:
    celula = crear_celula(sesion)
    usuario = crear_usuario(sesion, celula_id=celula.id)

    celula.activo = False
    sesion.flush()
    sesion.refresh(usuario)

    assert usuario.celula_id == celula.id
    assert sesion.get(Celula, celula.id) is not None
