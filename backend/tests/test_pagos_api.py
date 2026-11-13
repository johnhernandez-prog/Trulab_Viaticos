"""Bandeja de tesorería `/pagos` y `/pagos/resumen` (S2-09, docs/api-design.md §5.6).

Las pruebas con cifras exactas filtran por `usuario_id` del viajero de la prueba: la BD local
puede tener viáticos reales commiteados por pruebas manuales y no deben contaminar las sumas.
"""

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import EstadoFinanciero, EstadoOperativo, Etapa, Modalidad, Rol
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.models import Viatico
from tests.fabricas import (
    bearer,
    crear_gasto,
    crear_proyecto,
    crear_usuario,
    crear_viatico,
)

URL = "/api/v1/pagos"
RESUMEN = "/api/v1/pagos/resumen"
E, F = EstadoOperativo, EstadoFinanciero


def _actor(sesion: Session, rol: Rol, **campos: Any) -> tuple[Usuario, dict[str, str]]:
    usuario = crear_usuario(sesion, rol=rol, **campos)
    return usuario, bearer(sesion, usuario)


def _solicitud(sesion: Session, dueno: Usuario, **campos: Any) -> Viatico:
    valores: dict[str, Any] = {
        "estado": E.APROBADO,
        "requiere_gastos_viaje": True,
        "presupuesto_solicitado": Decimal("120000"),
    }
    valores.update(campos)
    return crear_viatico(sesion, usuario=dueno, modalidad=Modalidad.CON_SOLICITUD, **valores)


def _legalizacion(
    sesion: Session, dueno: Usuario, gastos: tuple[str, ...] = ("50000",), **campos: Any
) -> Viatico:
    valores: dict[str, Any] = {"estado": E.APROBADO}
    valores.update(campos)
    viatico = crear_viatico(sesion, usuario=dueno, **valores)
    for valor in gastos:
        crear_gasto(sesion, viatico, valor=Decimal(valor))
    return viatico


def _ids(respuesta: Any) -> set[str]:
    return {fila["id"] for fila in respuesta.json()["items"]}


def _listar(api: TestClient, encabezados: dict[str, str], **params: Any) -> Any:
    return api.get(URL, params=params, headers=encabezados)


@pytest.fixture
def escenario(sesion: Session) -> dict[str, Any]:
    """Un viajero con un viático de cada tipo; unos entran a la bandeja y otros no."""
    dueno = crear_usuario(sesion, nombre_completo="Ana Viajera Prueba")
    v: dict[str, Viatico] = {
        # --- entran ---
        "sol_pendiente": _solicitud(sesion, dueno),
        "sol_transferida": _solicitud(
            sesion, dueno, estado_financiero=F.TRANSFERIDO, valor_asignado=Decimal("100000")
        ),
        "leg_pendiente": _legalizacion(sesion, dueno),
        "leg_transferida": _legalizacion(
            sesion, dueno, estado_financiero=F.TRANSFERIDO, valor_asignado=Decimal("80000")
        ),
        "leg_pagada": _legalizacion(sesion, dueno, estado_financiero=F.PAGADO),
        "leg_procesada": _legalizacion(sesion, dueno, estado_financiero=F.PROCESADO),
        # --- no entran ---
        "sol_sin_gastos_de_viaje": _solicitud(sesion, dueno, requiere_gastos_viaje=False),
        "sol_pendiente_de_aprobar": _solicitud(sesion, dueno, estado=E.PENDIENTE),
        "sol_rechazada": _solicitud(sesion, dueno, estado=E.RECHAZADO),
        "leg_sin_aprobar": _legalizacion(sesion, dueno, estado=E.PENDIENTE),
        "leg_rechazada": _legalizacion(sesion, dueno, estado=E.RECHAZADO),
        "leg_eliminada": _legalizacion(sesion, dueno, deleted_at=datetime.now(UTC)),
    }
    return {"dueno": dueno, **v}


