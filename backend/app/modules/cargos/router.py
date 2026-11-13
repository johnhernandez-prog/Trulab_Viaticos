"""Rutas de `/cargos` (docs/api-design.md §5.2). Lectura: F A S; gestión: A S."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.paginacion import Pagina, Paginacion
from app.core.permissions import Permiso, require_permission
from app.modules.auth.dependencias import DB, Autenticado, Ctx
from app.modules.cargos import service
from app.modules.cargos.schemas import CargoCrear, CargoEditar, CargoSalida

router = APIRouter(prefix="/cargos", tags=["cargos"])

Lector = Annotated[Autenticado, Depends(require_permission(Permiso.CARGOS_LEER))]
Gestor = Annotated[Autenticado, Depends(require_permission(Permiso.CARGOS_GESTIONAR))]


@router.get("", summary="Listar cargos")
def listar(
    _: Lector,
    session: DB,
    paginacion: Paginacion,
    q: Annotated[str | None, Query(max_length=100, description="Busca en nombre y folio")] = None,
    sort: service.OrdenCargos = "nombre",
) -> Pagina[CargoSalida]:
    filas, total = service.listar(session, paginacion, q, sort)
    return Pagina[CargoSalida](
        items=[CargoSalida.model_validate(c) for c in filas],
        total=total,
        page=paginacion.page,
        size=paginacion.size,
    )


@router.post("", status_code=status.HTTP_201_CREATED, summary="Crear cargo (folio CA- generado)")
def crear(
    datos: CargoCrear, autenticado: Gestor, session: DB, ctx: Ctx, response: Response
) -> CargoSalida:
    cargo = service.crear(session, datos, autenticado.usuario, ctx)
    response.headers["Location"] = f"/api/v1/cargos/{cargo.id}"
    return CargoSalida.model_validate(cargo)


@router.get("/{cargo_id}", summary="Detalle de un cargo")
def detalle(cargo_id: uuid.UUID, _: Lector, session: DB) -> CargoSalida:
    return CargoSalida.model_validate(service.obtener(session, cargo_id))


@router.patch("/{cargo_id}", summary="Editar cargo")
def editar(
    cargo_id: uuid.UUID, datos: CargoEditar, autenticado: Gestor, session: DB, ctx: Ctx
) -> CargoSalida:
    return CargoSalida.model_validate(
        service.editar(session, cargo_id, datos, autenticado.usuario, ctx)
    )


@router.delete(
    "/{cargo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar cargo (lógico; 409 EN_USO si tiene usuarios)",
)
def eliminar(cargo_id: uuid.UUID, autenticado: Gestor, session: DB, ctx: Ctx) -> None:
    service.eliminar(session, cargo_id, autenticado.usuario, ctx)
