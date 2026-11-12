"""Modelo del acceso híbrido (S1-07b, ADR-027): credenciales en `usuarios` y tokens de recuperación.

- Operativos (VIAJERO, ADMIN, FINANCIERO): `username` y `password_hash` (Argon2id) obligatorios.
- SUPERADMIN: sin contraseña (entra solo con Google); es el único que puede tener `google_sub`.
- `tokens_recuperacion_password`: solo el hash SHA-256 del token, de un solo uso.

Corre como `trulab_app` (la conexión de la API) y todo se revierte al terminar.
"""

import hashlib
import secrets
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.enums import Rol
from app.modules.auth.models import TokenRecuperacionPassword
from app.modules.usuarios.models import Usuario
from tests.fabricas import HASH_FICTICIO, crear_usuario, username_unico

OPERATIVOS = [Rol.VIAJERO, Rol.ADMIN, Rol.FINANCIERO]


# --- usuarios: contraseña según el rol ----------------------------------------------------------


@pytest.mark.parametrize("rol", OPERATIVOS)
def test_operativo_sin_password_se_rechaza(sesion: Session, rol: Rol) -> None:
    with pytest.raises(IntegrityError, match="ck_usuarios__password_segun_rol"):
        crear_usuario(sesion, rol=rol, password_hash=None)


@pytest.mark.parametrize("rol", OPERATIVOS)
def test_operativo_con_username_y_password(sesion: Session, rol: Rol) -> None:
    usuario = crear_usuario(sesion, rol=rol)
    sesion.refresh(usuario)

    assert usuario.username is not None
    assert usuario.password_hash is not None and usuario.password_hash.startswith("$argon2id$")


def test_superadmin_con_password_se_rechaza(sesion: Session) -> None:
    with pytest.raises(IntegrityError, match="ck_usuarios__password_segun_rol"):
        crear_usuario(sesion, rol=Rol.SUPERADMIN, password_hash=HASH_FICTICIO)


def test_superadmin_sin_username_ni_password(sesion: Session) -> None:
    usuario = crear_usuario(sesion, rol=Rol.SUPERADMIN)
    sesion.refresh(usuario)

    assert (usuario.username, usuario.password_hash) == (None, None)
    assert usuario.debe_cambiar_password is False


@pytest.mark.parametrize(
    "password_hash",
    ["contraseña-en-claro", "$2b$12$abcdefghijklmnopqrstuv", "$argon2i$v=19$m=65536,t=3,p=4$x$y"],
)
def test_password_hash_debe_ser_argon2id(sesion: Session, password_hash: str) -> None:
    with pytest.raises(IntegrityError, match="ck_usuarios__password_argon2id"):
        crear_usuario(sesion, password_hash=password_hash)


# --- usuarios: username -------------------------------------------------------------------------


@pytest.mark.parametrize("rol", OPERATIVOS)
def test_operativo_sin_username_se_rechaza(sesion: Session, rol: Rol) -> None:
    with pytest.raises(IntegrityError, match="ck_usuarios__username_operativo"):
        crear_usuario(sesion, rol=rol, username=None)


def test_username_unico_y_buscable_sin_distinguir_mayusculas(sesion: Session) -> None:
    # Se guarda en minúsculas (CHECK de formato); CITEXT permite buscarlo como lo escriba el
    # usuario en el login.
    username = username_unico()
    usuario = crear_usuario(sesion, username=username)

    encontrado = sesion.scalar(select(Usuario).where(Usuario.username == username.upper()))
    assert encontrado is not None and encontrado.id == usuario.id
    with pytest.raises(IntegrityError, match="uq_usuarios__username"):
        crear_usuario(sesion, username=username)


@pytest.mark.parametrize("username", ["ab", "con espacio", "Mayusculas", "ñandú", "a" * 41, "x@y"])
def test_username_con_formato_invalido_se_rechaza(sesion: Session, username: str) -> None:
    with pytest.raises(IntegrityError, match="ck_usuarios__username_formato"):
        crear_usuario(sesion, username=username)


@pytest.mark.parametrize("username", ["ana.perez", "jperez_2", "prestador-07", "abc"])
def test_username_con_formato_valido(sesion: Session, username: str) -> None:
    assert crear_usuario(sesion, username=username).username == username


def test_superadmin_puede_conservar_username(sesion: Session) -> None:
    # Al promover a un operativo se quita la contraseña; el username puede quedar (no estorba).
    usuario = crear_usuario(sesion, rol=Rol.SUPERADMIN, username=username_unico())

    assert usuario.username is not None


# --- usuarios: Google solo para SUPERADMIN ------------------------------------------------------


@pytest.mark.parametrize("rol", OPERATIVOS)
def test_operativo_con_google_sub_se_rechaza(sesion: Session, rol: Rol) -> None:
    with pytest.raises(IntegrityError, match="ck_usuarios__google_solo_superadmin"):
        crear_usuario(sesion, rol=rol, google_sub="108234567890123456789")


