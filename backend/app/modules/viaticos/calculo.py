"""Cálculo tarifario de una solicitud de viáticos (RN-29, RN-30, RN-33; ADR-030).

Dos capas, a propósito:

- **Funciones puras** (`validar_trayectos`, `calcular_presupuesto`): no tocan la BD. Reciben las
  tarifas ya resueltas (`TarifaConceptos`) en un diccionario por ciudad, así que las pruebas cubren
  la aritmética (RN-29) y las validaciones (RN-30) con tablas de casos, sin Postgres.
- `app/modules/viaticos/service.py::calcular_presupuesto_bd()` hace las consultas (proyecto,
  tarifas activas) y llama a estas funciones: es el único punto donde `POST /viaticos` y
  `POST /viaticos/calcular-presupuesto` comparten la lógica (docs/api-design.md §5.4).

El cliente nunca envía tarifas ni totales (RN-29): todo lo calculado aquí sale del servidor.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.core.errors import error_de_campo
from app.modules.viaticos.errores import TrayectosInvalidos

MOTIVO_SIN_GASTOS_VIAJE = "SIN_GASTOS_VIAJE"
MOTIVO_FORMATO_PRESTADOR = "FORMATO_PRESTADOR"
MAXIMO_TRAYECTOS = 5
CIUDAD_OTRO = "otro"


@dataclass(frozen=True)
class TarifaConceptos:
    """Los 6 conceptos de una fila activa de `tarifas_viaticos` para una ciudad y un tipo."""

    tarifa_id: uuid.UUID
    vr_alimentacion: Decimal
    otros_gastos: Decimal
    transporte_aeropuerto: Decimal
    transporte_intermunicipal: Decimal
    trans_interno_dia_1: Decimal
    trans_interno_varios_dias: Decimal


@dataclass(frozen=True)
class TrayectoEntrada:
    """Un tramo tal como lo envía el cliente (`docs/api-design.md` §5.4)."""

    orden: int
    ciudad_origen: str
    ciudad_destino: str
    fecha_ida: datetime
    fecha_regreso: datetime
    requiere_hospedaje: bool
    dias_estadia: int


@dataclass(frozen=True)
class TrayectoCalculado:
    """`TrayectoEntrada` más la instantánea tarifaria (o `None` si no aplicó, RN-33/S-11)."""

    orden: int
    ciudad_origen: str
    ciudad_destino: str
    fecha_ida: datetime
    fecha_regreso: datetime
    requiere_hospedaje: bool
    dias_estadia: int
    tarifa_id: uuid.UUID | None
    vr_alimentacion: Decimal | None
    otros_gastos: Decimal | None
    trans_interno: Decimal | None
    transporte_aeropuerto: Decimal | None
    transporte_intermunicipal: Decimal | None
    subtotal_estadia: Decimal | None


@dataclass(frozen=True)
class ResultadoPresupuesto:
    aplica: bool
    motivo_no_aplica: str | None
    trayectos: list[TrayectoCalculado]
    presupuesto_solicitado: Decimal | None
    exige_formato_prestador: bool


def validar_trayectos(trayectos: Sequence[TrayectoEntrada]) -> None:
    """RN-30: 1 a 5 trayectos, `orden` único, destino ≠ origen (salvo "Otro"), regreso ≥ ida."""
    errores: list[dict[str, str]] = []
    if not 1 <= len(trayectos) <= MAXIMO_TRAYECTOS:
        raise TrayectosInvalidos(
            errors=error_de_campo(
                "trayectos",
                f"Debe haber entre 1 y {MAXIMO_TRAYECTOS} trayectos",
                "TRAYECTOS_INVALIDOS",
            )
        )
    ordenes = [t.orden for t in trayectos]
    if len(set(ordenes)) != len(ordenes):
        errores.extend(
            error_de_campo(
                "trayectos", "El orden de los trayectos no puede repetirse", "TRAYECTOS_INVALIDOS"
            )
        )
    for indice, trayecto in enumerate(trayectos):
        campo = f"trayectos[{indice}]"
        es_otro = trayecto.ciudad_destino.strip().lower() == CIUDAD_OTRO
        if (
            not es_otro
            and trayecto.ciudad_destino.strip().lower() == trayecto.ciudad_origen.strip().lower()
        ):
            errores.extend(
                error_de_campo(
                    f"{campo}.ciudad_destino",
                    'El destino debe ser distinto del origen (salvo "Otro")',
                    "TRAYECTOS_INVALIDOS",
                )
            )
        if trayecto.fecha_regreso < trayecto.fecha_ida:
            errores.extend(
                error_de_campo(
                    f"{campo}.fecha_regreso",
                    "La fecha de regreso no puede ser anterior a la de ida",
                    "TRAYECTOS_INVALIDOS",
                )
            )
        if trayecto.dias_estadia < 1:
            errores.extend(
                error_de_campo(
                    f"{campo}.dias_estadia",
                    "Los días de estadía deben ser al menos 1",
                    "TRAYECTOS_INVALIDOS",
                )
            )
    if errores:
        raise TrayectosInvalidos(errors=errores)


def _trans_interno(tarifa: TarifaConceptos, dias_estadia: int) -> Decimal:
    return tarifa.trans_interno_varios_dias if dias_estadia > 1 else tarifa.trans_interno_dia_1


def _sin_calculo(trayecto: TrayectoEntrada) -> TrayectoCalculado:
    return TrayectoCalculado(
        orden=trayecto.orden,
        ciudad_origen=trayecto.ciudad_origen,
        ciudad_destino=trayecto.ciudad_destino,
        fecha_ida=trayecto.fecha_ida,
        fecha_regreso=trayecto.fecha_regreso,
        requiere_hospedaje=trayecto.requiere_hospedaje,
        dias_estadia=trayecto.dias_estadia,
        tarifa_id=None,
        vr_alimentacion=None,
        otros_gastos=None,
        trans_interno=None,
        transporte_aeropuerto=None,
        transporte_intermunicipal=None,
        subtotal_estadia=None,
    )


class CiudadSinTarifaError(KeyError):
    """La ciudad de destino de un trayecto no tiene una tarifa activa para ese tipo."""


def calcular_presupuesto(
    trayectos: Sequence[TrayectoEntrada],
    *,
    tarifas_por_ciudad: Mapping[str, TarifaConceptos],
    requiere_gastos_viaje: bool,
    es_prestador_servicios: bool,
    exige_formato_prestador: bool,
) -> ResultadoPresupuesto:
    """RN-29: calcula el presupuesto de una solicitud. Pura: valida (RN-30) y hace la aritmética
    con `Decimal`; quien la llama ya resolvió `tarifas_por_ciudad` (clave: ciudad en minúsculas).

    - `requiere_gastos_viaje = False` (S-11): no hay cálculo (`aplica = False`).
    - Prestador + `exige_formato_prestador` (RN-33): no se calcula por tabla; adjunta formato.
    - En los dos casos anteriores los trayectos se devuelven **sin** instantánea tarifaria.
    """
    validar_trayectos(trayectos)
    if not requiere_gastos_viaje:
        return ResultadoPresupuesto(
            aplica=False,
            motivo_no_aplica=MOTIVO_SIN_GASTOS_VIAJE,
            trayectos=[_sin_calculo(t) for t in trayectos],
            presupuesto_solicitado=None,
            exige_formato_prestador=exige_formato_prestador,
        )
    if es_prestador_servicios and exige_formato_prestador:
        return ResultadoPresupuesto(
            aplica=False,
            motivo_no_aplica=MOTIVO_FORMATO_PRESTADOR,
            trayectos=[_sin_calculo(t) for t in trayectos],
            presupuesto_solicitado=None,
            exige_formato_prestador=True,
        )

    calculados: list[TrayectoCalculado] = []
    total = Decimal("0")
    for trayecto in trayectos:
        tarifa = tarifas_por_ciudad.get(trayecto.ciudad_destino.strip().lower())
        if tarifa is None:
            raise CiudadSinTarifaError(trayecto.ciudad_destino)
        trans_interno = _trans_interno(tarifa, trayecto.dias_estadia)
        subtotal_estadia = (tarifa.vr_alimentacion + trans_interno + tarifa.otros_gastos) * (
            trayecto.dias_estadia
        )
        calculados.append(
            TrayectoCalculado(
                orden=trayecto.orden,
                ciudad_origen=trayecto.ciudad_origen,
                ciudad_destino=trayecto.ciudad_destino,
                fecha_ida=trayecto.fecha_ida,
                fecha_regreso=trayecto.fecha_regreso,
                requiere_hospedaje=trayecto.requiere_hospedaje,
                dias_estadia=trayecto.dias_estadia,
                tarifa_id=tarifa.tarifa_id,
                vr_alimentacion=tarifa.vr_alimentacion,
                otros_gastos=tarifa.otros_gastos,
                trans_interno=trans_interno,
                transporte_aeropuerto=tarifa.transporte_aeropuerto,
                transporte_intermunicipal=tarifa.transporte_intermunicipal,
                subtotal_estadia=subtotal_estadia,
            )
        )
        total += subtotal_estadia + tarifa.transporte_aeropuerto + tarifa.transporte_intermunicipal
    return ResultadoPresupuesto(
        aplica=True,
        motivo_no_aplica=None,
        trayectos=calculados,
        presupuesto_solicitado=total,
        exige_formato_prestador=False,
    )
