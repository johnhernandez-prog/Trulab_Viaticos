"""Rutas de `/usuarios` (docs/api-design.md §5.1, F-02).

Todas exigen `usuarios:gestionar_operativos` (ADMIN y SUPERADMIN); lo que toca a un SUPERADMIN
lo restringe además el service a SUPERADMIN.

Los correos con la contraseña temporal se envían en segundo plano, después del commit.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status

from app.core.enums import Rol
from app.core.mail import Mailer, enviar_sin_fallar, get_mailer
from app.core.paginacion import Pagina, Paginacion
from app.core.permissions import Permiso, require_permission
from app.modules.auth.dependencias import DB, Autenticado, Config, Ctx
from app.modules.auth.schemas import MensajeSalida
from app.modules.usuarios import service
from app.modules.usuarios.schemas import (
    UsuarioCrear,
    UsuarioDetalle,
    UsuarioEditar,
    UsuarioResumen,
)

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

Gestor = Annotated[Autenticado, Depends(require_permission(Permiso.USUARIOS_GESTIONAR_OPERATIVOS))]
Correos = Annotated[Mailer, Depends(get_mailer)]


def _enviar(tareas: BackgroundTasks, mailer: Mailer, resultado: service.Resultado) -> None:
    for correo in resultado.correos:
        tareas.add_task(enviar_sin_fallar, mailer, correo)


@router.get("", summary="Listar usuarios (sin cédula ni fecha de nacimiento)")
def listar(
    _: Gestor,
    session: DB,
    paginacion: Paginacion,
    q: Annotated[
        str | None, Query(max_length=100, description="Busca en nombre, correo y usuario")
    ] = None,
    rol: Rol | None = None,
    cargo_id: uuid.UUID | None = None,
    celula_id: uuid.UUID | None = None,
    es_prestador_servicios: bool | None = None,
    activo: bool | None = None,
    sort: service.OrdenUsuarios = "nombre_completo",
) -> Pagina[UsuarioResumen]:
    items, total = service.listar(
        session,
        paginacion,
        q=q,
        rol=rol,
        cargo_id=cargo_id,
        celula_id=celula_id,
        es_prestador_servicios=es_prestador_servicios,
        activo=activo,
        sort=sort,
    )
    return Pagina[UsuarioResumen](
        items=items, total=total, page=paginacion.page, size=paginacion.size
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario (operativo con contraseña temporal por correo, o SUPERADMIN)",
)
def crear(
    datos: UsuarioCrear,
    autenticado: Gestor,
    session: DB,
    settings: Config,
    ctx: Ctx,
    response: Response,
    tareas: BackgroundTasks,
    mailer: Correos,
) -> UsuarioDetalle:
    resultado = service.crear(session, datos, autenticado.usuario, settings, ctx)
    _enviar(tareas, mailer, resultado)
    response.headers["Location"] = f"/api/v1/usuarios/{resultado.usuario.id}"
    return service.detalle(session, resultado.usuario)


@router.get("/{usuario_id}", summary="Detalle de un usuario")
def detalle(usuario_id: uuid.UUID, _: Gestor, session: DB) -> UsuarioDetalle:
    return service.detalle(session, service.obtener(session, usuario_id))


@router.patch(
    "/{usuario_id}",
    summary="Editar usuario (cambiar el rol revoca sesiones; promover/degradar SUPERADMIN)",
)
def editar(
    usuario_id: uuid.UUID,
    datos: UsuarioEditar,
    autenticado: Gestor,
    session: DB,
    settings: Config,
    ctx: Ctx,
    tareas: BackgroundTasks,
    mailer: Correos,
) -> UsuarioDetalle:
    resultado = service.editar(session, usuario_id, datos, autenticado.usuario, settings, ctx)
    _enviar(tareas, mailer, resultado)
    return service.detalle(session, resultado.usuario)


@router.post("/{usuario_id}/desactivar", summary="Desactivar usuario (revoca sus sesiones)")
def desactivar(usuario_id: uuid.UUID, autenticado: Gestor, session: DB, ctx: Ctx) -> UsuarioDetalle:
    usuario = service.desactivar(session, usuario_id, autenticado.usuario, ctx)
    return service.detalle(session, usuario)


@router.post("/{usuario_id}/activar", summary="Reactivar usuario")
def activar(usuario_id: uuid.UUID, autenticado: Gestor, session: DB, ctx: Ctx) -> UsuarioDetalle:
    usuario = service.activar(session, usuario_id, autenticado.usuario, ctx)
    return service.detalle(session, usuario)


@router.post(
    "/{usuario_id}/restablecer-password",
    summary="Enviar una contraseña temporal nueva por correo (solo operativos)",
)
def restablecer_password(
    usuario_id: uuid.UUID,
    autenticado: Gestor,
    session: DB,
    settings: Config,
    ctx: Ctx,
    tareas: BackgroundTasks,
    mailer: Correos,
) -> MensajeSalida:
    resultado = service.restablecer_password(
        session, usuario_id, autenticado.usuario, settings, ctx
    )
    _enviar(tareas, mailer, resultado)
    return MensajeSalida(
        detail="Se envió una contraseña temporal al correo del usuario y se cerraron sus sesiones."
    )
