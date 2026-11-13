"""Tiquetes y dinero (S2-07, docs/api-design.md §5.4): `gestionar-tiquetes`, `valor-asignado` y
`estado-financiero` (con la liquidación). RN-03, RN-10, RN-14, RN-19, RN-22, RN-26, RN-27, S-03,
S-10, S-12.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import Auditoria
from app.core.enums import (
    EstadoFinanciero,
    EstadoOperativo,
    Etapa,
    Modalidad,
    PropositoArchivo,
    Rol,
)
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.models import Viatico, ViaticoEvento
from app.modules.viaticos.service import sentido_liquidacion
from tests.fabricas import (
    bearer,
    crear_archivo,
    crear_gasto,
    crear_rubro,
    crear_usuario,
    crear_viatico,
)

URL = "/api/v1/viaticos"
E, F = EstadoOperativo, EstadoFinanciero


def _actor(sesion: Session, rol: Rol) -> tuple[Usuario, dict[str, str]]:
    usuario = crear_usuario(sesion, rol=rol)
    return usuario, bearer(sesion, usuario)


def _eventos(sesion: Session, viatico_id: uuid.UUID, accion: str) -> list[ViaticoEvento]:
    return list(
        sesion.scalars(
            select(ViaticoEvento)
            .where(ViaticoEvento.viatico_id == viatico_id, ViaticoEvento.accion == accion)
            .order_by(ViaticoEvento.created_at)
        )
    )


def _auditoria(sesion: Session, entidad_id: uuid.UUID) -> list[Auditoria]:
    return list(
        sesion.scalars(
            select(Auditoria).where(
                Auditoria.accion == "AUTOAPROBACION_SUPERADMIN",
                Auditoria.entidad_id == entidad_id,
                Auditoria.created_at >= func.now(),
            )
        )
    )


def _solicitud_aprobada(sesion: Session, dueno: Usuario | None = None, **campos: Any) -> Viatico:
    valores: dict[str, Any] = {
        "estado": E.APROBADO,
        "requiere_gastos_viaje": True,
        "presupuesto_solicitado": Decimal("980000"),
    }
    valores.update(campos)
    return crear_viatico(sesion, usuario=dueno, modalidad=Modalidad.CON_SOLICITUD, **valores)


def _legalizacion_aprobada(
    sesion: Session,
    dueno: Usuario | None = None,
    gastos: tuple[str, ...] = ("50000",),
    **campos: Any,
) -> Viatico:
    """Legalización directa APROBADO con gastos con comprobante (RN-03 cumplida)."""
    dueno = dueno or crear_usuario(sesion)
    viatico = crear_viatico(sesion, usuario=dueno, **campos)
    for valor in gastos:
        crear_gasto(
            sesion,
            viatico,
            valor=Decimal(valor),
            soporte_id=crear_archivo(sesion, created_by=dueno.id).id,
        )
    viatico.estado = E.APROBADO
    sesion.flush()
    return viatico


# =================================================================================================
# PATCH /viaticos/{id}/valor-asignado
# =================================================================================================


@pytest.mark.parametrize("rol", [Rol.FINANCIERO, Rol.SUPERADMIN])
def test_financiero_registra_el_valor_asignado(api: TestClient, sesion: Session, rol: Rol) -> None:
    viatico = _solicitud_aprobada(sesion)
    actor, encabezados = _actor(sesion, rol)

    respuesta = api.patch(
        f"{URL}/{viatico.id}/valor-asignado",
        json={"valor_asignado": "1000000", "comentario": "Según tarifa"},
        headers=encabezados,
    )

    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["valor_asignado"] == "1000000.00"
    assert cuerpo["valor_transferido"] == "1000000.00"  # RN-14, columna generada
    assert cuerpo["estado_financiero"] == "PENDIENTE"
    (evento,) = _eventos(sesion, viatico.id, "EDITAR_VALOR_ASIGNADO")
    assert evento.usuario_id == actor.id
    assert evento.dimension == "FINANCIERO"
    assert evento.comentario == "Según tarifa"
    assert evento.estado_anterior is None and evento.estado_nuevo is None
    assert evento.datos == {
        "antes": {"valor_asignado": "0.00"},
        "despues": {"valor_asignado": "1000000.00"},
        "presupuesto_solicitado": "980000.00",
    }


@pytest.mark.parametrize("rol", [Rol.VIAJERO, Rol.ADMIN])
def test_viajero_y_admin_no_registran_valor_asignado(
    api: TestClient, sesion: Session, rol: Rol
) -> None:
    viatico = _solicitud_aprobada(sesion)
    _, encabezados = _actor(sesion, rol)

    respuesta = api.patch(
        f"{URL}/{viatico.id}/valor-asignado", json={"valor_asignado": "1"}, headers=encabezados
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["code"] == "SIN_PERMISO"


def test_financiero_no_registra_el_valor_de_su_propio_viatico(
    api: TestClient, sesion: Session
) -> None:
    financiero, encabezados = _actor(sesion, Rol.FINANCIERO)
    viatico = _solicitud_aprobada(sesion, dueno=financiero)

    respuesta = api.patch(
        f"{URL}/{viatico.id}/valor-asignado", json={"valor_asignado": "1"}, headers=encabezados
    )

    assert respuesta.status_code == 403
    assert respuesta.json()["code"] == "AUTOAPROBACION_NO_PERMITIDA"
    assert respuesta.json()["detail"] == "No puede registrar el valor asignado de su propio viático"
    sesion.refresh(viatico)
    assert viatico.valor_asignado == 0


def test_superadmin_registra_el_valor_de_su_propio_viatico_con_auditoria(
    api: TestClient, sesion: Session
) -> None:
    superadmin, encabezados = _actor(sesion, Rol.SUPERADMIN)
    viatico = _solicitud_aprobada(sesion, dueno=superadmin)

    respuesta = api.patch(
        f"{URL}/{viatico.id}/valor-asignado", json={"valor_asignado": "5"}, headers=encabezados
    )

    assert respuesta.status_code == 200
    (registro,) = _auditoria(sesion, viatico.id)
    assert registro.datos == {"folio": viatico.folio, "accion": "EDITAR_VALOR_ASIGNADO"}


@pytest.mark.parametrize(
    ("campos", "detalle"),
    [
        ({"estado": E.PENDIENTE}, "El viático debe estar APROBADO"),
        ({"estado": E.RECHAZADO}, "El viático debe estar APROBADO"),
    ],
)
def test_valor_asignado_exige_aprobado(
    api: TestClient, sesion: Session, campos: dict[str, Any], detalle: str
) -> None:
    viatico = _solicitud_aprobada(sesion, **campos)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = api.patch(
        f"{URL}/{viatico.id}/valor-asignado", json={"valor_asignado": "1"}, headers=encabezados
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "TRANSICION_INVALIDA"
    assert respuesta.json()["detail"] == detalle


def test_valor_asignado_no_aplica_con_recursos_propios(api: TestClient, sesion: Session) -> None:
    viatico = _legalizacion_aprobada(sesion, recursos_propios=True)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = api.patch(
        f"{URL}/{viatico.id}/valor-asignado", json={"valor_asignado": "1"}, headers=encabezados
    )

    assert respuesta.status_code == 409
    assert "RN-14" in respuesta.json()["detail"]


def test_valor_asignado_no_cambia_si_ya_esta_liquidado(api: TestClient, sesion: Session) -> None:
    viatico = _legalizacion_aprobada(sesion)
    viatico.estado_financiero = F.PAGADO
    sesion.flush()
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = api.patch(
        f"{URL}/{viatico.id}/valor-asignado", json={"valor_asignado": "1"}, headers=encabezados
    )

    assert respuesta.status_code == 409


def test_valor_asignado_se_corrige_despues_de_transferir(api: TestClient, sesion: Session) -> None:
    viatico = _solicitud_aprobada(
        sesion, estado_financiero=F.TRANSFERIDO, valor_asignado=Decimal("100")
    )
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = api.patch(
        f"{URL}/{viatico.id}/valor-asignado", json={"valor_asignado": "150"}, headers=encabezados
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["valor_asignado"] == "150.00"


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"valor_asignado": "-1"},
        {"valor_asignado": "1.234"},
        {"valor_asignado": "abc"},
        {},
        {"valor_asignado": "1", "valor_transferido": "1"},
    ],
)
def test_valor_asignado_valida_el_cuerpo(
    api: TestClient, sesion: Session, cuerpo: dict[str, object]
) -> None:
    viatico = _solicitud_aprobada(sesion)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = api.patch(f"{URL}/{viatico.id}/valor-asignado", json=cuerpo, headers=encabezados)

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "VALIDACION"


def test_valor_asignado_cero_es_valido(api: TestClient, sesion: Session) -> None:
    viatico = _solicitud_aprobada(sesion, valor_asignado=Decimal("10"))
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = api.patch(
        f"{URL}/{viatico.id}/valor-asignado", json={"valor_asignado": 0}, headers=encabezados
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["valor_transferido"] == "0.00"


# =================================================================================================
# POST /viaticos/{id}/estado-financiero
# =================================================================================================


def _estado(
    api: TestClient,
    viatico: Viatico,
    destino: str,
    encabezados: dict[str, str],
    comentario: str | None = None,
) -> httpx.Response:
    cuerpo: dict[str, object] = {"estado_financiero": destino}
    if comentario is not None:
        cuerpo["comentario"] = comentario
    return api.post(f"{URL}/{viatico.id}/estado-financiero", json=cuerpo, headers=encabezados)


def test_transferir_una_solicitud_aprobada_con_valor(api: TestClient, sesion: Session) -> None:
    viatico = _solicitud_aprobada(sesion, valor_asignado=Decimal("1000000"))
    financiero, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _estado(api, viatico, "TRANSFERIDO", encabezados, "Transferencia 123")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado_financiero"] == "TRANSFERIDO"
    sesion.refresh(viatico)
    assert viatico.estado_financiero_at is not None
    (evento,) = _eventos(sesion, viatico.id, "CAMBIAR_ESTADO_FINANCIERO")
    assert (evento.dimension, evento.estado_anterior, evento.estado_nuevo) == (
        "FINANCIERO",
        "PENDIENTE",
        "TRANSFERIDO",
    )
    assert evento.usuario_id == financiero.id and evento.comentario == "Transferencia 123"
    assert _eventos(sesion, viatico.id, "LIQUIDAR") == []
    # Con eso el dueño ya puede habilitar la legalización (RN-28).
    dueno = sesion.get(Usuario, viatico.usuario_id)
    assert dueno is not None
    detalle = api.get(f"{URL}/{viatico.id}", headers=bearer(sesion, dueno)).json()
    assert "habilitar_legalizacion" in detalle["acciones_permitidas"]


def test_transferir_exige_valor_asignado(api: TestClient, sesion: Session) -> None:
    viatico = _solicitud_aprobada(sesion)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _estado(api, viatico, "TRANSFERIDO", encabezados)

    assert respuesta.status_code == 409
    assert respuesta.json()["detail"] == "Registre primero el valor asignado"


@pytest.mark.parametrize("estado", [E.PENDIENTE, E.RECHAZADO])
def test_estado_financiero_exige_aprobado(
    api: TestClient, sesion: Session, estado: EstadoOperativo
) -> None:
    viatico = _solicitud_aprobada(sesion, estado=estado, valor_asignado=Decimal("1"))
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _estado(api, viatico, "TRANSFERIDO", encabezados)

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "TRANSICION_INVALIDA"


def test_no_se_transfiere_con_recursos_propios(api: TestClient, sesion: Session) -> None:
    viatico = _legalizacion_aprobada(sesion, recursos_propios=True)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _estado(api, viatico, "TRANSFERIDO", encabezados)

    assert respuesta.status_code == 409


@pytest.mark.parametrize(
    ("actual", "destino"),
    [
        (F.TRANSFERIDO, "TRANSFERIDO"),
        (F.TRANSFERIDO, "PENDIENTE"),
        (F.PAGADO, "TRANSFERIDO"),
        (F.PAGADO, "PAGADO"),
        (F.PROCESADO, "PAGADO"),
        (F.PENDIENTE, "PENDIENTE"),
    ],
)
def test_el_estado_financiero_solo_avanza(
    api: TestClient, sesion: Session, actual: EstadoFinanciero, destino: str
) -> None:
    viatico = _legalizacion_aprobada(sesion, valor_asignado=Decimal("100"))
    viatico.estado_financiero = actual
    sesion.flush()
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _estado(api, viatico, destino, encabezados)

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "TRANSICION_INVALIDA"


def test_pagar_una_solicitud_es_409_rn03(api: TestClient, sesion: Session) -> None:
    viatico = _solicitud_aprobada(
        sesion, estado_financiero=F.TRANSFERIDO, valor_asignado=Decimal("1")
    )
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _estado(api, viatico, "PAGADO", encabezados)

    assert respuesta.status_code == 409
    assert "RN-03" in respuesta.json()["detail"]


def test_pagar_exige_comprobantes_rn03(api: TestClient, sesion: Session) -> None:
    viatico = _legalizacion_aprobada(sesion)
    crear_gasto(sesion, viatico)  # sin soporte ni archivo
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _estado(api, viatico, "PAGADO", encabezados)

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "COMPROBANTE_FALTANTE"


@pytest.mark.parametrize(
    ("valor_asignado", "gastos", "saldo", "sentido"),
    [
        ("100000", ("30000", "20000"), "50000.00", "REINTEGRO"),
        ("100000", ("80000", "40000"), "-20000.00", "REEMBOLSO"),
        ("50000", ("50000",), "0.00", "SIN_SALDO"),
    ],
)
def test_liquidar_registra_el_sentido_del_saldo(
    api: TestClient,
    sesion: Session,
    valor_asignado: str,
    gastos: tuple[str, ...],
    saldo: str,
    sentido: str,
) -> None:
    viatico = _legalizacion_aprobada(
        sesion,
        gastos=gastos,
        valor_asignado=Decimal(valor_asignado),
        estado_financiero=F.TRANSFERIDO,
    )
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _estado(api, viatico, "PAGADO", encabezados, "Liquidación")

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["saldo"] == saldo
    (liquidacion,) = _eventos(sesion, viatico.id, "LIQUIDAR")
    assert liquidacion.dimension == "FINANCIERO"
    assert liquidacion.datos is not None
    assert liquidacion.datos["saldo"] == saldo
    assert liquidacion.datos["sentido"] == sentido
    assert liquidacion.datos["valor_transferido"] == f"{Decimal(valor_asignado):.2f}"


def test_recursos_propios_se_liquida_directo_como_reembolso(
    api: TestClient, sesion: Session
) -> None:
    viatico = _legalizacion_aprobada(sesion, gastos=("70000",), recursos_propios=True)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _estado(api, viatico, "PAGADO", encabezados)

    assert respuesta.status_code == 200, respuesta.text
    (liquidacion,) = _eventos(sesion, viatico.id, "LIQUIDAR")
    assert liquidacion.datos is not None
    assert liquidacion.datos["sentido"] == "REEMBOLSO"
    assert liquidacion.datos["saldo"] == "-70000.00"


def test_procesar_tras_pagar_no_vuelve_a_liquidar(api: TestClient, sesion: Session) -> None:
    viatico = _legalizacion_aprobada(sesion, recursos_propios=True)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    assert _estado(api, viatico, "PAGADO", encabezados).status_code == 200
    procesado = _estado(api, viatico, "PROCESADO", encabezados)

    assert procesado.status_code == 200
    assert procesado.json()["estado_financiero"] == "PROCESADO"
    assert len(_eventos(sesion, viatico.id, "LIQUIDAR")) == 1
    cambios = _eventos(sesion, viatico.id, "CAMBIAR_ESTADO_FINANCIERO")
    assert [(e.estado_anterior, e.estado_nuevo) for e in cambios] == [
        ("PENDIENTE", "PAGADO"),
        ("PAGADO", "PROCESADO"),
    ]
    # Pagado/procesado: ya no se devuelve (RN-20) ni se tocan los gastos.
    assert "devolver" not in procesado.json()["acciones_permitidas"]


def test_procesar_directamente_tambien_liquida(api: TestClient, sesion: Session) -> None:
    viatico = _legalizacion_aprobada(sesion, recursos_propios=True)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _estado(api, viatico, "PROCESADO", encabezados)

    assert respuesta.status_code == 200
    assert len(_eventos(sesion, viatico.id, "LIQUIDAR")) == 1


@pytest.mark.parametrize("rol", [Rol.VIAJERO, Rol.ADMIN])
def test_viajero_y_admin_no_cambian_el_estado_financiero(
    api: TestClient, sesion: Session, rol: Rol
) -> None:
    viatico = _legalizacion_aprobada(sesion, recursos_propios=True)
    _, encabezados = _actor(sesion, rol)

    respuesta = _estado(api, viatico, "PAGADO", encabezados)

    assert respuesta.status_code == 403


def test_financiero_no_liquida_su_propio_viatico(api: TestClient, sesion: Session) -> None:
    financiero, encabezados = _actor(sesion, Rol.FINANCIERO)
    viatico = _legalizacion_aprobada(sesion, dueno=financiero, recursos_propios=True)

    respuesta = _estado(api, viatico, "PAGADO", encabezados)

    assert respuesta.status_code == 403
    assert respuesta.json()["code"] == "AUTOAPROBACION_NO_PERMITIDA"
    sesion.refresh(viatico)
    assert viatico.estado_financiero == "PENDIENTE"
    assert _eventos(sesion, viatico.id, "CAMBIAR_ESTADO_FINANCIERO") == []


def test_superadmin_liquida_su_propio_viatico_con_auditoria(
    api: TestClient, sesion: Session
) -> None:
    superadmin, encabezados = _actor(sesion, Rol.SUPERADMIN)
    viatico = _legalizacion_aprobada(sesion, dueno=superadmin, recursos_propios=True)

    respuesta = _estado(api, viatico, "PAGADO", encabezados)

    assert respuesta.status_code == 200
    (registro,) = _auditoria(sesion, viatico.id)
    assert registro.datos["accion"] == "CAMBIAR_ESTADO_FINANCIERO"


def test_estado_financiero_de_viatico_ajeno_invisible_es_404(
    api: TestClient, sesion: Session
) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = api.post(
        f"{URL}/{uuid.uuid4()}/estado-financiero",
        json={"estado_financiero": "PAGADO"},
        headers=encabezados,
    )

    assert respuesta.status_code == 404


def test_estado_financiero_invalido_es_422(api: TestClient, sesion: Session) -> None:
    viatico = _legalizacion_aprobada(sesion)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _estado(api, viatico, "CANCELADO", encabezados)

    assert respuesta.status_code == 422


def test_flujo_completo_con_solicitud(api: TestClient, sesion: Session) -> None:
    """CON_SOLICITUD de punta a punta sobre el mismo VT-: aprobar, asignar, transferir,
    habilitar, gastos, aprobar la legalización y liquidar (docs/user-flows.md, pasos 1–7)."""
    viajero, enc_viajero = _actor(sesion, Rol.VIAJERO)
    _, enc_admin = _actor(sesion, Rol.ADMIN)
    _, enc_fin = _actor(sesion, Rol.FINANCIERO)
    firma = crear_archivo(
        sesion, created_by=viajero.id, proposito=PropositoArchivo.FIRMA, mime_type="image/png"
    )
    viatico = crear_viatico(
        sesion,
        usuario=viajero,
        modalidad=Modalidad.CON_SOLICITUD,
        requiere_gastos_viaje=True,
        firma_archivo_id=firma.id,
    )
    soporte = crear_archivo(sesion, created_by=viajero.id)
    rubro = crear_rubro(sesion)

    pasos = [
        api.post(f"{URL}/{viatico.id}/aprobar", json={}, headers=enc_admin),
        api.patch(
            f"{URL}/{viatico.id}/valor-asignado",
            json={"valor_asignado": "300000"},
            headers=enc_fin,
        ),
        _estado(api, viatico, "TRANSFERIDO", enc_fin),
        api.post(f"{URL}/{viatico.id}/habilitar-legalizacion", headers=enc_viajero),
        api.post(
            f"{URL}/{viatico.id}/gastos",
            json={
                "fecha_factura": "2026-11-05",
                "rubro_id": str(rubro.id),
                "proyecto_otro": "Proyecto escrito",
                "concepto": "Hotel",
                "valor": "350000",
                "soporte_id": str(soporte.id),
            },
            headers=enc_viajero,
        ),
        api.post(f"{URL}/{viatico.id}/aprobar", json={}, headers=enc_admin),
        _estado(api, viatico, "PAGADO", enc_fin),
    ]

    for paso in pasos:
        assert paso.status_code in (200, 201), paso.text
    final = pasos[-1].json()
    assert (final["etapa"], final["estado"], final["estado_financiero"]) == (
        "LEGALIZACION",
        "APROBADO",
        "PAGADO",
    )
    assert final["folio"] == viatico.folio
    assert final["saldo"] == "-50000.00"
    (liquidacion,) = _eventos(sesion, viatico.id, "LIQUIDAR")
    assert liquidacion.datos is not None and liquidacion.datos["sentido"] == "REEMBOLSO"
    assert liquidacion.etapa == Etapa.LEGALIZACION


@pytest.mark.parametrize(
    ("saldo", "sentido"),
    [(Decimal("1"), "REINTEGRO"), (Decimal("-0.01"), "REEMBOLSO"), (Decimal("0"), "SIN_SALDO")],
)
def test_sentido_liquidacion(saldo: Decimal, sentido: str) -> None:
    assert sentido_liquidacion(saldo) == sentido


# =================================================================================================
# POST /viaticos/{id}/gestionar-tiquetes
# =================================================================================================


@pytest.mark.parametrize("rol", [Rol.ADMIN, Rol.SUPERADMIN])
def test_admin_gestiona_tiquetes(api: TestClient, sesion: Session, rol: Rol) -> None:
    viatico = _solicitud_aprobada(sesion, requiere_tiquete=True)
    admin, encabezados = _actor(sesion, rol)

    respuesta = api.post(
        f"{URL}/{viatico.id}/gestionar-tiquetes",
        json={"comentario": "Emitidos con Avianca", "referencia": "PNR ABC123"},
        headers=encabezados,
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "APROBADO"
    (evento,) = _eventos(sesion, viatico.id, "GESTIONAR_TIQUETES")
    assert evento.usuario_id == admin.id
    assert evento.comentario == "Emitidos con Avianca"
    assert evento.datos == {"referencia": "PNR ABC123"}
    assert evento.estado_anterior is None and evento.estado_nuevo is None


def test_gestionar_tiquetes_sin_comentario_y_repetible(api: TestClient, sesion: Session) -> None:
    viatico = _solicitud_aprobada(sesion, requiere_tiquete=True)
    _, encabezados = _actor(sesion, Rol.ADMIN)

    for _ in range(2):
        respuesta = api.post(f"{URL}/{viatico.id}/gestionar-tiquetes", json={}, headers=encabezados)
        assert respuesta.status_code == 200

    eventos = _eventos(sesion, viatico.id, "GESTIONAR_TIQUETES")
    assert len(eventos) == 2 and eventos[0].datos is None and eventos[0].comentario is None


@pytest.mark.parametrize("rol", [Rol.VIAJERO, Rol.FINANCIERO])
def test_viajero_y_financiero_no_gestionan_tiquetes(
    api: TestClient, sesion: Session, rol: Rol
) -> None:
    viatico = _solicitud_aprobada(sesion, requiere_tiquete=True)
    _, encabezados = _actor(sesion, rol)

    respuesta = api.post(f"{URL}/{viatico.id}/gestionar-tiquetes", json={}, headers=encabezados)

    assert respuesta.status_code == 403


def test_admin_no_gestiona_tiquetes_de_su_propio_viatico(api: TestClient, sesion: Session) -> None:
    admin, encabezados = _actor(sesion, Rol.ADMIN)
    viatico = _solicitud_aprobada(sesion, dueno=admin, requiere_tiquete=True)

    respuesta = api.post(f"{URL}/{viatico.id}/gestionar-tiquetes", json={}, headers=encabezados)

    assert respuesta.status_code == 403
    assert respuesta.json()["code"] == "AUTOAPROBACION_NO_PERMITIDA"


@pytest.mark.parametrize(
    "campos",
    [
        {"requiere_tiquete": False},
        {"requiere_tiquete": True, "estado": E.PENDIENTE},
        {"requiere_tiquete": True, "estado": E.RECHAZADO},
        {
            "requiere_tiquete": True,
            "etapa": Etapa.LEGALIZACION,
            "legalizacion_habilitada_at": datetime.now(UTC),
        },
    ],
)
def test_gestionar_tiquetes_exige_solicitud_aprobada_con_tiquete(
    api: TestClient, sesion: Session, campos: dict[str, Any]
) -> None:
    viatico = _solicitud_aprobada(sesion, **campos)
    _, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(f"{URL}/{viatico.id}/gestionar-tiquetes", json={}, headers=encabezados)

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "TRANSICION_INVALIDA"


def test_gestionar_tiquetes_en_legalizacion_directa_es_409(
    api: TestClient, sesion: Session
) -> None:
    viatico = _legalizacion_aprobada(sesion)
    _, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = api.post(f"{URL}/{viatico.id}/gestionar-tiquetes", json={}, headers=encabezados)

    assert respuesta.status_code == 409
