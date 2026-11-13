"""Reglas de negocio de usuarios (RN-11, RN-12, S-13; ADR-027; docs/api-design.md §5.1, F-02).

- SUPERADMIN inicial desde la configuración (seed, S1-07).
- Gestión (S1-10): alta de operativos con **contraseña temporal** que solo viaja por correo
  (`debe_cambiar_password = true`; ADMIN no la ve); alta y promoción de SUPERADMIN solo por un
  SUPERADMIN y con correo del dominio corporativo (sin usuario ni contraseña); degradación con
  usuario nuevo y contraseña temporal; nunca se desactiva ni degrada al **último SUPERADMIN
  activo** (con bloqueo `FOR UPDATE` de las filas de SUPERADMIN para que dos peticiones
  simultáneas no lo dejen en cero); cambiar el rol, desactivar o restablecer la contraseña
  revocan las sesiones.
- Todo cambio se audita en la misma transacción, sin secretos y con la cédula enmascarada.
  Las funciones de gestión hacen `commit` y devuelven los correos a enviar después.
"""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from html import escape
from typing import Any, Literal

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import AccionAuditoria, registrar
from app.core.config import Settings
from app.core.enums import Rol
from app.core.errors import Duplicado, NoEncontrado, ValorNoPermitido, error_de_campo
from app.core.mail import Correo
from app.core.paginacion import ParametrosPagina, orden, paginar, patron_busqueda
from app.core.permissions import Permiso, SinPermiso, tiene_permiso
from app.core.security import hash_password, password_temporal
from app.modules.auth.schemas import Referencia
from app.modules.auth.service import Contexto, invalidar_tokens_recuperacion, revocar_sesiones
from app.modules.cargos.models import Cargo
from app.modules.catalogos.models import Celula
from app.modules.usuarios.errores import (
    AccionSobreSiMismo,
    SuperadminSinPassword,
    UltimoSuperadmin,
)
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.schemas import (
    UsuarioCrear,
    UsuarioDetalle,
    UsuarioEditar,
    UsuarioResumen,
)

_CORREO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ErrorConfiguracion(ValueError):
    """Valor de configuración inválido (por ejemplo, `SUPERADMIN_EMAIL` de otro dominio)."""


class ResultadoSuperadmin(StrEnum):
    OMITIDO_SIN_CORREO = "OMITIDO_SIN_CORREO"
    YA_HAY_SUPERADMIN = "YA_HAY_SUPERADMIN"
    CREADO = "CREADO"
    PROMOVIDO = "PROMOVIDO"


def validar_correo_corporativo(correo: str, dominio: str) -> str:
    """Devuelve el correo normalizado si es del dominio de Google Workspace (RN-12)."""
    normalizado = correo.strip().lower()
    if not _CORREO.match(normalizado):
        raise ErrorConfiguracion("El correo no tiene un formato válido")
    if normalizado.rsplit("@", 1)[1] != dominio.strip().lower():
        raise ErrorConfiguracion(f"El correo debe ser del dominio @{dominio}")
    return normalizado


