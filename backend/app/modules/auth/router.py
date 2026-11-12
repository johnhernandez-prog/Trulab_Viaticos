"""Rutas de autenticación (`/auth/*`) y perfil (`/me`). Contrato: docs/api-design.md §3.

Routers delgados: la lógica está en `service.py`. Aquí solo viven la cookie de refresh, el
encabezado anti-CSRF, los límites de peticiones y el envío del correo en segundo plano.
"""

from contextlib import suppress
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status

from app.core.config import Settings
from app.core.mail import Correo, ErrorEnvioCorreo, Mailer, get_mailer
from app.core.rate_limit import limitar
from app.modules.auth import service
from app.modules.auth.dependencias import (
    DB,
    Config,
    Ctx,
    UsuarioActualPermitiendoCambio,
)
from app.modules.auth.errores import SolicitudSpaRequerida
from app.modules.auth.google import VerificadorGoogle, get_verificador_google
from app.modules.auth.schemas import (
    CambiarPasswordEntrada,
    DevLoginEntrada,
    GoogleEntrada,
    LoginEntrada,
    MensajeSalida,
    OlvidePasswordEntrada,
    RestablecerPasswordEntrada,
    SesionSalida,
    UsuarioActualSalida,
)

COOKIE_REFRESH = "trulab_refresh"
COOKIE_PATH = "/api/v1/auth"
ENCABEZADO_SPA = ("x-requested-with", "trulab-spa")

MENSAJE_RECUPERACION = (
    "Si la cuenta existe y está activa, enviaremos un enlace de restablecimiento al correo "
    "registrado."
)

router = APIRouter(prefix="/auth", tags=["auth"])
router_me = APIRouter(tags=["auth"])
# Solo se registra con ENV=local (create_app): login de SUPERADMIN sin OAuth Client ID (R1.1).
router_desarrollo = APIRouter(prefix="/auth", tags=["auth (solo local)"])


def _exigir_spa(request: Request) -> None:
    nombre, valor = ENCABEZADO_SPA
    if request.headers.get(nombre) != valor:
        raise SolicitudSpaRequerida()


def _poner_cookie(response: Response, refresh: str, settings: Settings) -> None:
    response.set_cookie(
        COOKIE_REFRESH,
        refresh,
        max_age=settings.refresh_token_ttl_days * 86400,
        path=COOKIE_PATH,
        httponly=True,
        # En local la SPA va por http://localhost; en staging y producción, solo HTTPS.
        secure=settings.env != "local",
        samesite="strict",
    )


def _borrar_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        COOKIE_REFRESH,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.env != "local",
        samesite="strict",
    )


def _respuesta(
    session: DB, emitida: service.SesionEmitida, response: Response, settings: Settings
) -> SesionSalida:
    _poner_cookie(response, emitida.refresh_token, settings)
    return SesionSalida(
        access_token=emitida.access_token,
        expires_in=emitida.expires_in,
        debe_cambiar_password=emitida.usuario.debe_cambiar_password,
        usuario=service.perfil(session, emitida.usuario),
    )


@router.post(
    "/login",
    summary="Iniciar sesión con usuario y contraseña (VIAJERO, ADMIN, FINANCIERO)",
    dependencies=[Depends(limitar("auth.login", 10, 60))],
)
def login(
    datos: LoginEntrada, session: DB, settings: Config, ctx: Ctx, response: Response
) -> SesionSalida:
    emitida = service.iniciar_sesion_password(
        session, datos.username, datos.password, settings, ctx
    )
    return _respuesta(session, emitida, response, settings)


@router.post(
    "/google",
    summary="Iniciar sesión con Google Workspace (solo SUPERADMIN)",
    dependencies=[Depends(limitar("auth.google", 10, 60))],
)
def login_google(
    datos: GoogleEntrada,
    session: DB,
    settings: Config,
    ctx: Ctx,
    response: Response,
    verificar: Annotated[VerificadorGoogle, Depends(get_verificador_google)],
) -> SesionSalida:
    claims = verificar(datos.id_token)
    emitida = service.iniciar_sesion_google(session, claims, settings, ctx)
    return _respuesta(session, emitida, response, settings)


