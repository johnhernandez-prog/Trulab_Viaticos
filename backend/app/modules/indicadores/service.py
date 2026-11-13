"""Indicadores (S2-09; docs/api-design.md §5.7; RN-07, RN-18, ADR-024, ADR-031, S-07, S-15).

**Dos bases, explícitas:**

1. **Dinero** (totales, por proyecto/rubro/célula/mes y el CSV): los gastos activos de las
   **legalizaciones aprobadas** (`etapa = LEGALIZACION`, `estado = APROBADO`), con
   `gastos.fecha_factura BETWEEN desde AND hasta` (nunca fechas de viaje ni de registro).
   `total_solicitado` y `total_transferido` son los de los viáticos a los que pertenecen esos
   gastos: con un rango, un viático cuenta entero aunque solo parte de sus gastos caiga en él.
2. **Estados** (`por_estado`, `por_estado_financiero`): viáticos de cualquier estado (si no, todo
   saldría `APROBADO`). Con filtros de gasto (fechas, proyecto, rubro) se cuentan solo los que
   tienen al menos un gasto que los cumpla (S-07).

El proyecto del catálogo se agrupa por id y los escritos con "Otro" por nombre normalizado
(`lower(btrim())`, ADR-031); el filtro `proyecto_id` no incluye los "Otro" (S-15). La célula es la
actual del viajero. Todo lo que ve cada rol lo limita RLS (F, A y S ven todo).
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, Select, exists, func, literal_column, select
from sqlalchemy.orm import Session

from app.core.enums import EstadoFinanciero, EstadoOperativo, Etapa, Modalidad
from app.core.tiempo import validar_rango_fechas
from app.modules.catalogos.models import Celula, Proyecto, Rubro
from app.modules.gastos.models import Gasto
from app.modules.indicadores.schemas import (
    IndicadoresResumen,
    ItemCelula,
    ItemEstadoFinanciero,
    ItemEstadoOperativo,
    ItemMes,
    ItemProyecto,
    ItemRubro,
    Totales,
)
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.models import Viatico

_CENTAVOS = Decimal("0.01")
SIN_CELULA = "Sin célula"


@dataclass(frozen=True)
class Filtros:
    desde: date | None = None
    hasta: date | None = None
    proyecto_id: uuid.UUID | None = None
    rubro_id: uuid.UUID | None = None
    celula_id: uuid.UUID | None = None
    usuario_id: uuid.UUID | None = None
    modalidad: Modalidad | None = None


def _q(valor: Decimal | int | None) -> Decimal:
    return Decimal(valor or 0).quantize(_CENTAVOS)


# --- base de dinero: gastos de legalizaciones aprobadas ------------------------------------------


def sobre_gastos(consulta: Select[Any]) -> Select[Any]:
    """`FROM gastos JOIN viaticos JOIN usuarios`, la base de todas las consultas de dinero."""
    return (
        consulta.select_from(Gasto)
        .join(Viatico, Viatico.id == Gasto.viatico_id)
        .join(Usuario, Usuario.id == Viatico.usuario_id)
    )


def _condiciones_de_gasto(f: Filtros) -> list[ColumnElement[bool]]:
    """Las que miran al gasto: fecha de factura (RN-18), proyecto del catálogo y rubro."""
    condiciones: list[ColumnElement[bool]] = []
    if f.desde is not None:
        condiciones.append(Gasto.fecha_factura >= f.desde)
    if f.hasta is not None:
        condiciones.append(Gasto.fecha_factura <= f.hasta)
    if f.proyecto_id is not None:
        condiciones.append(Gasto.proyecto_id == f.proyecto_id)
    if f.rubro_id is not None:
        condiciones.append(Gasto.rubro_id == f.rubro_id)
    return condiciones


def _condiciones_de_viatico(f: Filtros) -> list[ColumnElement[bool]]:
    condiciones: list[ColumnElement[bool]] = []
    if f.usuario_id is not None:
        condiciones.append(Viatico.usuario_id == f.usuario_id)
    if f.modalidad is not None:
        condiciones.append(Viatico.modalidad == f.modalidad)
    if f.celula_id is not None:
        condiciones.append(Usuario.celula_id == f.celula_id)
    return condiciones


def condiciones_dinero(f: Filtros) -> list[ColumnElement[bool]]:
    return [
        Gasto.deleted_at.is_(None),
        Viatico.deleted_at.is_(None),
        Viatico.etapa == Etapa.LEGALIZACION,
        Viatico.estado == EstadoOperativo.APROBADO,
        *_condiciones_de_gasto(f),
        *_condiciones_de_viatico(f),
    ]


# --- resumen -------------------------------------------------------------------------------------


def _totales(session: Session, f: Filtros) -> Totales:
    cond = condiciones_dinero(f)
    gastado, n_gastos, n_viaticos = session.execute(
        sobre_gastos(
            select(
                func.coalesce(func.sum(Gasto.valor), 0),
                func.count(Gasto.id),
                func.count(func.distinct(Gasto.viatico_id)),
            )
        ).where(*cond)
    ).one()
    ids = sobre_gastos(select(Gasto.viatico_id)).where(*cond).distinct()
    solicitado, transferido = session.execute(
        select(
            func.coalesce(func.sum(Viatico.presupuesto_solicitado), 0),
            func.coalesce(func.sum(Viatico.valor_transferido), 0),
        ).where(Viatico.id.in_(ids))
    ).one()
    return Totales(
        total_solicitado=_q(solicitado),
        total_transferido=_q(transferido),
        total_gastado=_q(gastado),
        saldo_neto=_q(transferido) - _q(gastado),
        cantidad_viaticos=n_viaticos,
        cantidad_gastos=n_gastos,
    )


def _por_proyecto(session: Session, f: Filtros) -> list[ItemProyecto]:
    otro = func.btrim(Gasto.proyecto_otro)
    total = func.sum(Gasto.valor)
    filas = session.execute(
        sobre_gastos(
            select(
                Gasto.proyecto_id,
                func.min(Proyecto.nombre),
                func.min(otro),
                total,
                func.count(Gasto.id),
            )
        )
        .outerjoin(Proyecto, Proyecto.id == Gasto.proyecto_id)
        .where(*condiciones_dinero(f))
        .group_by(Gasto.proyecto_id, func.lower(otro))
        .order_by(total.desc(), func.min(Proyecto.nombre), func.min(otro))
    ).all()
    return [
        ItemProyecto(
            proyecto_id=proyecto_id,
            proyecto=nombre_catalogo or nombre_otro or "",
            es_fuera_catalogo=proyecto_id is None,
            total_gastado=_q(suma),
            cantidad_gastos=cantidad,
        )
        for proyecto_id, nombre_catalogo, nombre_otro, suma, cantidad in filas
    ]


def _por_rubro(session: Session, f: Filtros) -> list[ItemRubro]:
    total = func.sum(Gasto.valor)
    filas = session.execute(
        sobre_gastos(select(Rubro.id, Rubro.nombre, total, func.count(Gasto.id)))
        .join(Rubro, Rubro.id == Gasto.rubro_id)
        .where(*condiciones_dinero(f))
        .group_by(Rubro.id, Rubro.nombre)
        .order_by(total.desc(), Rubro.nombre)
    ).all()
    return [
        ItemRubro(rubro_id=i, rubro=n, total_gastado=_q(s), cantidad_gastos=c)
        for i, n, s, c in filas
    ]


def _por_celula(session: Session, f: Filtros) -> list[ItemCelula]:
    total = func.sum(Gasto.valor)
    filas = session.execute(
        sobre_gastos(select(Usuario.celula_id, Celula.nombre, total, func.count(Gasto.id)))
        .outerjoin(Celula, Celula.id == Usuario.celula_id)
        .where(*condiciones_dinero(f))
        .group_by(Usuario.celula_id, Celula.nombre)
        .order_by(total.desc(), Celula.nombre)
    ).all()
    return [
        ItemCelula(celula_id=i, celula=n or SIN_CELULA, total_gastado=_q(s), cantidad_gastos=c)
        for i, n, s, c in filas
    ]


def _por_mes(session: Session, f: Filtros) -> list[ItemMes]:
    # El formato va inline (no como parámetro): si no, PostgreSQL ve dos expresiones distintas
    # en el `SELECT` y en el `GROUP BY`.
    mes = func.to_char(Gasto.fecha_factura, literal_column("'YYYY-MM'"))
    filas = session.execute(
        sobre_gastos(select(mes, func.sum(Gasto.valor), func.count(Gasto.id)))
        .where(*condiciones_dinero(f))
        .group_by(mes)
        .order_by(mes)
    ).all()
    return [ItemMes(mes=m, total_gastado=_q(s), cantidad_gastos=c) for m, s, c in filas]


# --- base de estados (S-07) ----------------------------------------------------------------------


def _condiciones_estados(f: Filtros) -> list[ColumnElement[bool]]:
    condiciones = [Viatico.deleted_at.is_(None), *_condiciones_de_viatico(f)]
    de_gasto = _condiciones_de_gasto(f)
    if de_gasto:
        condiciones.append(
            exists().where(Gasto.viatico_id == Viatico.id, Gasto.deleted_at.is_(None), *de_gasto)
        )
    return condiciones


def _distribucion(
    session: Session, f: Filtros, columna: Any, valores: Sequence[Any]
) -> dict[str, int]:
    """Cuenta por `columna`; todos los valores del enum aparecen, también con cero."""
    filas = session.execute(
        select(columna, func.count(Viatico.id))
        .join(Usuario, Usuario.id == Viatico.usuario_id)
        .where(*_condiciones_estados(f))
        .group_by(columna)
    ).all()
    contados = {estado: cantidad for estado, cantidad in filas}
    return {v.value: contados.get(v.value, 0) for v in valores}


def resumen(session: Session, f: Filtros) -> IndicadoresResumen:
    validar_rango_fechas(f.desde, f.hasta)
    por_estado = _distribucion(session, f, Viatico.estado, list(EstadoOperativo))
    por_financiero = _distribucion(session, f, Viatico.estado_financiero, list(EstadoFinanciero))
    return IndicadoresResumen(
        totales=_totales(session, f),
        por_proyecto=_por_proyecto(session, f),
        por_rubro=_por_rubro(session, f),
        por_celula=_por_celula(session, f),
        por_mes=_por_mes(session, f),
        por_estado=[
            ItemEstadoOperativo(estado=EstadoOperativo(e), cantidad=c)
            for e, c in por_estado.items()
        ],
        por_estado_financiero=[
            ItemEstadoFinanciero(estado=EstadoFinanciero(e), cantidad=c)
            for e, c in por_financiero.items()
        ],
    )
