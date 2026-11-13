"""Reglas del acceso híbrido (ADR-027; docs/architecture.md §5, docs/api-design.md §3).

- Operativos (VIAJERO, ADMIN, FINANCIERO): usuario y contraseña, bloqueo por intentos fallidos,
  recuperación por correo y cambio de contraseña (obligatorio si es temporal).
- SUPERADMIN: solo Google OAuth del dominio corporativo; nunca por contraseña.
- Sesión propia (ADR-005): access JWT corto + refresh opaco rotativo (en `sesiones`, solo SHA-256).

Cada función hace `commit` ella misma, también antes de rechazar un acceso: los intentos fallidos,
los bloqueos y su auditoría deben quedar guardados aunque la petición termine en error.
"""

import ipaddress
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from app.core.audit import AccionAuditoria, registrar
from app.core.config import Settings
from app.core.enums import Rol
from app.core.mail import Correo
from app.core.permissions import permisos_de
from app.core.security import (
    emitir_access_token,
    errores_politica_password,
    hash_password,
    necesita_rehash,
    sha256_hex,
    token_opaco,
    verificacion_ficticia,
    verificar_password,
)
from app.modules.auth.errores import (
    AccesoDenegado,
    CredencialesInvalidas,
    CuentaBloqueada,
    DominioNoPermitido,
    MetodoAccesoNoPermitido,
    NoAutenticado,
    PasswordActualIncorrecta,
    PasswordDebil,
    TokenExpirado,
    TokenRecuperacionInvalido,
    UsuarioInactivo,
)
from app.modules.auth.models import Sesion, TokenRecuperacionPassword
from app.modules.auth.schemas import Referencia, UsuarioActualSalida
from app.modules.cargos.models import Cargo
from app.modules.catalogos.models import Celula
from app.modules.usuarios.models import Usuario

ENTIDAD = "auth"


@dataclass(frozen=True)
class Contexto:
    """Origen de la petición, para la auditoría y las sesiones."""

    ip: str | None
    user_agent: str | None

    @classmethod
    def crear(cls, ip: str | None, user_agent: str | None) -> "Contexto":
        # `auditoria.ip` y `sesiones.ip` son INET: un valor que no es IP (p. ej. "testclient")
        # se guarda como NULL en lugar de romper la transacción.
        try:
            ip_valida = str(ipaddress.ip_address(ip)) if ip else None
        except ValueError:
            ip_valida = None
        return cls(ip=ip_valida, user_agent=(user_agent or "")[:512] or None)


@dataclass(frozen=True)
class SesionEmitida:
    access_token: str
    expires_in: int
    refresh_token: str
    sesion_id: uuid.UUID
    usuario: Usuario


def _ahora() -> datetime:
    return datetime.now(UTC)


def _normalizar(valor: str) -> str:
    return valor.strip().lower()


# --- sesiones ---------------------------------------------------------------------------------


def _emitir_sesion(
    session: Session, usuario: Usuario, settings: Settings, ctx: Contexto
) -> SesionEmitida:
    refresh = token_opaco()
    registro = Sesion(
        usuario_id=usuario.id,
        token_hash=sha256_hex(refresh),
        expires_at=_ahora() + timedelta(days=settings.refresh_token_ttl_days),
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )
    session.add(registro)
    session.flush()
    access, expira_en = emitir_access_token(
        usuario_id=usuario.id,
        sesion_id=registro.id,
        rol=usuario.rol,
        cambio_password=usuario.debe_cambiar_password,
        secreto=settings.jwt_secret,
        ttl=timedelta(minutes=settings.access_token_ttl_minutes),
    )
    return SesionEmitida(access, expira_en, refresh, registro.id, usuario)


def revocar_sesiones(session: Session, usuario_id: uuid.UUID) -> None:
    """Revoca todas las sesiones vigentes del usuario (cambio de contraseña, rol, desactivación)."""
    session.execute(
        update(Sesion)
        .where(Sesion.usuario_id == usuario_id, Sesion.revoked_at.is_(None))
        .values(revoked_at=_ahora())
    )


