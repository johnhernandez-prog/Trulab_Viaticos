"""Rutas de `/viaticos/{viatico_id}/gastos` (docs/api-design.md §5.5; S2-06)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.permissions import Permiso, require_permission
from app.modules.auth.dependencias import DB, Autenticado
from app.modules.gastos import service
from app.modules.gastos.schemas import GastoCrear, GastoEditar, GastoSalida

router = APIRouter(prefix="/viaticos/{viatico_id}/gastos", tags=["gastos"])

Lector = Annotated[Autenticado, Depends(require_permission(Permiso.VIATICOS_LEER_PROPIOS))]
Gestor = Annotated[Autenticado, Depends(require_permission(Permiso.GASTOS_GESTIONAR_PROPIOS))]


@router.get("", summary="Gastos activos de un viático (dueño, FINANCIERO, ADMIN, SUPERADMIN)")
def listar(viatico_id: uuid.UUID, _: Lector, session: DB) -> list[GastoSalida]:
    return service.listar(session, viatico_id)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un gasto (dueño o SUPERADMIN; legalización PENDIENTE)",
)
def crear(
    viatico_id: uuid.UUID,
    datos: GastoCrear,
    autenticado: Gestor,
    session: DB,
    response: Response,
) -> GastoSalida:
    gasto = service.crear(session, viatico_id, datos, autenticado.usuario)
    response.headers["Location"] = f"/api/v1/viaticos/{viatico_id}/gastos/{gasto.id}"
    return gasto


@router.get("/{gasto_id}", summary="Detalle de un gasto")
def detalle(viatico_id: uuid.UUID, gasto_id: uuid.UUID, _: Lector, session: DB) -> GastoSalida:
    return service.obtener(session, viatico_id, gasto_id)


@router.patch(
    "/{gasto_id}",
    summary="Editar un gasto o reemplazar/quitar sus adjuntos (dueño o SUPERADMIN)",
)
def editar(
    viatico_id: uuid.UUID,
    gasto_id: uuid.UUID,
    datos: GastoEditar,
    autenticado: Gestor,
    session: DB,
) -> GastoSalida:
    return service.editar(session, viatico_id, gasto_id, datos, autenticado.usuario)


@router.delete(
    "/{gasto_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un gasto (lógico; dueño o SUPERADMIN)",
)
def eliminar(viatico_id: uuid.UUID, gasto_id: uuid.UUID, autenticado: Gestor, session: DB) -> None:
    service.eliminar(session, viatico_id, gasto_id, autenticado.usuario)
