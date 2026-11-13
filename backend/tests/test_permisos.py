"""Matriz RBAC (S1-09): `app/core/permissions.py`, `require_permission` y `permisos` en `/me`.

La tabla `ESPERADO` de este archivo es la especificación (docs/api-design.md §4 y SPEC.md §6),
transcrita a mano a propósito: la prueba no deriva nada de la matriz del código, así que un
cambio en `MATRIZ` que no esté en la documentación la rompe.
"""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import fijar_contexto_rls, get_engine
from app.core.enums import Rol
from app.core.permissions import MATRIZ, Permiso, permisos_de, require_permission, tiene_permiso
from app.core.security import emitir_access_token
from app.modules.auth.dependencias import Autenticado
from app.modules.auth.models import Sesion
from app.modules.usuarios.models import Usuario
from tests.fabricas import crear_usuario

V, F, A, S = Rol.VIAJERO, Rol.FINANCIERO, Rol.ADMIN, Rol.SUPERADMIN
TODOS = frozenset({V, F, A, S})

ESPERADO: dict[str, frozenset[Rol]] = {
    # Lo propio: cualquier rol (el alcance por dueño lo aplica el service, ADR-012).
    "viaticos:leer_propios": TODOS,
    "viaticos:crear": TODOS,
    "viaticos:calcular_presupuesto": TODOS,
    "viaticos:habilitar_legalizacion": TODOS,
    "gastos:gestionar_propios": TODOS,
    "catalogos:leer": TODOS,
    # Lectura de lo ajeno.
    "viaticos:leer_todos": frozenset({F, A, S}),
    "comprobantes:leer_todos": frozenset({F, A, S}),
    "pagos:leer": frozenset({F, A, S}),
    "cargos:leer": frozenset({F, A, S}),
    "tarifas:leer": frozenset({F, A, S}),
    "indicadores:leer": frozenset({F, A, S}),
    # Estado operativo: ADMIN, nunca FINANCIERO (DP-13, DP-18).
    "viaticos:aprobar": frozenset({A, S}),
    "viaticos:rechazar": frozenset({A, S}),
    "viaticos:devolver": frozenset({A, S}),
    "viaticos:gestionar_tiquetes": frozenset({A, S}),
    # Dinero: FINANCIERO, nunca ADMIN (DP-04, DP-18).
    "viaticos:registrar_valor_asignado": frozenset({F, S}),
    "viaticos:cambiar_estado_financiero": frozenset({F, S}),
    # Administración.
    "cargos:gestionar": frozenset({A, S}),
    "usuarios:gestionar_operativos": frozenset({A, S}),
    "usuarios:gestionar_superadmin": frozenset({S}),
    "catalogos:gestionar": frozenset({S}),
    "tarifas:gestionar": frozenset({S}),
    "auditoria:leer": frozenset({S}),
}

CASOS = [(rol, permiso) for permiso in ESPERADO for rol in Rol]


def _id(caso: object) -> str:
    return str(caso)


# --- matriz -----------------------------------------------------------------------------------


def test_el_catalogo_de_permisos_es_exactamente_el_documentado() -> None:
    assert {p.value for p in Permiso} == set(ESPERADO)


def test_la_matriz_define_todos_los_roles() -> None:
    assert set(MATRIZ) == set(Rol)


@pytest.mark.parametrize(("rol", "permiso"), CASOS, ids=_id)
def test_matriz_rol_por_permiso(rol: Rol, permiso: str) -> None:
    """Recorre las 4 × N celdas de la matriz: lo concedido y, sobre todo, lo denegado."""
    assert tiene_permiso(rol, Permiso(permiso)) is (rol in ESPERADO[permiso])


@pytest.mark.parametrize("rol", list(Rol), ids=_id)
def test_permisos_de_cada_rol(rol: Rol) -> None:
    esperado = {permiso for permiso, roles in ESPERADO.items() if rol in roles}
    assert {p.value for p in permisos_de(rol)} == esperado


