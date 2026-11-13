"""Bandeja de tesorería (S2-09; docs/api-design.md §5.6; SPEC RF-008).

**Universo:** lo que tesorería puede tener que mover, siempre con `estado = APROBADO`:
- solicitudes (`etapa = SOLICITUD`) con `requiere_gastos_viaje` (hay anticipo que transferir);
- legalizaciones (`etapa = LEGALIZACION`) (hay saldo que reintegrar o reembolsar).

**Bandejas:** `pendientes_desembolso` (solicitud sin transferir), `pendientes_liquidacion`
(legalización `PENDIENTE`/`TRANSFERIDO`), `historico` (solicitud ya transferida, legalización ya
`PAGADO`/`PROCESADO`) y `todos`.

El saldo sale de `v_viatico_saldos` (una sola fuente, ADR-008) y solo se informa en legalización.
El alcance lo da RLS: la bandeja la leen F, A y S (`pagos:leer`, ADMIN en solo lectura, DP-18) y las
acciones de cada fila son las de tesorería (`acciones.py`), vacías para ADMIN y para lo propio.
"""

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.orm import Session

from app.core.enums import EstadoFinanciero, EstadoOperativo, Etapa, TipoLiquidacion
from app.core.paginacion import ParametrosPagina, patron_busqueda
from app.core.tiempo import validar_rango_fechas
from app.modules.auth.schemas import Referencia
from app.modules.gastos.models import Gasto
from app.modules.pagos.schemas import (
    BandejaFila,
    BandejaPagos,
    PagoFila,
    PagosResumen,
    ResumenDesembolso,
    ResumenLiquidacion,
    ResumenSaldo,
)
from app.modules.pagos.vista import saldos
from app.modules.usuarios.models import Usuario
from app.modules.viaticos import acciones
from app.modules.viaticos.models import Viatico
from app.modules.viaticos.service import sentido_liquidacion

OrdenPagos = Literal[
    "fecha_legalizacion", "-fecha_legalizacion", "folio", "-folio", "saldo", "-saldo"
]

_F = EstadoFinanciero
_ACCIONES_TESORERIA = frozenset({"registrar_valor_asignado", "cambiar_estado_financiero"})

_SOLICITUD = and_(
    Viatico.etapa == Etapa.SOLICITUD,
    Viatico.estado == EstadoOperativo.APROBADO,
    Viatico.requiere_gastos_viaje.is_(True),
)
_LEGALIZACION = and_(
    Viatico.etapa == Etapa.LEGALIZACION, Viatico.estado == EstadoOperativo.APROBADO
)

PENDIENTES_DESEMBOLSO = and_(_SOLICITUD, Viatico.estado_financiero == _F.PENDIENTE)
PENDIENTES_LIQUIDACION = and_(
    _LEGALIZACION, Viatico.estado_financiero.in_([_F.PENDIENTE, _F.TRANSFERIDO])
)
HISTORICO = or_(
    and_(_SOLICITUD, Viatico.estado_financiero != _F.PENDIENTE),
    and_(_LEGALIZACION, Viatico.estado_financiero.in_([_F.PAGADO, _F.PROCESADO])),
)
_PREDICADO: dict[BandejaPagos, ColumnElement[bool]] = {
    BandejaPagos.PENDIENTES_DESEMBOLSO: PENDIENTES_DESEMBOLSO,
    BandejaPagos.PENDIENTES_LIQUIDACION: PENDIENTES_LIQUIDACION,
    BandejaPagos.HISTORICO: HISTORICO,
    BandejaPagos.TODOS: or_(_SOLICITUD, _LEGALIZACION),
}

_ORDENES: dict[str, ColumnElement[Any]] = {
    "fecha_legalizacion": Viatico.fecha_legalizacion.asc(),
    "-fecha_legalizacion": Viatico.fecha_legalizacion.desc(),
    "folio": Viatico.folio.asc(),
    "-folio": Viatico.folio.desc(),
    "saldo": saldos.c.saldo.asc(),
    "-saldo": saldos.c.saldo.desc(),
}

_CENTAVOS = Decimal("0.01")


