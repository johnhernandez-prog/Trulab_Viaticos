"""Reglas de catálogos (DP-14, ADR-022) y tarifas de viáticos (DP-20, ADR-030).

- `proyectos`, `rubros` y `celulas` comparten servicio genérico por `TipoCatalogo`; solo
  `proyectos` acepta `codigo` y `exige_formato_prestador`.
- **Sin eliminación**: los catálogos y las tarifas se desactivan (RN-24); no hay `DELETE`. El
  "uso" que expone `GET /catalogos/{tipo}` (solo SUPERADMIN) es informativo.
- Toda escritura es de SUPERADMIN (`catalogos:gestionar` / `tarifas:gestionar`) y se audita.
"""

import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Literal, cast

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import AccionAuditoria, registrar
from app.core.errors import Duplicado, NoEncontrado, ValorNoPermitido, error_de_campo
from app.core.paginacion import ParametrosPagina, orden, paginar, patron_busqueda
from app.modules.auth.service import Contexto
from app.modules.catalogos.models import CONCEPTOS_TARIFA, Celula, Proyecto, Rubro, TarifaViatico
from app.modules.catalogos.schemas import CatalogoCrear, CatalogoEditar, TarifaCrear, TarifaEditar
from app.modules.gastos.models import Gasto
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.models import Viatico

ENTIDAD_CATALOGO = "catalogos"
ENTIDAD_TARIFA = "tarifas_viaticos"

CatalogoModelo = Proyecto | Rubro | Celula

_MODELOS: dict[str, type[CatalogoModelo]] = {
    "proyectos": Proyecto,
    "rubros": Rubro,
    "celulas": Celula,
}


def _modelo(tipo: str) -> type[CatalogoModelo]:
    return _MODELOS[tipo]


def _es_proyecto(tipo: str) -> bool:
    return tipo == "proyectos"


# --- lectura: selectores (GET /catalogos, todos los roles autenticados) -------------------------


def listar_activos(session: Session, tipo: str) -> Sequence[CatalogoModelo]:
    modelo = _modelo(tipo)
    consulta = select(modelo).where(modelo.activo).order_by(modelo.orden, func.lower(modelo.nombre))
    return cast("Sequence[CatalogoModelo]", session.scalars(consulta).all())


def ciudades_activas(session: Session, es_prestador_servicios: bool) -> list[str]:
    consulta = (
        select(TarifaViatico.ciudad)
        .where(
            TarifaViatico.activo,
            TarifaViatico.es_prestador_servicios == es_prestador_servicios,
        )
        .order_by(TarifaViatico.orden, func.lower(TarifaViatico.ciudad))
    )
    return list(session.scalars(consulta).all())


# --- lectura y gestión administrativa (SUPERADMIN) -----------------------------------------------


def _uso_expr(tipo: str, modelo: type[CatalogoModelo]) -> Any:
    if tipo == "proyectos":
        viaticos = (
            select(func.count())
            .where(Viatico.proyecto_id == modelo.id)
            .correlate(modelo)
            .scalar_subquery()
        )
        gastos = (
            select(func.count())
            .where(Gasto.proyecto_id == modelo.id, Gasto.deleted_at.is_(None))
            .correlate(modelo)
            .scalar_subquery()
        )
        return viaticos + gastos
    if tipo == "rubros":
        return (
            select(func.count())
            .where(Gasto.rubro_id == modelo.id, Gasto.deleted_at.is_(None))
            .correlate(modelo)
            .scalar_subquery()
        )
    # celulas: cuenta todos los usuarios, activos o no (igual que `cargos`, F-03a).
    return (
        select(func.count())
        .where(Usuario.celula_id == modelo.id)
        .correlate(modelo)
        .scalar_subquery()
    )


def listar_admin(session: Session, tipo: str) -> list[tuple[CatalogoModelo, int]]:
    modelo = _modelo(tipo)
    uso = _uso_expr(tipo, modelo)
    consulta = select(modelo, uso.label("uso")).order_by(modelo.orden, func.lower(modelo.nombre))
    return [(fila, usos) for fila, usos in session.execute(consulta).all()]


