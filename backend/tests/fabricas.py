"""Fábricas mínimas para las pruebas de BD (siempre dentro del fixture `sesion`)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import Etapa, Modalidad, PropositoArchivo, Rol
from app.core.security import emitir_access_token
from app.modules.archivos.models import Archivo
from app.modules.auth.models import Sesion
from app.modules.cargos.models import Cargo
from app.modules.catalogos.models import Celula, Proyecto, Rubro, TarifaViatico
from app.modules.gastos.models import Gasto
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.models import Viatico

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


def bearer(session: Session, usuario: Usuario) -> dict[str, str]:
    """Encabezado `Authorization` válido sin pasar por el login (evita el costo de Argon2).

    Crea una sesión vigente en la BD, como haría `/auth/login`.
    """
    registro = Sesion(
        usuario_id=usuario.id,
        token_hash=uuid.uuid4().hex * 2,  # 64 hex, como un SHA-256
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    session.add(registro)
    session.flush()
    token, _ = emitir_access_token(
        usuario_id=usuario.id,
        sesion_id=registro.id,
        rol=usuario.rol,
        cambio_password=usuario.debe_cambiar_password,
        secreto=get_settings().jwt_secret,
        ttl=timedelta(minutes=5),
    )
    return {"Authorization": f"Bearer {token}"}


# --- Catálogos, archivos, viáticos y gastos (S2-02) ---------------------------------------------


def crear_proyecto(session: Session, **campos: object) -> Proyecto:
    valores: dict[str, object] = {"nombre": f"Proyecto {uuid.uuid4().hex[:8]}"}
    valores.update(campos)
    proyecto = Proyecto(**valores)
    session.add(proyecto)
    session.flush()
    return proyecto


def crear_rubro(session: Session, nombre: str | None = None) -> Rubro:
    rubro = Rubro(nombre=nombre or f"Rubro {uuid.uuid4().hex[:8]}")
    session.add(rubro)
    session.flush()
    return rubro


def crear_tarifa(session: Session, **campos: object) -> TarifaViatico:
    valores: dict[str, object] = {
        "ciudad": f"Ciudad {uuid.uuid4().hex[:8]}",
        "es_prestador_servicios": False,
        "vr_alimentacion": Decimal("50000"),
        "otros_gastos": Decimal("10000"),
        "transporte_aeropuerto": Decimal("30000"),
        "transporte_intermunicipal": Decimal("20000"),
        "trans_interno_dia_1": Decimal("15000"),
        "trans_interno_varios_dias": Decimal("25000"),
    }
    valores.update(campos)
    tarifa = TarifaViatico(**valores)
    session.add(tarifa)
    session.flush()
    return tarifa


def crear_archivo(session: Session, **campos: object) -> Archivo:
    valores: dict[str, object] = {
        "storage_key": f"pruebas/{uuid.uuid4()}",
        "nombre_original": "factura.jpg",
        "mime_type": "image/jpeg",
        "tamano_bytes": 1024,
        "sha256": uuid.uuid4().hex * 2,
        "proposito": PropositoArchivo.SOPORTE,
    }
    valores.update(campos)
    archivo = Archivo(**valores)
    session.add(archivo)
    session.flush()
    return archivo


def crear_viatico(
    session: Session,
    usuario: Usuario | None = None,
    modalidad: Modalidad = Modalidad.LEGALIZACION_DIRECTA,
    **campos: object,
) -> Viatico:
    """Viático mínimo válido para su modalidad (instantánea del colaborador incluida)."""
    usuario = usuario or crear_usuario(session)
    valores: dict[str, object] = {
        "modalidad": modalidad,
        "etapa": Etapa.SOLICITUD if modalidad == Modalidad.CON_SOLICITUD else Etapa.LEGALIZACION,
        "usuario_id": usuario.id,
        "motivo_viaje": "Taller de campo",
        "colaborador_nombre": usuario.nombre_completo,
        "colaborador_es_prestador": usuario.es_prestador_servicios,
    }
    if modalidad == Modalidad.CON_SOLICITUD:
        valores.update(proyecto_otro="Proyecto de prueba", lider_proyecto="María Gómez")
    valores.update(campos)
    viatico = Viatico(**valores)
    session.add(viatico)
    session.flush()
    return viatico


def crear_gasto(session: Session, viatico: Viatico, **campos: object) -> Gasto:
    valores: dict[str, object] = {
        "viatico_id": viatico.id,
        "fecha_factura": date(2026, 11, 5),
        "concepto": "Almuerzo",
        "valor": Decimal("50000"),
        "proyecto_otro": "Proyecto de prueba",
    }
    valores.update(campos)
    if "rubro_id" not in valores:
        valores["rubro_id"] = crear_rubro(session).id
    gasto = Gasto(**valores)
    session.add(gasto)
    session.flush()
    return gasto
