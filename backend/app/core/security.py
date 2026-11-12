"""Primitivas de seguridad del acceso híbrido (ADR-027, docs/architecture.md §5).

- **Contraseñas:** Argon2id (`argon2-cffi`) con parámetros OWASP; política de RN-15.
- **Tokens opacos** (refresh y recuperación de contraseña): aleatorios de 32 bytes; en la BD solo
  su SHA-256 en hexadecimal (los `CHECK` de `sesiones` y `tokens_recuperacion_password`).
- **Access token:** JWT HS256 de vida corta con `sub` (usuario), `sid` (sesión) y `rol`.

Nada de este módulo registra contraseñas, hashes ni tokens.
"""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# --- Contraseñas -------------------------------------------------------------------------------

LONGITUD_MINIMA = 12
LONGITUD_MAXIMA = 128

# Contraseñas muy comunes (además de la longitud mínima). Lista corta a propósito: la longitud de
# 12 ya descarta la mayoría de las listas públicas; esto cubre las que la cumplen.
_COMUNES = frozenset(
    {
        "123456789012",
        "1234567890123",
        "contraseña123",
        "contrasena123",
        "password1234",
        "password12345",
        "qwertyuiop12",
        "trulab123456",
        "trulabviajes",
        "trulab2026!!",
        "viaticos1234",
        "colombia1234",
        "administrador",
        "superadmin123",
    }
)


@lru_cache
def _hasher() -> PasswordHasher:
    # OWASP (Password Storage Cheat Sheet): Argon2id, m = 19 MiB, t = 2, p = 1 como mínimo.
    return PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)


def hash_password(password: str) -> str:
    """Hash Argon2id en formato PHC (`$argon2id$...`), con sal aleatoria."""
    return _hasher().hash(password)


def verificar_password(password_hash: str, password: str) -> bool:
    """Compara en tiempo constante. Un hash corrupto cuenta como contraseña incorrecta."""
    try:
        return _hasher().verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def necesita_rehash(password_hash: str) -> bool:
    """True si el hash usa parámetros distintos de los actuales (se rehace al ingresar bien)."""
    return _hasher().check_needs_rehash(password_hash)


@lru_cache
def _hash_ficticio() -> str:
    return hash_password(secrets.token_urlsafe(16))


def verificacion_ficticia(password: str) -> None:
    """Gasta el mismo tiempo que una verificación real cuando el usuario no existe.

    Así el tiempo de respuesta del login no revela si un `username` existe (docs/api-design.md §3).
    """
    verificar_password(_hash_ficticio(), password)


def errores_politica_password(password: str, *, username: str | None, correo: str) -> list[str]:
    """Motivos por los que `password` no cumple RN-15 (lista vacía = válida)."""
    errores: list[str] = []
    if len(password) < LONGITUD_MINIMA:
        errores.append(f"Debe tener al menos {LONGITUD_MINIMA} caracteres")
    if len(password) > LONGITUD_MAXIMA:
        errores.append(f"Debe tener como máximo {LONGITUD_MAXIMA} caracteres")
    normalizada = password.strip().lower()
    personales = {correo.lower(), correo.split("@", 1)[0].lower()}
    if username:
        personales.add(username.lower())
    if normalizada in personales:
        errores.append("No puede ser igual al usuario ni al correo")
    if normalizada in _COMUNES:
        errores.append("Es una contraseña demasiado común")
    return errores


def password_temporal() -> str:
    """Contraseña temporal aleatoria (alta o restablecimiento por ADMIN; S1-10)."""
    return secrets.token_urlsafe(18)


# --- Tokens opacos -----------------------------------------------------------------------------


def token_opaco() -> str:
    """Token aleatorio de 32 bytes, apto para cookies y URLs."""
    return secrets.token_urlsafe(32)


def sha256_hex(valor: str) -> str:
    """Lo único que se guarda de un token: su SHA-256 (64 caracteres hexadecimales)."""
    return hashlib.sha256(valor.encode()).hexdigest()


# --- Access token (JWT) ------------------------------------------------------------------------

ALGORITMO = "HS256"
EMISOR = "trulab-viajes"
AUDIENCIA = "trulab-viajes-api"


class TokenInvalidoError(Exception):
    """El access token falta, está mal firmado o no tiene los claims esperados."""


class TokenExpiradoError(TokenInvalidoError):
    """El access token venció: la SPA debe renovarlo con /auth/refresh."""


@dataclass(frozen=True)
class ClaimsAcceso:
    usuario_id: uuid.UUID
    sesion_id: uuid.UUID
    rol: str
    expira: datetime


def emitir_access_token(
    *,
    usuario_id: uuid.UUID,
    sesion_id: uuid.UUID,
    rol: str,
    cambio_password: bool,
    secreto: str,
    ttl: timedelta,
) -> tuple[str, int]:
    """Devuelve el JWT y su vida en segundos.

    `pwd_change` es solo informativo para la SPA: la API vuelve a leer `debe_cambiar_password` de
    la BD en cada petición (el claim no autoriza nada).
    """
    ahora = datetime.now(UTC)
    claims = {
        "iss": EMISOR,
        "aud": AUDIENCIA,
        "sub": str(usuario_id),
        "sid": str(sesion_id),
        "rol": rol,
        "pwd_change": cambio_password,
        "iat": ahora,
        "exp": ahora + ttl,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, secreto, algorithm=ALGORITMO), int(ttl.total_seconds())


def decodificar_access_token(token: str, *, secreto: str) -> ClaimsAcceso:
    try:
        claims = jwt.decode(
            token,
            secreto,
            algorithms=[ALGORITMO],
            audience=AUDIENCIA,
            issuer=EMISOR,
            options={"require": ["exp", "iat", "sub", "sid", "iss", "aud"]},
        )
        return ClaimsAcceso(
            usuario_id=uuid.UUID(claims["sub"]),
            sesion_id=uuid.UUID(claims["sid"]),
            rol=str(claims["rol"]),
            expira=datetime.fromtimestamp(claims["exp"], UTC),
        )
    except jwt.ExpiredSignatureError as error:
        raise TokenExpiradoError from error
    except (jwt.InvalidTokenError, KeyError, ValueError) as error:
        raise TokenInvalidoError from error