def _q(valor: Decimal | int | None) -> Decimal:
    """Siempre con 2 decimales (ADR-012), también las sumas vacías (`0` → `0.00`)."""
    return Decimal(valor or 0).quantize(_CENTAVOS)


def _qn(valor: Decimal | None) -> Decimal | None:
    return None if valor is None else _q(valor)


def _filtros_comunes(
    *,
    proyecto_id: uuid.UUID | None,
    usuario_id: uuid.UUID | None,
    desde: date | None,
    hasta: date | None,
) -> list[ColumnElement[bool]]:
    condiciones: list[ColumnElement[bool]] = [Viatico.deleted_at.is_(None)]
    if usuario_id is not None:
        condiciones.append(Viatico.usuario_id == usuario_id)
    if desde is not None:
        condiciones.append(Viatico.fecha_legalizacion >= desde)
    if hasta is not None:
        condiciones.append(Viatico.fecha_legalizacion <= hasta)
    if proyecto_id is not None:
        # El proyecto de la solicitud o el de cualquiera de sus gastos; los "Otro" no entran (S-15).
        condiciones.append(
            or_(
                Viatico.proyecto_id == proyecto_id,
                exists().where(
                    Gasto.viatico_id == Viatico.id,
                    Gasto.deleted_at.is_(None),
                    Gasto.proyecto_id == proyecto_id,
                ),
            )
        )
    return condiciones


def bandeja_de(viatico: Viatico) -> BandejaFila:
    pendiente = viatico.estado_financiero == _F.PENDIENTE
    if viatico.etapa == Etapa.SOLICITUD:
        return BandejaFila.PENDIENTES_DESEMBOLSO if pendiente else BandejaFila.HISTORICO
    if viatico.estado_financiero in (_F.PENDIENTE, _F.TRANSFERIDO):
        return BandejaFila.PENDIENTES_LIQUIDACION
    return BandejaFila.HISTORICO


def _fila(
    viatico: Viatico, total_gastos: Decimal, saldo: Decimal, nombre: str, actor: Usuario
) -> PagoFila:
    en_legalizacion = viatico.etapa == Etapa.LEGALIZACION
    permitidas = [a for a in acciones.calcular(viatico, actor) if a in _ACCIONES_TESORERIA]
    tipo: TipoLiquidacion | None = sentido_liquidacion(saldo) if en_legalizacion else None
    return PagoFila(
        id=viatico.id,
        folio=viatico.folio,
        usuario=Referencia(id=viatico.usuario_id, nombre=nombre),
        modalidad=viatico.modalidad,
        etapa=viatico.etapa,
        estado=viatico.estado,
        estado_financiero=viatico.estado_financiero,
        bandeja=bandeja_de(viatico),
        motivo_viaje=viatico.motivo_viaje,
        fecha_legalizacion=viatico.fecha_legalizacion,
        recursos_propios=viatico.recursos_propios,
        presupuesto_solicitado=_qn(viatico.presupuesto_solicitado),
        valor_asignado=_q(viatico.valor_asignado),
        valor_transferido=_q(viatico.valor_transferido),
        total_gastos=total_gastos,
        saldo=saldo if en_legalizacion else None,
        tipo_liquidacion=tipo,
        acciones_permitidas=permitidas,
        destinos_financieros=(
            acciones.destinos_financieros(viatico)
            if "cambiar_estado_financiero" in permitidas
            else []
        ),
    )


