"""Auth híbrida (S1-08, ADR-027): endpoints `/auth/*` y `/me` contra PostgreSQL real.

La API usa la sesión de prueba (revertida al final), un buzón en memoria y un verificador de
Google falso (fixture `api` de conftest). Contrato: docs/api-design.md §3.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.audit import Auditoria
from app.core.config import get_settings
from app.core.enums import Rol
from app.core.security import emitir_access_token, hash_password, sha256_hex
from app.main import create_app
from app.modules.auth.dependencias import UsuarioActual
from app.modules.auth.errores import LoginGoogleNoDisponible
from app.modules.auth.google import verificar_id_token
from app.modules.auth.models import Sesion, TokenRecuperacionPassword
from app.modules.usuarios.models import Usuario
from tests.conftest import Buzon
from tests.fabricas import correo_unico, crear_usuario, username_unico

PASSWORD = "Viaje-a-Cali-2026"
NUEVA = "Otra-frase-segura-77"
SPA = {"X-Requested-With": "trulab-spa"}


def _operativo(sesion: Session, **campos: object) -> Usuario:
    valores: dict[str, object] = {
        "username": username_unico(),
        "password_hash": hash_password(PASSWORD),
        "correo": correo_unico("gmail.com"),  # prestador sin correo corporativo
    }
    valores.update(campos)
    return crear_usuario(sesion, **valores)


def _login(api: TestClient, username: str, password: str = PASSWORD) -> Response:
    return api.post("/api/v1/auth/login", json={"username": username, "password": password})


def _bearer(respuesta: Response) -> dict[str, str]:
    return {"Authorization": f"Bearer {respuesta.json()['access_token']}"}


def _auditoria(sesion: Session, accion: str) -> list[Auditoria]:
    """Eventos de esta prueba: toda la prueba corre en una transacción y `now()` es su inicio,
    así que los eventos de otras ejecuciones (ya confirmados) quedan fuera."""
    return list(
        sesion.scalars(
            select(Auditoria)
            .where(Auditoria.accion == accion, Auditoria.created_at >= func.now())
            .order_by(Auditoria.id)
        )
    )


# --- login con usuario y contraseña --------------------------------------------------------------


def test_login_correcto_emite_sesion_y_cookie(api: TestClient, sesion: Session) -> None:
    usuario = _operativo(sesion, rol=Rol.FINANCIERO)

    respuesta = _login(api, usuario.username or "")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["token_type"] == "Bearer" and cuerpo["expires_in"] == 900
    assert cuerpo["usuario"]["rol"] == "FINANCIERO" and cuerpo["debe_cambiar_password"] is False
    cookie = respuesta.headers["set-cookie"]
    assert "trulab_refresh=" in cookie and "HttpOnly" in cookie
    assert "Path=/api/v1/auth" in cookie and "SameSite=strict" in cookie
    refresh = respuesta.cookies["trulab_refresh"]
    registro = sesion.scalars(select(Sesion).where(Sesion.usuario_id == usuario.id)).one()
    assert registro.token_hash == sha256_hex(refresh)  # en la BD solo el hash
    sesion.refresh(usuario)
    assert usuario.ultimo_acceso is not None
    [evento] = _auditoria(sesion, "LOGIN_EXITOSO")
    assert evento.usuario_id == usuario.id and evento.datos["metodo"] == "password"


def test_username_sin_distinguir_mayusculas_ni_espacios(api: TestClient, sesion: Session) -> None:
    usuario = _operativo(sesion)

    assert _login(api, f"  {(usuario.username or '').upper()} ").status_code == 200


@pytest.mark.parametrize("caso", ["password_incorrecta", "no_existe", "inactivo", "superadmin"])
def test_fallos_de_login_responden_igual(api: TestClient, sesion: Session, caso: str) -> None:
    username, password = username_unico(), PASSWORD
    if caso == "password_incorrecta":
        username = _operativo(sesion).username or ""
        password = "otra-cosa-larga-1"
    elif caso == "inactivo":
        username = _operativo(sesion, activo=False).username or ""
    elif caso == "superadmin":
        # Un SUPERADMIN promovido puede conservar su username, pero no entra por contraseña.
        crear_usuario(sesion, rol=Rol.SUPERADMIN, username=username)

    respuesta = _login(api, username, password)

    assert respuesta.status_code == 401
    assert respuesta.json()["code"] == "CREDENCIALES_INVALIDAS"
    assert respuesta.json()["title"] == "Usuario o contraseña incorrectos"
    assert "trulab_refresh" not in respuesta.cookies
    [evento] = _auditoria(sesion, "LOGIN_FALLIDO")
    assert evento.datos["username"] == username.lower()
    assert password not in str(evento.datos)


def test_bloqueo_tras_intentos_fallidos(api: TestClient, sesion: Session) -> None:
    usuario = _operativo(sesion)
    username = usuario.username or ""
    maximo = get_settings().login_max_failed_attempts

    for _ in range(maximo):
        assert _login(api, username, "incorrecta-larga-1").status_code == 401

    bloqueado = _login(api, username)  # aun con la contraseña correcta
    assert bloqueado.status_code == 429
    assert bloqueado.json()["code"] == "CUENTA_BLOQUEADA_TEMPORALMENTE"
    sesion.refresh(usuario)
    assert usuario.bloqueado_hasta is not None and usuario.bloqueado_hasta > datetime.now(UTC)
    assert [e.datos["motivo"] for e in _auditoria(sesion, "LOGIN_FALLIDO")][-2:] == [
        "BLOQUEO_ACTIVADO",
        "BLOQUEADO",
    ]

    usuario.bloqueado_hasta = datetime.now(UTC) - timedelta(seconds=1)
    sesion.flush()
    assert _login(api, username).status_code == 200


def test_login_correcto_reinicia_intentos(api: TestClient, sesion: Session) -> None:
    usuario = _operativo(sesion)
    _login(api, usuario.username or "", "incorrecta-larga-1")

    _login(api, usuario.username or "")

    sesion.refresh(usuario)
    assert usuario.intentos_fallidos == 0


def test_limite_de_peticiones_por_ip(api: TestClient) -> None:
    respuestas = [_login(api, "nadie", "x").status_code for _ in range(11)]

    assert respuestas[:10] == [401] * 10
    assert respuestas[10] == 429


# --- access token y /me ----------------------------------------------------------------------


def test_me_devuelve_el_perfil(api: TestClient, sesion: Session) -> None:
    usuario = _operativo(sesion, es_prestador_servicios=True)
    login = _login(api, usuario.username or "")

    respuesta = api.get("/api/v1/me", headers=_bearer(login))

    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == str(usuario.id)
    assert respuesta.json()["es_prestador_servicios"] is True
    assert "password_hash" not in respuesta.text and "cedula" not in respuesta.text


@pytest.mark.parametrize(
    ("encabezados", "codigo"),
    [({}, "NO_AUTENTICADO"), ({"Authorization": "Bearer basura"}, "NO_AUTENTICADO")],
)
def test_me_sin_token_valido(api: TestClient, encabezados: dict[str, str], codigo: str) -> None:
    respuesta = api.get("/api/v1/me", headers=encabezados)

    assert respuesta.status_code == 401 and respuesta.json()["code"] == codigo


def test_token_vencido(api: TestClient, sesion: Session) -> None:
    usuario = _operativo(sesion)
    login = _login(api, usuario.username or "")
    registro = sesion.scalars(select(Sesion).where(Sesion.usuario_id == usuario.id)).one()
    vencido, _ = emitir_access_token(
        usuario_id=usuario.id,
        sesion_id=registro.id,
        rol=usuario.rol,
        cambio_password=False,
        secreto=get_settings().jwt_secret,
        ttl=timedelta(seconds=-1),
    )
    assert login.status_code == 200

    respuesta = api.get("/api/v1/me", headers={"Authorization": f"Bearer {vencido}"})

    assert respuesta.status_code == 401 and respuesta.json()["code"] == "TOKEN_EXPIRADO"


def test_desactivar_corta_el_acceso_de_inmediato(api: TestClient, sesion: Session) -> None:
    usuario = _operativo(sesion)
    encabezados = _bearer(_login(api, usuario.username or ""))

    usuario.activo = False
    sesion.flush()

    assert api.get("/api/v1/me", headers=encabezados).status_code == 401


# --- refresh y logout ------------------------------------------------------------------------


def test_refresh_rota_la_sesion(api: TestClient, sesion: Session) -> None:
    usuario = _operativo(sesion)
    login = _login(api, usuario.username or "")
    viejo = login.cookies["trulab_refresh"]

    respuesta = api.post("/api/v1/auth/refresh", headers=SPA)

    assert respuesta.status_code == 200
    nuevo = respuesta.cookies["trulab_refresh"]
    assert nuevo != viejo
    sesiones = {s.token_hash: s for s in sesion.scalars(select(Sesion))}
    assert sesiones[sha256_hex(viejo)].revoked_at is not None
    assert sesiones[sha256_hex(nuevo)].revoked_at is None
    # El access token de la sesión rotada deja de servir.
    assert api.get("/api/v1/me", headers=_bearer(login)).status_code == 401
    assert api.get("/api/v1/me", headers=_bearer(respuesta)).status_code == 200


def test_refresh_exige_encabezado_de_la_spa(api: TestClient, sesion: Session) -> None:
    _login(api, _operativo(sesion).username or "")

    respuesta = api.post("/api/v1/auth/refresh")

    assert respuesta.status_code == 403


def test_refresh_sin_cookie(api: TestClient) -> None:
    respuesta = api.post("/api/v1/auth/refresh", headers=SPA)

    assert respuesta.status_code == 401 and respuesta.json()["code"] == "NO_AUTENTICADO"


def test_reusar_un_refresh_rotado_revoca_todo(api: TestClient, sesion: Session) -> None:
    usuario = _operativo(sesion)
    viejo = _login(api, usuario.username or "").cookies["trulab_refresh"]
    api.post("/api/v1/auth/refresh", headers=SPA)

    api.cookies.clear()
    api.cookies.set("trulab_refresh", viejo)
    respuesta = api.post("/api/v1/auth/refresh", headers=SPA)

    assert respuesta.status_code == 401
    vigentes = sesion.scalars(
        select(Sesion).where(Sesion.usuario_id == usuario.id, Sesion.revoked_at.is_(None))
    ).all()
    assert vigentes == []
    assert _auditoria(sesion, "ACCESO_DENEGADO")[-1].datos["motivo"] == "REFRESH_REUTILIZADO"


def test_logout_revoca_y_borra_la_cookie(api: TestClient, sesion: Session) -> None:
    usuario = _operativo(sesion)
    encabezados = _bearer(_login(api, usuario.username or ""))

    respuesta = api.post("/api/v1/auth/logout", headers={**encabezados, **SPA})

    assert respuesta.status_code == 204
    assert 'trulab_refresh=""' in respuesta.headers["set-cookie"]
    assert api.get("/api/v1/me", headers=encabezados).status_code == 401
    assert api.post("/api/v1/auth/refresh", headers=SPA).status_code == 401


# --- recuperación de contraseña ---------------------------------------------------------------


def _token_del_correo(buzon: Buzon) -> str:
    enlace = next(p for p in buzon.correos[-1].texto.split() if "restablecer-password" in p)
    return parse_qs(urlparse(enlace).query)["token"][0]


def _olvide(api: TestClient, identificador: str) -> Response:
    return api.post("/api/v1/auth/password/forgot", json={"identificador": identificador})


@pytest.mark.parametrize("por", ["username", "correo"])
def test_olvide_password_envia_enlace_de_un_solo_uso(
    api: TestClient, sesion: Session, buzon: Buzon, por: str
) -> None:
    usuario = _operativo(sesion)
    identificador = usuario.username if por == "username" else usuario.correo

    respuesta = _olvide(api, (identificador or "").upper())

    assert respuesta.status_code == 202
    [correo] = buzon.correos
    assert correo.destinatario == usuario.correo
    token = _token_del_correo(buzon)
    assert token not in str(respuesta.json())
    registro = sesion.scalars(
        select(TokenRecuperacionPassword).where(TokenRecuperacionPassword.usuario_id == usuario.id)
    ).one()
    assert registro.token_hash == sha256_hex(token)
    ttl = get_settings().password_reset_ttl_minutes
    assert registro.expires_at - registro.created_at <= timedelta(minutes=ttl, seconds=5)
    assert _auditoria(sesion, "PASSWORD_RECUPERACION_SOLICITADA")[-1].datos["enviado"] is True


@pytest.mark.parametrize("caso", ["no_existe", "inactivo", "superadmin"])
def test_olvide_password_no_revela_cuentas(
    api: TestClient, sesion: Session, buzon: Buzon, caso: str
) -> None:
    identificador = "nadie-registrado"
    if caso == "inactivo":
        identificador = _operativo(sesion, activo=False).username or ""
    elif caso == "superadmin":
        identificador = crear_usuario(sesion, rol=Rol.SUPERADMIN).correo
    referencia = _olvide(api, _operativo(sesion).username or "")
    buzon.correos.clear()

    respuesta = _olvide(api, identificador)

    assert respuesta.status_code == 202 and respuesta.json() == referencia.json()
    assert buzon.correos == []


def test_restablecer_password(api: TestClient, sesion: Session, buzon: Buzon) -> None:
    usuario = _operativo(sesion, debe_cambiar_password=True)
    encabezados = _bearer(_login(api, usuario.username or ""))
    _olvide(api, usuario.username or "")
    token = _token_del_correo(buzon)

    respuesta = api.post(
        "/api/v1/auth/password/reset", json={"token": token, "nueva_password": NUEVA}
    )

    assert respuesta.status_code == 200
    sesion.refresh(usuario)
    assert usuario.debe_cambiar_password is False and usuario.password_cambiada_at is not None
    assert api.get("/api/v1/me", headers=encabezados).status_code == 401  # sesiones revocadas
    assert _login(api, usuario.username or "").status_code == 401
    assert _login(api, usuario.username or "", NUEVA).status_code == 200
    assert _auditoria(sesion, "PASSWORD_CAMBIADA")[-1].datos == {"origen": "recuperacion"}

    reuso = api.post("/api/v1/auth/password/reset", json={"token": token, "nueva_password": NUEVA})
    assert reuso.status_code == 422 and reuso.json()["code"] == "TOKEN_INVALIDO"


def test_token_vencido_o_inventado_no_sirve(api: TestClient, sesion: Session, buzon: Buzon) -> None:
    usuario = _operativo(sesion)
    _olvide(api, usuario.username or "")
    token = _token_del_correo(buzon)
    registro = sesion.scalars(
        select(TokenRecuperacionPassword).where(TokenRecuperacionPassword.usuario_id == usuario.id)
    ).one()
    registro.expires_at = registro.created_at + timedelta(microseconds=1)
    sesion.flush()

    for candidato in (token, "inventado"):
        respuesta = api.post(
            "/api/v1/auth/password/reset", json={"token": candidato, "nueva_password": NUEVA}
        )
        assert respuesta.status_code == 422 and respuesta.json()["code"] == "TOKEN_INVALIDO"


def test_nuevo_enlace_invalida_el_anterior(api: TestClient, sesion: Session, buzon: Buzon) -> None:
    usuario = _operativo(sesion)
    _olvide(api, usuario.username or "")
    primero = _token_del_correo(buzon)
    _olvide(api, usuario.username or "")

    respuesta = api.post(
        "/api/v1/auth/password/reset", json={"token": primero, "nueva_password": NUEVA}
    )

    assert respuesta.status_code == 422


def test_password_debil_no_consume_el_token(api: TestClient, sesion: Session, buzon: Buzon) -> None:
    usuario = _operativo(sesion)
    _olvide(api, usuario.username or "")
    token = _token_del_correo(buzon)

    debil = api.post(
        "/api/v1/auth/password/reset", json={"token": token, "nueva_password": "corta"}
    )

    assert debil.status_code == 422 and debil.json()["code"] == "PASSWORD_DEBIL"
    assert debil.json()["errors"][0]["field"] == "nueva_password"
    ok = api.post("/api/v1/auth/password/reset", json={"token": token, "nueva_password": NUEVA})
    assert ok.status_code == 200


# --- cambio de contraseña y contraseña temporal ---------------------------------------------


@pytest.fixture
def app_con_ruta_protegida(app: FastAPI) -> FastAPI:
    """Agrega una ruta con `UsuarioActual` (las de negocio llegan después de S1-08)."""

    @app.get("/api/v1/_prueba/protegida")
    def protegida(autenticado: UsuarioActual) -> dict[str, str]:
        return {"usuario": str(autenticado.usuario.id)}

    return app


def test_password_temporal_obliga_a_cambiarla(
    app_con_ruta_protegida: FastAPI, api: TestClient, sesion: Session
) -> None:
    usuario = _operativo(sesion, debe_cambiar_password=True)
    login = _login(api, usuario.username or "")
    assert login.status_code == 200 and login.json()["debe_cambiar_password"] is True

    bloqueada = api.get("/api/v1/_prueba/protegida", headers=_bearer(login))
    assert bloqueada.status_code == 403 and bloqueada.json()["code"] == "CAMBIO_PASSWORD_REQUERIDO"
    assert api.get("/api/v1/me", headers=_bearer(login)).status_code == 200

    cambio = api.post(
        "/api/v1/auth/password/change",
        json={"password_actual": PASSWORD, "nueva_password": NUEVA},
        headers=_bearer(login),
    )

    assert cambio.status_code == 200 and cambio.json()["debe_cambiar_password"] is False
    assert api.get("/api/v1/_prueba/protegida", headers=_bearer(cambio)).status_code == 200
    assert api.get("/api/v1/me", headers=_bearer(login)).status_code == 401  # sesión anterior
    assert _auditoria(sesion, "PASSWORD_CAMBIADA")[-1].datos == {
        "origen": "cambio",
        "era_temporal": True,
    }


@pytest.mark.parametrize(
    ("actual", "nueva", "codigo"),
    [
        ("incorrecta-larga-1", NUEVA, "PASSWORD_ACTUAL_INCORRECTA"),
        (PASSWORD, PASSWORD, "PASSWORD_DEBIL"),
        (PASSWORD, "corta", "PASSWORD_DEBIL"),
    ],
)
def test_cambio_de_password_rechazado(
    api: TestClient, sesion: Session, actual: str, nueva: str, codigo: str
) -> None:
    usuario = _operativo(sesion)
    login = _login(api, usuario.username or "")

    respuesta = api.post(
        "/api/v1/auth/password/change",
        json={"password_actual": actual, "nueva_password": nueva},
        headers=_bearer(login),
    )

    assert respuesta.status_code == 422 and respuesta.json()["code"] == codigo


# --- Google: solo SUPERADMIN -----------------------------------------------------------------


def _claims(correo: str, **extra: Any) -> dict[str, Any]:
    claims: dict[str, Any] = {
        "email": correo,
        "email_verified": True,
        "hd": "trulab.co",
        "sub": "1082" + uuid.uuid4().hex[:16],
    }
    claims.update(extra)
    return claims


def _google(api: TestClient, token: str) -> Response:
    return api.post("/api/v1/auth/google", json={"id_token": token})


def test_superadmin_entra_con_google_y_fija_el_sub(
    api: TestClient, sesion: Session, tokens_google: dict[str, dict[str, Any]]
) -> None:
    superadmin = crear_usuario(sesion, rol=Rol.SUPERADMIN)
    tokens_google["valido"] = _claims(superadmin.correo.upper())

    primera = _google(api, "valido")
    segunda = _google(api, "valido")

    assert primera.status_code == 200 and segunda.status_code == 200
    assert primera.json()["usuario"]["rol"] == "SUPERADMIN"
    sesion.refresh(superadmin)
    assert superadmin.google_sub == tokens_google["valido"]["sub"]

    tokens_google["otra-cuenta"] = _claims(superadmin.correo)  # mismo correo, otro `sub`
    assert _google(api, "otra-cuenta").status_code == 403


@pytest.mark.parametrize(
    ("caso", "estado", "codigo"),
    [
        ("otro_dominio", 403, "DOMINIO_NO_PERMITIDO"),
        ("sin_verificar", 403, "USUARIO_NO_REGISTRADO"),
        ("no_registrado", 403, "USUARIO_NO_REGISTRADO"),
        ("operativo", 403, "METODO_ACCESO_NO_PERMITIDO"),
        ("inactivo", 403, "USUARIO_INACTIVO"),
        ("token_invalido", 401, "NO_AUTENTICADO"),
    ],
)
def test_google_deniega(
    api: TestClient,
    sesion: Session,
    tokens_google: dict[str, dict[str, Any]],
    caso: str,
    estado: int,
    codigo: str,
) -> None:
    superadmin = crear_usuario(sesion, rol=Rol.SUPERADMIN, activo=caso != "inactivo")
    claims = _claims(superadmin.correo)
    if caso == "otro_dominio":
        claims = _claims("alguien@gmail.com", hd=None)
    elif caso == "sin_verificar":
        claims["email_verified"] = False
    elif caso == "no_registrado":
        claims = _claims(correo_unico())
    elif caso == "operativo":
        claims = _claims(_operativo(sesion, correo=correo_unico()).correo)
    if caso != "token_invalido":
        tokens_google["token"] = claims

    respuesta = _google(api, "token")

    assert respuesta.status_code == estado and respuesta.json()["code"] == codigo
    if estado == 403:
        assert _auditoria(sesion, "ACCESO_DENEGADO")
    assert sesion.scalars(select(Sesion).where(Sesion.usuario_id == superadmin.id)).all() == []


def test_google_sin_client_id_no_esta_disponible() -> None:
    if get_settings().google_client_id:
        pytest.skip("GOOGLE_CLIENT_ID configurado en este entorno")
    with pytest.raises(LoginGoogleNoDisponible):
        verificar_id_token("cualquiera")


def test_login_de_desarrollo_solo_superadmin(api: TestClient, sesion: Session) -> None:
    superadmin = crear_usuario(sesion, rol=Rol.SUPERADMIN)
    operativo = _operativo(sesion, correo=correo_unico())

    ok = api.post("/api/v1/auth/dev/login", json={"correo": superadmin.correo})
    rechazado = api.post("/api/v1/auth/dev/login", json={"correo": operativo.correo})

    assert ok.status_code == 200 and rechazado.status_code == 403
    sesion.refresh(superadmin)
    assert superadmin.google_sub is None  # no simula una cuenta de Google


def test_login_de_desarrollo_no_existe_fuera_de_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.setenv("MAIL_BACKEND", "ses")
    monkeypatch.setenv("AWS_SES_SENDER", "viaticos@trulab.co")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as cliente:
            respuesta = cliente.post("/api/v1/auth/dev/login", json={"correo": "x@trulab.co"})
        assert respuesta.status_code == 404
    finally:
        get_settings.cache_clear()


def test_la_auditoria_nunca_guarda_contrasenas_ni_tokens(
    api: TestClient, sesion: Session, buzon: Buzon
) -> None:
    usuario = _operativo(sesion)
    login = _login(api, usuario.username or "")
    _login(api, usuario.username or "", "incorrecta-larga-1")
    _olvide(api, usuario.username or "")
    token = _token_del_correo(buzon)
    api.post("/api/v1/auth/password/reset", json={"token": token, "nueva_password": NUEVA})

    eventos = sesion.scalars(select(Auditoria).where(Auditoria.created_at >= func.now()))
    volcado = " ".join(str(e.datos) for e in eventos)

    for secreto in (PASSWORD, NUEVA, "incorrecta-larga-1", token, login.json()["access_token"]):
        assert secreto not in volcado
