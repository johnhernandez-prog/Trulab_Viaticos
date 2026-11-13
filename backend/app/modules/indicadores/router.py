"""Rutas de `/indicadores` (docs/api-design.md §5.7; S2-09): resumen y exportación CSV."""

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.core.db import FabricaSesion, get_fabrica_sesion
from app.core.enums import Modalidad
from app.core.permissions import Permiso, require_permission
from app.core.tiempo import hoy_colombia, validar_rango_fechas
from app.modules.auth.dependencias import DB, Autenticado
from app.modules.indicadores import exportacion, service
from app.modules.indicadores.schemas import IndicadoresResumen
from app.modules.indicadores.service import Filtros

router = APIRouter(prefix="/indicadores", tags=["indicadores"])

Lector = Annotated[Autenticado, Depends(require_permission(Permiso.INDICADORES_LEER))]


def _filtros(
    desde: date | None = None,
    hasta: date | None = None,
    proyecto_id: uuid.UUID | None = None,
    rubro_id: uuid.UUID | None = None,
    celula_id: uuid.UUID | None = None,
    usuario_id: uuid.UUID | None = None,
    modalidad: Modalidad | None = None,
) -> Filtros:
    """`desde`/`hasta` son siempre sobre `gastos.fecha_factura`, inclusivos (RN-07, RN-18)."""
    return Filtros(
        desde=desde,
        hasta=hasta,
        proyecto_id=proyecto_id,
        rubro_id=rubro_id,
        celula_id=celula_id,
        usuario_id=usuario_id,
        modalidad=modalidad,
    )


FiltrosDep = Annotated[Filtros, Depends(_filtros)]


@router.get(
    "/resumen",
    summary="Totales y desgloses por proyecto, rubro, célula, mes y estado (F, A, S)",
)
def resumen(_: Lector, session: DB, filtros: FiltrosDep) -> IndicadoresResumen:
    return service.resumen(session, filtros)


@router.get(
    "/exportar.csv",
    summary="Detalle de gastos en CSV (UTF-8 con BOM, en streaming; F, A, S)",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/csv": {}}, "description": "Un gasto por fila"}},
)
def exportar(
    autenticado: Lector,
    filtros: FiltrosDep,
    fabrica: Annotated[FabricaSesion, Depends(get_fabrica_sesion)],
    separador: Literal[";", ","] = ";",
) -> StreamingResponse:
    # Se valida antes de empezar a enviar: ya con el cuerpo en camino no se puede responder 422.
    validar_rango_fechas(filtros.desde, filtros.hasta)
    usuario = autenticado.usuario
    nombre = f"indicadores-{hoy_colombia():%Y%m%d}.csv"
    return StreamingResponse(
        exportacion.generar(fabrica, usuario.id, usuario.rol, filtros, separador),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre}"',
            # Lleva nombres y montos: ni caché compartida ni almacenamiento en el navegador.
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
