"""Esquemas de `/archivos` y `/me/firma` (docs/api-design.md §5.1 y §5.9)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import PropositoArchivo


class ArchivoSalida(BaseModel):
    """Metadatos de un archivo subido. Nunca incluye la clave de almacenamiento."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre_original: str
    mime_type: str
    tamano_bytes: int
    sha256: str
    proposito: PropositoArchivo
    created_at: datetime


class ArchivoUrl(BaseModel):
    """URL temporal de lectura: prefirmada de S3 (o firmada en local), vigente 5 minutos."""

    url: str
    expires_at: datetime
    mime_type: str
    nombre: str


class FirmaAsignar(BaseModel):
    model_config = ConfigDict(extra="forbid")

    archivo_id: uuid.UUID


class FirmaSalida(ArchivoUrl):
    archivo_id: uuid.UUID
