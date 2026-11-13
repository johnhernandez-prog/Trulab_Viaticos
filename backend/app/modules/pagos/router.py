"""Rutas de `/pagos` (docs/api-design.md §5.6; S2-09): bandeja de tesorería y su resumen."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.enums import EstadoFinanciero
from app.core.paginacion import Pagina, Paginacion
from app.core.permissions import Permiso, require_permission
from app.modules.auth.dependencias import DB, Autenticado
from app.modules.pagos import service
from app.modules.pagos.schemas import BandejaPagos, PagoFila, PagosResumen

router = APIRouter(prefix="/pagos", tags=["pagos"])

Lector = Annotated[Autenticado, Depends(require_permission(Permiso.PAGOS_LEER))]


@router.get(
    "",
    summary="Bandeja de tesorería: solicitudes por desembolsar y legalizaciones por liquidar",
)
def listar(
    autenticado: Lector,
    session: DB,
    paginacion: Paginacion,
    bandeja: BandejaPagos = BandejaPagos.TODOS,
    estado_financiero: EstadoFinanciero | None = None,
    proyecto_id: uuid.UUID | None = None,
    usuario_id: uuid.UUID | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Folio, motivo o viajero")] = None,
    sort: service.OrdenPagos = "-fecha_legalizacion",
) -> Pagina[PagoFila]:
    items, total = service.listar(
        session,
        autenticado.usuario,
        paginacion,
        bandeja=bandeja,
        estado_financiero=estado_financiero,
        proyecto_id=proyecto_id,
        usuario_id=usuario_id,
        desde=desde,
        hasta=hasta,
        q=q,
        sort=sort,
    )
    return Pagina[PagoFila](items=items, total=total, page=paginacion.page, size=paginacion.size)


@router.get("/resumen", summary="KPIs de tesorería de lo que cumple los filtros")
def resumen(
    _: Lector,
    session: DB,
    proyecto_id: uuid.UUID | None = None,
    usuario_id: uuid.UUID | None = None,
    desde: date | None = None,
    hasta: date | None = None,
) -> PagosResumen:
    return service.resumen(
        session, proyecto_id=proyecto_id, usuario_id=usuario_id, desde=desde, hasta=hasta
    )
