"""API de cargos (S1-10, docs/api-design.md §5.2): CRUD, folio `CA-`, borrado lógico, auditoría."""

import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import Auditoria
from app.core.enums import Rol
from app.modules.cargos.models import Cargo
from app.modules.usuarios.models import Usuario
from tests.fabricas import bearer, crear_cargo, crear_usuario

URL = "/api/v1/cargos"


def _actor(sesion: Session, rol: Rol = Rol.ADMIN) -> tuple[Usuario, dict[str, str]]:
    usuario = crear_usuario(sesion, rol=rol)
    return usuario, bearer(sesion, usuario)


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


# --- permisos ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rol", "leer", "gestionar"),
    [
        (Rol.VIAJERO, 403, 403),
        (Rol.FINANCIERO, 200, 403),
        (Rol.ADMIN, 200, 201),
        (Rol.SUPERADMIN, 200, 201),
    ],
)
def test_permisos_por_rol(
    api: TestClient, sesion: Session, rol: Rol, leer: int, gestionar: int
) -> None:
    _, encabezados = _actor(sesion, rol)

    assert api.get(URL, headers=encabezados).status_code == leer
    nombre = f"Cargo {uuid.uuid4().hex[:8]}"
    assert api.post(URL, json={"nombre": nombre}, headers=encabezados).status_code == gestionar


def test_sin_token(api: TestClient) -> None:
    assert api.get(URL).status_code == 401


# --- crear ------------------------------------------------------------------------------------


def test_crear_cargo(api: TestClient, sesion: Session) -> None:
    actor, encabezados = _actor(sesion)

    respuesta = api.post(
        URL,
        json={"nombre": "  Profesional de campo  ", "descripcion": "Visitas"},
        headers=encabezados,
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert re.fullmatch(r"CA-\d{6}", cuerpo["folio"])
    assert cuerpo["nombre"] == "Profesional de campo"
    assert cuerpo["descripcion"] == "Visitas"
    assert respuesta.headers["location"] == f"{URL}/{cuerpo['id']}"
    cargo = sesion.get(Cargo, uuid.UUID(cuerpo["id"]))
    assert cargo is not None and cargo.created_by == actor.id
    (evento,) = _auditoria(sesion, "CARGO_CREAR", cargo.id)
    assert evento.usuario_id == actor.id
    assert evento.datos["nombre"] == "Profesional de campo"


def test_nombre_duplicado_sin_distinguir_mayusculas(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    crear_cargo(sesion, "Coordinador")

    respuesta = api.post(URL, json={"nombre": "COORDINADOR"}, headers=encabezados)

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "DUPLICADO"


@pytest.mark.parametrize("cuerpo", [{"nombre": "   "}, {}, {"nombre": "x", "folio": "CA-999999"}])
def test_crear_rechaza_datos_invalidos(
    api: TestClient, sesion: Session, cuerpo: dict[str, str]
) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(URL, json=cuerpo, headers=encabezados)

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALIDACION"


# --- leer y listar ----------------------------------------------------------------------------


def test_detalle(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)
    cargo = crear_cargo(sesion)

    respuesta = api.get(f"{URL}/{cargo.id}", headers=encabezados)

    assert respuesta.status_code == 200
    assert respuesta.json()["folio"] == cargo.folio


def test_detalle_inexistente(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.get(f"{URL}/{uuid.uuid4()}", headers=encabezados)

    assert respuesta.status_code == 404 and respuesta.json()["code"] == "NO_ENCONTRADO"


def test_listar_con_busqueda_y_paginacion(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    marca = uuid.uuid4().hex[:8]
    for i in range(3):
        crear_cargo(sesion, f"Analista {marca} {i}")

    pagina1 = api.get(URL, params={"q": marca, "size": 2}, headers=encabezados).json()
    pagina2 = api.get(URL, params={"q": marca, "size": 2, "page": 2}, headers=encabezados).json()

    assert pagina1["total"] == 3 and pagina1["page"] == 1 and pagina1["size"] == 2
    assert [c["nombre"] for c in pagina1["items"]] == [f"Analista {marca} 0", f"Analista {marca} 1"]
    assert [c["nombre"] for c in pagina2["items"]] == [f"Analista {marca} 2"]


@pytest.mark.parametrize("params", [{"size": 101}, {"page": 0}, {"sort": "password_hash"}])
def test_paginacion_invalida(
    api: TestClient, sesion: Session, params: dict[str, int | str]
) -> None:
    _, encabezados = _actor(sesion)

    assert api.get(URL, params=params, headers=encabezados).status_code == 422


# --- editar -----------------------------------------------------------------------------------


def test_editar(api: TestClient, sesion: Session) -> None:
    actor, encabezados = _actor(sesion)
    cargo = crear_cargo(sesion, "Auxiliar")

    respuesta = api.patch(
        f"{URL}/{cargo.id}", json={"nombre": "Auxiliar de campo"}, headers=encabezados
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre"] == "Auxiliar de campo"
    sesion.refresh(cargo)
    assert cargo.updated_by == actor.id
    (evento,) = _auditoria(sesion, "CARGO_EDITAR", cargo.id)
    assert evento.datos == {
        "antes": {"nombre": "Auxiliar"},
        "despues": {"nombre": "Auxiliar de campo"},
    }


def test_editar_a_un_nombre_existente(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    crear_cargo(sesion, "Contador")
    cargo = crear_cargo(sesion, "Tesorero")

    respuesta = api.patch(f"{URL}/{cargo.id}", json={"nombre": "contador"}, headers=encabezados)

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "DUPLICADO"


# --- eliminar (lógico) ------------------------------------------------------------------------


def test_eliminar_sin_uso(api: TestClient, sesion: Session) -> None:
    actor, encabezados = _actor(sesion)
    cargo = crear_cargo(sesion, "Temporal")

    respuesta = api.delete(f"{URL}/{cargo.id}", headers=encabezados)

    assert respuesta.status_code == 204
    sesion.refresh(cargo)
    assert cargo.deleted_at is not None and cargo.updated_by == actor.id
    assert len(_auditoria(sesion, "CARGO_ELIMINAR", cargo.id)) == 1
    assert api.get(f"{URL}/{cargo.id}", headers=encabezados).status_code == 404
    assert (
        api.patch(f"{URL}/{cargo.id}", json={"nombre": "X"}, headers=encabezados).status_code == 404
    )
    # El nombre queda libre para un cargo nuevo.
    assert api.post(URL, json={"nombre": "Temporal"}, headers=encabezados).status_code == 201


def test_no_se_elimina_un_cargo_en_uso(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    cargo = crear_cargo(sesion)
    crear_usuario(sesion, cargo_id=cargo.id, activo=False)  # también cuenta un inactivo

    respuesta = api.delete(f"{URL}/{cargo.id}", headers=encabezados)

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "EN_USO"
    sesion.refresh(cargo)
    assert cargo.deleted_at is None