def asegurar_superadmin_inicial(
    session: Session, correo: str, nombre: str, dominio: str
) -> ResultadoSuperadmin:
    """Garantiza que exista al menos un SUPERADMIN activo (idempotente; no hace commit).

    - Sin correo configurado: no hace nada.
    - Si ya hay un SUPERADMIN activo: no hace nada. Así la variable de entorno no sirve para
      crear superadministradores adicionales; los siguientes se gestionan desde la app (S1-10).
    - Si no lo hay: crea el usuario o, si el correo ya existe, lo promueve y reactiva
      (recuperación de acceso). Ambos casos quedan en `auditoria` con `origen = seed`, más
      `SUPERADMIN_ASIGNADO` (RN-12).
    - El SUPERADMIN no tiene contraseña: entra solo con Google (ADR-027). Al promover a un
      operativo se borra su contraseña en la misma operación (lo exige el `CHECK` por rol).
    """
    if not correo.strip():
        return ResultadoSuperadmin.OMITIDO_SIN_CORREO
    correo = validar_correo_corporativo(correo, dominio)

    hay_superadmin = session.scalar(
        select(Usuario.id)
        .where(Usuario.rol == Rol.SUPERADMIN, Usuario.activo, Usuario.deleted_at.is_(None))
        .limit(1)
    )
    if hay_superadmin is not None:
        return ResultadoSuperadmin.YA_HAY_SUPERADMIN

    existente = session.scalar(select(Usuario).where(Usuario.correo == correo))
    if existente is None:
        usuario = Usuario(
            nombre_completo=nombre.strip() or "Superadministrador",
            correo=correo,
            rol=Rol.SUPERADMIN,
        )
        session.add(usuario)
        session.flush()
        registrar(
            session,
            AccionAuditoria.USUARIO_CREAR,
            "usuarios",
            usuario.id,
            datos={"origen": "seed", "correo": correo, "rol": Rol.SUPERADMIN.value},
        )
        _auditar_superadmin_asignado(session, usuario)
        return ResultadoSuperadmin.CREADO

    antes = {"rol": existente.rol, "activo": existente.activo}
    existente.rol = Rol.SUPERADMIN
    existente.activo = True
    existente.deleted_at = None
    # Sin contraseña ni cambio pendiente: desde ahora entra con Google (ADR-027).
    existente.password_hash = None
    existente.debe_cambiar_password = False
    existente.intentos_fallidos = 0
    existente.bloqueado_hasta = None
    session.flush()
    registrar(
        session,
        AccionAuditoria.ROL_CAMBIAR,
        "usuarios",
        existente.id,
        datos={
            "origen": "seed",
            "antes": antes,
            "despues": {"rol": Rol.SUPERADMIN.value, "activo": True},
        },
    )
    _auditar_superadmin_asignado(session, existente)
    return ResultadoSuperadmin.PROMOVIDO


def _auditar_superadmin_asignado(session: Session, usuario: Usuario) -> None:
    registrar(
        session,
        AccionAuditoria.SUPERADMIN_ASIGNADO,
        "usuarios",
        usuario.id,
        datos={"origen": "seed", "correo": usuario.correo},
    )


# =================================================================================================
# Gestión de usuarios (S1-10)
# =================================================================================================

ENTIDAD = "usuarios"
OrdenUsuarios = Literal["nombre_completo", "-nombre_completo", "created_at", "-created_at"]
_COLUMNAS = {"nombre_completo": Usuario.nombre_completo, "created_at": Usuario.created_at}
# Campos de datos (no de rol ni credenciales) que se pueden editar y se auditan con antes/después.
_CAMPOS_DATOS = (
    "nombre_completo",
    "correo",
    "username",
    "cargo_id",
    "celula_id",
    "cedula",
    "es_prestador_servicios",
    "fecha_nacimiento",
)
# Dato personal (RNF-09): en la auditoría solo consta que cambió, no su valor.
_OCULTOS_EN_AUDITORIA = frozenset({"fecha_nacimiento"})
MOTIVO_RESTABLECIDA = "RESTABLECIDA_POR_ADMIN"


@dataclass
class Resultado:
    """Usuario afectado y correos a enviar **después** del commit (en segundo plano)."""

    usuario: Usuario
    correos: list[Correo] = field(default_factory=list)


# --- lectura -------------------------------------------------------------------------------------


def listar(
    session: Session,
    parametros: ParametrosPagina,
    *,
    q: str | None = None,
    rol: Rol | None = None,
    cargo_id: uuid.UUID | None = None,
    celula_id: uuid.UUID | None = None,
    es_prestador_servicios: bool | None = None,
    activo: bool | None = None,
    sort: OrdenUsuarios = "nombre_completo",
) -> tuple[list[UsuarioResumen], int]:
    consulta = select(Usuario).where(Usuario.deleted_at.is_(None))
    if q and q.strip():
        patron = patron_busqueda(q.strip())
        consulta = consulta.where(
            or_(
                Usuario.nombre_completo.ilike(patron),
                Usuario.correo.ilike(patron),
                Usuario.username.ilike(patron),
            )
        )
    filtros: dict[str, Any] = {
        "rol": rol,
        "cargo_id": cargo_id,
        "celula_id": celula_id,
        "es_prestador_servicios": es_prestador_servicios,
        "activo": activo,
    }
    for campo, valor in filtros.items():
        if valor is not None:
            consulta = consulta.where(getattr(Usuario, campo) == valor)
    consulta = consulta.order_by(orden(_COLUMNAS, sort), Usuario.id)
    filas, total = paginar(session, consulta, parametros)
    cargos, celulas = _referencias(session, filas)
    return [_resumen(u, cargos, celulas) for u in filas], total