ENTRAN = {
    "sol_pendiente",
    "sol_transferida",
    "leg_pendiente",
    "leg_transferida",
    "leg_pagada",
    "leg_procesada",
}


# =================================================================================================
# permisos (matriz: pagos:leer = F A S; ADMIN solo lectura, DP-18; VIAJERO no)
# =================================================================================================


@pytest.mark.parametrize("url", [URL, RESUMEN])
def test_el_viajero_no_entra_a_pagos(api: TestClient, sesion: Session, url: str) -> None:
    _, encabezados = _actor(sesion, Rol.VIAJERO)

    respuesta = api.get(url, headers=encabezados)

    assert respuesta.status_code == 403
    assert respuesta.json()["code"] == "SIN_PERMISO"


@pytest.mark.parametrize("url", [URL, RESUMEN])
def test_pagos_sin_sesion_es_401(api: TestClient, url: str) -> None:
    assert api.get(url).status_code == 401


@pytest.mark.parametrize("rol", [Rol.FINANCIERO, Rol.ADMIN, Rol.SUPERADMIN])
@pytest.mark.parametrize("url", [URL, RESUMEN])
def test_financiero_admin_y_superadmin_leen_pagos(
    api: TestClient, sesion: Session, rol: Rol, url: str
) -> None:
    _, encabezados = _actor(sesion, rol)

    assert api.get(url, headers=encabezados).status_code == 200


def test_admin_ve_la_bandeja_en_solo_lectura(
    api: TestClient, sesion: Session, escenario: dict[str, Any]
) -> None:
    """DP-18/RN-26: ADMIN consulta pero no dispone de ninguna acción de tesorería."""
    _, encabezados = _actor(sesion, Rol.ADMIN)

    respuesta = _listar(api, encabezados, usuario_id=str(escenario["dueno"].id))

    assert respuesta.status_code == 200 and respuesta.json()["total"] == len(ENTRAN)
    for fila in respuesta.json()["items"]:
        assert fila["acciones_permitidas"] == [] and fila["destinos_financieros"] == []


# =================================================================================================
# qué entra en la bandeja
# =================================================================================================


def test_solo_entran_los_viaticos_relevantes_para_tesoreria(
    api: TestClient, sesion: Session, escenario: dict[str, Any]
) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _listar(api, encabezados, usuario_id=str(escenario["dueno"].id), size=100)

    assert respuesta.status_code == 200
    assert _ids(respuesta) == {str(escenario[n].id) for n in ENTRAN}
    assert respuesta.json()["total"] == len(ENTRAN)


@pytest.mark.parametrize(
    ("bandeja", "esperados"),
    [
        ("pendientes_desembolso", {"sol_pendiente"}),
        ("pendientes_liquidacion", {"leg_pendiente", "leg_transferida"}),
        ("historico", {"sol_transferida", "leg_pagada", "leg_procesada"}),
        ("todos", ENTRAN),
    ],
)
def test_bandejas(
    api: TestClient,
    sesion: Session,
    escenario: dict[str, Any],
    bandeja: str,
    esperados: set[str],
) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _listar(
        api, encabezados, usuario_id=str(escenario["dueno"].id), bandeja=bandeja, size=100
    )

    assert respuesta.status_code == 200
    assert _ids(respuesta) == {str(escenario[n].id) for n in esperados}
    for fila in respuesta.json()["items"]:
        if bandeja != "todos":
            assert fila["bandeja"] == bandeja


def test_cada_fila_dice_en_que_bandeja_esta(
    api: TestClient, sesion: Session, escenario: dict[str, Any]
) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    filas = {
        f["id"]: f["bandeja"]
        for f in _listar(api, encabezados, usuario_id=str(escenario["dueno"].id)).json()["items"]
    }

    assert filas[str(escenario["sol_pendiente"].id)] == "pendientes_desembolso"
    assert filas[str(escenario["leg_transferida"].id)] == "pendientes_liquidacion"
    assert filas[str(escenario["leg_pagada"].id)] == "historico"
    assert filas[str(escenario["sol_transferida"].id)] == "historico"