def _auditar(
    session: Session,
    accion: AccionAuditoria,
    ctx: Contexto,
    *,
    usuario_id: uuid.UUID | None,
    datos: dict[str, Any],
) -> None:
    registrar(
        session,
        accion,
        ENTIDAD,
        usuario_id,
        usuario_id=usuario_id,
        datos=datos,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


# --- login con usuario y contraseña (operativos) ---------------------------------------------


def iniciar_sesion_password(
    session: Session, username: str, password: str, settings: Settings, ctx: Contexto
) -> SesionEmitida:
    username = _normalizar(username)
    usuario = session.scalar(
        select(Usuario)
        .where(Usuario.username == username, Usuario.deleted_at.is_(None))
        .with_for_update()
    )
    ahora = _ahora()

    def rechazar(motivo: str, error: Exception) -> Exception:
        _auditar(
            session,
            AccionAuditoria.LOGIN_FALLIDO,
            ctx,
            usuario_id=usuario.id if usuario else None,
            datos={"metodo": "password", "username": username, "motivo": motivo},
        )
        session.commit()
        return error

    if usuario is not None and usuario.bloqueado_hasta and usuario.bloqueado_hasta > ahora:
        verificacion_ficticia(password)
        raise rechazar("BLOQUEADO", CuentaBloqueada())
    if usuario is None or usuario.rol == Rol.SUPERADMIN or usuario.password_hash is None:
        # Sin cuenta, o un SUPERADMIN (entra solo con Google): mismo tiempo y mismo mensaje.
        verificacion_ficticia(password)
        motivo = "NO_REGISTRADO" if usuario is None else "METODO_NO_PERMITIDO"
        raise rechazar(motivo, CredencialesInvalidas())
    if not verificar_password(usuario.password_hash, password):
        usuario.intentos_fallidos += 1
        motivo = "PASSWORD_INCORRECTA"
        if usuario.intentos_fallidos >= settings.login_max_failed_attempts:
            usuario.bloqueado_hasta = ahora + timedelta(minutes=settings.login_lockout_minutes)
            usuario.intentos_fallidos = 0
            motivo = "BLOQUEO_ACTIVADO"
        raise rechazar(motivo, CredencialesInvalidas())
    if not usuario.activo:
        raise rechazar("INACTIVO", CredencialesInvalidas())

    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultimo_acceso = ahora
    if necesita_rehash(usuario.password_hash):
        usuario.password_hash = hash_password(password)
    emitida = _emitir_sesion(session, usuario, settings, ctx)
    _auditar(
        session,
        AccionAuditoria.LOGIN_EXITOSO,
        ctx,
        usuario_id=usuario.id,
        datos={"metodo": "password", "cambio_password_pendiente": usuario.debe_cambiar_password},
    )
    session.commit()
    return emitida


# --- login con Google (solo SUPERADMIN) ------------------------------------------------------


def iniciar_sesion_google(
    session: Session,
    claims: dict[str, Any],
    settings: Settings,
    ctx: Contexto,
    *,
    metodo: str = "google",
) -> SesionEmitida:
    """Valida los claims de un ID token de Google **ya verificado** (firma, `aud`, `exp`).

    Con `metodo="desarrollo"` (solo `ENV=local`) no hay `sub` de Google y no se toca `google_sub`.
    """
    correo = _normalizar(str(claims.get("email", "")))
    dominio = _normalizar(settings.google_workspace_domain)
    usuario: Usuario | None = None

    def denegar(motivo: str, error: Exception) -> Exception:
        _auditar(
            session,
            AccionAuditoria.ACCESO_DENEGADO,
            ctx,
            usuario_id=usuario.id if usuario else None,
            datos={"metodo": metodo, "correo": correo, "motivo": motivo},
        )
        session.commit()
        return error

    if claims.get("email_verified") is not True:
        raise denegar("CORREO_NO_VERIFICADO", AccesoDenegado())
    if claims.get("hd") != dominio or not correo.endswith(f"@{dominio}"):
        raise denegar("DOMINIO_NO_PERMITIDO", DominioNoPermitido())
    usuario = session.scalar(
        select(Usuario)
        .where(Usuario.correo == correo, Usuario.deleted_at.is_(None))
        .with_for_update()
    )
    if usuario is None:
        raise denegar("NO_REGISTRADO", AccesoDenegado())
    if not usuario.activo:
        raise denegar("INACTIVO", UsuarioInactivo())
    if usuario.rol != Rol.SUPERADMIN:
        raise denegar("METODO_NO_PERMITIDO", MetodoAccesoNoPermitido("Use su usuario y contraseña"))
    sub = claims.get("sub")
    if metodo == "google":
        if not isinstance(sub, str) or not sub:
            raise denegar("SIN_SUB", AccesoDenegado())
        if usuario.google_sub is None:
            usuario.google_sub = sub  # primer login con Google
        elif usuario.google_sub != sub:
            # Cuenta de Google recreada con el mismo correo: lo revisa un administrador.
            raise denegar("GOOGLE_SUB_DISTINTO", AccesoDenegado())

    usuario.ultimo_acceso = _ahora()
    emitida = _emitir_sesion(session, usuario, settings, ctx)
    _auditar(
        session, AccionAuditoria.LOGIN_EXITOSO, ctx, usuario_id=usuario.id, datos={"metodo": metodo}
    )
    session.commit()
    return emitida


# --- refresh y logout ------------------------------------------------------------------------


def renovar_sesion(
    session: Session, refresh_token: str | None, settings: Settings, ctx: Contexto
) -> SesionEmitida:
    """Rota el refresh token. Reusar uno ya rotado revoca todas las sesiones (posible robo)."""
    if not refresh_token:
        raise NoAutenticado()
    registro = session.scalar(
        select(Sesion).where(Sesion.token_hash == sha256_hex(refresh_token)).with_for_update()
    )
    if registro is None:
        raise NoAutenticado()
    if registro.revoked_at is not None:
        revocar_sesiones(session, registro.usuario_id)
        _auditar(
            session,
            AccionAuditoria.ACCESO_DENEGADO,
            ctx,
            usuario_id=registro.usuario_id,
            datos={"metodo": "refresh", "motivo": "REFRESH_REUTILIZADO"},
        )
        session.commit()
        raise NoAutenticado()
    if registro.expires_at <= _ahora():
        raise TokenExpirado()
    usuario = session.get(Usuario, registro.usuario_id)
    if usuario is None or not usuario.activo or usuario.deleted_at is not None:
        registro.revoked_at = _ahora()
        session.commit()
        raise NoAutenticado()

    registro.revoked_at = _ahora()
    emitida = _emitir_sesion(session, usuario, settings, ctx)
    session.commit()
    return emitida


def cerrar_sesion(session: Session, sesion_id: uuid.UUID, refresh_token: str | None) -> None:
    condiciones = [Sesion.id == sesion_id]
    if refresh_token:
        condiciones.append(Sesion.token_hash == sha256_hex(refresh_token))
    session.execute(
        update(Sesion)
        .where(or_(*condiciones), Sesion.revoked_at.is_(None))
        .values(revoked_at=_ahora())
    )
    session.commit()


# --- contraseñas -----------------------------------------------------------------------------


def _fijar_password(usuario: Usuario, password: str) -> None:
    usuario.password_hash = hash_password(password)
    usuario.debe_cambiar_password = False
    usuario.password_cambiada_at = _ahora()
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None


def _validar_politica(password: str, usuario: Usuario) -> None:
    errores = errores_politica_password(password, username=usuario.username, correo=usuario.correo)
    if errores:
        raise PasswordDebil(
            "; ".join(errores),
            [{"field": "nueva_password", "code": "PASSWORD_DEBIL", "message": e} for e in errores],
        )


def invalidar_tokens_recuperacion(session: Session, usuario_id: uuid.UUID) -> None:
    session.execute(
        update(TokenRecuperacionPassword)
        .where(
            TokenRecuperacionPassword.usuario_id == usuario_id,
            TokenRecuperacionPassword.used_at.is_(None),
        )
        .values(used_at=_ahora())
    )


def solicitar_recuperacion(
    session: Session, identificador: str, settings: Settings, ctx: Contexto
) -> Correo | None:
    """Crea un token de restablecimiento y devuelve el correo a enviar (o None).

    La respuesta HTTP es la misma en todos los casos: no revela si la cuenta existe. El envío lo
    hace el router en segundo plano, para que el tiempo de respuesta tampoco lo revele.
    """
    identificador = _normalizar(identificador)
    usuario = session.scalar(
        select(Usuario).where(
            or_(Usuario.username == identificador, Usuario.correo == identificador),
            Usuario.deleted_at.is_(None),
        )
    )
    aplica = usuario is not None and usuario.activo and usuario.rol != Rol.SUPERADMIN
    _auditar(
        session,
        AccionAuditoria.PASSWORD_RECUPERACION_SOLICITADA,
        ctx,
        usuario_id=usuario.id if usuario else None,
        datos={"identificador": identificador, "enviado": aplica},
    )
    if usuario is None or not aplica:
        session.commit()
        return None

    invalidar_tokens_recuperacion(session, usuario.id)
    token = token_opaco()
    minutos = settings.password_reset_ttl_minutes
    session.add(
        TokenRecuperacionPassword(
            usuario_id=usuario.id,
            token_hash=sha256_hex(token),
            expires_at=_ahora() + timedelta(minutes=minutos),
            ip=ctx.ip,
        )
    )
    session.commit()
    return correo_restablecimiento(usuario, token, minutos, settings.frontend_url)


def correo_restablecimiento(
    usuario: Usuario, token: str, minutos: int, frontend_url: str
) -> Correo:
    enlace = f"{frontend_url.rstrip('/')}/restablecer-password?token={token}"
    texto = (
        f"Hola, {usuario.nombre_completo}:\n\n"
        "Recibimos una solicitud para restablecer su contraseña de Trulab Viajes.\n"
        f"Abra este enlace (vence en {minutos} minutos y solo sirve una vez):\n\n{enlace}\n\n"
        "Si no fue usted, ignore este correo: su contraseña no cambia.\n"
    )
    html = (
        f"<p>Hola, {_escapar(usuario.nombre_completo)}:</p>"
        "<p>Recibimos una solicitud para restablecer su contraseña de Trulab Viajes.</p>"
        f'<p><a href="{_escapar(enlace)}">Restablecer contraseña</a> '
        f"(vence en {minutos} minutos y solo sirve una vez).</p>"
        "<p>Si no fue usted, ignore este correo: su contraseña no cambia.</p>"
    )
    return Correo(usuario.correo, "Restablecer su contraseña de Trulab Viajes", texto, html)


def _escapar(texto: str) -> str:
    return (
        texto.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
    )


def restablecer_password(session: Session, token: str, nueva: str, ctx: Contexto) -> None:
    registro = session.scalar(
        select(TokenRecuperacionPassword)
        .where(
            TokenRecuperacionPassword.token_hash == sha256_hex(token),
            TokenRecuperacionPassword.used_at.is_(None),
            TokenRecuperacionPassword.expires_at > _ahora(),
        )
        .with_for_update()
    )
    if registro is None:
        raise TokenRecuperacionInvalido()
    usuario = session.get(Usuario, registro.usuario_id, with_for_update=True)
    if usuario is None or not usuario.activo or usuario.rol == Rol.SUPERADMIN:
        registro.used_at = _ahora()
        session.commit()
        raise TokenRecuperacionInvalido()
    # La política se valida antes de consumir el token: un error no obliga a pedir otro enlace.
    _validar_politica(nueva, usuario)

    registro.used_at = _ahora()
    invalidar_tokens_recuperacion(session, usuario.id)
    _fijar_password(usuario, nueva)
    revocar_sesiones(session, usuario.id)
    _auditar(
        session,
        AccionAuditoria.PASSWORD_CAMBIADA,
        ctx,
        usuario_id=usuario.id,
        datos={"origen": "recuperacion"},
    )
    session.commit()


def cambiar_password(
    session: Session,
    usuario: Usuario,
    actual: str,
    nueva: str,
    settings: Settings,
    ctx: Contexto,
) -> SesionEmitida:
    """Cambio voluntario u obligatorio (contraseña temporal). Cierra las demás sesiones."""
    if usuario.rol == Rol.SUPERADMIN or usuario.password_hash is None:
        raise MetodoAccesoNoPermitido("El superadministrador no usa contraseña")
    if not verificar_password(usuario.password_hash, actual):
        raise PasswordActualIncorrecta(
            errors=[
                {
                    "field": "password_actual",
                    "code": "PASSWORD_ACTUAL_INCORRECTA",
                    "message": "La contraseña actual no es correcta",
                }
            ]
        )
    if nueva == actual:
        raise PasswordDebil(
            "Debe ser distinta de la actual",
            [
                {
                    "field": "nueva_password",
                    "code": "PASSWORD_DEBIL",
                    "message": "Debe ser distinta de la actual",
                }
            ],
        )
    _validar_politica(nueva, usuario)

    era_temporal = usuario.debe_cambiar_password
    _fijar_password(usuario, nueva)
    revocar_sesiones(session, usuario.id)
    emitida = _emitir_sesion(session, usuario, settings, ctx)
    _auditar(
        session,
        AccionAuditoria.PASSWORD_CAMBIADA,
        ctx,
        usuario_id=usuario.id,
        datos={"origen": "cambio", "era_temporal": era_temporal},
    )
    session.commit()
    return emitida


# --- perfil ----------------------------------------------------------------------------------


def perfil(session: Session, usuario: Usuario) -> UsuarioActualSalida:
    cargo = session.get(Cargo, usuario.cargo_id) if usuario.cargo_id else None
    celula = session.get(Celula, usuario.celula_id) if usuario.celula_id else None
    return UsuarioActualSalida(
        id=usuario.id,
        nombre_completo=usuario.nombre_completo,
        correo=usuario.correo,
        username=usuario.username,
        rol=Rol(usuario.rol),
        es_prestador_servicios=usuario.es_prestador_servicios,
        debe_cambiar_password=usuario.debe_cambiar_password,
        cargo=Referencia(id=cargo.id, nombre=cargo.nombre) if cargo else None,
        celula=Referencia(id=celula.id, nombre=celula.nombre) if celula else None,
        permisos=([] if usuario.debe_cambiar_password else sorted(permisos_de(usuario.rol))),
    )