def obtener(session: Session, usuario_id: uuid.UUID, *, bloquear: bool = False) -> Usuario:
    consulta = select(Usuario).where(Usuario.id == usuario_id, Usuario.deleted_at.is_(None))
    if bloquear:
        consulta = consulta.with_for_update()
    usuario = session.scalar(consulta)
    if usuario is None:
        raise NoEncontrado()
    return usuario


def detalle(session: Session, usuario: Usuario) -> UsuarioDetalle:
    cargos, celulas = _referencias(session, [usuario])
    return UsuarioDetalle(
        **_resumen(usuario, cargos, celulas).model_dump(),
        cedula=usuario.cedula,
        fecha_nacimiento=usuario.fecha_nacimiento,
        updated_at=usuario.updated_at,
    )


def _referencias(
    session: Session, usuarios: Sequence[Usuario]
) -> tuple[dict[uuid.UUID, Referencia], dict[uuid.UUID, Referencia]]:
    """Nombres de cargo y célula de una página de usuarios, en dos consultas (sin N+1)."""
    ids_cargo = {u.cargo_id for u in usuarios if u.cargo_id}
    ids_celula = {u.celula_id for u in usuarios if u.celula_id}
    cargos = (
        {
            c.id: Referencia(id=c.id, nombre=c.nombre)
            for c in session.scalars(select(Cargo).where(Cargo.id.in_(ids_cargo)))
        }
        if ids_cargo
        else {}
    )
    celulas = (
        {
            c.id: Referencia(id=c.id, nombre=c.nombre)
            for c in session.scalars(select(Celula).where(Celula.id.in_(ids_celula)))
        }
        if ids_celula
        else {}
    )
    return cargos, celulas


def _resumen(
    usuario: Usuario,
    cargos: dict[uuid.UUID, Referencia],
    celulas: dict[uuid.UUID, Referencia],
) -> UsuarioResumen:
    bloqueado = usuario.bloqueado_hasta is not None and usuario.bloqueado_hasta > datetime.now(UTC)
    return UsuarioResumen(
        id=usuario.id,
        nombre_completo=usuario.nombre_completo,
        correo=usuario.correo,
        username=usuario.username,
        rol=Rol(usuario.rol),
        cargo=cargos.get(usuario.cargo_id) if usuario.cargo_id else None,
        celula=celulas.get(usuario.celula_id) if usuario.celula_id else None,
        es_prestador_servicios=usuario.es_prestador_servicios,
        activo=usuario.activo,
        debe_cambiar_password=usuario.debe_cambiar_password,
        bloqueado=bloqueado,
        ultimo_acceso=usuario.ultimo_acceso,
        created_at=usuario.created_at,
    )


# --- validaciones --------------------------------------------------------------------------------


def _exigir_gestion_superadmin(actor: Usuario) -> None:
    """Crear, promover, modificar, degradar o desactivar a un SUPERADMIN: solo SUPERADMIN."""
    if not tiene_permiso(actor.rol, Permiso.USUARIOS_GESTIONAR_SUPERADMIN):
        raise SinPermiso()


def _es_corporativo(correo: str, settings: Settings) -> bool:
    return correo.rsplit("@", 1)[-1] == settings.google_workspace_domain.strip().lower()


def _exigir_correo_corporativo(correo: str, settings: Settings) -> None:
    if not _es_corporativo(correo, settings):
        raise ValorNoPermitido(
            errors=error_de_campo(
                "correo",
                f"Un superadministrador necesita un correo @{settings.google_workspace_domain}",
            )
        )


