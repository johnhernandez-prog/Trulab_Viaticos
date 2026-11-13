"""Middleware ASGI de `X-Request-ID` y registro de acceso (docs/api-design.md §7)."""

import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logs import request_id_var

HEADER = "X-Request-ID"
# Se acepta el id del cliente solo si es corto y seguro; si no, se genera uno nuevo.
_ID_VALIDO = re.compile(r"^[A-Za-z0-9._-]{1,128}$")

logger = logging.getLogger("app.acceso")


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        recibido = dict(scope["headers"]).get(HEADER.lower().encode(), b"").decode("latin-1")
        request_id = recibido if _ID_VALIDO.match(recibido) else uuid.uuid4().hex
        # Disponible en `request.state.request_id` (también para el manejador de errores 500).
        scope.setdefault("state", {})["request_id"] = request_id
        request_id_var.set(request_id)

        inicio = time.perf_counter()
        estado = 500

        async def send_con_id(message: Message) -> None:
            nonlocal estado
            if message["type"] == "http.response.start":
                estado = message["status"]
                MutableHeaders(scope=message)[HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_con_id)
        finally:
            # Solo método y ruta: la query string podría contener datos sensibles.
            logger.info(
                "peticion",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": estado,
                    "duration_ms": round((time.perf_counter() - inicio) * 1000, 1),
                },
            )


class LimiteCuerpoAdjuntosMiddleware:
    """Rechaza con `413 ARCHIVO_MUY_GRANDE` una subida cuyo `Content-Length` ya excede el límite
    (docs/api-design.md §8), **antes** de que FastAPI lea y analice el multipart (que ocurre
    antes que cualquier dependencia de la ruta). Una subida sin `Content-Length` (chunked) la
    acota igual la lectura con límite del router."""

    def __init__(self, app: ASGIApp, *, rutas: frozenset[str], limite_bytes: int) -> None:
        self.app = app
        self.rutas = rutas
        self.limite_bytes = limite_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"] in self.rutas:
            longitud = dict(scope["headers"]).get(b"content-length", b"").decode("latin-1")
            if longitud.isdigit() and int(longitud) > self.limite_bytes:
                from starlette.requests import Request

                from app.core.errors import problema

                respuesta = problema(
                    Request(scope),
                    413,
                    "ARCHIVO_MUY_GRANDE",
                    "El archivo supera el tamaño máximo permitido",
                )
                await respuesta(scope, receive, send)
                return
        await self.app(scope, receive, send)
