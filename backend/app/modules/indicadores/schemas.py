"""Esquemas de `/indicadores` (docs/api-design.md §5.7; S2-09). Dinero siempre como *string*."""

import uuid

from pydantic import BaseModel

from app.core.enums import EstadoFinanciero, EstadoOperativo
from app.core.types import Dinero


class Totales(BaseModel):
    total_solicitado: Dinero  # Σ presupuesto_solicitado de los viáticos incluidos
    total_transferido: Dinero  # Σ valor_transferido de esos mismos viáticos
    total_gastado: Dinero  # Σ gastos que cumplen los filtros
    saldo_neto: Dinero  # total_transferido − total_gastado
    cantidad_viaticos: int
    cantidad_gastos: int


class ItemProyecto(BaseModel):
    # `None` para los proyectos escritos con "Otro" (ADR-031): se agrupan por nombre normalizado.
    proyecto_id: uuid.UUID | None
    proyecto: str
    es_fuera_catalogo: bool
    total_gastado: Dinero
    cantidad_gastos: int


class ItemRubro(BaseModel):
    rubro_id: uuid.UUID
    rubro: str
    total_gastado: Dinero
    cantidad_gastos: int


class ItemCelula(BaseModel):
    celula_id: uuid.UUID | None
    celula: str
    total_gastado: Dinero
    cantidad_gastos: int


class ItemMes(BaseModel):
    mes: str  # AAAA-MM
    total_gastado: Dinero
    cantidad_gastos: int


class ItemEstadoOperativo(BaseModel):
    estado: EstadoOperativo
    cantidad: int


class ItemEstadoFinanciero(BaseModel):
    estado: EstadoFinanciero
    cantidad: int


class IndicadoresResumen(BaseModel):
    totales: Totales
    por_proyecto: list[ItemProyecto]
    por_rubro: list[ItemRubro]
    por_celula: list[ItemCelula]
    por_mes: list[ItemMes]
    por_estado: list[ItemEstadoOperativo]
    por_estado_financiero: list[ItemEstadoFinanciero]