def test_superadmin_tiene_todos_los_permisos() -> None:
    assert permisos_de(S) == frozenset(Permiso)


def test_admin_no_toca_dinero_y_financiero_no_aprueba() -> None:
    # DP-04, DP-13 y DP-18: separación de funciones entre operación y tesorería.
    dinero = {Permiso.VIATICOS_REGISTRAR_VALOR_ASIGNADO, Permiso.VIATICOS_CAMBIAR_ESTADO_FINANCIERO}
    operativo = {
        Permiso.VIATICOS_APROBAR,
        Permiso.VIATICOS_RECHAZAR,
        Permiso.VIATICOS_DEVOLVER,
        Permiso.VIATICOS_GESTIONAR_TIQUETES,
    }
    assert not dinero & permisos_de(A)
    assert not operativo & permisos_de(F)


def test_solo_superadmin_gestiona_superadmins_catalogos_y_tarifas() -> None:
    exclusivos = {
        Permiso.USUARIOS_GESTIONAR_SUPERADMIN,
        Permiso.CATALOGOS_GESTIONAR,
        Permiso.TARIFAS_GESTIONAR,
        Permiso.AUDITORIA_LEER,
    }
    for rol in (V, F, A):
        assert not exclusivos & permisos_de(rol), rol


def test_la_matriz_es_inmutable() -> None:
    with pytest.raises(TypeError):
        MATRIZ[V] = frozenset(Permiso)  # type: ignore[index]
    assert isinstance(permisos_de(V), frozenset)


def test_los_permisos_siguen_el_formato_recurso_accion() -> None:
    for permiso in Permiso:
        recurso, _, accion = permiso.value.partition(":")
        assert recurso and accion and permiso.value == permiso.value.lower(), permiso


# --- require_permission (HTTP) -------------------------------------------------------------------


@pytest.fixture
def api_permisos(app: FastAPI, api: TestClient) -> Iterator[TestClient]:
    """La API de pruebas con una ruta protegida por cada permiso: `GET /_prueba/{permiso}`."""
    router = APIRouter(prefix="/api/v1/_prueba")
    for permiso in Permiso:

        def ruta(
            autenticado: Annotated[Autenticado, Depends(require_permission(permiso))],
        ) -> dict[str, str]:
            return {"usuario_id": str(autenticado.usuario.id)}

        router.add_api_route(f"/{permiso.value}", ruta, methods=["GET"])
    app.include_router(router)
    yield api


