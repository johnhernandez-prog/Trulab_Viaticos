"""Punto de entrada de la API: `uvicorn app.main:app`."""

from fastapi import FastAPI

from app import __version__
from app.core import health
from app.core.config import get_settings
from app.core.errors import registrar_manejadores
from app.core.logs import configurar_logging
from app.core.middleware import LimiteCuerpoAdjuntosMiddleware, RequestIdMiddleware
from app.modules.archivos import router as archivos
from app.modules.auditoria import router as auditoria
from app.modules.auth import router as auth
from app.modules.cargos import router as cargos
from app.modules.catalogos import router as catalogos
from app.modules.gastos import router as gastos
from app.modules.indicadores import router as indicadores
from app.modules.pagos import router as pagos
from app.modules.usuarios import router as usuarios
from app.modules.viaticos import router as viaticos

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
    # Interno respecto de RequestIdMiddleware (el último agregado es el externo): el 413 temprano
    # sale con su X-Request-ID. Margen de 1 MB para los encabezados del multipart (§8: 11 MB).
    app.add_middleware(
        LimiteCuerpoAdjuntosMiddleware,
        rutas=frozenset({f"{API_PREFIX}/archivos"}),
        limite_bytes=(settings.max_upload_mb + 1) * 1024 * 1024,
    )
    app.add_middleware(RequestIdMiddleware)
    registrar_manejadores(app)

    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(auth.router, prefix=API_PREFIX)
    app.include_router(auth.router_me, prefix=API_PREFIX)
    app.include_router(usuarios.router, prefix=API_PREFIX)
    app.include_router(cargos.router, prefix=API_PREFIX)
    app.include_router(catalogos.router, prefix=API_PREFIX)
    app.include_router(viaticos.router, prefix=API_PREFIX)
    app.include_router(gastos.router, prefix=API_PREFIX)
    app.include_router(pagos.router, prefix=API_PREFIX)
    app.include_router(indicadores.router, prefix=API_PREFIX)
    app.include_router(archivos.router, prefix=API_PREFIX)
    app.include_router(archivos.router_firma, prefix=API_PREFIX)
    app.include_router(auditoria.router, prefix=API_PREFIX)
    if settings.env == "local":
        # Login de SUPERADMIN sin OAuth Client ID (R1.1). Fuera de local la ruta no existe (404).
        app.include_router(auth.router_desarrollo, prefix=API_PREFIX)
    return app


app = create_app()
