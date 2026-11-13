"""Rutas de `/viaticos` (docs/api-design.md §5.4). Alcance de S2-04a: cálculo tarifario, creación
en ambas modalidades y lectura individual. La máquina de estados llega en S2-05.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.permissions import Permiso, require_permission
from app.modules.auth.dependencias import DB, Autenticado
from app.modules.viaticos import service
from app.modules.viaticos.schemas import (
    CalcularPresupuestoEntrada,
    CalculoPresupuestoSalida,
    TrayectoSalida,
    ViaticoCrear,
    ViaticoDetalle,
)

router = APIRouter(prefix="/viaticos", tags=["viaticos"])

Creador = Annotated[Autenticado, Depends(require_permission(Permiso.VIATICOS_CREAR))]
Calculador = Annotated[
    Autenticado, Depends(require_permission(Permiso.VIATICOS_CALCULAR_PRESUPUESTO))
]
Lector = Annotated[Autenticado, Depends(require_permission(Permiso.VIATICOS_LEER_PROPIOS))]


@router.post(
    "/calcular-presupuesto",
    summary="Vista previa del presupuesto tarifario, sin guardar (RN-29)",
)
def calcular_presupuesto(
    datos: CalcularPresupuestoEntrada, autenticado: Calculador, session: DB
) -> CalculoPresupuestoSalida:
    resultado = service.calcular_presupuesto_preview(session, autenticado.usuario, datos)
    return CalculoPresupuestoSalida(
        aplica=resultado.aplica,
        motivo_no_aplica=resultado.motivo_no_aplica,
        trayectos=[TrayectoSalida.model_validate(t) for t in resultado.trayectos],
        presupuesto_solicitado=resultado.presupuesto_solicitado,
        exige_formato_prestador=resultado.exige_formato_prestador,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Crear un viático: CON_SOLICITUD o LEGALIZACION_DIRECTA (ADR-029)",
)
def crear(
    datos: ViaticoCrear, autenticado: Creador, session: DB, response: Response
) -> ViaticoDetalle:
    viatico = service.crear(session, datos, autenticado.usuario)
    response.headers["Location"] = f"/api/v1/viaticos/{viatico.id}"
    return service.detalle(session, viatico)


@router.get("/{viatico_id}", summary="Detalle de un viático (dueño, FINANCIERO, ADMIN, SUPERADMIN)")
def detalle(viatico_id: uuid.UUID, _: Lector, session: DB) -> ViaticoDetalle:
    return service.detalle(session, service.obtener(session, viatico_id))
