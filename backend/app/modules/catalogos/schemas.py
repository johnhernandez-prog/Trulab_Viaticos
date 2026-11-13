"""Esquemas de `/catalogos` (docs/api-design.md §5.3, DP-14/DP-20, ADR-022/ADR-030).

- `TipoCatalogo`: los tres catálogos simples (`proyectos`, `rubros`, `celulas`) comparten rutas
  genéricas `/catalogos/{tipo}`. Solo `proyectos` usa `codigo` y `exige_formato_prestador`; el
  service rechaza esos campos para `rubros`/`celulas` (`422 VALOR_NO_PERMITIDO`).
- Dinero (`Dinero`, ADR-012): string en JSON, `Decimal` en Python.
- `extra="forbid"` en todas las entradas.
"""

import uuid
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.core.types import Dinero

TipoCatalogo = Literal["proyectos", "rubros", "celulas"]
TIPOS_CATALOGO: tuple[TipoCatalogo, ...] = ("proyectos", "rubros", "celulas")

Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Codigo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
Ciudad = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]

# Campos que solo aplican a `proyectos`; en `rubros`/`celulas` deben quedar sin enviar.
_SOLO_PROYECTOS = ("codigo", "exige_formato_prestador")


class CatalogoCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Nombre
    orden: int | None = None
    # Solo para `proyectos` (el service valida que no se envíen en los otros tipos).
    codigo: Codigo | None = None
    exige_formato_prestador: bool | None = None

    def campos_no_aplicables(self) -> list[str]:
        return [
            campo
            for campo in _SOLO_PROYECTOS
            if campo in self.model_fields_set and getattr(self, campo) is not None
        ]


class CatalogoEditar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Nombre | None = None
    orden: int | None = None
    codigo: Codigo | None = None
    exige_formato_prestador: bool | None = None

    @model_validator(mode="after")
    def _nombre_no_nulo(self) -> Self:
        if "nombre" in self.model_fields_set and self.nombre is None:
            raise ValueError("El nombre no puede quedar vacío")
        return self

    def campos_no_aplicables(self) -> list[str]:
        return [
            campo
            for campo in _SOLO_PROYECTOS
            if campo in self.model_fields_set and getattr(self, campo) is not None
        ]


class CatalogoResumen(BaseModel):
    """Fila activa para los selectores (`GET /catalogos`, V F A S)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    codigo: str | None = None
    exige_formato_prestador: bool | None = None


class CatalogosSalida(BaseModel):
    proyectos: list[CatalogoResumen]
    rubros: list[CatalogoResumen]
    celulas: list[CatalogoResumen]
    ciudades: list[str]


class CatalogoAdmin(BaseModel):
    """Fila con todo el detalle y el uso, para la administración (`GET /catalogos/{tipo}`, S)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    codigo: str | None = None
    exige_formato_prestador: bool | None = None
    activo: bool
    orden: int | None
    uso: int
    created_at: datetime
    updated_at: datetime


# --- Tarifas de viáticos (DP-20, ADR-030) -------------------------------------------------------


class TarifaCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ciudad: Ciudad
    es_prestador_servicios: bool
    vr_alimentacion: Dinero
    otros_gastos: Dinero
    transporte_aeropuerto: Dinero
    transporte_intermunicipal: Dinero
    trans_interno_dia_1: Dinero
    trans_interno_varios_dias: Dinero
    orden: int | None = None

    @model_validator(mode="after")
    def _montos_no_negativos(self) -> Self:
        for campo in _CONCEPTOS:
            if getattr(self, campo) < 0:
                raise ValueError(f"{campo} no puede ser negativo")
        return self


_CONCEPTOS = (
    "vr_alimentacion",
    "otros_gastos",
    "transporte_aeropuerto",
    "transporte_intermunicipal",
    "trans_interno_dia_1",
    "trans_interno_varios_dias",
)


class TarifaEditar(BaseModel):
    """Solo valores y orden (docs/api-design.md §5.3): `ciudad` y el tipo no se editan."""

    model_config = ConfigDict(extra="forbid")

    vr_alimentacion: Dinero | None = None
    otros_gastos: Dinero | None = None
    transporte_aeropuerto: Dinero | None = None
    transporte_intermunicipal: Dinero | None = None
    trans_interno_dia_1: Dinero | None = None
    trans_interno_varios_dias: Dinero | None = None
    orden: int | None = None

    @model_validator(mode="after")
    def _montos_no_negativos(self) -> Self:
        for campo in _CONCEPTOS:
            valor = getattr(self, campo)
            if valor is not None and valor < 0:
                raise ValueError(f"{campo} no puede ser negativo")
        return self


class TarifaSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ciudad: str
    es_prestador_servicios: bool
    vr_alimentacion: Dinero
    otros_gastos: Dinero
    transporte_aeropuerto: Dinero
    transporte_intermunicipal: Dinero
    trans_interno_dia_1: Dinero
    trans_interno_varios_dias: Dinero
    activo: bool
    orden: int | None
    created_at: datetime
    updated_at: datetime
