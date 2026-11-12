"""Esquemas de entrada y salida de `/auth` y `/me` (docs/api-design.md §3)."""

import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.enums import Rol

# Límites de tamaño: evitan cuerpos enormes sin revelar la política (que valida el service).
Password = Annotated[str, Field(min_length=1, max_length=256)]
Texto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=254)]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginEntrada(Entrada):
    username: Texto
    password: Password


class GoogleEntrada(Entrada):
    id_token: Annotated[str, Field(min_length=1, max_length=4096)]


class DevLoginEntrada(Entrada):
    correo: Texto


class OlvidePasswordEntrada(Entrada):
    # Username o correo registrado.
    identificador: Texto


class RestablecerPasswordEntrada(Entrada):
    token: Annotated[str, Field(min_length=1, max_length=256)]
    nueva_password: Password


class CambiarPasswordEntrada(Entrada):
    password_actual: Password
    nueva_password: Password


class Referencia(BaseModel):
    id: uuid.UUID
    nombre: str


class UsuarioActualSalida(BaseModel):
    id: uuid.UUID
    nombre_completo: str
    correo: str
    username: str | None
    rol: Rol
    es_prestador_servicios: bool
    debe_cambiar_password: bool
    cargo: Referencia | None
    celula: Referencia | None


class SesionSalida(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    debe_cambiar_password: bool
    usuario: UsuarioActualSalida


class MensajeSalida(BaseModel):
    detail: str