def test_bandeja_invalida_es_422(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    assert _listar(api, encabezados, bandeja="otra").status_code == 422


def test_el_viaticos_eliminado_o_rechazado_nunca_aparece(
    api: TestClient, sesion: Session, escenario: dict[str, Any]
) -> None:
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)

    ids = _ids(_listar(api, encabezados, usuario_id=str(escenario["dueno"].id), size=100))

    for excluido in ("leg_eliminada", "leg_rechazada", "sol_rechazada", "sol_sin_gastos_de_viaje"):
        assert str(escenario[excluido].id) not in ids


# =================================================================================================
# filtros
# =================================================================================================


def test_filtro_estado_financiero(
    api: TestClient, sesion: Session, escenario: dict[str, Any]
) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _listar(
        api,
        encabezados,
        usuario_id=str(escenario["dueno"].id),
        estado_financiero="TRANSFERIDO",
    )

    assert _ids(respuesta) == {
        str(escenario["sol_transferida"].id),
        str(escenario["leg_transferida"].id),
    }


def test_filtro_por_usuario_y_busqueda_por_viajero_y_folio(
    api: TestClient, sesion: Session, escenario: dict[str, Any]
) -> None:
    otro = crear_usuario(sesion, nombre_completo="Zacarías Otro Distinto")
    ajeno = _legalizacion(sesion, otro, colaborador_nombre="Zacarías Otro Distinto")
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    por_usuario = _listar(api, encabezados, usuario_id=str(otro.id))
    por_nombre = _listar(api, encabezados, q="Zacarías Otro")
    por_folio = _listar(api, encabezados, q=ajeno.folio)

    assert _ids(por_usuario) == {str(ajeno.id)}
    assert str(ajeno.id) in _ids(por_nombre)
    assert _ids(por_folio) == {str(ajeno.id)}


def test_filtro_por_proyecto_de_la_solicitud_y_de_los_gastos(
    api: TestClient, sesion: Session
) -> None:
    dueno = crear_usuario(sesion)
    proyecto = crear_proyecto(sesion)
    en_solicitud = _solicitud(sesion, dueno, proyecto_otro=None, proyecto_id=proyecto.id)
    en_gasto = _legalizacion(sesion, dueno, gastos=())
    crear_gasto(sesion, en_gasto, proyecto_otro=None, proyecto_id=proyecto.id)
    con_otro = _legalizacion(sesion, dueno)  # el gasto trae un "Otro": S-15, no entra
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _listar(api, encabezados, proyecto_id=str(proyecto.id))

    assert _ids(respuesta) == {str(en_solicitud.id), str(en_gasto.id)}
    assert str(con_otro.id) not in _ids(respuesta)


def test_filtro_por_fechas_usa_la_fecha_del_registro(api: TestClient, sesion: Session) -> None:
    dueno = crear_usuario(sesion)
    octubre = _legalizacion(sesion, dueno, fecha_legalizacion=date(2026, 10, 15))
    noviembre = _legalizacion(sesion, dueno, fecha_legalizacion=date(2026, 11, 15))
    _, encabezados = _actor(sesion, Rol.FINANCIERO)
    base = {"usuario_id": str(dueno.id)}

    assert _ids(_listar(api, encabezados, desde="2026-11-01", **base)) == {str(noviembre.id)}
    assert _ids(_listar(api, encabezados, hasta="2026-10-31", **base)) == {str(octubre.id)}
    assert _ids(_listar(api, encabezados, desde="2026-10-15", hasta="2026-11-15", **base)) == {
        str(octubre.id),
        str(noviembre.id),
    }
    assert _listar(api, encabezados, desde="2026-12-01", hasta="2026-11-01").status_code == 422


# =================================================================================================
# contenido de cada fila
# =================================================================================================


