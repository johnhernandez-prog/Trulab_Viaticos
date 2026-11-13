"""Esquemas de `/cargos` (docs/api-design.md §5.2)."""

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]
Descripcion = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


class CargoCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Nombre
    descripcion: Descripcion | None = None


class CargoEditar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: Nombre | None = None
    descripcion: Descripcion | None = None

    @model_validator(mode="after")
    def _nombre_no_nulo(self) -> Self:
        if "nombre" in self.model_fields_set and self.nombre is None:
            raise ValueError("El nombre no puede quedar vacío")
        return self


class CargoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    folio: str
    nombre: str
    descripcion: str | None
    created_at: datetime
    updated_at: datetime
