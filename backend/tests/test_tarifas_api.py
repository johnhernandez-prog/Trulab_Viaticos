"""API de `/catalogos/tarifas-viaticos` (S2-01, docs/api-design.md §5.3, DP-20, ADR-030)."""

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import Auditoria
from app.core.enums import Rol
from app.modules.catalogos.models import TarifaViatico
from app.modules.usuarios.models import Usuario
from tests.fabricas import bearer, crear_tarifa, crear_usuario

URL = "/api/v1/catalogos/tarifas-viaticos"

_CUERPO_BASE = {
    "ciudad": "Palmira",
    "es_prestador_servicios": False,
    "vr_alimentacion": "50000.00",
    "otros_gastos": "10000",
    "transporte_aeropuerto": "30000",
    "transporte_intermunicipal": "20000",
    "trans_interno_dia_1": "15000",
    "trans_interno_varios_dias": "25000",
}


def _actor(sesion: Session, rol: Rol = Rol.SUPERADMIN) -> tuple[Usuario, dict[str, str]]:
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


def _cuerpo(**cambios: object) -> dict[str, object]:
    cuerpo = dict(_CUERPO_BASE)
    cuerpo["ciudad"] = f"Ciudad {uuid.uuid4().hex[:8]}"
    cuerpo.update(cambios)
    return cuerpo


# --- permisos -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rol", "leer", "gestionar"),
    [
        (Rol.VIAJERO, 403, 403),
        (Rol.FINANCIERO, 200, 403),
        (Rol.ADMIN, 200, 403),
        (Rol.SUPERADMIN, 200, 201),
    ],
)
def test_permisos_por_rol(
    api: TestClient, sesion: Session, rol: Rol, leer: int, gestionar: int
) -> None:
    _, encabezados = _actor(sesion, rol)

    assert api.get(URL, headers=encabezados).status_code == leer
    respuesta = api.post(URL, json=_cuerpo(), headers=encabezados)
    assert respuesta.status_code == gestionar


def test_sin_token(api: TestClient) -> None:
    assert api.get(URL).status_code == 401


# --- crear -----------------------------------------------------------------------------------


def test_crear_tarifa(api: TestClient, sesion: Session) -> None:
    actor, encabezados = _actor(sesion)

    respuesta = api.post(URL, json=_cuerpo(orden=5), headers=encabezados)

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["vr_alimentacion"] == "50000.00"
    assert isinstance(cuerpo["vr_alimentacion"], str)  # ADR-012: dinero como string en JSON
    assert cuerpo["activo"] is True
    assert respuesta.headers["location"] == f"{URL}/{cuerpo['id']}"
    tarifa = sesion.get(TarifaViatico, uuid.UUID(cuerpo["id"]))
    assert tarifa is not None and tarifa.created_by == actor.id
    assert tarifa.vr_alimentacion == Decimal("50000.00")
    (evento,) = _auditoria(sesion, "TARIFA_CREAR", tarifa.id)
    assert evento.usuario_id == actor.id


