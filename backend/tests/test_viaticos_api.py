"""API de `/viaticos` (S2-04a, docs/api-design.md §5.4): cálculo tarifario, creación en ambas
modalidades (ADR-029) y lectura individual. La máquina de estados llega en S2-05.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Rol
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.models import Viatico, ViaticoEvento
from tests.fabricas import bearer, crear_proyecto, crear_usuario

URL_CALCULO = "/api/v1/viaticos/calcular-presupuesto"
URL = "/api/v1/viaticos"

IDA = datetime(2026, 12, 1, 8, tzinfo=UTC)


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
        "fecha_regreso": (IDA + timedelta(days=2)).isoformat(),
        "requiere_hospedaje": True,
        "dias_estadia": 3,
    }
    valores.update(campos)
    return valores


# =================================================================================================
# POST /viaticos/calcular-presupuesto
# =================================================================================================


@pytest.mark.parametrize("rol", list(Rol))
def test_calcular_presupuesto_permisos(api: TestClient, sesion: Session, rol: Rol) -> None:
    _, encabezados = _actor(sesion, rol)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL_CALCULO,
        json={
            "proyecto_id": str(proyecto.id),
            "requiere_gastos_viaje": True,
            "trayectos": [_trayecto()],
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 200


def test_calcular_presupuesto_sin_token(api: TestClient) -> None:
    assert api.post(URL_CALCULO, json={}).status_code == 401


def test_calcular_presupuesto_empleado(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, es_prestador_servicios=False)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL_CALCULO,
        json={
            "proyecto_id": str(proyecto.id),
            "requiere_gastos_viaje": True,
            "trayectos": [_trayecto(ciudad_destino="Cali", dias_estadia=1)],
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["aplica"] is True
    (trayecto,) = cuerpo["trayectos"]
    # Tarifa oficial de Cali-empleado (seed): alimentación 75000, trans_interno_dia_1 60000.
    assert trayecto["vr_alimentacion"] == "75000.00"
    assert Decimal(cuerpo["presupuesto_solicitado"]) > 0


def test_calcular_presupuesto_empleado_y_prestador_difieren(
    api: TestClient, sesion: Session
) -> None:
    _, enc_empleado = _actor(sesion, es_prestador_servicios=False)
    _, enc_prestador = _actor(sesion, es_prestador_servicios=True)
    proyecto = crear_proyecto(sesion)
    cuerpo_base = {
        "proyecto_id": str(proyecto.id),
        "requiere_gastos_viaje": True,
        "trayectos": [_trayecto(ciudad_destino="Cali", dias_estadia=1)],
    }

    empleado = api.post(URL_CALCULO, json=cuerpo_base, headers=enc_empleado).json()
    prestador = api.post(URL_CALCULO, json=cuerpo_base, headers=enc_prestador).json()

    assert empleado["presupuesto_solicitado"] != prestador["presupuesto_solicitado"]


def test_calcular_presupuesto_sin_gastos_de_viaje(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL_CALCULO,
        json={
            "proyecto_id": str(proyecto.id),
            "requiere_gastos_viaje": False,
            "trayectos": [_trayecto()],
        },
        headers=encabezados,
    )

    cuerpo = respuesta.json()
    assert cuerpo["aplica"] is False
    assert cuerpo["motivo_no_aplica"] == "SIN_GASTOS_VIAJE"
    assert cuerpo["presupuesto_solicitado"] is None


def test_calcular_presupuesto_prestador_con_formato_no_calcula(
    api: TestClient, sesion: Session
) -> None:
    _, encabezados = _actor(sesion, es_prestador_servicios=True)
    proyecto = crear_proyecto(sesion, exige_formato_prestador=True)

    respuesta = api.post(
        URL_CALCULO,
        json={
            "proyecto_id": str(proyecto.id),
            "requiere_gastos_viaje": True,
            "trayectos": [_trayecto()],
        },
        headers=encabezados,
    )

    cuerpo = respuesta.json()
    assert cuerpo["aplica"] is False
    assert cuerpo["motivo_no_aplica"] == "FORMATO_PRESTADOR"
    assert cuerpo["exige_formato_prestador"] is True


def test_calcular_presupuesto_proyecto_requerido(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(
        URL_CALCULO,
        json={"requiere_gastos_viaje": True, "trayectos": [_trayecto()]},
        headers=encabezados,
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "PROYECTO_REQUERIDO"


def test_calcular_presupuesto_proyecto_ambiguo(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL_CALCULO,
        json={
            "proyecto_id": str(proyecto.id),
            "proyecto_otro": "Otro proyecto cualquiera",
            "requiere_gastos_viaje": True,
            "trayectos": [_trayecto()],
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "PROYECTO_AMBIGUO"


def test_calcular_presupuesto_proyecto_otro_nunca_exige_formato(
    api: TestClient, sesion: Session
) -> None:
    _, encabezados = _actor(sesion, es_prestador_servicios=True)

    respuesta = api.post(
        URL_CALCULO,
        json={
            "proyecto_otro": "Proyecto externo",
            "requiere_gastos_viaje": True,
            "trayectos": [_trayecto(ciudad_destino="Cali", dias_estadia=1)],
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["aplica"] is True


@pytest.mark.parametrize(
    "trayectos",
    [
        [],
        [_trayecto(orden=i) for i in range(1, 7)],
    ],
)
def test_calcular_presupuesto_rechaza_cantidad_de_trayectos(
    api: TestClient, sesion: Session, trayectos: list[dict[str, object]]
) -> None:
    _, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL_CALCULO,
        json={
            "proyecto_id": str(proyecto.id),
            "requiere_gastos_viaje": True,
            "trayectos": trayectos,
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 422


def test_calcular_presupuesto_destino_igual_al_origen(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL_CALCULO,
        json={
            "proyecto_id": str(proyecto.id),
            "requiere_gastos_viaje": True,
            "trayectos": [_trayecto(ciudad_origen="Cali", ciudad_destino="Cali")],
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "TRAYECTOS_INVALIDOS"


def test_calcular_presupuesto_regreso_antes_de_la_ida(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL_CALCULO,
        json={
            "proyecto_id": str(proyecto.id),
            "requiere_gastos_viaje": True,
            "trayectos": [
                _trayecto(
                    fecha_ida=IDA.isoformat(), fecha_regreso=(IDA - timedelta(days=1)).isoformat()
                )
            ],
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "TRAYECTOS_INVALIDOS"


def test_calcular_presupuesto_ciudad_sin_tarifa(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL_CALCULO,
        json={
            "proyecto_id": str(proyecto.id),
            "requiere_gastos_viaje": True,
            "trayectos": [_trayecto(ciudad_destino="Ciudad Inexistente XYZ")],
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALOR_NO_PERMITIDO"


def test_calcular_presupuesto_rechaza_importes_del_cliente(
    api: TestClient, sesion: Session
) -> None:
    # RN-29: el cliente nunca envía tarifas ni totales; `extra="forbid"` lo rechaza.
    _, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL_CALCULO,
        json={
            "proyecto_id": str(proyecto.id),
            "requiere_gastos_viaje": True,
            "trayectos": [_trayecto()],
            "presupuesto_solicitado": "999999.00",
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALIDACION"


# =================================================================================================
# POST /viaticos (CON_SOLICITUD)
# =================================================================================================


def _cuerpo_con_solicitud(proyecto_id: uuid.UUID | str, **campos: object) -> dict[str, object]:
    cuerpo: dict[str, object] = {
        "modalidad": "CON_SOLICITUD",
        "motivo_viaje": "Taller de campo con el equipo",
        "proyecto_id": str(proyecto_id),
        "lider_proyecto": "María Gómez",
        "requiere_tiquete": False,
        "requiere_gastos_viaje": True,
        "trayectos": [_trayecto()],
    }
    cuerpo.update(campos)
    return cuerpo


@pytest.mark.parametrize("rol", list(Rol))
def test_crear_permisos(api: TestClient, sesion: Session, rol: Rol) -> None:
    _, encabezados = _actor(sesion, rol)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(URL, json=_cuerpo_con_solicitud(proyecto.id), headers=encabezados)

    assert respuesta.status_code == 201


def test_crear_sin_token(api: TestClient) -> None:
    assert api.post(URL, json={}).status_code == 401


def test_crear_con_solicitud(api: TestClient, sesion: Session) -> None:
    actor, encabezados = _actor(sesion, cargo_id=None, celula_id=None)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL,
        json=_cuerpo_con_solicitud(
            proyecto.id, trayectos=[_trayecto(ciudad_destino="Cali", dias_estadia=1)]
        ),
        headers=encabezados,
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["folio"].startswith("VT-")
    assert cuerpo["modalidad"] == "CON_SOLICITUD"
    assert cuerpo["etapa"] == "SOLICITUD"
    assert cuerpo["estado"] == "PENDIENTE"
    assert cuerpo["estado_financiero"] == "PENDIENTE"
    assert cuerpo["recursos_propios"] is False
    assert respuesta.headers["location"] == f"{URL}/{cuerpo['id']}"
    assert cuerpo["solicitud"]["proyecto"] == {
        "id": str(proyecto.id),
        "nombre": proyecto.nombre,
        "en_catalogo": True,
    }
    assert Decimal(cuerpo["solicitud"]["presupuesto_solicitado"]) > 0
    assert cuerpo["colaborador"]["nombre"] == actor.nombre_completo
    assert cuerpo["colaborador"]["es_prestador_servicios"] == actor.es_prestador_servicios
    assert len(cuerpo["eventos"]) == 1
    assert cuerpo["eventos"][0]["accion"] == "CREAR"

    viatico = sesion.get(Viatico, uuid.UUID(cuerpo["id"]))
    assert viatico is not None and viatico.usuario_id == actor.id
    eventos = sesion.scalars(
        select(ViaticoEvento).where(ViaticoEvento.viatico_id == viatico.id)
    ).all()
    assert len(eventos) == 1 and eventos[0].usuario_id == actor.id


def test_crear_con_solicitud_con_proyecto_otro(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(
        URL,
        json={
            "modalidad": "CON_SOLICITUD",
            "motivo_viaje": "Visita a un cliente nuevo",
            "proyecto_otro": "Proyecto externo sin catálogo",
            "lider_proyecto": "Juan Pérez",
            "requiere_gastos_viaje": True,
            "trayectos": [_trayecto(ciudad_destino="Cali", dias_estadia=1)],
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["solicitud"]["proyecto"] == {
        "id": None,
        "nombre": "Proyecto externo sin catálogo",
        "en_catalogo": False,
    }


def test_crear_con_solicitud_proyecto_requerido(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(
        URL,
        json={
            "modalidad": "CON_SOLICITUD",
            "motivo_viaje": "Taller de campo",
            "lider_proyecto": "María Gómez",
            "requiere_gastos_viaje": True,
            "trayectos": [_trayecto()],
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "PROYECTO_REQUERIDO"


def test_crear_con_solicitud_proyecto_inactivo(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion, activo=False)

    respuesta = api.post(URL, json=_cuerpo_con_solicitud(proyecto.id), headers=encabezados)

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALOR_NO_PERMITIDO"


def test_crear_con_solicitud_requiere_tiquete_sin_fecha_nacimiento(
    api: TestClient, sesion: Session
) -> None:
    _, encabezados = _actor(sesion, fecha_nacimiento=None)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL, json=_cuerpo_con_solicitud(proyecto.id, requiere_tiquete=True), headers=encabezados
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "FECHA_NACIMIENTO_REQUERIDA"


def test_crear_con_solicitud_requiere_tiquete_con_fecha_nacimiento(
    api: TestClient, sesion: Session
) -> None:
    _, encabezados = _actor(sesion, fecha_nacimiento=date(1990, 5, 20))
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL, json=_cuerpo_con_solicitud(proyecto.id, requiere_tiquete=True), headers=encabezados
    )

    assert respuesta.status_code == 201


def test_crear_con_solicitud_prestador_con_formato_no_calcula_presupuesto(
    api: TestClient, sesion: Session
) -> None:
    _, encabezados = _actor(sesion, es_prestador_servicios=True)
    proyecto = crear_proyecto(sesion, exige_formato_prestador=True)

    respuesta = api.post(URL, json=_cuerpo_con_solicitud(proyecto.id), headers=encabezados)

    assert respuesta.status_code == 201
    assert respuesta.json()["solicitud"]["presupuesto_solicitado"] is None


def test_crear_con_solicitud_rechaza_recursos_propios(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL, json=_cuerpo_con_solicitud(proyecto.id, recursos_propios=True), headers=encabezados
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALIDACION"


def test_crear_con_solicitud_rechaza_mas_de_5_trayectos(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL,
        json=_cuerpo_con_solicitud(
            proyecto.id, trayectos=[_trayecto(orden=i) for i in range(1, 7)]
        ),
        headers=encabezados,
    )

    assert respuesta.status_code == 422


# =================================================================================================
# POST /viaticos (LEGALIZACION_DIRECTA)
# =================================================================================================


def test_crear_legalizacion_directa(api: TestClient, sesion: Session) -> None:
    actor, encabezados = _actor(sesion)

    respuesta = api.post(
        URL,
        json={
            "modalidad": "LEGALIZACION_DIRECTA",
            "motivo_viaje": "Gastos ya realizados en campo",
            "recursos_propios": True,
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["modalidad"] == "LEGALIZACION_DIRECTA"
    assert cuerpo["etapa"] == "LEGALIZACION"
    assert cuerpo["recursos_propios"] is True
    assert cuerpo["valor_transferido"] == "0.00"
    assert cuerpo["solicitud"] is None
    assert len(cuerpo["eventos"]) == 1

    viatico = sesion.get(Viatico, uuid.UUID(cuerpo["id"]))
    assert viatico is not None and viatico.usuario_id == actor.id


def test_crear_legalizacion_directa_sin_recursos_propios(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(
        URL,
        json={"modalidad": "LEGALIZACION_DIRECTA", "motivo_viaje": "Viaje corto de rutina"},
        headers=encabezados,
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["recursos_propios"] is False


def test_crear_legalizacion_directa_rechaza_proyecto(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        URL,
        json={
            "modalidad": "LEGALIZACION_DIRECTA",
            "motivo_viaje": "Viaje corto de rutina",
            "proyecto_id": str(proyecto.id),
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALIDACION"


def test_crear_legalizacion_directa_rechaza_trayectos(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(
        URL,
        json={
            "modalidad": "LEGALIZACION_DIRECTA",
            "motivo_viaje": "Viaje corto de rutina",
            "trayectos": [_trayecto()],
        },
        headers=encabezados,
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == "VALIDACION"


def test_crear_rechaza_modalidad_desconocida(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(
        URL,
        json={"modalidad": "ALGO_RARO", "motivo_viaje": "Viaje corto de rutina"},
        headers=encabezados,
    )

    assert respuesta.status_code == 422


# =================================================================================================
# GET /viaticos/{id}
# =================================================================================================


def test_detalle_propio(api: TestClient, sesion: Session) -> None:
    actor, encabezados = _actor(sesion)
    creado = api.post(
        URL,
        json={"modalidad": "LEGALIZACION_DIRECTA", "motivo_viaje": "Viaje corto de rutina"},
        headers=encabezados,
    ).json()

    respuesta = api.get(f"{URL}/{creado['id']}", headers=encabezados)

    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == creado["id"]
    assert respuesta.json()["usuario"]["id"] == str(actor.id)


def test_detalle_ajeno_para_viajero_es_404(api: TestClient, sesion: Session) -> None:
    _, encabezados_dueno = _actor(sesion)
    creado = api.post(
        URL,
        json={"modalidad": "LEGALIZACION_DIRECTA", "motivo_viaje": "Viaje corto de rutina"},
        headers=encabezados_dueno,
    ).json()
    _, encabezados_otro = _actor(sesion)

    respuesta = api.get(f"{URL}/{creado['id']}", headers=encabezados_otro)

    assert respuesta.status_code == 404 and respuesta.json()["code"] == "NO_ENCONTRADO"


@pytest.mark.parametrize("rol", [Rol.FINANCIERO, Rol.ADMIN, Rol.SUPERADMIN])
def test_detalle_privilegiados_ven_cualquier_viatico(
    api: TestClient, sesion: Session, rol: Rol
) -> None:
    _, encabezados_dueno = _actor(sesion)
    creado = api.post(
        URL,
        json={"modalidad": "LEGALIZACION_DIRECTA", "motivo_viaje": "Viaje corto de rutina"},
        headers=encabezados_dueno,
    ).json()
    _, encabezados_privilegiado = _actor(sesion, rol)

    respuesta = api.get(f"{URL}/{creado['id']}", headers=encabezados_privilegiado)

    assert respuesta.status_code == 200


def test_detalle_inexistente(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.get(f"{URL}/{uuid.uuid4()}", headers=encabezados)

    assert respuesta.status_code == 404


def test_detalle_incluye_trayectos_y_eventos(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion)
    creado = api.post(
        URL,
        json=_cuerpo_con_solicitud(
            proyecto.id,
            trayectos=[_trayecto(orden=1, ciudad_destino="Cali", dias_estadia=1)],
        ),
        headers=encabezados,
    ).json()

    respuesta = api.get(f"{URL}/{creado['id']}", headers=encabezados)

    cuerpo = respuesta.json()
    assert len(cuerpo["solicitud"]["trayectos"]) == 1
    assert cuerpo["solicitud"]["trayectos"][0]["ciudad_destino"] == "Cali"
    assert len(cuerpo["eventos"]) == 1


def test_detalle_saldo_recien_creado_es_cero(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)
    creado = api.post(
        URL,
        json={"modalidad": "LEGALIZACION_DIRECTA", "motivo_viaje": "Viaje corto de rutina"},
        headers=encabezados,
    ).json()

    respuesta = api.get(f"{URL}/{creado['id']}", headers=encabezados)

    cuerpo = respuesta.json()
    assert cuerpo["total_gastos"] == "0.00"
    assert cuerpo["saldo"] == "0.00"
