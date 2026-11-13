"""`PATCH /viaticos/{id}` y `DELETE /viaticos/{id}` (S2-05, docs/api-design.md §5.4): solo el
dueño o SUPERADMIN, y solo mientras `estado == PENDIENTE` y `estado_financiero == PENDIENTE`
(RN-09, S-05)."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import Auditoria
from app.core.enums import EstadoFinanciero, EstadoOperativo, Etapa, Modalidad, Rol
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.models import Viatico, ViaticoEvento, ViaticoTrayecto
from tests.fabricas import bearer, crear_gasto, crear_proyecto, crear_usuario, crear_viatico

URL = "/api/v1/viaticos"
IDA = datetime(2026, 12, 10, 8, tzinfo=UTC)


def _actor(
    sesion: Session, rol: Rol = Rol.VIAJERO, **campos: object
) -> tuple[Usuario, dict[str, str]]:
    usuario = crear_usuario(sesion, rol=rol, **campos)
    return usuario, bearer(sesion, usuario)


def _trayecto(**campos: object) -> dict[str, object]:
    valores: dict[str, object] = {
        "orden": 1,
        "ciudad_origen": "Medellín",
        "ciudad_destino": "Bogotá",
        "fecha_ida": IDA.isoformat(),
        "fecha_regreso": (IDA + timedelta(days=1)).isoformat(),
        "requiere_hospedaje": True,
        "dias_estadia": 2,
    }
    valores.update(campos)
    return valores


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
# PATCH: permisos y gate PENDIENTE/PENDIENTE
# =================================================================================================


def test_dueno_edita_su_propio_viatico(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero, modalidad=Modalidad.LEGALIZACION_DIRECTA)

    respuesta = api.patch(
        f"{URL}/{viatico.id}", json={"motivo_viaje": "Motivo actualizado"}, headers=encabezados
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["motivo_viaje"] == "Motivo actualizado"


def test_otro_viajero_no_ve_ni_edita_un_viatico_ajeno(api: TestClient, sesion: Session) -> None:
    # RLS (S2-03) ya lo hace invisible para otro VIAJERO: 404, igual que GET (ADR-012).
    dueno = crear_usuario(sesion, rol=Rol.VIAJERO)
    viatico = crear_viatico(sesion, usuario=dueno)
    _, encabezados_otro = _actor(sesion)

    respuesta = api.patch(
        f"{URL}/{viatico.id}", json={"motivo_viaje": "Intento ajeno"}, headers=encabezados_otro
    )

    assert respuesta.status_code == 404


@pytest.mark.parametrize("rol", [Rol.FINANCIERO, Rol.ADMIN])
def test_financiero_y_admin_ven_pero_no_editan_un_viatico_ajeno(
    api: TestClient, sesion: Session, rol: Rol
) -> None:
    # A diferencia de otro VIAJERO, F/A sí lo ven (RLS los deja pasar); el service los rechaza.
    dueno = crear_usuario(sesion, rol=Rol.VIAJERO)
    viatico = crear_viatico(sesion, usuario=dueno)
    _, encabezados = _actor(sesion, rol)

    respuesta = api.patch(
        f"{URL}/{viatico.id}", json={"motivo_viaje": "Intento no autorizado"}, headers=encabezados
    )

    assert respuesta.status_code == 403


def test_superadmin_puede_editar_cualquier_viatico(api: TestClient, sesion: Session) -> None:
    dueno = crear_usuario(sesion, rol=Rol.VIAJERO)
    viatico = crear_viatico(sesion, usuario=dueno)
    _, encabezados_superadmin = _actor(sesion, Rol.SUPERADMIN)

    respuesta = api.patch(
        f"{URL}/{viatico.id}",
        json={"motivo_viaje": "Editado por superadmin"},
        headers=encabezados_superadmin,
    )

    assert respuesta.status_code == 200


def test_no_se_edita_fuera_de_pendiente(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero, estado=EstadoOperativo.APROBADO)

    respuesta = api.patch(
        f"{URL}/{viatico.id}", json={"motivo_viaje": "No debería pasar"}, headers=encabezados
    )

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "NO_EDITABLE"


def test_no_se_edita_con_estado_financiero_distinto_de_pendiente(
    api: TestClient, sesion: Session
) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero, estado_financiero=EstadoFinanciero.TRANSFERIDO)

    respuesta = api.patch(
        f"{URL}/{viatico.id}", json={"motivo_viaje": "No debería pasar"}, headers=encabezados
    )

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "NO_EDITABLE"


def test_editar_inexistente(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.patch(
        f"{URL}/{uuid.uuid4()}", json={"motivo_viaje": "Motivo cualquiera"}, headers=encabezados
    )

    assert respuesta.status_code == 404


# =================================================================================================
# PATCH: CON_SOLICITUD en etapa SOLICITUD
# =================================================================================================


def _viatico_con_solicitud(sesion: Session, viajero: Usuario, **campos: object) -> Viatico:
    proyecto = crear_proyecto(sesion)
    valores: dict[str, object] = {
        "proyecto_id": proyecto.id,
        "proyecto_otro": None,
        "lider_proyecto": "María Gómez",
    }
    valores.update(campos)
    viatico = crear_viatico(sesion, usuario=viajero, modalidad=Modalidad.CON_SOLICITUD, **valores)
    sesion.add(
        ViaticoTrayecto(
            viatico_id=viatico.id,
            orden=1,
            ciudad_origen="Medellín",
            ciudad_destino="Bogotá",
            fecha_ida=IDA,
            fecha_regreso=IDA + timedelta(days=1),
            dias_estadia=2,
        )
    )
    sesion.flush()
    return viatico


def test_editar_motivo_lider_y_comentarios(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = _viatico_con_solicitud(sesion, viajero)

    respuesta = api.patch(
        f"{URL}/{viatico.id}",
        json={
            "motivo_viaje": "Nuevo motivo del viaje",
            "lider_proyecto": "Otro líder",
            "comentarios": "Comentario nuevo",
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["motivo_viaje"] == "Nuevo motivo del viaje"
    assert cuerpo["solicitud"]["lider_proyecto"] == "Otro líder"
    assert cuerpo["solicitud"]["comentarios"] == "Comentario nuevo"
    (evento,) = _eventos(sesion, "EDITAR_SOLICITUD", viatico.id)
    assert evento.usuario_id == viajero.id


def test_editar_proyecto_a_otro_borra_proyecto_id(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = _viatico_con_solicitud(sesion, viajero)

    respuesta = api.patch(
        f"{URL}/{viatico.id}",
        json={"proyecto_otro": "Proyecto escrito a mano"},
        headers=encabezados,
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["solicitud"]["proyecto"] == {
        "id": None,
        "nombre": "Proyecto escrito a mano",
        "en_catalogo": False,
    }


def test_editar_proyecto_ambos_a_la_vez_es_ambiguo(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = _viatico_con_solicitud(sesion, viajero)
    otro_proyecto = crear_proyecto(sesion)

    respuesta = api.patch(
        f"{URL}/{viatico.id}",
        json={"proyecto_id": str(otro_proyecto.id), "proyecto_otro": "Y también otro"},
        headers=encabezados,
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "PROYECTO_AMBIGUO"


def test_editar_trayectos_recalcula_presupuesto(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = _viatico_con_solicitud(sesion, viajero, requiere_gastos_viaje=True)

    respuesta = api.patch(
        f"{URL}/{viatico.id}",
        json={"trayectos": [_trayecto(ciudad_destino="Cali", dias_estadia=1)]},
        headers=encabezados,
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert len(cuerpo["solicitud"]["trayectos"]) == 1
    assert cuerpo["solicitud"]["trayectos"][0]["ciudad_destino"] == "Cali"
    assert Decimal(cuerpo["solicitud"]["presupuesto_solicitado"]) > 0


def test_editar_requiere_gastos_viaje_recalcula_sin_enviar_trayectos(
    api: TestClient, sesion: Session
) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = _viatico_con_solicitud(sesion, viajero, requiere_gastos_viaje=False)

    respuesta = api.patch(
        f"{URL}/{viatico.id}", json={"requiere_gastos_viaje": True}, headers=encabezados
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["solicitud"]["requiere_gastos_viaje"] is True
    assert cuerpo["solicitud"]["presupuesto_solicitado"] is not None


def test_editar_requiere_tiquete_sin_fecha_nacimiento(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion, fecha_nacimiento=None)
    viatico = _viatico_con_solicitud(sesion, viajero)

    respuesta = api.patch(
        f"{URL}/{viatico.id}", json={"requiere_tiquete": True}, headers=encabezados
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "FECHA_NACIMIENTO_REQUERIDA"


def test_editar_rechaza_recursos_propios_en_solicitud(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = _viatico_con_solicitud(sesion, viajero)

    respuesta = api.patch(
        f"{URL}/{viatico.id}", json={"recursos_propios": True}, headers=encabezados
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALOR_NO_PERMITIDO"


# =================================================================================================
# PATCH: etapa LEGALIZACION
# =================================================================================================


def test_editar_legalizacion_directa_motivo_y_recursos_propios(
    api: TestClient, sesion: Session
) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(
        sesion,
        usuario=viajero,
        modalidad=Modalidad.LEGALIZACION_DIRECTA,
        recursos_propios=False,
    )

    respuesta = api.patch(
        f"{URL}/{viatico.id}",
        json={"motivo_viaje": "Motivo revisado", "recursos_propios": True},
        headers=encabezados,
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["motivo_viaje"] == "Motivo revisado"
    assert cuerpo["recursos_propios"] is True
    (evento,) = _eventos(sesion, "CAMBIAR_RECURSOS_PROPIOS", viatico.id)
    assert evento.datos is not None
    assert evento.datos["despues"]["recursos_propios"] is True


def test_editar_legalizacion_rechaza_proyecto_y_trayectos(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero, modalidad=Modalidad.LEGALIZACION_DIRECTA)

    respuesta = api.patch(
        f"{URL}/{viatico.id}",
        json={"trayectos": [_trayecto()]},
        headers=encabezados,
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALOR_NO_PERMITIDO"


def test_editar_legalizacion_de_con_solicitud_no_acepta_recursos_propios(
    api: TestClient, sesion: Session
) -> None:
    # Tras habilitar la legalización, un CON_SOLICITUD queda en etapa LEGALIZACION pero no admite
    # `recursos_propios` (DP-17: solo lo marca el viajero al crear una LEGALIZACION_DIRECTA).
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(
        sesion,
        usuario=viajero,
        modalidad=Modalidad.CON_SOLICITUD,
        etapa=Etapa.LEGALIZACION,
        proyecto_otro="Proyecto habilitado",
        lider_proyecto="María Gómez",
        legalizacion_habilitada_at=datetime.now(UTC),
    )

    respuesta = api.patch(
        f"{URL}/{viatico.id}", json={"recursos_propios": True}, headers=encabezados
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALOR_NO_PERMITIDO"


# =================================================================================================
# DELETE
# =================================================================================================


def test_eliminar_viatico_propio(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)

    respuesta = api.delete(f"{URL}/{viatico.id}", headers=encabezados)

    assert respuesta.status_code == 204
    sesion.refresh(viatico)
    assert viatico.deleted_at is not None and viatico.updated_by == viajero.id
    assert api.get(f"{URL}/{viatico.id}", headers=encabezados).status_code == 404
    (evento,) = _eventos(sesion, "ELIMINAR", viatico.id)
    assert evento.usuario_id == viajero.id
    (auditado,) = _auditoria(sesion, "VIATICO_ELIMINAR", viatico.id)
    assert auditado.usuario_id == viajero.id


def test_eliminar_cascada_a_sus_gastos(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    gasto = crear_gasto(sesion, viatico)

    respuesta = api.delete(f"{URL}/{viatico.id}", headers=encabezados)

    assert respuesta.status_code == 204
    sesion.refresh(gasto)
    assert gasto.deleted_at is not None


def test_otro_viajero_no_ve_ni_elimina_un_viatico_ajeno(api: TestClient, sesion: Session) -> None:
    # No se verifica `viatico.deleted_at` tras la petición: RLS dejó el contexto de la sesión
    # compartida como el de "otro" (sin acceso a la fila de `dueno`); el 404 ya prueba que la
    # fila sigue intacta (invisible, nunca llegó a mutarse).
    dueno = crear_usuario(sesion, rol=Rol.VIAJERO)
    viatico = crear_viatico(sesion, usuario=dueno)
    _, encabezados_otro = _actor(sesion)

    respuesta = api.delete(f"{URL}/{viatico.id}", headers=encabezados_otro)

    assert respuesta.status_code == 404


def test_financiero_ve_pero_no_elimina_un_viatico_ajeno(api: TestClient, sesion: Session) -> None:
    dueno = crear_usuario(sesion, rol=Rol.VIAJERO)
    viatico = crear_viatico(sesion, usuario=dueno)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = api.delete(f"{URL}/{viatico.id}", headers=encabezados)

    assert respuesta.status_code == 403
    sesion.refresh(viatico)
    assert viatico.deleted_at is None


def test_superadmin_puede_eliminar_cualquier_viatico(api: TestClient, sesion: Session) -> None:
    dueno = crear_usuario(sesion, rol=Rol.VIAJERO)
    viatico = crear_viatico(sesion, usuario=dueno)
    _, encabezados_superadmin = _actor(sesion, Rol.SUPERADMIN)

    respuesta = api.delete(f"{URL}/{viatico.id}", headers=encabezados_superadmin)

    assert respuesta.status_code == 204


def test_no_se_elimina_fuera_de_pendiente(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero, estado=EstadoOperativo.APROBADO)

    respuesta = api.delete(f"{URL}/{viatico.id}", headers=encabezados)

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "NO_EDITABLE"


def test_no_se_elimina_con_estado_financiero_transferido(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero, estado_financiero=EstadoFinanciero.TRANSFERIDO)

    respuesta = api.delete(f"{URL}/{viatico.id}", headers=encabezados)

    assert respuesta.status_code == 409 and respuesta.json()["code"] == "NO_EDITABLE"


def test_eliminar_inexistente(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.delete(f"{URL}/{uuid.uuid4()}", headers=encabezados)

    assert respuesta.status_code == 404