def obtener(session: Session, tipo: str, item_id: uuid.UUID) -> CatalogoModelo:
    modelo = _modelo(tipo)
    item = session.scalar(select(modelo).where(modelo.id == item_id))
    if item is None:
        raise NoEncontrado()
    return cast("CatalogoModelo", item)


def _duplicado_nombre() -> Duplicado:
    return Duplicado(errors=error_de_campo("nombre", "Ya existe un registro con ese nombre"))


def _duplicado_codigo() -> Duplicado:
    return Duplicado(errors=error_de_campo("codigo", "Ya existe un proyecto con ese código"))


def _exigir_nombre_libre(
    session: Session, modelo: type[CatalogoModelo], nombre: str, excluir: uuid.UUID | None = None
) -> None:
    consulta = select(modelo.id).where(func.lower(modelo.nombre) == nombre.lower())
    if excluir is not None:
        consulta = consulta.where(modelo.id != excluir)
    if session.scalar(consulta.limit(1)) is not None:
        raise _duplicado_nombre()


def _exigir_codigo_libre(session: Session, codigo: str, excluir: uuid.UUID | None = None) -> None:
    consulta = select(Proyecto.id).where(func.lower(Proyecto.codigo) == codigo.lower())
    if excluir is not None:
        consulta = consulta.where(Proyecto.id != excluir)
    if session.scalar(consulta.limit(1)) is not None:
        raise _duplicado_codigo()


def _exigir_campos_aplicables(tipo: str, campos_no_aplicables: list[str]) -> None:
    if not _es_proyecto(tipo) and campos_no_aplicables:
        campo = campos_no_aplicables[0]
        raise ValorNoPermitido(errors=error_de_campo(campo, f"'{campo}' solo aplica a proyectos"))


def _guardar(session: Session, duplicado: Duplicado) -> None:
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise duplicado from error


def crear(
    session: Session, tipo: str, datos: CatalogoCrear, actor: Usuario, ctx: Contexto
) -> CatalogoModelo:
    _exigir_campos_aplicables(tipo, datos.campos_no_aplicables())
    modelo = _modelo(tipo)
    _exigir_nombre_libre(session, modelo, datos.nombre)
    valores: dict[str, Any] = {
        "nombre": datos.nombre,
        "orden": datos.orden,
        "created_by": actor.id,
        "updated_by": actor.id,
    }
    if _es_proyecto(tipo):
        if datos.codigo is not None:
            _exigir_codigo_libre(session, datos.codigo)
        valores["codigo"] = datos.codigo
        valores["exige_formato_prestador"] = bool(datos.exige_formato_prestador)
    item = modelo(**valores)
    session.add(item)
    _guardar(session, _duplicado_nombre())
    session.refresh(item)
    _auditar(
        session,
        AccionAuditoria.CATALOGO_CREAR,
        tipo,
        item.id,
        actor,
        ctx,
        {"tipo": tipo, "nombre": item.nombre},
    )
    session.commit()
    return item


def editar(
    session: Session,
    tipo: str,
    item_id: uuid.UUID,
    datos: CatalogoEditar,
    actor: Usuario,
    ctx: Contexto,
) -> CatalogoModelo:
    _exigir_campos_aplicables(tipo, datos.campos_no_aplicables())
    item = obtener(session, tipo, item_id)
    cambios = datos.model_dump(exclude_unset=True, exclude={"codigo", "exige_formato_prestador"})
    if _es_proyecto(tipo):
        if "codigo" in datos.model_fields_set:
            cambios["codigo"] = datos.codigo
        if "exige_formato_prestador" in datos.model_fields_set:
            cambios["exige_formato_prestador"] = bool(datos.exige_formato_prestador)

    if cambios.get("nombre") is not None:
        _exigir_nombre_libre(session, _modelo(tipo), cambios["nombre"], excluir=item.id)
    if cambios.get("codigo") is not None:
        _exigir_codigo_libre(session, cambios["codigo"], excluir=item.id)

    antes: dict[str, object] = {}
    despues: dict[str, object] = {}
    for campo, valor in cambios.items():
        if getattr(item, campo) != valor:
            antes[campo], despues[campo] = getattr(item, campo), valor
            setattr(item, campo, valor)
    if despues:
        item.updated_by = actor.id
        _guardar(session, _duplicado_nombre())
        _auditar(
            session,
            AccionAuditoria.CATALOGO_EDITAR,
            tipo,
            item.id,
            actor,
            ctx,
            {"tipo": tipo, "antes": antes, "despues": despues},
        )
        session.commit()
        session.refresh(item)
    return item


