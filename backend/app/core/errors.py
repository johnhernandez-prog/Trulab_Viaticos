"""Errores en formato RFC 9457 `application/problem+json` con `code` estable (ADR-014).

Contrato en docs/api-design.md §7.
Las excepciones de dominio de cada módulo heredan de `ErrorDominio`.
"""

import logging
from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.middleware import HEADER

MEDIA_TYPE = "application/problem+json"

logger = logging.getLogger("app.errores")

# Código estable por estado HTTP para los errores que no vienen de una regla de dominio.
_CODIGO_POR_ESTADO = {
    400: "SOLICITUD_INVALIDA",
    401: "NO_AUTENTICADO",
    403: "SIN_PERMISO",
    404: "NO_ENCONTRADO",
    405: "METODO_NO_PERMITIDO",
    413: "ARCHIVO_MUY_GRANDE",
    415: "TIPO_ARCHIVO_NO_PERMITIDO",
    429: "DEMASIADAS_SOLICITUDES",
}


class ErrorDominio(Exception):
    """Base de los errores de negocio. Cada subclase fija `status`, `code` y `title`."""

    status: int = 409
    code: str = "REGLA_NEGOCIO"
    title: str = "La operación no cumple una regla de negocio"

    def __init__(self, detail: str | None = None, errors: list[dict[str, str]] | None = None):
        super().__init__(detail or self.title)
        self.detail = detail
        self.errors = errors


# --- Errores de dominio comunes a todos los módulos (docs/api-design.md §7) ---------------------


class NoEncontrado(ErrorDominio):
    # También para un recurso ajeno: no se revela que existe (ADR-012).
    status = 404
    code = "NO_ENCONTRADO"
    title = "El recurso no existe"


class Duplicado(ErrorDominio):
    status = 409
    code = "DUPLICADO"
    title = "Ya existe un registro con ese valor"


class EnUso(ErrorDominio):
    status = 409
    code = "EN_USO"
    title = "El registro está en uso y no se puede eliminar"


class ValorNoPermitido(ErrorDominio):
    status = 422
    code = "VALOR_NO_PERMITIDO"
    title = "Un valor no está permitido"


def error_de_campo(campo: str, mensaje: str, code: str | None = None) -> list[dict[str, str]]:
    """`errors[]` de un solo campo, con el mismo formato que los errores de validación."""
    return [{"field": campo, "code": code or "VALOR_NO_PERMITIDO", "message": mensaje}]


def problema(
    request: Request,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    errors: list[dict[str, str]] | None = None,
) -> JSONResponse:
    request_id: str | None = getattr(request.state, "request_id", None)
    cuerpo: dict[str, Any] = {
        "type": f"https://trulab.co/errores/{code.lower().replace('_', '-')}",
        "title": title,
        "status": status,
        "code": code,
        "detail": detail,
        "request_id": request_id,
    }
    if errors:
        cuerpo["errors"] = errors
    # El encabezado se agrega aquí porque los 500 se responden por fuera del middleware.
    encabezados = {HEADER: request_id} if request_id else None
    return JSONResponse(cuerpo, status_code=status, media_type=MEDIA_TYPE, headers=encabezados)


# Starlette tipa los manejadores con `Exception`; `cast` refleja la clase con la que se registran.
async def _error_dominio(request: Request, exc: Exception) -> JSONResponse:
    error = cast(ErrorDominio, exc)
    return problema(request, error.status, error.code, error.title, error.detail, error.errors)


async def _error_http(request: Request, exc: Exception) -> JSONResponse:
    error = cast(StarletteHTTPException, exc)
    codigo = _CODIGO_POR_ESTADO.get(error.status_code, "ERROR_HTTP")
    titulo = HTTPStatus(error.status_code).phrase
    detalle = error.detail if isinstance(error.detail, str) and error.detail != titulo else None
    return problema(request, error.status_code, codigo, titulo, detalle)


async def _error_validacion(request: Request, exc: Exception) -> JSONResponse:
    error_validacion = cast(RequestValidationError, exc)
    errores = [
        {
            # Se omite el origen ("body", "query"...) y queda la ruta del campo.
            "field": ".".join(str(parte) for parte in error["loc"][1:]) or str(error["loc"][0]),
            "code": str(error["type"]).upper(),
            "message": str(error["msg"]),
        }
        for error in error_validacion.errors()
    ]
    return problema(request, 422, "VALIDACION", "La solicitud tiene datos inválidos", None, errores)


async def _error_interno(request: Request, exc: Exception) -> JSONResponse:
    # El detalle va solo al log; al cliente nunca se le muestran datos internos.
    logger.error("error_no_controlado", exc_info=exc)
    return problema(request, 500, "ERROR_INTERNO", "Error interno del servidor")


def registrar_manejadores(app: FastAPI) -> None:
    app.add_exception_handler(ErrorDominio, _error_dominio)
    app.add_exception_handler(StarletteHTTPException, _error_http)
    app.add_exception_handler(RequestValidationError, _error_validacion)
    app.add_exception_handler(Exception, _error_interno)