def _sin_username_de_superadmin(username: str | None) -> None:
    if username is not None:
        raise ValorNoPermitido(
            errors=error_de_campo(
                "username", "Un superadministrador entra con Google y no lleva nombre de usuario"
            )
        )


def _exigir_referencias(session: Session, campos: dict[str, Any]) -> None:
    cargo_id = campos.get("cargo_id")
    if (
        cargo_id is not None
        and session.scalar(select(Cargo.id).where(Cargo.id == cargo_id, Cargo.deleted_at.is_(None)))
        is None
    ):
        raise ValorNoPermitido(errors=error_de_campo("cargo_id", "El cargo no existe"))
    celula_id = campos.get("celula_id")
    if (
        celula_id is not None
        and session.scalar(select(Celula.id).where(Celula.id == celula_id, Celula.activo)) is None
    ):
        raise ValorNoPermitido(
            errors=error_de_campo("celula_id", "La célula no existe o está inactiva")
        )


def _exigir_unicos(
    session: Session, campos: dict[str, Any], excluir: uuid.UUID | None = None
) -> None:
    """`correo` y `username` (CITEXT: sin distinguir mayúsculas) y `cedula`, únicos."""
    condiciones = {
        "correo": Usuario.correo,
        "username": Usuario.username,
        "cedula": Usuario.cedula,
    }
    for campo, columna in condiciones.items():
        valor = campos.get(campo)
        if valor is None:
            continue
        consulta = select(Usuario.id).where(columna == valor)
        if campo == "cedula":
            consulta = consulta.where(Usuario.deleted_at.is_(None))
        if excluir is not None:
            consulta = consulta.where(Usuario.id != excluir)
        if session.scalar(consulta.limit(1)) is not None:
            raise Duplicado(
                errors=error_de_campo(campo, f"Ya existe un usuario con ese {campo}", "DUPLICADO")
            )


def _guardar(session: Session) -> None:
    # Respaldo ante una carrera entre la verificación de únicos y el INSERT/UPDATE.
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise Duplicado("Ya existe un usuario con alguno de esos datos") from error


def _proteger_ultimo_superadmin(session: Session, objetivo: Usuario) -> None:
    """RN-12. Bloquea las filas de SUPERADMIN activos hasta el commit (`FOR UPDATE`)."""
    activos = session.scalars(
        select(Usuario.id)
        .where(Usuario.rol == Rol.SUPERADMIN, Usuario.activo, Usuario.deleted_at.is_(None))
        .with_for_update()
    ).all()
    if objetivo.activo and set(activos) <= {objetivo.id}:
        raise UltimoSuperadmin()


# --- contraseña temporal (S-13) ------------------------------------------------------------------


def _asignar_password_temporal(usuario: Usuario, settings: Settings) -> Correo:
    """Fija una contraseña temporal (Argon2id) y prepara el correo: es el único lugar donde
    viaja en claro. Obliga a cambiarla en el primer acceso y levanta un bloqueo previo."""
    temporal = password_temporal()
    usuario.password_hash = hash_password(temporal)
    usuario.debe_cambiar_password = True
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    return correo_password_temporal(usuario, temporal, settings.frontend_url)


def correo_password_temporal(usuario: Usuario, temporal: str, frontend_url: str) -> Correo:
    enlace = f"{frontend_url.rstrip('/')}/login"
    texto = (
        f"Hola, {usuario.nombre_completo}:\n\n"
        "Se le asignó una contraseña temporal para Trulab Viajes.\n\n"
        f"Usuario: {usuario.username}\n"
        f"Contraseña temporal: {temporal}\n\n"
        f"Ingrese en {enlace}. Por seguridad, el sistema le pedirá cambiarla en su primer acceso.\n"
        "Si no esperaba este correo, avise al administrador.\n"
    )
    html = (
        f"<p>Hola, {escape(usuario.nombre_completo)}:</p>"
        "<p>Se le asignó una contraseña temporal para Trulab Viajes.</p>"
        f"<p>Usuario: <strong>{escape(usuario.username or '')}</strong><br>"
        f"Contraseña temporal: <code>{escape(temporal)}</code></p>"
        f'<p><a href="{escape(enlace)}">Ingresar</a>. El sistema le pedirá cambiarla en su '
        "primer acceso.</p>"
        "<p>Si no esperaba este correo, avise al administrador.</p>"
    )
    return Correo(usuario.correo, "Su acceso a Trulab Viajes", texto, html)


