"""API de usuarios (S1-10, docs/api-design.md §5.1, F-02; RN-11, RN-12, S-13, ADR-027).

La BD local tiene el SUPERADMIN inicial (seed) confirmado; las pruebas de "último SUPERADMIN"
desactivan a los demás dentro de su transacción (se revierte al final).
"""

import re
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.audit import Auditoria
from app.core.enums import Rol
from app.core.security import verificar_password
from app.modules.auth.models import Sesion
from app.modules.auth.service import Contexto
from app.modules.usuarios import service
from app.modules.usuarios.errores import UltimoSuperadmin
from app.modules.usuarios.models import Usuario
from tests.conftest import Buzon
from tests.fabricas import (
    bearer,
    correo_unico,
    crear_cargo,
    crear_celula,
    crear_usuario,
    username_unico,
)

URL = "/api/v1/usuarios"
OPERATIVOS = [Rol.VIAJERO, Rol.FINANCIERO, Rol.ADMIN]


def _actor(sesion: Session, rol: Rol = Rol.ADMIN) -> tuple[Usuario, dict[str, str]]:
    usuario = crear_usuario(sesion, rol=rol)
    return usuario, bearer(sesion, usuario)


def _superadmin(sesion: Session) -> Usuario:
    return crear_usuario(sesion, rol=Rol.SUPERADMIN, correo=correo_unico("trulab.co"))


def _auditoria(sesion: Session, accion: str, entidad_id: uuid.UUID) -> list[Auditoria]:
    return list(
        sesion.scalars(
            select(Auditoria)
            .where(
                Auditoria.accion == accion,
                Auditoria.entidad_id == entidad_id,
                Auditoria.created_at >= func.now(),
            )
            .order_by(Auditoria.id)
        )
    )


def _todas_las_claves(datos: object) -> set[str]:
    if isinstance(datos, dict):
        claves = {str(k).lower() for k in datos}
        for valor in datos.values():
            claves |= _todas_las_claves(valor)
        return claves
    if isinstance(datos, list):
        return set().union(*(_todas_las_claves(v) for v in datos)) if datos else set()
    return set()


def _password_del_correo(buzon: Buzon, destinatario: str) -> str:
    (correo,) = (c for c in buzon.correos if c.destinatario == destinatario)
    encontrado = re.search(r"Contraseña temporal: (\S+)", correo.texto)
    assert encontrado, correo.texto
    return encontrado.group(1)


def _sesiones_vigentes(sesion: Session, usuario: Usuario) -> int:
    return (
        sesion.scalar(
            select(func.count())
            .select_from(Sesion)
            .where(Sesion.usuario_id == usuario.id, Sesion.revoked_at.is_(None))
        )
        or 0
    )


def _nuevo_operativo(**campos: Any) -> dict[str, Any]:
    datos: dict[str, Any] = {
        "nombre_completo": "Laura Gómez",
        "correo": correo_unico("gmail.com"),
        "username": username_unico(),
        "rol": "VIAJERO",
        "es_prestador_servicios": True,
    }
    datos.update(campos)
    return datos


def _dejar_solo(sesion: Session, superadmin: Usuario) -> None:
    """Deja a `superadmin` como único SUPERADMIN activo (dentro de la transacción de la prueba)."""
    sesion.execute(
        update(Usuario)
        .where(Usuario.rol == Rol.SUPERADMIN, Usuario.id != superadmin.id)
        .values(activo=False)
    )
    sesion.flush()


# --- permisos y listado -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rol", "esperado"),
    [(Rol.VIAJERO, 403), (Rol.FINANCIERO, 403), (Rol.ADMIN, 200), (Rol.SUPERADMIN, 200)],
)
def test_listar_por_rol(api: TestClient, sesion: Session, rol: Rol, esperado: int) -> None:
    _, encabezados = _actor(sesion, rol)

    assert api.get(URL, headers=encabezados).status_code == esperado


def test_listado_sin_datos_personales_y_con_filtros(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    marca = uuid.uuid4().hex[:8]
    cargo = crear_cargo(sesion)
    crear_usuario(sesion, nombre_completo=f"Ana {marca}", cedula=f"9{marca}", cargo_id=cargo.id)
    crear_usuario(sesion, nombre_completo=f"Beto {marca}", rol=Rol.FINANCIERO, activo=False)

    todos = api.get(URL, params={"q": marca}, headers=encabezados).json()
    activos = api.get(URL, params={"q": marca, "activo": True}, headers=encabezados).json()
    financieros = api.get(URL, params={"q": marca, "rol": "FINANCIERO"}, headers=encabezados).json()
    por_cargo = api.get(URL, params={"cargo_id": str(cargo.id)}, headers=encabezados).json()

    assert todos["total"] == 2
    assert [u["nombre_completo"] for u in todos["items"]] == [f"Ana {marca}", f"Beto {marca}"]
    for item in todos["items"]:
        assert not {"cedula", "fecha_nacimiento", "password_hash", "google_sub"} & set(item)
    assert [u["nombre_completo"] for u in activos["items"]] == [f"Ana {marca}"]
    assert [u["nombre_completo"] for u in financieros["items"]] == [f"Beto {marca}"]
    assert [u["nombre_completo"] for u in por_cargo["items"]] == [f"Ana {marca}"]
    assert por_cargo["items"][0]["cargo"]["id"] == str(cargo.id)


def test_detalle_incluye_datos_personales(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    usuario = crear_usuario(sesion, cedula=f"1{uuid.uuid4().int % 10**9}")

    respuesta = api.get(f"{URL}/{usuario.id}", headers=encabezados)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["cedula"] == usuario.cedula
    assert "password_hash" not in cuerpo and "google_sub" not in cuerpo


def test_detalle_inexistente(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.get(f"{URL}/{uuid.uuid4()}", headers=encabezados)

    assert respuesta.status_code == 404 and respuesta.json()["code"] == "NO_ENCONTRADO"


# --- crear operativo --------------------------------------------------------------------------


@pytest.mark.parametrize("rol_actor", [Rol.ADMIN, Rol.SUPERADMIN])
@pytest.mark.parametrize("rol_nuevo", OPERATIVOS)
def test_crear_operativo_con_password_temporal(
    api: TestClient, sesion: Session, buzon: Buzon, rol_actor: Rol, rol_nuevo: Rol
) -> None:
    actor, encabezados = _actor(sesion, rol_actor)
    cargo, celula = crear_cargo(sesion), crear_celula(sesion)
    datos = _nuevo_operativo(
        rol=rol_nuevo.value,
        username="  Laura.Gomez." + uuid.uuid4().hex[:6].upper() + " ",
        cargo_id=str(cargo.id),
        celula_id=str(celula.id),
        cedula="1234567890",
        fecha_nacimiento="1990-05-17",
    )

    respuesta = api.post(URL, json=datos, headers=encabezados)

    assert respuesta.status_code == 201, respuesta.json()
    cuerpo = respuesta.json()
    assert respuesta.headers["location"] == f"{URL}/{cuerpo['id']}"
    assert cuerpo["username"] == datos["username"].strip().lower()
    assert cuerpo["rol"] == rol_nuevo.value
    assert cuerpo["debe_cambiar_password"] is True and cuerpo["activo"] is True
    assert cuerpo["cargo"]["id"] == str(cargo.id) and cuerpo["celula"]["id"] == str(celula.id)
    assert "password" not in str(cuerpo).lower().replace("debe_cambiar_password", "")
    # La contraseña temporal solo viaja por correo (S-13) y queda como Argon2id.
    usuario = sesion.get(Usuario, uuid.UUID(cuerpo["id"]))
    assert usuario is not None and usuario.created_by == actor.id
    temporal = _password_del_correo(buzon, datos["correo"])
    assert usuario.password_hash and verificar_password(usuario.password_hash, temporal)
    (correo,) = buzon.correos
    assert cuerpo["username"] in correo.texto
    (evento,) = _auditoria(sesion, "USUARIO_CREAR", usuario.id)
    assert evento.usuario_id == actor.id
    assert evento.datos["cedula"] == "******7890"
    assert temporal not in str(evento.datos)
    assert not _auditoria(sesion, "SUPERADMIN_ASIGNADO", usuario.id)


def test_la_password_temporal_sirve_para_entrar_y_obliga_a_cambiarla(
    api: TestClient, sesion: Session, buzon: Buzon
) -> None:
    _, encabezados = _actor(sesion)
    datos = _nuevo_operativo()
    assert api.post(URL, json=datos, headers=encabezados).status_code == 201

    login = api.post(
        "/api/v1/auth/login",
        json={
            "username": datos["username"],
            "password": _password_del_correo(buzon, datos["correo"]),
        },
    )

    assert login.status_code == 200
    assert login.json()["debe_cambiar_password"] is True


@pytest.mark.parametrize(
    "cambios",
    [
        {"username": None},
        {"username": "ab"},
        {"username": "con espacio"},
        {"correo": "no-es-correo"},
        {"nombre_completo": "  "},
        {"rol": "JEFE"},
        {"password": "Elegida-por-admin-1"},
        {"debe_cambiar_password": False},
    ],
)
def test_crear_operativo_rechaza_datos_invalidos(
    api: TestClient, sesion: Session, cambios: dict[str, Any]
) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(URL, json=_nuevo_operativo(**cambios), headers=encabezados)

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALIDACION"


@pytest.mark.parametrize("campo", ["correo", "username", "cedula"])
def test_crear_duplicado(api: TestClient, sesion: Session, campo: str) -> None:
    _, encabezados = _actor(sesion)
    existente = crear_usuario(sesion, cedula=f"7{uuid.uuid4().int % 10**9}")
    valor = getattr(existente, campo)

    respuesta = api.post(URL, json=_nuevo_operativo(**{campo: valor.upper()}), headers=encabezados)

    assert respuesta.status_code == 409
    cuerpo = respuesta.json()
    assert cuerpo["code"] == "DUPLICADO"
    assert cuerpo["errors"][0]["field"] == campo


def test_crear_con_cargo_o_celula_no_validos(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    inactiva = crear_celula(sesion)
    inactiva.activo = False
    sesion.flush()

    sin_cargo = api.post(
        URL, json=_nuevo_operativo(cargo_id=str(uuid.uuid4())), headers=encabezados
    )
    celula = api.post(URL, json=_nuevo_operativo(celula_id=str(inactiva.id)), headers=encabezados)

    assert sin_cargo.status_code == 422 and sin_cargo.json()["code"] == "VALOR_NO_PERMITIDO"
    assert celula.status_code == 422 and celula.json()["errors"][0]["field"] == "celula_id"


# --- crear SUPERADMIN (RN-12) -----------------------------------------------------------------


def test_superadmin_crea_otro_superadmin(api: TestClient, sesion: Session, buzon: Buzon) -> None:
    actor, encabezados = _actor(sesion, Rol.SUPERADMIN)
    correo = correo_unico("TRULAB.CO")

    respuesta = api.post(
        URL,
        json={"nombre_completo": "Nuevo Super", "correo": correo, "rol": "SUPERADMIN"},
        headers=encabezados,
    )

    assert respuesta.status_code == 201, respuesta.json()
    cuerpo = respuesta.json()
    assert cuerpo["username"] is None and cuerpo["debe_cambiar_password"] is False
    assert cuerpo["correo"] == correo.lower()
    usuario = sesion.get(Usuario, uuid.UUID(cuerpo["id"]))
    assert usuario is not None and usuario.password_hash is None
    assert buzon.correos == []  # entra con Google: no hay contraseña que enviar
    (evento,) = _auditoria(sesion, "SUPERADMIN_ASIGNADO", usuario.id)
    assert evento.usuario_id == actor.id
    assert len(_auditoria(sesion, "USUARIO_CREAR", usuario.id)) == 1


def test_admin_no_crea_superadmin(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(
        URL,
        json={"nombre_completo": "X", "correo": correo_unico("trulab.co"), "rol": "SUPERADMIN"},
        headers=encabezados,
    )

    assert respuesta.status_code == 403 and respuesta.json()["code"] == "SIN_PERMISO"


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"correo": "externo@gmail.com"}, "correo"),
        ({"correo": "alguien@trulab.co.evil.com"}, "correo"),
        ({"username": "super.user"}, "username"),
    ],
)
def test_superadmin_nuevo_exige_dominio_y_sin_username(
    api: TestClient, sesion: Session, cambios: dict[str, str], campo: str
) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    datos = {"nombre_completo": "X", "correo": correo_unico("trulab.co"), "rol": "SUPERADMIN"}
    datos.update(cambios)

    respuesta = api.post(URL, json=datos, headers=encabezados)

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "VALOR_NO_PERMITIDO"
    assert respuesta.json()["errors"][0]["field"] == campo


# --- editar -----------------------------------------------------------------------------------


def test_editar_datos_basicos(api: TestClient, sesion: Session) -> None:
    actor, encabezados = _actor(sesion)
    usuario = crear_usuario(sesion, cedula="1111111111")
    sesiones_antes = bearer(sesion, usuario)

    respuesta = api.patch(
        f"{URL}/{usuario.id}",
        json={"nombre_completo": "Ana María Pérez", "cedula": "2222222222", "cargo_id": None},
        headers=encabezados,
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre_completo"] == "Ana María Pérez"
    sesion.refresh(usuario)
    assert usuario.updated_by == actor.id
    (evento,) = _auditoria(sesion, "USUARIO_EDITAR", usuario.id)
    assert evento.datos["antes"]["cedula"] == "******1111"
    assert evento.datos["despues"]["cedula"] == "******2222"
    assert "cargo_id" not in evento.datos["despues"]  # sin cambio real, no se audita
    # Editar datos no cierra sesiones.
    assert api.get("/api/v1/me", headers=sesiones_antes).status_code == 200


@pytest.mark.parametrize("nuevo_rol", ["FINANCIERO", "ADMIN"])
def test_cambiar_rol_revoca_sesiones_y_se_audita(
    api: TestClient, sesion: Session, nuevo_rol: str
) -> None:
    _, encabezados = _actor(sesion)
    usuario = crear_usuario(sesion, rol=Rol.VIAJERO)
    del_usuario = bearer(sesion, usuario)

    respuesta = api.patch(f"{URL}/{usuario.id}", json={"rol": nuevo_rol}, headers=encabezados)

    assert respuesta.status_code == 200 and respuesta.json()["rol"] == nuevo_rol
    assert _sesiones_vigentes(sesion, usuario) == 0
    assert api.get("/api/v1/me", headers=del_usuario).status_code == 401
    (evento,) = _auditoria(sesion, "ROL_CAMBIAR", usuario.id)
    assert evento.datos == {"antes": {"rol": "VIAJERO"}, "despues": {"rol": nuevo_rol}}


def test_admin_no_modifica_ni_promueve_superadmins(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.ADMIN)
    superadmin = _superadmin(sesion)
    operativo = crear_usuario(sesion, correo=correo_unico("trulab.co"))

    editar = api.patch(f"{URL}/{superadmin.id}", json={"nombre_completo": "X"}, headers=encabezados)
    promover = api.patch(f"{URL}/{operativo.id}", json={"rol": "SUPERADMIN"}, headers=encabezados)
    desactivar = api.post(f"{URL}/{superadmin.id}/desactivar", headers=encabezados)

    for respuesta in (editar, promover, desactivar):
        assert respuesta.status_code == 403 and respuesta.json()["code"] == "SIN_PERMISO"
    # ADMIN sí puede verlo (listado y detalle).
    assert api.get(f"{URL}/{superadmin.id}", headers=encabezados).status_code == 200


def test_promover_a_superadmin(api: TestClient, sesion: Session) -> None:
    actor, encabezados = _actor(sesion, Rol.SUPERADMIN)
    usuario = crear_usuario(sesion, rol=Rol.ADMIN, correo=correo_unico("trulab.co"))
    del_usuario = bearer(sesion, usuario)

    respuesta = api.patch(f"{URL}/{usuario.id}", json={"rol": "SUPERADMIN"}, headers=encabezados)

    assert respuesta.status_code == 200, respuesta.json()
    sesion.refresh(usuario)
    assert usuario.rol == Rol.SUPERADMIN
    assert usuario.username is None and usuario.password_hash is None
    assert usuario.debe_cambiar_password is False
    assert api.get("/api/v1/me", headers=del_usuario).status_code == 401
    assert len(_auditoria(sesion, "ROL_CAMBIAR", usuario.id)) == 1
    (asignado,) = _auditoria(sesion, "SUPERADMIN_ASIGNADO", usuario.id)
    assert asignado.usuario_id == actor.id


def test_promover_exige_correo_corporativo(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    usuario = crear_usuario(sesion, correo=correo_unico("gmail.com"))

    sin_cambiar = api.patch(f"{URL}/{usuario.id}", json={"rol": "SUPERADMIN"}, headers=encabezados)
    corrigiendo = api.patch(
        f"{URL}/{usuario.id}",
        json={"rol": "SUPERADMIN", "correo": correo_unico("trulab.co")},
        headers=encabezados,
    )

    assert sin_cambiar.status_code == 422
    assert sin_cambiar.json()["errors"][0]["field"] == "correo"
    assert corrigiendo.status_code == 200


def test_degradar_superadmin_exige_username_y_envia_temporal(
    api: TestClient, sesion: Session, buzon: Buzon
) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    superadmin = _superadmin(sesion)
    superadmin.google_sub = f"sub-{uuid.uuid4().hex}"
    sesion.flush()
    username = username_unico()

    sin_username = api.patch(f"{URL}/{superadmin.id}", json={"rol": "ADMIN"}, headers=encabezados)
    respuesta = api.patch(
        f"{URL}/{superadmin.id}", json={"rol": "ADMIN", "username": username}, headers=encabezados
    )

    assert sin_username.status_code == 422
    assert sin_username.json()["errors"][0]["field"] == "username"
    assert respuesta.status_code == 200, respuesta.json()
    sesion.refresh(superadmin)
    assert superadmin.rol == Rol.ADMIN and superadmin.username == username
    assert superadmin.google_sub is None and superadmin.debe_cambiar_password is True
    temporal = _password_del_correo(buzon, superadmin.correo)
    assert superadmin.password_hash and verificar_password(superadmin.password_hash, temporal)


def test_no_se_degrada_al_ultimo_superadmin(api: TestClient, sesion: Session) -> None:
    unico, encabezados = _actor(sesion, Rol.SUPERADMIN)
    _dejar_solo(sesion, unico)

    respuesta = api.patch(
        f"{URL}/{unico.id}",
        json={"rol": "ADMIN", "username": username_unico()},
        headers=encabezados,
    )

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "ULTIMO_SUPERADMIN"
    sesion.refresh(unico)
    assert unico.rol == Rol.SUPERADMIN


def test_superadmin_se_degrada_si_hay_otro(api: TestClient, sesion: Session) -> None:
    yo, encabezados = _actor(sesion, Rol.SUPERADMIN)
    _dejar_solo(sesion, yo)
    _superadmin(sesion)

    respuesta = api.patch(
        f"{URL}/{yo.id}",
        json={"rol": "FINANCIERO", "username": username_unico()},
        headers=encabezados,
    )

    assert respuesta.status_code == 200
    assert api.get("/api/v1/me", headers=encabezados).status_code == 401  # sesión revocada


def test_superadmin_no_lleva_username_sin_degradar(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    superadmin = _superadmin(sesion)

    respuesta = api.patch(
        f"{URL}/{superadmin.id}", json={"username": username_unico()}, headers=encabezados
    )
    correo = api.patch(
        f"{URL}/{superadmin.id}", json={"correo": "x@gmail.com"}, headers=encabezados
    )

    assert respuesta.status_code == 422 and respuesta.json()["errors"][0]["field"] == "username"
    assert correo.status_code == 422 and correo.json()["errors"][0]["field"] == "correo"


def test_cambiar_correo_de_superadmin_desvincula_google(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    superadmin = _superadmin(sesion)
    superadmin.google_sub = f"sub-{uuid.uuid4().hex}"
    sesion.flush()

    respuesta = api.patch(
        f"{URL}/{superadmin.id}", json={"correo": correo_unico("trulab.co")}, headers=encabezados
    )

    assert respuesta.status_code == 200
    sesion.refresh(superadmin)
    assert superadmin.google_sub is None


def test_editar_duplicado(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    otro = crear_usuario(sesion)
    usuario = crear_usuario(sesion)

    respuesta = api.patch(
        f"{URL}/{usuario.id}", json={"username": otro.username}, headers=encabezados
    )

    assert respuesta.status_code == 409 and respuesta.json()["errors"][0]["field"] == "username"


# --- activar y desactivar (RN-11) -------------------------------------------------------------


def test_desactivar_revoca_sesiones_y_se_audita(api: TestClient, sesion: Session) -> None:
    actor, encabezados = _actor(sesion)
    usuario = crear_usuario(sesion)
    del_usuario = bearer(sesion, usuario)

    respuesta = api.post(f"{URL}/{usuario.id}/desactivar", headers=encabezados)
    repetida = api.post(f"{URL}/{usuario.id}/desactivar", headers=encabezados)

    assert respuesta.status_code == 200 and respuesta.json()["activo"] is False
    assert repetida.status_code == 200  # idempotente, sin un segundo evento
    assert _sesiones_vigentes(sesion, usuario) == 0
    assert api.get("/api/v1/me", headers=del_usuario).status_code == 401
    (evento,) = _auditoria(sesion, "USUARIO_DESACTIVAR", usuario.id)
    assert evento.usuario_id == actor.id


def test_activar(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    usuario = crear_usuario(sesion, activo=False)

    respuesta = api.post(f"{URL}/{usuario.id}/activar", headers=encabezados)

    assert respuesta.status_code == 200 and respuesta.json()["activo"] is True
    assert len(_auditoria(sesion, "USUARIO_ACTIVAR", usuario.id)) == 1


@pytest.mark.parametrize("rol", [Rol.ADMIN, Rol.SUPERADMIN])
def test_nadie_se_desactiva_a_si_mismo(api: TestClient, sesion: Session, rol: Rol) -> None:
    yo, encabezados = _actor(sesion, rol)

    respuesta = api.post(f"{URL}/{yo.id}/desactivar", headers=encabezados)

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "ACCION_SOBRE_SI_MISMO"


def test_superadmin_desactiva_a_otro_superadmin(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    otro = _superadmin(sesion)

    respuesta = api.post(f"{URL}/{otro.id}/desactivar", headers=encabezados)

    assert respuesta.status_code == 200 and respuesta.json()["activo"] is False


def test_el_service_no_desactiva_al_ultimo_superadmin(sesion: Session) -> None:
    # Por la API es inalcanzable (el actor es otro SUPERADMIN activo); el service lo protege igual.
    actor = _superadmin(sesion)
    unico = _superadmin(sesion)
    _dejar_solo(sesion, unico)

    with pytest.raises(UltimoSuperadmin):
        service.desactivar(sesion, unico.id, actor, Contexto(None, None))


# --- restablecer contraseña -------------------------------------------------------------------


def test_restablecer_password(api: TestClient, sesion: Session, buzon: Buzon) -> None:
    actor, encabezados = _actor(sesion)
    usuario = crear_usuario(sesion, intentos_fallidos=5)
    del_usuario = bearer(sesion, usuario)

    respuesta = api.post(f"{URL}/{usuario.id}/restablecer-password", headers=encabezados)

    assert respuesta.status_code == 200
    sesion.refresh(usuario)
    assert usuario.debe_cambiar_password is True and usuario.intentos_fallidos == 0
    temporal = _password_del_correo(buzon, usuario.correo)
    assert usuario.password_hash and verificar_password(usuario.password_hash, temporal)
    assert api.get("/api/v1/me", headers=del_usuario).status_code == 401
    (evento,) = _auditoria(sesion, "PASSWORD_CAMBIADA", usuario.id)
    assert evento.usuario_id == actor.id and evento.datos["motivo"] == "RESTABLECIDA_POR_ADMIN"


def test_restablecer_password_de_superadmin(api: TestClient, sesion: Session) -> None:
    _, de_superadmin = _actor(sesion, Rol.SUPERADMIN)
    _, de_admin = _actor(sesion, Rol.ADMIN)
    superadmin = _superadmin(sesion)

    por_superadmin = api.post(f"{URL}/{superadmin.id}/restablecer-password", headers=de_superadmin)
    por_admin = api.post(f"{URL}/{superadmin.id}/restablecer-password", headers=de_admin)

    assert por_superadmin.status_code == 409
    assert por_superadmin.json()["code"] == "SUPERADMIN_SIN_PASSWORD"
    assert por_admin.status_code == 403


# --- auditoría --------------------------------------------------------------------------------


def test_la_auditoria_de_usuarios_nunca_guarda_secretos(
    api: TestClient, sesion: Session, buzon: Buzon
) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)
    datos = _nuevo_operativo(cedula="5555555555")
    creado = api.post(URL, json=datos, headers=encabezados).json()
    api.post(f"{URL}/{creado['id']}/restablecer-password", headers=encabezados)
    api.patch(f"{URL}/{creado['id']}", json={"rol": "ADMIN"}, headers=encabezados)
    api.post(f"{URL}/{creado['id']}/desactivar", headers=encabezados)

    eventos = list(
        sesion.scalars(
            select(Auditoria).where(
                Auditoria.entidad_id == uuid.UUID(creado["id"]), Auditoria.created_at >= func.now()
            )
        )
    )

    assert {e.accion for e in eventos} >= {
        "USUARIO_CREAR",
        "PASSWORD_CAMBIADA",
        "ROL_CAMBIAR",
        "USUARIO_DESACTIVAR",
    }
    temporales = [
        m.group(1)
        for c in buzon.correos
        if (m := re.search(r"Contraseña temporal: (\S+)", c.texto))
    ]
    for evento in eventos:
        texto = str(evento.datos)
        assert "5555555555" not in texto
        assert not any(t in texto for t in temporales)
        assert not {"password", "password_hash", "password_temporal"} & _todas_las_claves(
            evento.datos
        )


@pytest.mark.parametrize(("rol", "esperado"), [(Rol.ADMIN, 403), (Rol.SUPERADMIN, 200)])
def test_consultar_auditoria(api: TestClient, sesion: Session, rol: Rol, esperado: int) -> None:
    _, de_admin = _actor(sesion, Rol.ADMIN)
    usuario = crear_usuario(sesion)
    api.post(f"{URL}/{usuario.id}/desactivar", headers=de_admin)
    _, encabezados = _actor(sesion, rol)

    respuesta = api.get(
        "/api/v1/auditoria",
        params={"entidad": "usuarios", "entidad_id": str(usuario.id)},
        headers=encabezados,
    )

    assert respuesta.status_code == esperado
    if esperado == 200:
        cuerpo = respuesta.json()
        assert cuerpo["total"] == 1
        assert cuerpo["items"][0]["accion"] == "USUARIO_DESACTIVAR"
