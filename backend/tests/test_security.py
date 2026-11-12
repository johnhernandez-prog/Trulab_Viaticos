"""Primitivas de seguridad (S1-08): Argon2id, política de contraseñas, tokens opacos y JWT."""

import re
import uuid
from datetime import timedelta

import pytest

from app.core import rate_limit
from app.core.security import (
    TokenExpiradoError,
    TokenInvalidoError,
    decodificar_access_token,
    emitir_access_token,
    errores_politica_password,
    hash_password,
    necesita_rehash,
    password_temporal,
    sha256_hex,
    token_opaco,
    verificar_password,
)

SECRETO = "s" * 48


def test_hash_argon2id_con_sal_y_verificacion() -> None:
    primero = hash_password("Una-frase-larga-123")
    segundo = hash_password("Una-frase-larga-123")

    assert primero.startswith("$argon2id$v=19$m=19456,t=2,p=1$")  # cumple ck_usuarios__password
    assert primero != segundo  # sal aleatoria
    assert verificar_password(primero, "Una-frase-larga-123")
    assert not verificar_password(primero, "una-frase-larga-123")
    assert not necesita_rehash(primero)


@pytest.mark.parametrize("hash_roto", ["", "no-es-un-hash", "$argon2id$v=19$m=1,t=1,p=1$x$y"])
def test_hash_corrupto_cuenta_como_password_incorrecta(hash_roto: str) -> None:
    assert verificar_password(hash_roto, "lo-que-sea") is False


def test_parametros_viejos_piden_rehash() -> None:
    from argon2 import PasswordHasher

    viejo = PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1).hash("Frase-larga-123")

    assert verificar_password(viejo, "Frase-larga-123")
    assert necesita_rehash(viejo)


@pytest.mark.parametrize(
    ("password", "motivo"),
    [
        ("corta-123", "al menos 12"),
        ("x" * 129, "como máximo 128"),
        ("ana.perez.trulab", "igual al usuario"),
        ("ana.perez@gmail.com", "igual al usuario ni al correo"),
        ("Password1234", "demasiado común"),
    ],
)
def test_politica_rechaza(password: str, motivo: str) -> None:
    errores = errores_politica_password(
        password, username="ana.perez.trulab", correo="ana.perez@gmail.com"
    )

    assert any(motivo in error for error in errores), errores


def test_politica_acepta_una_frase_larga() -> None:
    assert errores_politica_password("mi viaje a Cali 2026", username="ana", correo="a@b.co") == []


def test_password_temporal_cumple_la_politica() -> None:
    temporal = password_temporal()

    assert errores_politica_password(temporal, username="ana", correo="a@b.co") == []


def test_token_opaco_y_su_hash() -> None:
    token = token_opaco()

    assert len(token) >= 43 and token != token_opaco()
    assert re.fullmatch(r"[0-9a-f]{64}", sha256_hex(token))
    assert sha256_hex(token) == sha256_hex(token)


def _emitir(ttl: timedelta = timedelta(minutes=15), secreto: str = SECRETO) -> str:
    token, _ = emitir_access_token(
        usuario_id=uuid.uuid4(),
        sesion_id=uuid.uuid4(),
        rol="VIAJERO",
        cambio_password=False,
        secreto=secreto,
        ttl=ttl,
    )
    return token


def test_jwt_ida_y_vuelta() -> None:
    usuario, sesion = uuid.uuid4(), uuid.uuid4()
    token, expira_en = emitir_access_token(
        usuario_id=usuario,
        sesion_id=sesion,
        rol="ADMIN",
        cambio_password=True,
        secreto=SECRETO,
        ttl=timedelta(minutes=15),
    )

    claims = decodificar_access_token(token, secreto=SECRETO)
    assert (claims.usuario_id, claims.sesion_id, claims.rol) == (usuario, sesion, "ADMIN")
    assert expira_en == 900


def test_jwt_vencido() -> None:
    with pytest.raises(TokenExpiradoError):
        decodificar_access_token(_emitir(ttl=timedelta(seconds=-1)), secreto=SECRETO)


@pytest.mark.parametrize(
    "token",
    [
        "no-es-un-jwt",
        _emitir(secreto="otro-secreto-" + "z" * 40),
        _emitir()[:-4] + "AAAA",  # firma alterada
    ],
)
def test_jwt_invalido(token: str) -> None:
    with pytest.raises(TokenInvalidoError):
        decodificar_access_token(token, secreto=SECRETO)


def test_jwt_sin_algoritmo_none() -> None:
    import jwt

    sin_firma = jwt.encode({"sub": str(uuid.uuid4())}, key=None, algorithm="none")

    with pytest.raises(TokenInvalidoError):
        decodificar_access_token(sin_firma, secreto=SECRETO)


def test_limitador_por_ventana() -> None:
    contador = rate_limit._Contador()

    resultados = [contador.registrar("ip", maximo=3, ventana=60) for _ in range(4)]

    assert resultados[:3] == [None, None, None]
    assert resultados[3] is not None and 0 < resultados[3] <= 60
