"""Fábricas mínimas para las pruebas de BD (siempre dentro del fixture `sesion`)."""

import uuid

from sqlalchemy.orm import Session

from app.core.enums import Rol
from app.modules.cargos.models import Cargo
from app.modules.catalogos.models import Celula
from app.modules.usuarios.models import Usuario

# Hash Argon2id con formato PHC válido pero ficticio: las pruebas de modelo no necesitan uno real
# (el hashing llega en S1-08) y así no pagan el costo de Argon2.
HASH_FICTICIO = "$argon2id$v=19$m=19456,t=2,p=1$c2FsLWRlLXBydWViYQ$aGFzaC1maWN0aWNpby1kZS1wcnVlYmE"


def correo_unico(dominio: str = "trulab.co") -> str:
    return f"prueba-{uuid.uuid4().hex[:12]}@{dominio}"


def username_unico() -> str:
    return f"prueba.{uuid.uuid4().hex[:12]}"


def crear_usuario(session: Session, **campos: object) -> Usuario:
    """Crea un usuario válido para su rol (ADR-027).

    Los operativos reciben `username` y un `password_hash` ficticio; el SUPERADMIN, ninguno de los
    dos. Pasar `username=None` o `password_hash=None` explícitamente permite probar los `CHECK`.
    """
    valores: dict[str, object] = {
        "nombre_completo": "Ana Pérez",
        "correo": correo_unico(),
        "rol": Rol.VIAJERO,
    }
    valores.update(campos)
    if valores["rol"] != Rol.SUPERADMIN:
        valores.setdefault("username", username_unico())
        valores.setdefault("password_hash", HASH_FICTICIO)
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
