"""Rutas de `/catalogos` (docs/api-design.md §5.3).

- Lectura de selectores (`/catalogos`, `/catalogos/tarifas-viaticos`): todos los autenticados o
  solo F A S, según el permiso.
- Gestión (crear, editar, activar/desactivar): solo SUPERADMIN.
- **Orden de registro:** `tarifas-viaticos` se registra antes que `/{tipo}` para que no la
  intercepte como un valor de `tipo` (docs/api-design.md §5.3, nota final).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.core.paginacion import Pagina, Paginacion
from app.core.permissions import Permiso, require_permission
from app.modules.auth.dependencias import DB, Autenticado, Ctx
from app.modules.catalogos import service
from app.modules.catalogos.schemas import (
    CatalogoAdmin,
    CatalogoCrear,
    CatalogoEditar,
    CatalogoResumen,
    CatalogosSalida,
    TarifaCrear,
    TarifaEditar,
    TarifaSalida,
    TipoCatalogo,
)

router = APIRouter(prefix="/catalogos", tags=["catalogos"])

Lector = Annotated[Autenticado, Depends(require_permission(Permiso.CATALOGOS_LEER))]
Gestor = Annotated[Autenticado, Depends(require_permission(Permiso.CATALOGOS_GESTIONAR))]
LectorTarifas = Annotated[Autenticado, Depends(require_permission(Permiso.TARIFAS_LEER))]
GestorTarifas = Annotated[Autenticado, Depends(require_permission(Permiso.TARIFAS_GESTIONAR))]


def _resumenes(session: DB, tipo: TipoCatalogo) -> list[CatalogoResumen]:
    return [CatalogoResumen.model_validate(item) for item in service.listar_activos(session, tipo)]


@router.get("", summary="Catálogos activos para los selectores (todos los roles)")
def listar_combinado(autenticado: Lector, session: DB) -> CatalogosSalida:
    return CatalogosSalida(
        proyectos=_resumenes(session, "proyectos"),
        rubros=_resumenes(session, "rubros"),
        celulas=_resumenes(session, "celulas"),
        ciudades=service.ciudades_activas(session, autenticado.usuario.es_prestador_servicios),
    )


# --- Tarifas de viáticos (registradas antes de `/{tipo}`) ----------------------------------------


@router.get("/tarifas-viaticos", summary="Listar tarifas de viáticos")
def listar_tarifas(
    _: LectorTarifas,
    session: DB,
    paginacion: Paginacion,
    ciudad: str | None = None,
    es_prestador_servicios: bool | None = None,
    activo: bool | None = None,
    sort: service.OrdenTarifas = "ciudad",
) -> Pagina[TarifaSalida]:
    filas, total = service.listar_tarifas(
        session,
        paginacion,
        ciudad=ciudad,
        es_prestador_servicios=es_prestador_servicios,
        activo=activo,
        sort=sort,
    )
    return Pagina[TarifaSalida](
        items=[TarifaSalida.model_validate(t) for t in filas],
        total=total,
        page=paginacion.page,
        size=paginacion.size,
    )


@router.post(
    "/tarifas-viaticos",
    status_code=status.HTTP_201_CREATED,
    summary="Crear tarifa (ciudad + tipo de vinculación)",
)
def crear_tarifa(
    datos: TarifaCrear, autenticado: GestorTarifas, session: DB, ctx: Ctx, response: Response
) -> TarifaSalida:
    tarifa = service.crear_tarifa(session, datos, autenticado.usuario, ctx)
    response.headers["Location"] = f"/api/v1/catalogos/tarifas-viaticos/{tarifa.id}"
    return TarifaSalida.model_validate(tarifa)


@router.get("/tarifas-viaticos/{tarifa_id}", summary="Detalle de una tarifa")
def detalle_tarifa(tarifa_id: uuid.UUID, _: LectorTarifas, session: DB) -> TarifaSalida:
    return TarifaSalida.model_validate(service.obtener_tarifa(session, tarifa_id))


@router.patch(
    "/tarifas-viaticos/{tarifa_id}",
    summary="Editar valores y orden de una tarifa (no afecta solicitudes ya calculadas)",
)
def editar_tarifa(
    tarifa_id: uuid.UUID, datos: TarifaEditar, autenticado: GestorTarifas, session: DB, ctx: Ctx
) -> TarifaSalida:
    return TarifaSalida.model_validate(
        service.editar_tarifa(session, tarifa_id, datos, autenticado.usuario, ctx)
    )


@router.post("/tarifas-viaticos/{tarifa_id}/desactivar", summary="Desactivar tarifa")
def desactivar_tarifa(
    tarifa_id: uuid.UUID, autenticado: GestorTarifas, session: DB, ctx: Ctx
) -> TarifaSalida:
    return TarifaSalida.model_validate(
        service.desactivar_tarifa(session, tarifa_id, autenticado.usuario, ctx)
    )


@router.post("/tarifas-viaticos/{tarifa_id}/activar", summary="Reactivar tarifa")
def activar_tarifa(
    tarifa_id: uuid.UUID, autenticado: GestorTarifas, session: DB, ctx: Ctx
) -> TarifaSalida:
    return TarifaSalida.model_validate(
        service.activar_tarifa(session, tarifa_id, autenticado.usuario, ctx)
    )


# --- Catálogos simples: proyectos, rubros, células (solo SUPERADMIN desde aquí) -------------------


def _admin(item: service.CatalogoModelo, uso: int) -> CatalogoAdmin:
    return CatalogoAdmin(
        id=item.id,
        nombre=item.nombre,
        codigo=getattr(item, "codigo", None),
        exige_formato_prestador=getattr(item, "exige_formato_prestador", None),
        activo=item.activo,
        orden=item.orden,
        uso=uso,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/{tipo}", summary="Listar un catálogo completo, con su uso (solo SUPERADMIN)")
def listar_admin(
    tipo: TipoCatalogo,
    _: Gestor,
    session: DB,
) -> list[CatalogoAdmin]:
    return [_admin(item, uso) for item, uso in service.listar_admin(session, tipo)]


@router.post(
    "/{tipo}",
    status_code=status.HTTP_201_CREATED,
    summary="Crear un valor de catálogo (solo SUPERADMIN)",
)
def crear(
    tipo: TipoCatalogo,
    datos: CatalogoCrear,
    autenticado: Gestor,
    session: DB,
    ctx: Ctx,
    response: Response,
) -> CatalogoResumen:
    item = service.crear(session, tipo, datos, autenticado.usuario, ctx)
    response.headers["Location"] = f"/api/v1/catalogos/{tipo}/{item.id}"
    return CatalogoResumen.model_validate(item)


@router.patch("/{tipo}/{item_id}", summary="Renombrar u ordenar un valor de catálogo")
def editar(
    tipo: TipoCatalogo,
    item_id: uuid.UUID,
    datos: CatalogoEditar,
    autenticado: Gestor,
    session: DB,
    ctx: Ctx,
) -> CatalogoResumen:
    item = service.editar(session, tipo, item_id, datos, autenticado.usuario, ctx)
    return CatalogoResumen.model_validate(item)


@router.post("/{tipo}/{item_id}/desactivar", summary="Desactivar un valor de catálogo (RN-24)")
def desactivar(
    tipo: TipoCatalogo, item_id: uuid.UUID, autenticado: Gestor, session: DB, ctx: Ctx
) -> CatalogoResumen:
    item = service.desactivar(session, tipo, item_id, autenticado.usuario, ctx)
    return CatalogoResumen.model_validate(item)


@router.post("/{tipo}/{item_id}/activar", summary="Reactivar un valor de catálogo")
def activar(
    tipo: TipoCatalogo, item_id: uuid.UUID, autenticado: Gestor, session: DB, ctx: Ctx
) -> CatalogoResumen:
    item = service.activar(session, tipo, item_id, autenticado.usuario, ctx)
    return CatalogoResumen.model_validate(item)
