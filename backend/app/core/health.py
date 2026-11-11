"""`GET /api/v1/health`: estado de la API y de la BD, sin autenticación (docs/api-design.md §2)."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import __version__
from app.core.db import bd_disponible

router = APIRouter(tags=["salud"])

Estado = Literal["ok", "error"]


class Salud(BaseModel):
    status: Estado
    version: str
    db: Estado


@router.get(
    "/health",
    response_model=Salud,
    summary="Estado de la API y de la base de datos",
    responses={503: {"model": Salud, "description": "La base de datos no responde"}},
)
def health(bd_ok: Annotated[bool, Depends(bd_disponible)]) -> JSONResponse:
    estado: Estado = "ok" if bd_ok else "error"
    salud = Salud(status=estado, version=__version__, db=estado)
    # 503 si la BD no responde, para que el healthcheck de Docker marque la API como no sana.
    return JSONResponse(salud.model_dump(), status_code=200 if bd_ok else 503)
