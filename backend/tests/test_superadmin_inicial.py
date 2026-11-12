"""SUPERADMIN inicial desde `SUPERADMIN_EMAIL` (S1-07). Como `trulab_app`, con rollback."""

from collections.abc import Iterator

import pytest
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.audit import Auditoria
from app.core.config import get_settings
from app.core.enums import Rol
from app.modules.usuarios import seed
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.service import (
    ErrorConfiguracion,
    ResultadoSuperadmin,
    asegurar_superadmin_inicial,
    validar_correo_corporativo,
)
from tests.fabricas import correo_unico, crear_usuario

DOMINIO = "trulab.co"


@pytest.fixture
def sin_superadmin(sesion: Session) -> Session:
    """Parte de una BD sin SUPERADMIN activo (el de desarrollo, si existe, se desactiva aquí)."""
    sesion.execute(update(Usuario).where(Usuario.rol == Rol.SUPERADMIN).values(activo=False))
    return sesion


def _eventos(sesion: Session, usuario: Usuario) -> list[Auditoria]:
    return list(
        sesion.scalars(
            select(Auditoria).where(Auditoria.entidad_id == usuario.id).order_by(Auditoria.id)
        )
    )


@pytest.mark.parametrize(
    ("correo", "normalizado"),
    [("Admin@Trulab.co", "admin@trulab.co"), ("  ana@trulab.co ", "ana@trulab.co")],
)
def test_valida_y_normaliza_el_correo_corporativo(correo: str, normalizado: str) -> None:
    assert validar_correo_corporativo(correo, DOMINIO) == normalizado


@pytest.mark.parametrize("correo", ["ana@gmail.com", "ana@trulab.co.evil.com", "no-es-correo"])
def test_rechaza_correos_fuera_del_dominio(correo: str) -> None:
    with pytest.raises(ErrorConfiguracion):
        validar_correo_corporativo(correo, DOMINIO)


def test_sin_correo_no_hace_nada(sin_superadmin: Session) -> None:
    resultado = asegurar_superadmin_inicial(sin_superadmin, "  ", "X", DOMINIO)

    assert resultado is ResultadoSuperadmin.OMITIDO_SIN_CORREO


def test_crea_el_superadmin_y_lo_audita(sin_superadmin: Session) -> None:
    correo = correo_unico()

    resultado = asegurar_superadmin_inicial(sin_superadmin, correo, "Admin Trulab", DOMINIO)

    usuario = sin_superadmin.scalars(select(Usuario).where(Usuario.correo == correo)).one()
    assert resultado is ResultadoSuperadmin.CREADO
    assert (usuario.rol, usuario.activo, usuario.nombre_completo) == (
        Rol.SUPERADMIN,
        True,
        "Admin Trulab",
    )
    # Sin contraseña ni username: entra solo con Google (ADR-027).
    assert (usuario.username, usuario.password_hash, usuario.debe_cambiar_password) == (
        None,
        None,
        False,
    )
    eventos = _eventos(sin_superadmin, usuario)
    assert [e.accion for e in eventos] == ["USUARIO_CREAR", "SUPERADMIN_ASIGNADO"]
    assert all(e.usuario_id is None and e.datos["origen"] == "seed" for e in eventos)


def test_es_idempotente(sin_superadmin: Session) -> None:
    correo = correo_unico()
    asegurar_superadmin_inicial(sin_superadmin, correo, "Admin", DOMINIO)

    resultado = asegurar_superadmin_inicial(sin_superadmin, correo, "Admin", DOMINIO)

    assert resultado is ResultadoSuperadmin.YA_HAY_SUPERADMIN
    usuarios = sin_superadmin.scalars(select(Usuario).where(Usuario.correo == correo)).all()
    assert len(usuarios) == 1


def test_no_crea_otro_si_ya_hay_un_superadmin_activo(sin_superadmin: Session) -> None:
    crear_usuario(sin_superadmin, rol=Rol.SUPERADMIN)
    otro = correo_unico()

    resultado = asegurar_superadmin_inicial(sin_superadmin, otro, "Otro", DOMINIO)

    assert resultado is ResultadoSuperadmin.YA_HAY_SUPERADMIN
    assert sin_superadmin.scalar(select(Usuario).where(Usuario.correo == otro)) is None


def test_promueve_y_reactiva_un_usuario_existente(sin_superadmin: Session) -> None:
    usuario = crear_usuario(
        sin_superadmin, rol=Rol.VIAJERO, activo=False, debe_cambiar_password=True
    )
    username = usuario.username

    resultado = asegurar_superadmin_inicial(
        sin_superadmin, usuario.correo.upper(), "Ignorado", DOMINIO
    )

    sin_superadmin.refresh(usuario)
    assert resultado is ResultadoSuperadmin.PROMOVIDO
    assert (usuario.rol, usuario.activo) == (Rol.SUPERADMIN, True)
    assert usuario.nombre_completo == "Ana Pérez"
    # Al pasar a SUPERADMIN pierde la contraseña (el CHECK lo exige); el username se conserva.
    assert (usuario.password_hash, usuario.debe_cambiar_password) == (None, False)
    assert usuario.username == username
    eventos = _eventos(sin_superadmin, usuario)
    assert [e.accion for e in eventos] == ["ROL_CAMBIAR", "SUPERADMIN_ASIGNADO"]
    assert eventos[0].datos["antes"] == {"rol": "VIAJERO", "activo": False}
    assert "password_hash" not in str(eventos[0].datos)


def test_un_superadmin_inactivo_no_cuenta(sin_superadmin: Session) -> None:
    crear_usuario(sin_superadmin, rol=Rol.SUPERADMIN, activo=False)

    resultado = asegurar_superadmin_inicial(sin_superadmin, correo_unico(), "Nuevo", DOMINIO)

    assert resultado is ResultadoSuperadmin.CREADO


def test_rechaza_un_correo_de_otro_dominio(sin_superadmin: Session) -> None:
    with pytest.raises(ErrorConfiguracion):
        asegurar_superadmin_inicial(sin_superadmin, "admin@gmail.com", "Admin", DOMINIO)


# --- comando `python -m app.modules.usuarios.seed` ----------------------------------------------


@pytest.fixture
def configuracion(monkeypatch: pytest.MonkeyPatch) -> Iterator[pytest.MonkeyPatch]:
    get_settings.cache_clear()
    yield monkeypatch
    get_settings.cache_clear()


def test_comando_sin_correo_termina_bien(configuracion: pytest.MonkeyPatch) -> None:
    configuracion.setenv("SUPERADMIN_EMAIL", "")

    assert seed.main() == 0


def test_comando_con_correo_de_otro_dominio_falla(configuracion: pytest.MonkeyPatch) -> None:
    configuracion.setenv("SUPERADMIN_EMAIL", "admin@gmail.com")

    assert seed.main() == 1