# --- auditoría -----------------------------------------------------------------------------------


def _auditable(campo: str, valor: object) -> object:
    if campo in _OCULTOS_EN_AUDITORIA:
        return "[dato personal]" if valor is not None else None
    if isinstance(valor, uuid.UUID):
        return str(valor)
    if isinstance(valor, date):
        return valor.isoformat()
    return valor


def _auditar(
    session: Session,
    accion: AccionAuditoria,
    usuario: Usuario,
    actor: Usuario,
    ctx: Contexto,
    datos: dict[str, object],
) -> None:
    registrar(
        session,
        accion,
        ENTIDAD,
        usuario.id,
        usuario_id=actor.id,
        datos=datos,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


# --- crear ---------------------------------------------------------------------------------------


def crear(
    session: Session, datos: UsuarioCrear, actor: Usuario, settings: Settings, ctx: Contexto
) -> Resultado:
    if datos.rol == Rol.SUPERADMIN:
        _exigir_gestion_superadmin(actor)
        _exigir_correo_corporativo(datos.correo, settings)
        _sin_username_de_superadmin(datos.username)
    campos = datos.model_dump()
    _exigir_referencias(session, campos)
    _exigir_unicos(session, campos)

    usuario = Usuario(**campos, created_by=actor.id, updated_by=actor.id)
    resultado = Resultado(usuario)
    if datos.rol != Rol.SUPERADMIN:
        resultado.correos.append(_asignar_password_temporal(usuario, settings))
    session.add(usuario)
    _guardar(session)
    session.refresh(usuario)

    _auditar(
        session,
        AccionAuditoria.USUARIO_CREAR,
        usuario,
        actor,
        ctx,
        {"rol": datos.rol.value} | {c: _auditable(c, campos[c]) for c in _CAMPOS_DATOS},
    )
    if datos.rol == Rol.SUPERADMIN:
        _auditar(
            session,
            AccionAuditoria.SUPERADMIN_ASIGNADO,
            usuario,
            actor,
            ctx,
            {"correo": usuario.correo, "via": "alta"},
        )
    session.commit()
    return resultado


# --- editar (incluye cambio de rol, promoción y degradación) -------------------------------------


def editar(
    session: Session,
    usuario_id: uuid.UUID,
    datos: UsuarioEditar,
    actor: Usuario,
    settings: Settings,
    ctx: Contexto,
) -> Resultado:
    usuario = obtener(session, usuario_id, bloquear=True)
    campos = datos.model_dump(exclude_unset=True)
    rol_antes = Rol(usuario.rol)
    rol_despues = Rol(campos.pop("rol", None) or rol_antes)
    promueve = rol_antes != Rol.SUPERADMIN and rol_despues == Rol.SUPERADMIN
    degrada = rol_antes == Rol.SUPERADMIN and rol_despues != Rol.SUPERADMIN

    if Rol.SUPERADMIN in (rol_antes, rol_despues):
        _exigir_gestion_superadmin(actor)
    if rol_despues == Rol.SUPERADMIN:
        _exigir_correo_corporativo(campos.get("correo", usuario.correo), settings)
        _sin_username_de_superadmin(campos.get("username"))
    elif (degrada and campos.get("username") is None) or (
        "username" in campos and campos["username"] is None
    ):
        raise ValorNoPermitido(
            errors=error_de_campo("username", "Indique el nombre de usuario para entrar")
        )
    _exigir_referencias(session, campos)
    _exigir_unicos(session, campos, excluir=usuario.id)
    if degrada:
        _proteger_ultimo_superadmin(session, usuario)

    antes: dict[str, object] = {}
    despues: dict[str, object] = {}
    for campo, valor in campos.items():
        if getattr(usuario, campo) != valor:
            antes[campo] = _auditable(campo, getattr(usuario, campo))
            despues[campo] = _auditable(campo, valor)
            setattr(usuario, campo, valor)

    resultado = Resultado(usuario)
    # El rol primero: los `CHECK` por rol deben ver credenciales y rol coherentes en cada flush.
    usuario.rol = rol_despues
    if rol_despues == Rol.SUPERADMIN and "correo" in despues:
        # El `sub` de Google quedó ligado al correo anterior: se vuelve a fijar en el próximo login.
        usuario.google_sub = None
    if promueve:
        # Desde ahora entra solo con Google (ADR-027): sin usuario ni contraseña.
        usuario.username = None
        usuario.password_hash = None
        usuario.debe_cambiar_password = False
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None
    if degrada:
        usuario.google_sub = None
        resultado.correos.append(_asignar_password_temporal(usuario, settings))
    if despues or rol_antes != rol_despues:
        usuario.updated_by = actor.id
    _guardar(session)
    if promueve:
        invalidar_tokens_recuperacion(session, usuario.id)

    if despues:
        _auditar(
            session,
            AccionAuditoria.USUARIO_EDITAR,
            usuario,
            actor,
            ctx,
            {"antes": antes, "despues": despues},
        )
    if rol_antes != rol_despues:
        revocar_sesiones(session, usuario.id)
        _auditar(
            session,
            AccionAuditoria.ROL_CAMBIAR,
            usuario,
            actor,
            ctx,
            {"antes": {"rol": rol_antes.value}, "despues": {"rol": rol_despues.value}},
        )
    if promueve:
        _auditar(
            session,
            AccionAuditoria.SUPERADMIN_ASIGNADO,
            usuario,
            actor,
            ctx,
            {"correo": usuario.correo, "via": "promocion"},
        )
    session.commit()
    session.refresh(usuario)
    return resultado


# --- activar y desactivar (RN-11) ----------------------------------------------------------------


def desactivar(session: Session, usuario_id: uuid.UUID, actor: Usuario, ctx: Contexto) -> Usuario:
    usuario = obtener(session, usuario_id, bloquear=True)
    if usuario.id == actor.id:
        raise AccionSobreSiMismo("No puede desactivar su propio usuario")
    if usuario.rol == Rol.SUPERADMIN:
        _exigir_gestion_superadmin(actor)
        _proteger_ultimo_superadmin(session, usuario)
    if not usuario.activo:
        return usuario  # idempotente: sin cambios ni auditoría
    usuario.activo = False
    usuario.updated_by = actor.id
    session.flush()
    revocar_sesiones(session, usuario.id)
    _auditar(session, AccionAuditoria.USUARIO_DESACTIVAR, usuario, actor, ctx, {"rol": usuario.rol})
    session.commit()
    session.refresh(usuario)
    return usuario


def activar(session: Session, usuario_id: uuid.UUID, actor: Usuario, ctx: Contexto) -> Usuario:
    usuario = obtener(session, usuario_id, bloquear=True)
    if usuario.rol == Rol.SUPERADMIN:
        _exigir_gestion_superadmin(actor)
    if usuario.activo:
        return usuario
    usuario.activo = True
    usuario.updated_by = actor.id
    session.flush()
    _auditar(session, AccionAuditoria.USUARIO_ACTIVAR, usuario, actor, ctx, {"rol": usuario.rol})
    session.commit()
    session.refresh(usuario)
    return usuario


# --- restablecer contraseña (operativos) ---------------------------------------------------------


def restablecer_password(
    session: Session, usuario_id: uuid.UUID, actor: Usuario, settings: Settings, ctx: Contexto
) -> Resultado:
    usuario = obtener(session, usuario_id, bloquear=True)
    if usuario.rol == Rol.SUPERADMIN:
        _exigir_gestion_superadmin(actor)
        raise SuperadminSinPassword()
    resultado = Resultado(usuario, [_asignar_password_temporal(usuario, settings)])
    usuario.updated_by = actor.id
    session.flush()
    revocar_sesiones(session, usuario.id)
    invalidar_tokens_recuperacion(session, usuario.id)
    _auditar(
        session,
        AccionAuditoria.PASSWORD_CAMBIADA,
        usuario,
        actor,
        ctx,
        {"motivo": MOTIVO_RESTABLECIDA},
    )
    session.commit()
    return resultado