def _bearer(sesion: Session, usuario: Usuario) -> dict[str, str]:
    """Access token válido sin pasar por el login (evita el costo de Argon2 en cada caso)."""
    registro = Sesion(
        usuario_id=usuario.id,
        token_hash=uuid.uuid4().hex * 2,  # 64 hex, como un SHA-256
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    sesion.add(registro)
    sesion.flush()
    token, _ = emitir_access_token(
        usuario_id=usuario.id,
        sesion_id=registro.id,
        rol=usuario.rol,
        cambio_password=usuario.debe_cambiar_password,
        secreto=get_settings().jwt_secret,
        ttl=timedelta(minutes=5),
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(("rol", "permiso"), CASOS, ids=_id)
def test_require_permission_por_rol(
    api_permisos: TestClient, sesion: Session, rol: Rol, permiso: str
) -> None:
    usuario = crear_usuario(sesion, rol=rol)

    respuesta = api_permisos.get(f"/api/v1/_prueba/{permiso}", headers=_bearer(sesion, usuario))

    if rol in ESPERADO[permiso]:
        assert respuesta.status_code == 200
        assert respuesta.json() == {"usuario_id": str(usuario.id)}
    else:
        assert respuesta.status_code == 403
        cuerpo = respuesta.json()
        assert cuerpo["code"] == "SIN_PERMISO"
        assert respuesta.headers["content-type"].startswith("application/problem+json")
        assert permiso not in str(cuerpo)  # no se revela qué permiso faltó


def test_require_permission_sin_token(api_permisos: TestClient) -> None:
    respuesta = api_permisos.get("/api/v1/_prueba/catalogos:leer")

    assert respuesta.status_code == 401 and respuesta.json()["code"] == "NO_AUTENTICADO"


def test_require_permission_con_cambio_de_password_pendiente(
    api_permisos: TestClient, sesion: Session
) -> None:
    usuario = crear_usuario(sesion, rol=Rol.ADMIN, debe_cambiar_password=True)

    respuesta = api_permisos.get("/api/v1/_prueba/cargos:leer", headers=_bearer(sesion, usuario))

    assert respuesta.status_code == 403
    assert respuesta.json()["code"] == "CAMBIO_PASSWORD_REQUERIDO"


def test_el_rol_se_lee_de_la_bd_y_no_del_token(api_permisos: TestClient, sesion: Session) -> None:
    usuario = crear_usuario(sesion, rol=Rol.ADMIN)
    encabezados = _bearer(sesion, usuario)  # el JWT dice ADMIN
    ruta = "/api/v1/_prueba/cargos:gestionar"
    assert api_permisos.get(ruta, headers=encabezados).status_code == 200

    usuario.rol = Rol.VIAJERO
    sesion.flush()

    assert api_permisos.get(ruta, headers=encabezados).status_code == 403


# --- /me ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("rol", list(Rol), ids=_id)
def test_me_expone_los_permisos_del_rol(api: TestClient, sesion: Session, rol: Rol) -> None:
    usuario = crear_usuario(sesion, rol=rol)

    respuesta = api.get("/api/v1/me", headers=_bearer(sesion, usuario))

    assert respuesta.status_code == 200
    permisos = respuesta.json()["permisos"]
    assert permisos == sorted(permisos)  # orden estable para la UI y los snapshots
    assert set(permisos) == {p for p, roles in ESPERADO.items() if rol in roles}


def test_me_con_cambio_pendiente_no_expone_permisos(api: TestClient, sesion: Session) -> None:
    # Hasta cambiar la contraseña temporal, el resto de la API responde 403: la UI no debe mostrar
    # un menú que no puede usar.
    usuario = crear_usuario(sesion, rol=Rol.ADMIN, debe_cambiar_password=True)

    respuesta = api.get("/api/v1/me", headers=_bearer(sesion, usuario))

    assert respuesta.status_code == 200
    assert respuesta.json()["debe_cambiar_password"] is True
    assert respuesta.json()["permisos"] == []


# --- contexto de RLS (SET LOCAL por transacción, base de S2-03) ----------------------------------


def _contexto(session: Session) -> tuple[str | None, str | None]:
    fila = session.execute(
        text("SELECT current_setting('app.usuario_id', true), current_setting('app.rol', true)")
    ).one()
    return fila[0] or None, fila[1] or None


def test_peticion_autenticada_fija_el_contexto_de_rls(
    api_permisos: TestClient, sesion: Session
) -> None:
    usuario = crear_usuario(sesion, rol=Rol.FINANCIERO)

    respuesta = api_permisos.get("/api/v1/_prueba/pagos:leer", headers=_bearer(sesion, usuario))

    assert respuesta.status_code == 200
    assert _contexto(sesion) == (str(usuario.id), "FINANCIERO")


def test_el_contexto_de_rls_es_local_y_se_reaplica_en_cada_transaccion() -> None:
    usuario_id = uuid.uuid4()
    with Session(get_engine()) as session:
        assert _contexto(session) == (None, None)

        fijar_contexto_rls(session, usuario_id, Rol.ADMIN)
        assert _contexto(session) == (str(usuario_id), "ADMIN")

        session.rollback()  # termina la transacción: SET LOCAL se pierde en PostgreSQL...
        assert _contexto(session) == (str(usuario_id), "ADMIN")  # ...y se reaplica al empezar otra

    with Session(get_engine()) as otra:  # la conexión vuelve al pool sin contexto
        assert _contexto(otra) == (None, None)