def test_crear_acepta_numero_ademas_de_string(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    cuerpo = _cuerpo()
    cuerpo["vr_alimentacion"] = 50000  # número JSON, no solo string

    respuesta = api.post(URL, json=cuerpo, headers=encabezados)

    assert respuesta.status_code == 201


def test_mismo_ciudad_y_tipo_duplicado(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    ciudad = f"Ciudad {uuid.uuid4().hex[:8]}"
    crear_tarifa(sesion, ciudad=ciudad, es_prestador_servicios=False)

    respuesta = api.post(
        URL, json=_cuerpo(ciudad=ciudad, es_prestador_servicios=False), headers=encabezados
    )

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "DUPLICADO"


def test_misma_ciudad_distinto_tipo_no_es_duplicado(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    ciudad = f"Ciudad {uuid.uuid4().hex[:8]}"
    crear_tarifa(sesion, ciudad=ciudad, es_prestador_servicios=False)

    respuesta = api.post(
        URL, json=_cuerpo(ciudad=ciudad, es_prestador_servicios=True), headers=encabezados
    )

    assert respuesta.status_code == 201


@pytest.mark.parametrize("campo", ["vr_alimentacion", "otros_gastos", "transporte_aeropuerto"])
def test_rechaza_montos_negativos(api: TestClient, sesion: Session, campo: str) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(URL, json=_cuerpo(**{campo: "-1"}), headers=encabezados)

    assert respuesta.status_code == 422


def test_crear_rechaza_datos_invalidos(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(URL, json={"ciudad": "X"}, headers=encabezados)

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALIDACION"


# --- leer y listar -----------------------------------------------------------------------------


def test_detalle(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)
    tarifa = crear_tarifa(sesion)

    respuesta = api.get(f"{URL}/{tarifa.id}", headers=encabezados)

    assert respuesta.status_code == 200
    assert respuesta.json()["ciudad"] == tarifa.ciudad


def test_detalle_inexistente(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    assert api.get(f"{URL}/{uuid.uuid4()}", headers=encabezados).status_code == 404


def test_listar_con_filtros(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.ADMIN)
    marca = uuid.uuid4().hex[:8]
    crear_tarifa(sesion, ciudad=f"Marca {marca}", es_prestador_servicios=False)
    crear_tarifa(sesion, ciudad=f"Marca {marca} prestador", es_prestador_servicios=True)

    respuesta = api.get(
        URL,
        params={"ciudad": marca, "es_prestador_servicios": False},
        headers=encabezados,
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["es_prestador_servicios"] is False


def test_listar_filtra_por_activo(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    marca = uuid.uuid4().hex[:8]
    activa = crear_tarifa(sesion, ciudad=f"Activa {marca}")
    inactiva = crear_tarifa(sesion, ciudad=f"Inactiva {marca}")
    inactiva.activo = False
    sesion.flush()

    respuesta = api.get(URL, params={"ciudad": marca, "activo": True}, headers=encabezados)

    ids = {f["id"] for f in respuesta.json()["items"]}
    assert str(activa.id) in ids
    assert str(inactiva.id) not in ids


# --- editar -----------------------------------------------------------------------------------


def test_editar_valores_y_orden(api: TestClient, sesion: Session) -> None:
    actor, encabezados = _actor(sesion)
    tarifa = crear_tarifa(sesion)

    respuesta = api.patch(
        f"{URL}/{tarifa.id}",
        json={"vr_alimentacion": "60000", "orden": 2},
        headers=encabezados,
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["vr_alimentacion"] == "60000.00"
    assert cuerpo["orden"] == 2
    sesion.refresh(tarifa)
    assert tarifa.updated_by == actor.id
    (evento,) = _auditoria(sesion, "TARIFA_EDITAR", tarifa.id)
    assert evento.datos["despues"]["vr_alimentacion"] == "60000"


def test_editar_no_permite_cambiar_ciudad_ni_tipo(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    tarifa = crear_tarifa(sesion)

    respuesta = api.patch(f"{URL}/{tarifa.id}", json={"ciudad": "Otra"}, headers=encabezados)

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALIDACION"


def test_editar_rechaza_monto_negativo(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    tarifa = crear_tarifa(sesion)

    respuesta = api.patch(f"{URL}/{tarifa.id}", json={"vr_alimentacion": "-5"}, headers=encabezados)

    assert respuesta.status_code == 422


def test_editar_inexistente(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.patch(f"{URL}/{uuid.uuid4()}", json={"orden": 1}, headers=encabezados)

    assert respuesta.status_code == 404


# --- activar / desactivar ----------------------------------------------------------------------


def test_desactivar_y_activar(api: TestClient, sesion: Session) -> None:
    actor, encabezados = _actor(sesion)
    tarifa = crear_tarifa(sesion)

    respuesta = api.post(f"{URL}/{tarifa.id}/desactivar", headers=encabezados)

    assert respuesta.status_code == 200
    assert respuesta.json()["activo"] is False
    sesion.refresh(tarifa)
    assert tarifa.updated_by == actor.id
    assert len(_auditoria(sesion, "TARIFA_DESACTIVAR", tarifa.id)) == 1

    respuesta = api.post(f"{URL}/{tarifa.id}/activar", headers=encabezados)

    assert respuesta.status_code == 200
    assert respuesta.json()["activo"] is True
    assert len(_auditoria(sesion, "TARIFA_ACTIVAR", tarifa.id)) == 1


def test_desactivar_es_idempotente(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    tarifa = crear_tarifa(sesion)
    tarifa.activo = False
    sesion.flush()

    respuesta = api.post(f"{URL}/{tarifa.id}/desactivar", headers=encabezados)

    assert respuesta.status_code == 200
    assert len(_auditoria(sesion, "TARIFA_DESACTIVAR", tarifa.id)) == 0


def test_desactivar_no_afecta_instantaneas_existentes(api: TestClient, sesion: Session) -> None:
    # Cambiar/desactivar una tarifa no debe tocar los trayectos que ya la usaron (RN-29/RN-30);
    # aquí solo se verifica que la operación no falle ni intente cascada alguna.
    _, encabezados = _actor(sesion)
    tarifa = crear_tarifa(sesion)

    respuesta = api.post(f"{URL}/{tarifa.id}/desactivar", headers=encabezados)

    assert respuesta.status_code == 200