def listar(
    session: Session,
    actor: Usuario,
    parametros: ParametrosPagina,
    *,
    bandeja: BandejaPagos,
    estado_financiero: EstadoFinanciero | None,
    proyecto_id: uuid.UUID | None,
    usuario_id: uuid.UUID | None,
    desde: date | None,
    hasta: date | None,
    q: str | None,
    sort: OrdenPagos,
) -> tuple[list[PagoFila], int]:
    validar_rango_fechas(desde, hasta)
    condiciones = [
        *_filtros_comunes(proyecto_id=proyecto_id, usuario_id=usuario_id, desde=desde, hasta=hasta),
        _PREDICADO[bandeja],
    ]
    if estado_financiero is not None:
        condiciones.append(Viatico.estado_financiero == estado_financiero)
    if q and q.strip():
        patron = patron_busqueda(q.strip())
        condiciones.append(
            or_(
                Viatico.folio.ilike(patron),
                Viatico.motivo_viaje.ilike(patron),
                Viatico.colaborador_nombre.ilike(patron),
            )
        )

    total = session.scalar(select(func.count(Viatico.id)).where(*condiciones)) or 0
    filas: Any = session.execute(
        select(Viatico, saldos.c.total_gastos, saldos.c.saldo, Usuario.nombre_completo)
        .join(saldos, saldos.c.viatico_id == Viatico.id)
        .join(Usuario, Usuario.id == Viatico.usuario_id)
        .where(*condiciones)
        .order_by(_ORDENES[sort], Viatico.id.desc())
        .limit(parametros.size)
        .offset(parametros.offset)
    ).all()
    return [_fila(v, _q(tg), _q(s), nombre, actor) for v, tg, s, nombre in filas], total


def resumen(
    session: Session,
    *,
    proyecto_id: uuid.UUID | None,
    usuario_id: uuid.UUID | None,
    desde: date | None,
    hasta: date | None,
) -> PagosResumen:
    """KPIs de tesorería de lo que cumple los filtros, en una sola consulta con `FILTER`."""
    validar_rango_fechas(desde, hasta)

    def cuenta(predicado: ColumnElement[bool]) -> Any:
        return func.count(Viatico.id).filter(predicado)

    def suma(columna: Any, predicado: ColumnElement[bool]) -> Any:
        return func.coalesce(func.sum(columna).filter(predicado), 0)

    a_favor_empresa = and_(PENDIENTES_LIQUIDACION, saldos.c.saldo > 0)
    a_favor_viajero = and_(PENDIENTES_LIQUIDACION, saldos.c.saldo < 0)
    ya_transferido = Viatico.estado_financiero.in_([_F.TRANSFERIDO, _F.PAGADO, _F.PROCESADO])

    fila = session.execute(
        select(
            cuenta(PENDIENTES_DESEMBOLSO),
            suma(Viatico.valor_asignado, PENDIENTES_DESEMBOLSO),
            suma(Viatico.presupuesto_solicitado, PENDIENTES_DESEMBOLSO),
            cuenta(PENDIENTES_LIQUIDACION),
            suma(saldos.c.total_gastos, PENDIENTES_LIQUIDACION),
            suma(Viatico.valor_transferido, PENDIENTES_LIQUIDACION),
            # Dinero que ya salió, esté o no aprobada su legalización (y aunque se haya rechazado).
            suma(Viatico.valor_transferido, ya_transferido),
            suma(saldos.c.total_gastos, _LEGALIZACION),
            cuenta(a_favor_empresa),
            suma(saldos.c.saldo, a_favor_empresa),
            cuenta(a_favor_viajero),
            suma(-saldos.c.saldo, a_favor_viajero),
        )
        .select_from(Viatico)
        .join(saldos, saldos.c.viatico_id == Viatico.id)
        .where(
            *_filtros_comunes(
                proyecto_id=proyecto_id, usuario_id=usuario_id, desde=desde, hasta=hasta
            )
        )
    ).one()
    (
        n_desembolso,
        asignado,
        presupuestado,
        n_liquidacion,
        gastos,
        transferido_pend,
        transferido_total,
        legalizado,
        n_reintegro,
        m_reintegro,
        n_reembolso,
        m_reembolso,
    ) = fila
    return PagosResumen(
        pendientes_desembolso=ResumenDesembolso(
            cantidad=n_desembolso,
            monto_asignado=_q(asignado),
            monto_presupuestado=_q(presupuestado),
        ),
        pendientes_liquidacion=ResumenLiquidacion(
            cantidad=n_liquidacion, monto_gastos=_q(gastos), monto_transferido=_q(transferido_pend)
        ),
        total_transferido=_q(transferido_total),
        total_legalizado=_q(legalizado),
        reintegros_pendientes=ResumenSaldo(cantidad=n_reintegro, monto=_q(m_reintegro)),
        reembolsos_pendientes=ResumenSaldo(cantidad=n_reembolso, monto=_q(m_reembolso)),
    )
