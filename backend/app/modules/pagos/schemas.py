"""Esquemas de `/pagos` (docs/api-design.md §5.6; S2-09). Dinero siempre como *string* (ADR-012)."""

import uuid
from datetime import date
from enum import StrEnum

from pydantic import BaseModel

from app.core.enums import EstadoFinanciero, EstadoOperativo, Etapa, Modalidad, TipoLiquidacion
from app.core.types import Dinero
from app.modules.auth.schemas import Referencia


class BandejaPagos(StrEnum):
    """Qué le toca hacer a tesorería con un viático aprobado."""

    PENDIENTES_DESEMBOLSO = "pendientes_desembolso"  # solicitud aprobada, sin transferir
    PENDIENTES_LIQUIDACION = "pendientes_liquidacion"  # legalización aprobada, sin pagar
    HISTORICO = "historico"  # ya transferida / ya pagada o procesada
    TODOS = "todos"


class BandejaFila(StrEnum):
    """Bandeja concreta de una fila (nunca `todos`)."""

    PENDIENTES_DESEMBOLSO = "pendientes_desembolso"
    PENDIENTES_LIQUIDACION = "pendientes_liquidacion"
    HISTORICO = "historico"


class PagoFila(BaseModel):
    id: uuid.UUID
    folio: str
    usuario: Referencia
    modalidad: Modalidad
    etapa: Etapa
    estado: EstadoOperativo
    estado_financiero: EstadoFinanciero
    bandeja: BandejaFila
    motivo_viaje: str
    fecha_legalizacion: date
    recursos_propios: bool
    presupuesto_solicitado: Dinero | None
    valor_asignado: Dinero
    valor_transferido: Dinero
    total_gastos: Dinero
    # El saldo y su sentido solo significan algo en la etapa LEGALIZACION (RN-02).
    saldo: Dinero | None
    tipo_liquidacion: TipoLiquidacion | None
    # Solo las de tesorería (`registrar_valor_asignado`, `cambiar_estado_financiero`) y los estados
    # financieros a los que se puede pasar ahora; vacías para ADMIN (solo lectura) y para lo propio.
    acciones_permitidas: list[str]
    destinos_financieros: list[EstadoFinanciero]


class ResumenDesembolso(BaseModel):
    cantidad: int
    monto_asignado: Dinero
    monto_presupuestado: Dinero


class ResumenLiquidacion(BaseModel):
    cantidad: int
    monto_gastos: Dinero
    monto_transferido: Dinero


class ResumenSaldo(BaseModel):
    cantidad: int
    # Magnitud positiva: lo que se debe reintegrar o reembolsar.
    monto: Dinero


class PagosResumen(BaseModel):
    pendientes_desembolso: ResumenDesembolso
    pendientes_liquidacion: ResumenLiquidacion
    total_transferido: Dinero
    total_legalizado: Dinero
    reintegros_pendientes: ResumenSaldo
    reembolsos_pendientes: ResumenSaldo