def desactivar(
    session: Session, tipo: str, item_id: uuid.UUID, actor: Usuario, ctx: Contexto
) -> CatalogoModelo:
    item = obtener(session, tipo, item_id)
    if not item.activo:
        return item
    item.activo = False
    item.updated_by = actor.id
    session.flush()
    _auditar(
        session,
        AccionAuditoria.CATALOGO_DESACTIVAR,
        tipo,
        item.id,
        actor,
        ctx,
        {"tipo": tipo, "nombre": item.nombre},
    )
    session.commit()
    session.refresh(item)
    return item


def activar(
    session: Session, tipo: str, item_id: uuid.UUID, actor: Usuario, ctx: Contexto
) -> CatalogoModelo:
    item = obtener(session, tipo, item_id)
    if item.activo:
        return item
    item.activo = True
    item.updated_by = actor.id
    session.flush()
    _auditar(
        session,
        AccionAuditoria.CATALOGO_ACTIVAR,
        tipo,
        item.id,
        actor,
        ctx,
        {"tipo": tipo, "nombre": item.nombre},
    )
    session.commit()
    session.refresh(item)
    return item


def _auditar(
    session: Session,
    accion: AccionAuditoria,
    tipo: str,
    item_id: uuid.UUID,
    actor: Usuario,
    ctx: Contexto,
    datos: dict[str, object],
) -> None:
    registrar(
        session,
        accion,
        ENTIDAD_CATALOGO,
        item_id,
        usuario_id=actor.id,
        datos=datos,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


# =================================================================================================
# Tarifas de viáticos (DP-20, ADR-030)
# =================================================================================================

OrdenTarifas = Literal["ciudad", "-ciudad", "created_at", "-created_at"]
_COLUMNAS_TARIFA = {"ciudad": TarifaViatico.ciudad, "created_at": TarifaViatico.created_at}


def listar_tarifas(
    session: Session,
    parametros: ParametrosPagina,
    *,
    ciudad: str | None = None,
    es_prestador_servicios: bool | None = None,
    activo: bool | None = None,
    sort: OrdenTarifas = "ciudad",
) -> tuple[Sequence[TarifaViatico], int]:
    consulta = select(TarifaViatico)
    if ciudad and ciudad.strip():
        consulta = consulta.where(TarifaViatico.ciudad.ilike(patron_busqueda(ciudad.strip())))
    if es_prestador_servicios is not None:
        consulta = consulta.where(TarifaViatico.es_prestador_servicios == es_prestador_servicios)
    if activo is not None:
        consulta = consulta.where(TarifaViatico.activo == activo)
    consulta = consulta.order_by(orden(_COLUMNAS_TARIFA, sort), TarifaViatico.id)
    return paginar(session, consulta, parametros)


def obtener_tarifa(session: Session, tarifa_id: uuid.UUID) -> TarifaViatico:
    tarifa = session.scalar(select(TarifaViatico).where(TarifaViatico.id == tarifa_id))
    if tarifa is None:
        raise NoEncontrado()
    return tarifa


def _duplicado_tarifa() -> Duplicado:
    return Duplicado(
        errors=error_de_campo("ciudad", "Ya existe una tarifa para esa ciudad y ese tipo")
    )


def _exigir_tarifa_libre(
    session: Session, ciudad: str, es_prestador_servicios: bool, excluir: uuid.UUID | None = None
) -> None:
    consulta = select(TarifaViatico.id).where(
        func.lower(TarifaViatico.ciudad) == ciudad.lower(),
        TarifaViatico.es_prestador_servicios == es_prestador_servicios,
    )
    if excluir is not None:
        consulta = consulta.where(TarifaViatico.id != excluir)
    if session.scalar(consulta.limit(1)) is not None:
        raise _duplicado_tarifa()


def _guardar_tarifa(session: Session) -> None:
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise _duplicado_tarifa() from error


def crear_tarifa(
    session: Session, datos: TarifaCrear, actor: Usuario, ctx: Contexto
) -> TarifaViatico:
    _exigir_tarifa_libre(session, datos.ciudad, datos.es_prestador_servicios)
    campos = datos.model_dump()
    tarifa = TarifaViatico(**campos, created_by=actor.id, updated_by=actor.id)
    session.add(tarifa)
    _guardar_tarifa(session)
    session.refresh(tarifa)
    _auditar_tarifa(
        session,
        AccionAuditoria.TARIFA_CREAR,
        tarifa,
        actor,
        ctx,
        {"ciudad": tarifa.ciudad, "es_prestador_servicios": tarifa.es_prestador_servicios},
    )
    session.commit()
    return tarifa


def editar_tarifa(
    session: Session, tarifa_id: uuid.UUID, datos: TarifaEditar, actor: Usuario, ctx: Contexto
) -> TarifaViatico:
    tarifa = obtener_tarifa(session, tarifa_id)
    cambios = datos.model_dump(exclude_unset=True)
    antes: dict[str, object] = {}
    despues: dict[str, object] = {}
    for campo, valor in cambios.items():
        actual = getattr(tarifa, campo)
        if campo in CONCEPTOS_TARIFA:
            valor_comparado: object = Decimal(valor)
        else:
            valor_comparado = valor
        if actual != valor_comparado:
            antes[campo] = str(actual) if isinstance(actual, Decimal) else actual
            despues[campo] = str(valor_comparado) if isinstance(valor_comparado, Decimal) else valor
            setattr(tarifa, campo, valor_comparado)
    if despues:
        tarifa.updated_by = actor.id
        session.flush()
        _auditar_tarifa(
            session,
            AccionAuditoria.TARIFA_EDITAR,
            tarifa,
            actor,
            ctx,
            {"antes": antes, "despues": despues},
        )
        session.commit()
        session.refresh(tarifa)
    return tarifa


def desactivar_tarifa(
    session: Session, tarifa_id: uuid.UUID, actor: Usuario, ctx: Contexto
) -> TarifaViatico:
    tarifa = obtener_tarifa(session, tarifa_id)
    if not tarifa.activo:
        return tarifa
    tarifa.activo = False
    tarifa.updated_by = actor.id
    session.flush()
    _auditar_tarifa(
        session, AccionAuditoria.TARIFA_DESACTIVAR, tarifa, actor, ctx, {"ciudad": tarifa.ciudad}
    )
    session.commit()
    session.refresh(tarifa)
    return tarifa


def activar_tarifa(
    session: Session, tarifa_id: uuid.UUID, actor: Usuario, ctx: Contexto
) -> TarifaViatico:
    tarifa = obtener_tarifa(session, tarifa_id)
    if tarifa.activo:
        return tarifa
    tarifa.activo = True
    tarifa.updated_by = actor.id
    session.flush()
    _auditar_tarifa(
        session, AccionAuditoria.TARIFA_ACTIVAR, tarifa, actor, ctx, {"ciudad": tarifa.ciudad}
    )
    session.commit()
    session.refresh(tarifa)
    return tarifa


def _auditar_tarifa(
    session: Session,
    accion: AccionAuditoria,
    tarifa: TarifaViatico,
    actor: Usuario,
    ctx: Contexto,
    datos: dict[str, object],
) -> None:
    registrar(
        session,
        accion,
        ENTIDAD_TARIFA,
        tarifa.id,
        usuario_id=actor.id,
        datos=datos,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )
