"""Punto de entrada de la API: `uvicorn app.main:app`."""

from fastapi import FastAPI

from app import __version__
from app.core import health
from app.core.config import get_settings
from app.core.errors import registrar_manejadores
from app.core.logs import configurar_logging
from app.core.middleware import RequestIdMiddleware

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    configurar_logging(settings.log_level)

    docs = settings.docs_habilitada
    app = FastAPI(
        title="Trulab Viajes API",
        version=__version__,
        # El contrato OpenAPI vive bajo el prefijo versionado (docs/api-design.md §1).
        openapi_url=f"{API_PREFIX}/openapi.json" if docs else None,
        docs_url=f"{API_PREFIX}/docs" if docs else None,
        redoc_url=None,
    )
    app.add_middleware(RequestIdMiddleware)
    registrar_manejadores(app)

    app.include_router(health.router, prefix=API_PREFIX)
    # Los routers de los módulos de dominio se registran aquí a partir de S1-08.
    return app


app = create_app()
