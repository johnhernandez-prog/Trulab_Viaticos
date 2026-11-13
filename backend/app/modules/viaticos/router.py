"""Rutas de `/viaticos` (docs/api-design.md §5.4): cálculo tarifario, creación en ambas
modalidades, listado paginado, edición/eliminación en `PENDIENTE` y la máquina de estados
operativa (`aprobar`, `rechazar`, `devolver`, `habilitar-legalizacion`).
"""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.enums import EstadoFinanciero, EstadoOperativo, Etapa, Modalidad
from app.core.paginacion import Pagina, Paginacion
from app.core.permissions import Permiso, require_permission
from app.modules.auth.dependencias import DB, Autenticado, Ctx
from app.modules.viaticos import service
from app.modules.viaticos.schemas import (
    AccionEntrada,
    CalcularPresupuestoEntrada,
    CalculoPresupuestoSalida,
    TrayectoSalida,
    ViaticoCrear,
    ViaticoDetalle,
    ViaticoEditar,
    ViaticoResumen,
)

router = APIRouter(prefix="/viaticos", tags=["viaticos"])

Creador = Annotated[Autenticado, Depends(require_permission(Permiso.VIATICOS_CREAR))]
Calculador = Annotated[
    Autenticado, Depends(require_permission(Permiso.VIATICOS_CALCULAR_PRESUPUESTO))
]
Lector = Annotated[Autenticado, Depends(require_permission(Permiso.VIATICOS_LEER_PROPIOS))]
Aprobador = Annotated[Autenticado, Depends(require_permission(Permiso.VIATICOS_APROBAR))]
Rechazador = Annotated[Autenticado, Depends(require_permission(Permiso.VIATICOS_RECHAZAR))]
Devolvedor = Annotated[Autenticado, Depends(require_permission(Permiso.VIATICOS_DEVOLVER))]
Habilitador = Annotated[
    Autenticado, Depends(require_permission(Permiso.VIATICOS_HABILITAR_LEGALIZACION))
]


@router.get(
    "", summary="Listar viáticos (propios para VIAJERO; todos para FINANCIERO/ADMIN/SUPERADMIN)"
)
def listar(
    autenticado: Lector,
    session: DB,
    paginacion: Paginacion,
    etapa: Etapa | None = None,
    estado: EstadoOperativo | None = None,
    estado_financiero: EstadoFinanciero | None = None,
    modalidad: Modalidad | None = None,
    proyecto_id: uuid.UUID | None = None,
    usuario_id: uuid.UUID | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Busca en folio y motivo")] = None,
) -> Pagina[ViaticoResumen]:
    items, total = service.listar(
        session,
        autenticado.usuario,
        paginacion,
        etapa=etapa,
        estado=estado,
        estado_financiero=estado_financiero,
        modalidad=modalidad,
        proyecto_id=proyecto_id,
        usuario_id=usuario_id,
        desde=desde,
        hasta=hasta,
        q=q,
    )
    return Pagina[ViaticoResumen](
        items=items, total=total, page=paginacion.page, size=paginacion.size
    )


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
    return service.detalle(session, viatico, autenticado.usuario)


@router.get("/{viatico_id}", summary="Detalle de un viático (dueño, FINANCIERO, ADMIN, SUPERADMIN)")
def detalle(viatico_id: uuid.UUID, autenticado: Lector, session: DB) -> ViaticoDetalle:
    viatico = service.obtener(session, viatico_id)
    return service.detalle(session, viatico, autenticado.usuario)


@router.patch(
    "/{viatico_id}",
    summary="Editar un viático (dueño o SUPERADMIN, solo PENDIENTE/PENDIENTE; RN-09, S-05)",
)
def editar(
    viatico_id: uuid.UUID, datos: ViaticoEditar, autenticado: Creador, session: DB
) -> ViaticoDetalle:
    viatico = service.editar(session, viatico_id, datos, autenticado.usuario)
    return service.detalle(session, viatico, autenticado.usuario)


@router.delete(
    "/{viatico_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un viático (lógico; dueño o SUPERADMIN, solo PENDIENTE/PENDIENTE; RN-09)",
)
def eliminar(viatico_id: uuid.UUID, autenticado: Creador, session: DB, ctx: Ctx) -> None:
    service.eliminar(session, viatico_id, autenticado.usuario, ctx)


@router.post(
    "/{viatico_id}/aprobar",
    summary="Aprobar un viático (ADMIN, SUPERADMIN; RN-06, RN-21, RN-27)",
)
def aprobar(
    viatico_id: uuid.UUID, datos: AccionEntrada, autenticado: Aprobador, session: DB, ctx: Ctx
) -> ViaticoDetalle:
    viatico = service.aprobar(session, viatico_id, autenticado.usuario, datos.comentario, ctx)
    return service.detalle(session, viatico, autenticado.usuario)


@router.post(
    "/{viatico_id}/rechazar",
    summary="Rechazar un viático, estado final (ADMIN, SUPERADMIN; RN-27)",
)
def rechazar(
    viatico_id: uuid.UUID, datos: AccionEntrada, autenticado: Rechazador, session: DB, ctx: Ctx
) -> ViaticoDetalle:
    viatico = service.rechazar(session, viatico_id, autenticado.usuario, datos.comentario, ctx)
    return service.detalle(session, viatico, autenticado.usuario)


@router.post(
    "/{viatico_id}/devolver",
    summary="Devolver un viático a PENDIENTE (ADMIN, SUPERADMIN; RN-20, RN-27)",
)
def devolver(
    viatico_id: uuid.UUID, datos: AccionEntrada, autenticado: Devolvedor, session: DB, ctx: Ctx
) -> ViaticoDetalle:
    viatico = service.devolver(session, viatico_id, autenticado.usuario, datos.comentario, ctx)
    return service.detalle(session, viatico, autenticado.usuario)


@router.post(
    "/{viatico_id}/habilitar-legalizacion",
    summary="Pasar la solicitud aprobada a la etapa LEGALIZACION (dueño, SUPERADMIN; RN-28)",
)
def habilitar_legalizacion(
    viatico_id: uuid.UUID, autenticado: Habilitador, session: DB
) -> ViaticoDetalle:
    viatico = service.habilitar_legalizacion(session, viatico_id, autenticado.usuario)
    return service.detalle(session, viatico, autenticado.usuario)