@pytest.mark.parametrize(
    ("valor_asignado", "gastos", "saldo", "tipo"),
    [
        ("1000000", ("400000", "100000"), "500000.00", "REINTEGRO"),
        ("100000", ("150000",), "-50000.00", "REEMBOLSO"),
        ("300000", ("300000",), "0.00", "SALDADO"),
    ],
)
def test_resumen_financiero_de_una_legalizacion(
    api: TestClient,
    sesion: Session,
    valor_asignado: str,
    gastos: tuple[str, ...],
    saldo: str,
    tipo: str,
) -> None:
    dueno = crear_usuario(sesion)
    viatico = _legalizacion(
        sesion,
        dueno,
        gastos=gastos,
        valor_asignado=Decimal(valor_asignado),
        estado_financiero=F.TRANSFERIDO,
    )
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    (fila,) = _listar(api, encabezados, usuario_id=str(dueno.id)).json()["items"]

    assert fila["id"] == str(viatico.id) and fila["folio"] == viatico.folio
    assert fila["valor_asignado"] == f"{Decimal(valor_asignado):.2f}"
    assert fila["valor_transferido"] == f"{Decimal(valor_asignado):.2f}"
    assert fila["total_gastos"] == f"{sum(Decimal(g) for g in gastos):.2f}"
    assert fila["saldo"] == saldo and fila["tipo_liquidacion"] == tipo
    assert fila["presupuesto_solicitado"] is None
    assert fila["usuario"] == {"id": str(dueno.id), "nombre": dueno.nombre_completo}
    assert (fila["modalidad"], fila["etapa"], fila["estado"]) == (
        "LEGALIZACION_DIRECTA",
        "LEGALIZACION",
        "APROBADO",
    )


def test_recursos_propios_es_reembolso_con_transferido_cero(
    api: TestClient, sesion: Session
) -> None:
    dueno = crear_usuario(sesion)
    _legalizacion(sesion, dueno, gastos=("70000",), recursos_propios=True)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    (fila,) = _listar(api, encabezados, usuario_id=str(dueno.id)).json()["items"]

    assert fila["recursos_propios"] is True and fila["valor_transferido"] == "0.00"
    assert fila["saldo"] == "-70000.00" and fila["tipo_liquidacion"] == "REEMBOLSO"


def test_una_solicitud_no_tiene_saldo_ni_tipo_de_liquidacion(
    api: TestClient, sesion: Session
) -> None:
    dueno = crear_usuario(sesion)
    _solicitud(sesion, dueno, valor_asignado=Decimal("100000"), estado_financiero=F.TRANSFERIDO)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    (fila,) = _listar(api, encabezados, usuario_id=str(dueno.id)).json()["items"]

    assert fila["etapa"] == "SOLICITUD" and fila["modalidad"] == "CON_SOLICITUD"
    assert fila["saldo"] is None and fila["tipo_liquidacion"] is None
    assert fila["presupuesto_solicitado"] == "120000.00"
    assert fila["valor_transferido"] == "100000.00"


# --- acciones de tesorería -----------------------------------------------------------------------


def test_acciones_de_tesoreria_de_una_solicitud(api: TestClient, sesion: Session) -> None:
    dueno = crear_usuario(sesion)
    sin_valor = _solicitud(sesion, dueno)
    con_valor = _solicitud(sesion, dueno, valor_asignado=Decimal("90000"))
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    filas = {
        f["id"]: f for f in _listar(api, encabezados, usuario_id=str(dueno.id)).json()["items"]
    }

    assert filas[str(sin_valor.id)]["acciones_permitidas"] == ["registrar_valor_asignado"]
    assert filas[str(sin_valor.id)]["destinos_financieros"] == []
    assert filas[str(con_valor.id)]["acciones_permitidas"] == [
        "registrar_valor_asignado",
        "cambiar_estado_financiero",
    ]
    assert filas[str(con_valor.id)]["destinos_financieros"] == ["TRANSFERIDO"]


