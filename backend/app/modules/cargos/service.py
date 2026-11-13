"""Reglas de cargos (docs/api-design.md §5.2, F-03a).

- Folio `CA-000001` generado por la BD; nombre único sin distinguir mayúsculas entre los no
  eliminados.
- Eliminación **lógica** (`deleted_at`) y solo si ningún usuario (activo o no) tiene el cargo.
- Cada cambio se audita en la misma transacción (`CARGO_*`) y fija `created_by`/`updated_by`.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import AccionAuditoria, registrar
from app.core.errors import Duplicado, EnUso, NoEncontrado, error_de_campo
from app.core.paginacion import ParametrosPagina, orden, paginar, patron_busqueda
from app.modules.auth.service import Contexto
from app.modules.cargos.models import Cargo
from app.modules.cargos.schemas import CargoCrear, CargoEditar
from app.modules.usuarios.models import Usuario

ENTIDAD = "cargos"
OrdenCargos = Literal["nombre", "-nombre", "folio", "-folio", "created_at", "-created_at"]
_COLUMNAS = {"nombre": Cargo.nombre, "folio": Cargo.folio, "created_at": Cargo.created_at}
_NOMBRE_DUPLICADO = "Ya existe un cargo con ese nombre"


def listar(
    session: Session, parametros: ParametrosPagina, q: str | None, sort: OrdenCargos
) -> tuple[Sequence[Cargo], int]:
    consulta = select(Cargo).where(Cargo.deleted_at.is_(None))
    if q and q.strip():
        patron = patron_busqueda(q.strip())
        consulta = consulta.where(or_(Cargo.nombre.ilike(patron), Cargo.folio.ilike(patron)))
    return paginar(session, consulta.order_by(orden(_COLUMNAS, sort), Cargo.id), parametros)


def obtener(session: Session, cargo_id: uuid.UUID) -> Cargo:
    cargo = session.scalar(select(Cargo).where(Cargo.id == cargo_id, Cargo.deleted_at.is_(None)))
    if cargo is None:
        raise NoEncontrado()
    return cargo


def _duplicado() -> Duplicado:
    return Duplicado(errors=error_de_campo("nombre", _NOMBRE_DUPLICADO, "DUPLICADO"))


def _exigir_nombre_libre(session: Session, nombre: str, excluir: uuid.UUID | None = None) -> None:
    consulta = select(Cargo.id).where(
        func.lower(Cargo.nombre) == nombre.lower(), Cargo.deleted_at.is_(None)
    )
    if excluir is not None:
        consulta = consulta.where(Cargo.id != excluir)
    if session.scalar(consulta.limit(1)) is not None:
        raise _duplicado()


def _guardar(session: Session) -> None:
    # Respaldo ante una carrera entre la verificación y el INSERT (índice único parcial).
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise _duplicado() from error


def crear(session: Session, datos: CargoCrear, actor: Usuario, ctx: Contexto) -> Cargo:
    _exigir_nombre_libre(session, datos.nombre)
    cargo = Cargo(
        nombre=datos.nombre,
        descripcion=datos.descripcion or None,
        created_by=actor.id,
        updated_by=actor.id,
    )
    session.add(cargo)
    _guardar(session)
    session.refresh(cargo)  # folio y marcas de tiempo generados por la BD
    _auditar(
        session,
        AccionAuditoria.CARGO_CREAR,
        cargo,
        actor,
        ctx,
        {"folio": cargo.folio, "nombre": cargo.nombre, "descripcion": cargo.descripcion},
    )
    session.commit()
    return cargo


def editar(
    session: Session, cargo_id: uuid.UUID, datos: CargoEditar, actor: Usuario, ctx: Contexto
) -> Cargo:
    cargo = obtener(session, cargo_id)
    cambios = datos.model_dump(exclude_unset=True)
    if "descripcion" in cambios:
        cambios["descripcion"] = cambios["descripcion"] or None
    if cambios.get("nombre") is not None:
        _exigir_nombre_libre(session, cambios["nombre"], excluir=cargo.id)
    antes: dict[str, object] = {}
    despues: dict[str, object] = {}
    for campo, valor in cambios.items():
        if getattr(cargo, campo) != valor:
            antes[campo], despues[campo] = getattr(cargo, campo), valor
            setattr(cargo, campo, valor)
    if despues:
        cargo.updated_by = actor.id
        _guardar(session)
        _auditar(
            session,
            AccionAuditoria.CARGO_EDITAR,
            cargo,
            actor,
            ctx,
            {"antes": antes, "despues": despues},
        )
        session.commit()
        session.refresh(cargo)
    return cargo


def eliminar(session: Session, cargo_id: uuid.UUID, actor: Usuario, ctx: Contexto) -> None:
    cargo = obtener(session, cargo_id)
    if session.scalar(select(exists().where(Usuario.cargo_id == cargo.id))):
        raise EnUso("El cargo está asignado a uno o más usuarios")
    cargo.deleted_at = datetime.now(UTC)
    cargo.updated_by = actor.id
    session.flush()
    _auditar(
        session,
        AccionAuditoria.CARGO_ELIMINAR,
        cargo,
        actor,
        ctx,
        {"folio": cargo.folio, "nombre": cargo.nombre},
    )
    session.commit()


def _auditar(
    session: Session,
    accion: AccionAuditoria,
    cargo: Cargo,
    actor: Usuario,
    ctx: Contexto,
    datos: dict[str, object],
) -> None:
    registrar(
        session,
        accion,
        ENTIDAD,
        cargo.id,
        usuario_id=actor.id,
        datos=datos,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )
