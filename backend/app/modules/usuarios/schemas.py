"""Esquemas de `/usuarios` (docs/api-design.md §5.1).

- Entradas con `extra="forbid"`: la API nunca acepta `password`, `password_hash`,
  `debe_cambiar_password`, `google_sub` ni `activo` (estos dos últimos tienen acciones propias).
- El listado (`UsuarioResumen`) no lleva cédula ni fecha de nacimiento; el detalle sí.
- Ninguna salida expone `password_hash` ni `google_sub`.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints, model_validator

from app.core.enums import Rol
from app.modules.auth.schemas import Referencia


def _normalizar(valor: object) -> object:
    # Antes del patrón: pydantic comprueba `pattern` sin aplicar antes `to_lower`.
    return valor.strip().lower() if isinstance(valor, str) else valor


Nombre = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Correo = Annotated[
    str,
    BeforeValidator(_normalizar),
    StringConstraints(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
]
# Mismo formato que `ck_usuarios__username_formato`; se normaliza a minúsculas.
Username = Annotated[
    str, BeforeValidator(_normalizar), StringConstraints(pattern=r"^[a-z0-9._-]{3,40}$")
]
Cedula = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=20)]

# Campos que, si se envían en un PATCH, no pueden ser `null`.
_NO_NULABLES = ("nombre_completo", "correo", "rol", "es_prestador_servicios")


class UsuarioCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre_completo: Nombre
    correo: Correo
    # Obligatorio para operativos; un SUPERADMIN no lleva (entra con Google, ADR-027).
    username: Username | None = None
    rol: Rol
    cargo_id: uuid.UUID | None = None
    celula_id: uuid.UUID | None = None
    cedula: Cedula | None = None
    es_prestador_servicios: bool = False
    fecha_nacimiento: date | None = None

    @model_validator(mode="after")
    def _username_de_operativo(self) -> Self:
        if self.rol != Rol.SUPERADMIN and self.username is None:
            raise ValueError("Los usuarios operativos necesitan un nombre de usuario")
        return self


class UsuarioEditar(BaseModel):
    """Edición parcial: solo cambian los campos enviados (`null` limpia los opcionales).

    Cambiar el `rol` revoca las sesiones. Promover a SUPERADMIN borra usuario y contraseña;
    degradar a un SUPERADMIN exige `username` y genera una contraseña temporal.
    """

    model_config = ConfigDict(extra="forbid")

    nombre_completo: Nombre | None = None
    correo: Correo | None = None
    username: Username | None = None
    rol: Rol | None = None
    cargo_id: uuid.UUID | None = None
    celula_id: uuid.UUID | None = None
    cedula: Cedula | None = None
    es_prestador_servicios: bool | None = None
    fecha_nacimiento: date | None = None

    @model_validator(mode="after")
    def _sin_nulos_obligatorios(self) -> Self:
        nulos = [c for c in _NO_NULABLES if c in self.model_fields_set and getattr(self, c) is None]
        if nulos:
            raise ValueError(f"Estos campos no pueden ser nulos: {', '.join(nulos)}")
        return self


class UsuarioResumen(BaseModel):
    id: uuid.UUID
    nombre_completo: str
    correo: str
    username: str | None
    rol: Rol
    cargo: Referencia | None
    celula: Referencia | None
    es_prestador_servicios: bool
    activo: bool
    debe_cambiar_password: bool
    bloqueado: bool
    ultimo_acceso: datetime | None
    created_at: datetime


class UsuarioDetalle(UsuarioResumen):
    cedula: str | None
    fecha_nacimiento: date | None
    updated_at: datetime