def test_acciones_de_tesoreria_de_una_legalizacion(api: TestClient, sesion: Session) -> None:
    dueno = crear_usuario(sesion)
    _legalizacion(sesion, dueno, recursos_propios=True)
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)

    (fila,) = _listar(api, encabezados, usuario_id=str(dueno.id)).json()["items"]

    # Recursos propios: no hay valor asignado ni desembolso; solo liquidar.
    assert fila["acciones_permitidas"] == ["cambiar_estado_financiero"]
    assert fila["destinos_financieros"] == ["PAGADO", "PROCESADO"]


def test_financiero_no_tiene_acciones_sobre_su_propio_viatico(
    api: TestClient, sesion: Session
) -> None:
    """RN-27: ve su propio viático en la bandeja pero no puede operarlo."""
    financiero, encabezados = _actor(sesion, Rol.FINANCIERO)
    _legalizacion(sesion, financiero, recursos_propios=True)

    (fila,) = _listar(api, encabezados, usuario_id=str(financiero.id)).json()["items"]

    assert fila["acciones_permitidas"] == [] and fila["destinos_financieros"] == []


def test_las_acciones_de_la_bandeja_no_incluyen_las_del_viajero_ni_las_del_admin(
    api: TestClient, sesion: Session
) -> None:
    dueno = crear_usuario(sesion)
    _legalizacion(sesion, dueno, estado=E.APROBADO)
    _, encabezados = _actor(sesion, Rol.SUPERADMIN)

    (fila,) = _listar(api, encabezados, usuario_id=str(dueno.id)).json()["items"]

    permitidas = {"registrar_valor_asignado", "cambiar_estado_financiero"}
    assert set(fila["acciones_permitidas"]) <= permitidas


# --- paginación y orden --------------------------------------------------------------------------


def test_paginacion(api: TestClient, sesion: Session) -> None:
    dueno = crear_usuario(sesion)
    for _ in range(5):
        _legalizacion(sesion, dueno)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)
    base = {"usuario_id": str(dueno.id), "size": 2}

    primera = _listar(api, encabezados, page=1, **base).json()
    ultima = _listar(api, encabezados, page=3, **base).json()
    vacia = _listar(api, encabezados, page=4, **base).json()

    assert (primera["total"], primera["page"], primera["size"]) == (5, 1, 2)
    assert len(primera["items"]) == 2 and len(ultima["items"]) == 1 and vacia["items"] == []
    assert _ids_de(primera).isdisjoint(_ids_de(ultima))
    assert _listar(api, encabezados, size=101).status_code == 422
    assert _listar(api, encabezados, page=0).status_code == 422


def _ids_de(pagina: dict[str, Any]) -> set[str]:
    return {f["id"] for f in pagina["items"]}


@pytest.mark.parametrize(
    ("orden", "esperado"),
    [("saldo", [-50000, 0, 500000]), ("-saldo", [500000, 0, -50000])],
)
def test_orden_por_saldo(api: TestClient, sesion: Session, orden: str, esperado: list[int]) -> None:
    dueno = crear_usuario(sesion)
    for asignado, gasto in (("1000000", "500000"), ("100000", "150000"), ("300000", "300000")):
        _legalizacion(
            sesion,
            dueno,
            gastos=(gasto,),
            valor_asignado=Decimal(asignado),
            estado_financiero=F.TRANSFERIDO,
        )
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    items = _listar(api, encabezados, usuario_id=str(dueno.id), sort=orden).json()["items"]

    assert [int(Decimal(f["saldo"])) for f in items] == esperado


