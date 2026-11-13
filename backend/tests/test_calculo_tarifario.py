"""Cálculo tarifario puro (RN-29, RN-30, RN-33; `app/modules/viaticos/calculo.py`).

Sin BD: las tarifas llegan ya resueltas en `tarifas_por_ciudad`. Tablas de casos para la aritmética
(empleado/prestador, 1 día / varios días) y las validaciones de trayectos.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.viaticos.calculo import (
    MOTIVO_FORMATO_PRESTADOR,
    MOTIVO_SIN_GASTOS_VIAJE,
    CiudadSinTarifaError,
    TarifaConceptos,
    TrayectoEntrada,
    calcular_presupuesto,
    validar_trayectos,
)
from app.modules.viaticos.errores import TrayectosInvalidos

IDA = datetime(2026, 11, 20, 8, tzinfo=UTC)


def _trayecto(**campos: object) -> TrayectoEntrada:
    valores: dict[str, object] = {
        "orden": 1,
        "ciudad_origen": "Cali",
        "ciudad_destino": "Bogotá",
        "fecha_ida": IDA,
        "fecha_regreso": IDA + timedelta(days=2),
        "requiere_hospedaje": True,
        "dias_estadia": 3,
    }
    valores.update(campos)
    return TrayectoEntrada(**valores)  # type: ignore[arg-type]


def _tarifa(**campos: object) -> TarifaConceptos:
    valores: dict[str, object] = {
        "tarifa_id": uuid.uuid4(),
        "vr_alimentacion": Decimal("60000"),
        "otros_gastos": Decimal("10000"),
        "transporte_aeropuerto": Decimal("40000"),
        "transporte_intermunicipal": Decimal("20000"),
        "trans_interno_dia_1": Decimal("15000"),
        "trans_interno_varios_dias": Decimal("25000"),
    }
    valores.update(campos)
    return TarifaConceptos(**valores)  # type: ignore[arg-type]


# --- validar_trayectos (RN-30) ---------------------------------------------------------------


def test_acepta_entre_1_y_5_trayectos() -> None:
    validar_trayectos([_trayecto(orden=i) for i in range(1, 6)])  # no lanza


@pytest.mark.parametrize("cantidad", [0, 6])
def test_rechaza_fuera_de_1_a_5_trayectos(cantidad: int) -> None:
    trayectos = [_trayecto(orden=i + 1) for i in range(cantidad)]
    with pytest.raises(TrayectosInvalidos) as exc:
        validar_trayectos(trayectos)
    assert exc.value.code == "TRAYECTOS_INVALIDOS"


def test_rechaza_orden_repetido() -> None:
    with pytest.raises(TrayectosInvalidos):
        validar_trayectos([_trayecto(orden=1), _trayecto(orden=1)])


def test_rechaza_destino_igual_al_origen() -> None:
    with pytest.raises(TrayectosInvalidos) as exc:
        validar_trayectos([_trayecto(ciudad_origen="Cali", ciudad_destino="Cali")])
    assert exc.value.errors is not None
    assert exc.value.errors[0]["field"] == "trayectos[0].ciudad_destino"


@pytest.mark.parametrize("otro", ["Otro", "OTRO", "otro"])
def test_destino_otro_puede_coincidir_con_el_origen(otro: str) -> None:
    validar_trayectos([_trayecto(ciudad_origen=otro, ciudad_destino=otro)])  # no lanza


def test_rechaza_regreso_anterior_a_la_ida() -> None:
    with pytest.raises(TrayectosInvalidos) as exc:
        validar_trayectos([_trayecto(fecha_ida=IDA, fecha_regreso=IDA - timedelta(days=1))])
    assert exc.value.errors is not None
    assert exc.value.errors[0]["field"] == "trayectos[0].fecha_regreso"


def test_rechaza_dias_estadia_menor_a_1() -> None:
    with pytest.raises(TrayectosInvalidos) as exc:
        validar_trayectos([_trayecto(dias_estadia=0)])
    assert exc.value.errors is not None
    assert exc.value.errors[0]["field"] == "trayectos[0].dias_estadia"


def test_acumula_varios_errores_de_distintos_trayectos() -> None:
    with pytest.raises(TrayectosInvalidos) as exc:
        validar_trayectos(
            [
                _trayecto(orden=1, ciudad_origen="Cali", ciudad_destino="Cali"),
                _trayecto(orden=2, dias_estadia=0),
            ]
        )
    assert exc.value.errors is not None
    assert len(exc.value.errors) == 2


# --- calcular_presupuesto: aritmética (RN-29) -------------------------------------------------


def test_un_dia_usa_trans_interno_dia_1() -> None:
    trayecto = _trayecto(dias_estadia=1)
    tarifa = _tarifa()

    resultado = calcular_presupuesto(
        [trayecto],
        tarifas_por_ciudad={"bogotá": tarifa},
        requiere_gastos_viaje=True,
        es_prestador_servicios=False,
        exige_formato_prestador=False,
    )

    assert resultado.aplica is True
    (calculado,) = resultado.trayectos
    assert calculado.trans_interno == Decimal("15000")
    gasto_diario = Decimal("60000") + Decimal("15000") + Decimal("10000")
    assert calculado.subtotal_estadia == gasto_diario * 1
    assert resultado.presupuesto_solicitado == (
        calculado.subtotal_estadia + Decimal("40000") + Decimal("20000")
    )


def test_varios_dias_usa_trans_interno_varios_dias() -> None:
    trayecto = _trayecto(dias_estadia=3)
    tarifa = _tarifa()

    resultado = calcular_presupuesto(
        [trayecto],
        tarifas_por_ciudad={"bogotá": tarifa},
        requiere_gastos_viaje=True,
        es_prestador_servicios=False,
        exige_formato_prestador=False,
    )

    (calculado,) = resultado.trayectos
    assert calculado.trans_interno == Decimal("25000")
    gasto_diario = Decimal("60000") + Decimal("25000") + Decimal("10000")
    assert calculado.subtotal_estadia == gasto_diario * 3


def test_suma_el_presupuesto_de_varios_trayectos() -> None:
    trayectos = [
        _trayecto(orden=1, ciudad_destino="Bogotá", dias_estadia=1),
        _trayecto(orden=2, ciudad_origen="Bogotá", ciudad_destino="Medellín", dias_estadia=2),
    ]
    tarifas = {
        "bogotá": _tarifa(vr_alimentacion=Decimal("60000")),
        "medellín": _tarifa(vr_alimentacion=Decimal("70000"), tarifa_id=uuid.uuid4()),
    }

    resultado = calcular_presupuesto(
        trayectos,
        tarifas_por_ciudad=tarifas,
        requiere_gastos_viaje=True,
        es_prestador_servicios=False,
        exige_formato_prestador=False,
    )

    total_esperado = Decimal("0")
    for calculado in resultado.trayectos:
        assert calculado.subtotal_estadia is not None
        assert calculado.transporte_aeropuerto is not None
        assert calculado.transporte_intermunicipal is not None
        total_esperado += (
            calculado.subtotal_estadia
            + calculado.transporte_aeropuerto
            + calculado.transporte_intermunicipal
        )
    assert resultado.presupuesto_solicitado == total_esperado


def test_tarifa_de_empleado_distinta_de_prestador() -> None:
    trayecto = _trayecto(dias_estadia=1)
    tarifa_empleado = _tarifa(vr_alimentacion=Decimal("60000"))
    tarifa_prestador = _tarifa(vr_alimentacion=Decimal("45000"), tarifa_id=uuid.uuid4())

    resultado_empleado = calcular_presupuesto(
        [trayecto],
        tarifas_por_ciudad={"bogotá": tarifa_empleado},
        requiere_gastos_viaje=True,
        es_prestador_servicios=False,
        exige_formato_prestador=False,
    )
    resultado_prestador = calcular_presupuesto(
        [trayecto],
        tarifas_por_ciudad={"bogotá": tarifa_prestador},
        requiere_gastos_viaje=True,
        es_prestador_servicios=True,
        exige_formato_prestador=False,
    )

    assert resultado_empleado.presupuesto_solicitado != resultado_prestador.presupuesto_solicitado


def test_ciudad_sin_tarifa_activa_lanza_error() -> None:
    with pytest.raises(CiudadSinTarifaError):
        calcular_presupuesto(
            [_trayecto(ciudad_destino="Leticia")],
            tarifas_por_ciudad={},
            requiere_gastos_viaje=True,
            es_prestador_servicios=False,
            exige_formato_prestador=False,
        )


# --- calcular_presupuesto: cuándo NO aplica (S-11, RN-33) --------------------------------------


def test_sin_gastos_de_viaje_no_calcula() -> None:
    resultado = calcular_presupuesto(
        [_trayecto()],
        tarifas_por_ciudad={"bogotá": _tarifa()},
        requiere_gastos_viaje=False,
        es_prestador_servicios=False,
        exige_formato_prestador=False,
    )

    assert resultado.aplica is False
    assert resultado.motivo_no_aplica == MOTIVO_SIN_GASTOS_VIAJE
    assert resultado.presupuesto_solicitado is None
    (trayecto,) = resultado.trayectos
    assert trayecto.tarifa_id is None and trayecto.subtotal_estadia is None


def test_prestador_con_proyecto_que_exige_formato_no_calcula() -> None:
    resultado = calcular_presupuesto(
        [_trayecto()],
        tarifas_por_ciudad={"bogotá": _tarifa()},
        requiere_gastos_viaje=True,
        es_prestador_servicios=True,
        exige_formato_prestador=True,
    )

    assert resultado.aplica is False
    assert resultado.motivo_no_aplica == MOTIVO_FORMATO_PRESTADOR
    assert resultado.exige_formato_prestador is True
    assert resultado.presupuesto_solicitado is None


def test_empleado_en_proyecto_que_exige_formato_si_calcula() -> None:
    # RN-33 es solo para prestadores; un empleado en el mismo proyecto calcula normal.
    resultado = calcular_presupuesto(
        [_trayecto(dias_estadia=1)],
        tarifas_por_ciudad={"bogotá": _tarifa()},
        requiere_gastos_viaje=True,
        es_prestador_servicios=False,
        exige_formato_prestador=True,
    )

    assert resultado.aplica is True
    assert resultado.presupuesto_solicitado is not None


def test_proyecto_otro_no_exige_formato_asi_sea_prestador() -> None:
    # Un proyecto escrito a mano ("Otro") nunca tiene exige_formato_prestador (RN-33): lo decide
    # quien llama (`exige_formato_prestador=False` si viene de `proyecto_otro`).
    resultado = calcular_presupuesto(
        [_trayecto(dias_estadia=1)],
        tarifas_por_ciudad={"bogotá": _tarifa()},
        requiere_gastos_viaje=True,
        es_prestador_servicios=True,
        exige_formato_prestador=False,
    )

    assert resultado.aplica is True
