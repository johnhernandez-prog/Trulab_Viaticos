"""Colecciones paginadas: `{items, total, page, size}` (docs/api-design.md §6).

`page` empieza en 1; `size` es 20 por defecto y como máximo 100. El orden (`sort`) lo declara cada
ruta como una lista cerrada de valores (`Literal`), para no ordenar por columnas arbitrarias.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Annotated, Any, Generic, TypeVar

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import Select, UnaryExpression, func, select
from sqlalchemy.orm import QueryableAttribute, Session

TAMANO_POR_DEFECTO = 20
TAMANO_MAXIMO = 100

T = TypeVar("T")
M = TypeVar("M")


# Generic con TypeVar: es la forma que pydantic documenta para modelos genéricos.
class Pagina(BaseModel, Generic[T]):  # noqa: UP046
    items: list[T]
    total: int
    page: int
    size: int


@dataclass(frozen=True)
class ParametrosPagina:
    page: int
    size: int

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size


def _parametros(
    page: Annotated[int, Query(ge=1, description="Página, desde 1")] = 1,
    size: Annotated[
        int, Query(ge=1, le=TAMANO_MAXIMO, description="Tamaño de página (máx. 100)")
    ] = TAMANO_POR_DEFECTO,
) -> ParametrosPagina:
    return ParametrosPagina(page=page, size=size)


Paginacion = Annotated[ParametrosPagina, Depends(_parametros)]


def paginar(  # noqa: UP047
    session: Session, consulta: Select[tuple[M]], parametros: ParametrosPagina
) -> tuple[Sequence[M], int]:
    """Ejecuta `consulta` (ya filtrada y ordenada) para una página; devuelve filas y total."""
    total = session.scalar(select(func.count()).select_from(consulta.order_by(None).subquery()))
    filas = session.scalars(consulta.limit(parametros.size).offset(parametros.offset)).all()
    return filas, total or 0


def orden(columnas: Mapping[str, QueryableAttribute[Any]], sort: str) -> UnaryExpression[Any]:
    """Traduce `campo` / `-campo` a la columna con su dirección."""
    columna = columnas[sort.removeprefix("-")]
    return columna.desc() if sort.startswith("-") else columna.asc()


def patron_busqueda(texto: str) -> str:
    """Patrón `ILIKE` que trata `%`, `_` y `\\` del usuario como texto literal."""
    escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escapado}%"