# --- usuarios: datos nuevos y valores por defecto -----------------------------------------------


def test_valores_por_defecto_de_los_campos_nuevos(sesion: Session) -> None:
    usuario = crear_usuario(sesion)
    sesion.refresh(usuario)

    assert usuario.debe_cambiar_password is False
    assert usuario.es_prestador_servicios is False
    assert usuario.intentos_fallidos == 0
    assert (usuario.bloqueado_hasta, usuario.password_cambiada_at) == (None, None)
    assert usuario.fecha_nacimiento is None


def test_prestador_con_fecha_de_nacimiento_y_password_temporal(sesion: Session) -> None:
    usuario = crear_usuario(
        sesion,
        es_prestador_servicios=True,
        fecha_nacimiento=date(1990, 5, 17),
        debe_cambiar_password=True,
        correo="prestador.externo@gmail.com",  # los operativos no necesitan correo corporativo
    )
    sesion.refresh(usuario)

    assert (usuario.es_prestador_servicios, usuario.debe_cambiar_password) == (True, True)
    assert usuario.fecha_nacimiento == date(1990, 5, 17)


def test_intentos_fallidos_no_negativos(sesion: Session) -> None:
    with pytest.raises(IntegrityError, match="ck_usuarios__intentos_fallidos_no_negativos"):
        crear_usuario(sesion, intentos_fallidos=-1)


def test_superadmin_no_puede_tener_cambio_de_password_pendiente(sesion: Session) -> None:
    with pytest.raises(IntegrityError, match="ck_usuarios__superadmin_sin_cambio_password"):
        crear_usuario(sesion, rol=Rol.SUPERADMIN, debe_cambiar_password=True)


# --- tokens_recuperacion_password ---------------------------------------------------------------


def _hash() -> str:
    return hashlib.sha256(secrets.token_bytes(32)).hexdigest()


def _token(sesion: Session, **campos: object) -> TokenRecuperacionPassword:
    valores: dict[str, object] = {
        "usuario_id": crear_usuario(sesion).id,
        "token_hash": _hash(),
        "expires_at": datetime.now(UTC) + timedelta(minutes=30),
    }
    valores.update(campos)
    token = TokenRecuperacionPassword(**valores)
    sesion.add(token)
    sesion.flush()
    return token


def test_token_guarda_solo_el_hash_y_se_marca_usado(sesion: Session) -> None:
    token = _token(sesion, ip="192.0.2.20")
    sesion.refresh(token)
    assert token.used_at is None and token.created_at.tzinfo is not None

    token.used_at = datetime.now(UTC)
    sesion.flush()
    sesion.refresh(token)

    assert token.used_at is not None


@pytest.mark.parametrize(
    "token_hash", ["token-en-claro", "A" * 64, "0" * 63, secrets.token_urlsafe(48)]
)
def test_token_rechaza_lo_que_no_sea_un_sha256_hex(sesion: Session, token_hash: str) -> None:
    with pytest.raises(IntegrityError, match="ck_tokens_recuperacion_password__token_hash_sha256"):
        _token(sesion, token_hash=token_hash)


def test_token_hash_unico(sesion: Session) -> None:
    repetido = _hash()
    _token(sesion, token_hash=repetido)

    with pytest.raises(IntegrityError, match="uq_tokens_recuperacion_password__token_hash"):
        _token(sesion, token_hash=repetido)


def test_token_debe_expirar_despues_de_crearse(sesion: Session) -> None:
    with pytest.raises(
        IntegrityError, match="ck_tokens_recuperacion_password__expira_despues_de_crear"
    ):
        _token(sesion, expires_at=datetime.now(UTC) - timedelta(minutes=1))


def test_trulab_app_no_borra_tokens(sesion: Session) -> None:
    # Se invalidan con `used_at`; no se borran (trazabilidad de la recuperación).
    _token(sesion)

    with pytest.raises(ProgrammingError, match="permission denied"):
        sesion.execute(text("DELETE FROM tokens_recuperacion_password WHERE false"))


def test_tokens_se_borran_con_la_purga_del_usuario(sesion: Session) -> None:
    # La FK es ON DELETE CASCADE (purga manual con trulab_owner, fuera del MVP); aquí solo se
    # comprueba la definición, porque trulab_app no puede borrar usuarios.
    regla = sesion.scalar(
        text(
            "SELECT confdeltype FROM pg_constraint "
            "WHERE conname = 'fk_tokens_recuperacion_password__usuario_id__usuarios'"
        )
    )
    assert regla == "c"


def test_tokens_del_usuario_se_listan(sesion: Session) -> None:
    token = _token(sesion)
    _token(sesion, usuario_id=token.usuario_id)

    cantidad = sesion.scalar(
        select(func.count())
        .select_from(TokenRecuperacionPassword)
        .where(TokenRecuperacionPassword.usuario_id == token.usuario_id)
    )
    assert cantidad == 2
