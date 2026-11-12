"""Fábricas mínimas para las pruebas de BD (siempre dentro del fixture `sesion`)."""

import uuid

from sqlalchemy.orm import Session

from app.core.enums import Rol
from app.modules.cargos.models import Cargo
from app.modules.catalogos.models import Celula
from app.modules.usuarios.models import Usuario


def correo_unico(dominio: str = "trulab.co") -> str:
    return f"prueba-{uuid.uuid4().hex[:12]}@{dominio}"


def crear_usuario(session: Session, **campos: object) -> Usuario:
    valores: dict[str, object] = {
        "nombre_completo": "Ana Pérez",
        "correo": correo_unico(),
        "rol": Rol.VIAJERO,
    }
    valores.update(campos)
    usuario = Usuario(**valores)
    session.add(usuario)
    session.flush()
    return usuario


def crear_cargo(session: Session, nombre: str | None = None) -> Cargo:
    cargo = Cargo(nombre=nombre or f"Cargo {uuid.uuid4().hex[:8]}")
    session.add(cargo)
    session.flush()
    return cargo


def crear_celula(session: Session, nombre: str | None = None) -> Celula:
    celula = Celula(nombre=nombre or f"Célula {uuid.uuid4().hex[:8]}")
    session.add(celula)
    session.flush()
    return celula