@router_desarrollo.post(
    "/dev/login",
    summary="Login de desarrollo de SUPERADMIN por correo (solo ENV=local)",
)
def login_desarrollo(
    datos: DevLoginEntrada, session: DB, settings: Config, ctx: Ctx, response: Response
) -> SesionSalida:
    claims = {
        "email": datos.correo,
        "email_verified": True,
        "hd": settings.google_workspace_domain,
    }
    emitida = service.iniciar_sesion_google(session, claims, settings, ctx, metodo="desarrollo")
    return _respuesta(session, emitida, response, settings)


@router.post(
    "/password/forgot",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Solicitar el enlace de restablecimiento de contraseña",
    dependencies=[Depends(limitar("auth.forgot", 5, 900))],
)
def olvide_password(
    datos: OlvidePasswordEntrada,
    session: DB,
    settings: Config,
    ctx: Ctx,
    tareas: BackgroundTasks,
    mailer: Annotated[Mailer, Depends(get_mailer)],
) -> MensajeSalida:
    correo = service.solicitar_recuperacion(session, datos.identificador, settings, ctx)
    if correo is not None:
        tareas.add_task(_enviar_sin_revelar, mailer, correo)
    return MensajeSalida(detail=MENSAJE_RECUPERACION)


def _enviar_sin_revelar(mailer: Mailer, correo: Correo) -> None:
    # Un fallo de envío ya quedó en el log (Mailer); al usuario se le responde igual siempre.
    with suppress(ErrorEnvioCorreo):
        mailer.enviar(correo)


@router.post(
    "/password/reset",
    summary="Fijar una contraseña nueva con el token del correo",
    dependencies=[Depends(limitar("auth.reset", 10, 900))],
)
def restablecer_password(datos: RestablecerPasswordEntrada, session: DB, ctx: Ctx) -> MensajeSalida:
    service.restablecer_password(session, datos.token, datos.nueva_password, ctx)
    return MensajeSalida(detail="Contraseña actualizada. Inicie sesión con la nueva contraseña.")


@router.post("/password/change", summary="Cambiar la contraseña (también la temporal)")
def cambiar_password(
    datos: CambiarPasswordEntrada,
    autenticado: UsuarioActualPermitiendoCambio,
    session: DB,
    settings: Config,
    ctx: Ctx,
    response: Response,
) -> SesionSalida:
    emitida = service.cambiar_password(
        session, autenticado.usuario, datos.password_actual, datos.nueva_password, settings, ctx
    )
    return _respuesta(session, emitida, response, settings)


@router.post(
    "/refresh",
    summary="Renovar el access token con la cookie de refresh (rotativa)",
    dependencies=[Depends(_exigir_spa)],
)
def refresh(
    request: Request, session: DB, settings: Config, ctx: Ctx, response: Response
) -> SesionSalida:
    emitida = service.renovar_sesion(session, request.cookies.get(COOKIE_REFRESH), settings, ctx)
    return _respuesta(session, emitida, response, settings)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cerrar la sesión actual",
    dependencies=[Depends(_exigir_spa)],
)
def logout(
    request: Request,
    autenticado: UsuarioActualPermitiendoCambio,
    session: DB,
    settings: Config,
    response: Response,
) -> None:
    service.cerrar_sesion(session, autenticado.sesion_id, request.cookies.get(COOKIE_REFRESH))
    _borrar_cookie(response, settings)


@router_me.get("/me", summary="Usuario autenticado")
def me(autenticado: UsuarioActualPermitiendoCambio, session: DB) -> UsuarioActualSalida:
    return service.perfil(session, autenticado.usuario)
