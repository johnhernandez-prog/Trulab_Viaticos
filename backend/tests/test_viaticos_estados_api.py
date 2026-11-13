"""Máquina de estados operativa (S2-05, docs/api-design.md §5.4): `aprobar`, `rechazar`,
`devolver`, `habilitar-legalizacion`. RN-06, RN-20, RN-21, RN-27, RN-28.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import Auditoria
from app.core.enums import EstadoFinanciero, EstadoOperativo, Etapa, Modalidad, Rol
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.models import ViaticoEvento
from tests.fabricas import bearer, crear_archivo, crear_gasto, crear_usuario, crear_viatico

URL = "/api/v1/viaticos"


def _actor(
    sesion: Session, rol: Rol = Rol.ADMIN, **campos: object
) -> tuple[Usuario, dict[str, str]]:
    usuario = crear_usuario(sesion, rol=rol, **campos)
    return usuario, bearer(sesion, usuario)


def _eventos(sesion: Session, accion: str, viatico_id: uuid.UUID) -> list[ViaticoEvento]:
    return list(
        sesion.scalars(
            select(ViaticoEvento).where(
                ViaticoEvento.viatico_id == viatico_id, ViaticoEvento.accion == accion
            )
        )
    )


def _auditoria(sesion: Session, accion: str, entidad_id: uuid.UUID) -> list[Auditoria]:
    return list(
        sesion.scalars(
            select(Auditoria).where(
                Auditoria.accion == accion,
                Auditoria.entidad_id == entidad_id,
                Auditoria.created_at >= func.now(),
            )
        )
    )


# =================================================================================================
# aprobar
# =================================================================================================


@pytest.mark.parametrize("rol", [Rol.VIAJERO, Rol.FINANCIERO])
def test_viajero_y_financiero_no_pueden_aprobar(api: TestClient, sesion: Session, rol: Rol) -> None:
    viatico = crear_viatico(sesion)
    _, encabezados = _actor(sesion, rol)

    respuesta = api.post(f"{URL}/{viatico.id}/aprobar", json={}, headers=encabezados)

    assert respuesta.status_code == 403


def test_admin_aprueba_una_legalizacion_directa_ajena(api: TestClient, sesion: Session) -> None:
    viajero = crear_usuario(sesion, rol=Rol.VIAJERO)
    viatico = crear_viatico(sesion, usuario=viajero)
    admin, encabezados = _actor(sesion, Rol.ADMIN)
    archivo = crear_archivo(sesion, created_by=viajero.id)
    crear_gasto(sesion, viatico, soporte_id=archivo.id)

    respuesta = api.post(
        f"{URL}/{viatico.id}/aprobar", json={"comentario": "Todo en orden"}, headers=encabezados
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "APROBADO"
    (evento,) = _eventos(sesion, "APROBAR", viatico.id)
    assert evento.usuario_id == admin.id
    assert evento.estado_anterior == "PENDIENTE" and evento.estado_nuevo == "APROBADO"


def test_admin_no_aprueba_su_propio_viatico_rn27(api: TestClient, sesion: Session) -> None:
    admin, encabezados = _actor(sesion, Rol.ADMIN)
    viatico = crear_viatico(sesion, usuario=admin)

    respuesta = api.post(f"{URL}/{viatico.id}/aprobar", json={}, headers=encabezados)

    assert respuesta.status_code == 403
    assert respuesta.json()["code"] == "AUTOAPROBACION_NO_PERMITIDA"


def test_superadmin_aprueba_su_propio_viatico_y_queda_auditado(
    api: TestClient, sesion: Session
) -> None:
    superadmin, encabezados = _actor(sesion, Rol.SUPERADMIN)
    viatico = crear_viatico(sesion, usuario=superadmin, modalidad=Modalidad.CON_SOLICITUD)

    respuesta = api.post(f"{URL}/{viatico.id}/aprobar", json={}, headers=encabezados)

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "APROBADO"
    (auditado,) = _auditoria(sesion, "AUTOAPROBACION_SUPERADMIN", viatico.id)
    assert auditado.usuario_id == superadmin.id


def test_no_se_aprueba_lo_que_ya_no_esta_pendiente(api: TestClient, sesion: Session) -> None:
    viatico = crear_viatico(sesion, estado=EstadoOperativo.APROBADO)
    _, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(f"{URL}/{viatico.id}/aprobar", json={}, headers=encabezados)

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "TRANSICION_INVALIDA"


def test_no_se_aprueba_una_legalizacion_sin_gastos(api: TestClient, sesion: Session) -> None:
    viatico = crear_viatico(sesion)  # LEGALIZACION_DIRECTA, sin gastos
    _, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(f"{URL}/{viatico.id}/aprobar", json={}, headers=encabezados)

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "COMPROBANTE_FALTANTE"


def test_no_se_aprueba_una_legalizacion_con_un_gasto_sin_comprobante(
    api: TestClient, sesion: Session
) -> None:
    viatico = crear_viatico(sesion)
    crear_gasto(sesion, viatico, soporte_id=None, archivo_id=None)
    _, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(f"{URL}/{viatico.id}/aprobar", json={}, headers=encabezados)

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "COMPROBANTE_FALTANTE"


def test_se_aprueba_la_solicitud_sin_exigir_gastos(api: TestClient, sesion: Session) -> None:
    # Etapa SOLICITUD: RN-06/RN-21 (gastos) no aplica todavía (eso es de la legalización).
    viatico = crear_viatico(sesion, modalidad=Modalidad.CON_SOLICITUD)
    _, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(f"{URL}/{viatico.id}/aprobar", json={}, headers=encabezados)

    assert respuesta.status_code == 200


def test_aprobar_inexistente(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(f"{URL}/{uuid.uuid4()}/aprobar", json={}, headers=encabezados)

    assert respuesta.status_code == 404


# =================================================================================================
# rechazar
# =================================================================================================


def test_admin_rechaza_con_comentario(api: TestClient, sesion: Session) -> None:
    viatico = crear_viatico(sesion)
    admin, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(
        f"{URL}/{viatico.id}/rechazar",
        json={"comentario": "Falta soporte de todos los gastos"},
        headers=encabezados,
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["estado"] == "RECHAZADO"
    (evento,) = _eventos(sesion, "RECHAZAR", viatico.id)
    assert evento.comentario == "Falta soporte de todos los gastos"
    assert evento.usuario_id == admin.id


@pytest.mark.parametrize("cuerpo", [{}, {"comentario": ""}, {"comentario": "   "}])
def test_rechazar_exige_comentario(
    api: TestClient, sesion: Session, cuerpo: dict[str, str]
) -> None:
    viatico = crear_viatico(sesion)
    _, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(f"{URL}/{viatico.id}/rechazar", json=cuerpo, headers=encabezados)

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "COMENTARIO_REQUERIDO"


def test_admin_no_rechaza_su_propio_viatico_rn27(api: TestClient, sesion: Session) -> None:
    admin, encabezados = _actor(sesion, Rol.ADMIN)
    viatico = crear_viatico(sesion, usuario=admin)

    respuesta = api.post(
        f"{URL}/{viatico.id}/rechazar", json={"comentario": "No debería poder"}, headers=encabezados
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["code"] == "AUTOAPROBACION_NO_PERMITIDA"


def test_no_se_rechaza_lo_que_ya_no_esta_pendiente(api: TestClient, sesion: Session) -> None:
    viatico = crear_viatico(sesion, estado=EstadoOperativo.RECHAZADO)
    _, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(
        f"{URL}/{viatico.id}/rechazar", json={"comentario": "De nuevo"}, headers=encabezados
    )

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "TRANSICION_INVALIDA"


@pytest.mark.parametrize("rol", [Rol.VIAJERO, Rol.FINANCIERO])
def test_viajero_y_financiero_no_pueden_rechazar(
    api: TestClient, sesion: Session, rol: Rol
) -> None:
    viatico = crear_viatico(sesion)
    _, encabezados = _actor(sesion, rol)

    respuesta = api.post(
        f"{URL}/{viatico.id}/rechazar", json={"comentario": "No debería"}, headers=encabezados
    )

    assert respuesta.status_code == 403


# =================================================================================================
# devolver
# =================================================================================================


@pytest.mark.parametrize("estado", [EstadoOperativo.PENDIENTE, EstadoOperativo.APROBADO])
def test_admin_devuelve_desde_pendiente_o_aprobado(
    api: TestClient, sesion: Session, estado: EstadoOperativo
) -> None:
    viatico = crear_viatico(sesion, estado=estado)
    admin, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(
        f"{URL}/{viatico.id}/devolver",
        json={"comentario": "Falta corregir el proyecto"},
        headers=encabezados,
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "PENDIENTE"
    (evento,) = _eventos(sesion, "DEVOLVER", viatico.id)
    assert evento.usuario_id == admin.id


def test_devolver_exige_comentario(api: TestClient, sesion: Session) -> None:
    viatico = crear_viatico(sesion)
    _, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(f"{URL}/{viatico.id}/devolver", json={}, headers=encabezados)

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "COMENTARIO_REQUERIDO"


def test_no_se_devuelve_un_rechazado(api: TestClient, sesion: Session) -> None:
    viatico = crear_viatico(sesion, estado=EstadoOperativo.RECHAZADO)
    _, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(
        f"{URL}/{viatico.id}/devolver", json={"comentario": "Intento"}, headers=encabezados
    )

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "TRANSICION_INVALIDA"


@pytest.mark.parametrize("estado_financiero", [EstadoFinanciero.PAGADO, EstadoFinanciero.PROCESADO])
def test_no_se_devuelve_si_ya_esta_pagado_o_procesado(
    api: TestClient, sesion: Session, estado_financiero: EstadoFinanciero
) -> None:
    viatico = crear_viatico(
        sesion, estado=EstadoOperativo.APROBADO, estado_financiero=estado_financiero
    )
    _, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(
        f"{URL}/{viatico.id}/devolver", json={"comentario": "Intento"}, headers=encabezados
    )

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "TRANSICION_INVALIDA"


def test_admin_no_devuelve_su_propio_viatico_rn27(api: TestClient, sesion: Session) -> None:
    admin, encabezados = _actor(sesion, Rol.ADMIN)
    viatico = crear_viatico(sesion, usuario=admin, estado=EstadoOperativo.APROBADO)

    respuesta = api.post(
        f"{URL}/{viatico.id}/devolver", json={"comentario": "No debería"}, headers=encabezados
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["code"] == "AUTOAPROBACION_NO_PERMITIDA"


# =================================================================================================
# habilitar-legalizacion
# =================================================================================================


def _solicitud_aprobada(sesion: Session, viajero: Usuario, **campos: object) -> uuid.UUID:
    valores: dict[str, object] = {
        "etapa": Etapa.SOLICITUD,
        "estado": EstadoOperativo.APROBADO,
        "requiere_gastos_viaje": False,
    }
    valores.update(campos)
    viatico = crear_viatico(sesion, usuario=viajero, modalidad=Modalidad.CON_SOLICITUD, **valores)
    return viatico.id


def test_dueno_habilita_legalizacion_sin_gastos_de_viaje(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion, Rol.VIAJERO)
    viatico_id = _solicitud_aprobada(sesion, viajero)

    respuesta = api.post(f"{URL}/{viatico_id}/habilitar-legalizacion", headers=encabezados)

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["etapa"] == "LEGALIZACION"
    assert cuerpo["estado"] == "PENDIENTE"
    (evento,) = _eventos(sesion, "HABILITAR_LEGALIZACION", viatico_id)
    assert evento.usuario_id == viajero.id


def test_no_habilita_sin_transferido_si_requiere_gastos_de_viaje(
    api: TestClient, sesion: Session
) -> None:
    viajero, encabezados = _actor(sesion, Rol.VIAJERO)
    viatico_id = _solicitud_aprobada(
        sesion, viajero, requiere_gastos_viaje=True, estado_financiero=EstadoFinanciero.PENDIENTE
    )

    respuesta = api.post(f"{URL}/{viatico_id}/habilitar-legalizacion", headers=encabezados)

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "LEGALIZACION_NO_HABILITABLE"


def test_habilita_con_transferido_si_requiere_gastos_de_viaje(
    api: TestClient, sesion: Session
) -> None:
    viajero, encabezados = _actor(sesion, Rol.VIAJERO)
    viatico_id = _solicitud_aprobada(
        sesion,
        viajero,
        requiere_gastos_viaje=True,
        estado_financiero=EstadoFinanciero.TRANSFERIDO,
    )

    respuesta = api.post(f"{URL}/{viatico_id}/habilitar-legalizacion", headers=encabezados)

    assert respuesta.status_code == 200
    assert respuesta.json()["estado_financiero"] == "TRANSFERIDO"  # se conserva (S-12)


def test_no_habilita_si_no_esta_aprobada(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion, Rol.VIAJERO)
    viatico_id = _solicitud_aprobada(sesion, viajero, estado=EstadoOperativo.PENDIENTE)

    respuesta = api.post(f"{URL}/{viatico_id}/habilitar-legalizacion", headers=encabezados)

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "LEGALIZACION_NO_HABILITABLE"


def test_no_habilita_una_legalizacion_directa(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion, Rol.VIAJERO)
    viatico = crear_viatico(sesion, usuario=viajero, modalidad=Modalidad.LEGALIZACION_DIRECTA)

    respuesta = api.post(f"{URL}/{viatico.id}/habilitar-legalizacion", headers=encabezados)

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "LEGALIZACION_NO_HABILITABLE"


def test_otro_viajero_no_ve_la_solicitud_ajena_para_habilitarla(
    api: TestClient, sesion: Session
) -> None:
    dueno = crear_usuario(sesion, rol=Rol.VIAJERO)
    viatico_id = _solicitud_aprobada(sesion, dueno)
    _, encabezados_otro = _actor(sesion, Rol.VIAJERO)

    respuesta = api.post(f"{URL}/{viatico_id}/habilitar-legalizacion", headers=encabezados_otro)

    assert respuesta.status_code == 404


def test_admin_no_puede_habilitar_legalizacion_ajena(api: TestClient, sesion: Session) -> None:
    dueno = crear_usuario(sesion, rol=Rol.VIAJERO)
    viatico_id = _solicitud_aprobada(sesion, dueno)
    _, encabezados_admin = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(f"{URL}/{viatico_id}/habilitar-legalizacion", headers=encabezados_admin)

    assert respuesta.status_code == 403


def test_superadmin_puede_habilitar_legalizacion_ajena(api: TestClient, sesion: Session) -> None:
    dueno = crear_usuario(sesion, rol=Rol.VIAJERO)
    viatico_id = _solicitud_aprobada(sesion, dueno)
    _, encabezados_superadmin = _actor(sesion, Rol.SUPERADMIN)

    respuesta = api.post(
        f"{URL}/{viatico_id}/habilitar-legalizacion", headers=encabezados_superadmin
    )

    assert respuesta.status_code == 200


# =================================================================================================
# acciones_permitidas en GET /viaticos/{id}
# =================================================================================================


def test_acciones_permitidas_reflejan_el_rol_y_el_estado(api: TestClient, sesion: Session) -> None:
    viajero, encabezados_viajero = _actor(sesion, Rol.VIAJERO)
    viatico = crear_viatico(sesion, usuario=viajero)
    _, encabezados_admin = _actor(sesion, Rol.ADMIN)

    detalle_viajero = api.get(f"{URL}/{viatico.id}", headers=encabezados_viajero).json()
    detalle_admin = api.get(f"{URL}/{viatico.id}", headers=encabezados_admin).json()

    assert "editar" in detalle_viajero["acciones_permitidas"]
    assert "aprobar" not in detalle_viajero["acciones_permitidas"]
    assert "aprobar" in detalle_admin["acciones_permitidas"]
    assert "editar" not in detalle_admin["acciones_permitidas"]


def test_acciones_permitidas_vacias_tras_rechazar(api: TestClient, sesion: Session) -> None:
    viajero, encabezados_viajero = _actor(sesion, Rol.VIAJERO)
    viatico = crear_viatico(sesion, usuario=viajero)
    _, encabezados_admin = _actor(sesion, Rol.ADMIN)
    api.post(
        f"{URL}/{viatico.id}/rechazar", json={"comentario": "No cumple"}, headers=encabezados_admin
    )

    detalle = api.get(f"{URL}/{viatico.id}", headers=encabezados_viajero).json()

    assert detalle["acciones_permitidas"] == []