def test_orden_invalido_es_422(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    assert _listar(api, encabezados, sort="valor_asignado").status_code == 422


# =================================================================================================
# GET /pagos/resumen
# =================================================================================================


@pytest.fixture
def escenario_resumen(sesion: Session) -> Usuario:
    dueno = crear_usuario(sesion)
    # Solicitudes aprobadas con gastos de viaje.
    _solicitud(
        sesion, dueno, valor_asignado=Decimal("100000"), presupuesto_solicitado=Decimal("120000")
    )
    _solicitud(sesion, dueno, valor_asignado=Decimal("0"), presupuesto_solicitado=Decimal("80000"))
    _solicitud(
        sesion,
        dueno,
        estado_financiero=F.TRANSFERIDO,
        valor_asignado=Decimal("500000"),
        presupuesto_solicitado=Decimal("450000"),
    )
    # Legalizaciones aprobadas.
    _legalizacion(  # L1: reintegro de 500.000
        sesion,
        dueno,
        gastos=("400000", "100000"),
        valor_asignado=Decimal("1000000"),
        estado_financiero=F.TRANSFERIDO,
    )
    _legalizacion(sesion, dueno, gastos=("70000",), recursos_propios=True)  # L2: reembolso 70.000
    _legalizacion(  # L3: saldada y pagada
        sesion,
        dueno,
        gastos=("300000",),
        valor_asignado=Decimal("300000"),
        estado_financiero=F.PAGADO,
    )
    _legalizacion(  # L4: reembolso 50.000
        sesion,
        dueno,
        gastos=("150000",),
        valor_asignado=Decimal("100000"),
        estado_financiero=F.TRANSFERIDO,
    )
    # L5: sin aprobar, pero el dinero ya salió.
    _legalizacion(
        sesion,
        dueno,
        estado=E.PENDIENTE,
        gastos=("10000",),
        valor_asignado=Decimal("200000"),
        estado_financiero=F.TRANSFERIDO,
    )
    return dueno


def test_resumen_con_cifras_exactas(
    api: TestClient, sesion: Session, escenario_resumen: Usuario
) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = api.get(
        RESUMEN, params={"usuario_id": str(escenario_resumen.id)}, headers=encabezados
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json() == {
        "pendientes_desembolso": {
            "cantidad": 2,
            "monto_asignado": "100000.00",
            "monto_presupuestado": "200000.00",
        },
        "pendientes_liquidacion": {
            "cantidad": 3,  # L1, L2, L4
            "monto_gastos": "720000.00",
            "monto_transferido": "1100000.00",
        },
        # S3 500.000 + L1 1.000.000 + L3 300.000 + L4 100.000 + L5 200.000 (L2 no transfirió nada)
        "total_transferido": "2100000.00",
        # Solo legalizaciones aprobadas: 500.000 + 70.000 + 300.000 + 150.000
        "total_legalizado": "1020000.00",
        "reintegros_pendientes": {"cantidad": 1, "monto": "500000.00"},
        "reembolsos_pendientes": {"cantidad": 2, "monto": "120000.00"},
    }


def test_resumen_sin_datos_devuelve_ceros_con_dos_decimales(
    api: TestClient, sesion: Session
) -> None:
    vacio = crear_usuario(sesion)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    cuerpo = api.get(RESUMEN, params={"usuario_id": str(vacio.id)}, headers=encabezados).json()

    assert cuerpo == {
        "pendientes_desembolso": {
            "cantidad": 0,
            "monto_asignado": "0.00",
            "monto_presupuestado": "0.00",
        },
        "pendientes_liquidacion": {
            "cantidad": 0,
            "monto_gastos": "0.00",
            "monto_transferido": "0.00",
        },
        "total_transferido": "0.00",
        "total_legalizado": "0.00",
        "reintegros_pendientes": {"cantidad": 0, "monto": "0.00"},
        "reembolsos_pendientes": {"cantidad": 0, "monto": "0.00"},
    }


def test_resumen_respeta_los_filtros_de_fecha_y_usuario(api: TestClient, sesion: Session) -> None:
    dueno = crear_usuario(sesion)
    _legalizacion(
        sesion,
        dueno,
        gastos=("100000",),
        valor_asignado=Decimal("300000"),
        estado_financiero=F.TRANSFERIDO,
        fecha_legalizacion=date(2026, 10, 10),
    )
    _legalizacion(
        sesion,
        dueno,
        gastos=("40000",),
        valor_asignado=Decimal("0"),
        fecha_legalizacion=date(2026, 11, 10),
    )
    otro = crear_usuario(sesion)
    _legalizacion(sesion, otro, gastos=("999",), fecha_legalizacion=date(2026, 11, 10))
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    octubre = api.get(
        RESUMEN,
        params={"usuario_id": str(dueno.id), "hasta": "2026-10-31"},
        headers=encabezados,
    ).json()
    noviembre = api.get(
        RESUMEN,
        params={"usuario_id": str(dueno.id), "desde": "2026-11-01"},
        headers=encabezados,
    ).json()

    assert octubre["total_transferido"] == "300000.00"
    assert octubre["reintegros_pendientes"] == {"cantidad": 1, "monto": "200000.00"}
    assert noviembre["total_transferido"] == "0.00"
    assert noviembre["reembolsos_pendientes"] == {"cantidad": 1, "monto": "40000.00"}
    assert (
        api.get(RESUMEN, params={"desde": "2026-12-01", "hasta": "2026-11-01"}, headers=encabezados)
    ).status_code == 422


def test_resumen_filtra_por_proyecto(api: TestClient, sesion: Session) -> None:
    dueno = crear_usuario(sesion)
    proyecto = crear_proyecto(sesion)
    de_proyecto = _legalizacion(sesion, dueno, gastos=(), recursos_propios=True)
    crear_gasto(
        sesion, de_proyecto, valor=Decimal("25000"), proyecto_otro=None, proyecto_id=proyecto.id
    )
    _legalizacion(sesion, dueno, gastos=("77000",), recursos_propios=True)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    cuerpo = api.get(
        RESUMEN,
        params={"usuario_id": str(dueno.id), "proyecto_id": str(proyecto.id)},
        headers=encabezados,
    ).json()

    assert cuerpo["reembolsos_pendientes"] == {"cantidad": 1, "monto": "25000.00"}


def test_resumen_es_consistente_con_la_bandeja(
    api: TestClient, sesion: Session, escenario_resumen: Usuario
) -> None:
    """El conteo de pendientes del resumen coincide con las bandejas del listado."""
    _, encabezados = _actor(sesion, Rol.FINANCIERO)
    filtro = {"usuario_id": str(escenario_resumen.id)}

    resumen = api.get(RESUMEN, params=filtro, headers=encabezados).json()
    desembolso = _listar(api, encabezados, bandeja="pendientes_desembolso", **filtro).json()
    liquidacion = _listar(api, encabezados, bandeja="pendientes_liquidacion", **filtro).json()

    assert resumen["pendientes_desembolso"]["cantidad"] == desembolso["total"]
    assert resumen["pendientes_liquidacion"]["cantidad"] == liquidacion["total"]
    assert sum(Decimal(f["total_gastos"]) for f in liquidacion["items"]) == Decimal(
        resumen["pendientes_liquidacion"]["monto_gastos"]
    )


def test_el_id_inexistente_como_usuario_no_falla(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = api.get(RESUMEN, params={"usuario_id": str(uuid.uuid4())}, headers=encabezados)

    assert respuesta.status_code == 200
    assert respuesta.json()["total_transferido"] == "0.00"


def test_la_vinculacion_de_sentido_es_la_misma_que_en_la_liquidacion() -> None:
    """Un solo vocabulario: `SALDADO` en `/pagos` y en el evento `LIQUIDAR`."""
    from app.core.enums import TipoLiquidacion
    from app.modules.viaticos.service import sentido_liquidacion

    assert sentido_liquidacion(Decimal("1")) == TipoLiquidacion.REINTEGRO
    assert sentido_liquidacion(Decimal("-1")) == TipoLiquidacion.REEMBOLSO
    assert sentido_liquidacion(Decimal("0")) == TipoLiquidacion.SALDADO == "SALDADO"
    assert Etapa.LEGALIZACION == "LEGALIZACION"
