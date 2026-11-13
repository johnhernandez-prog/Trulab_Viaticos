"""Metadatos de los archivos guardados en el bucket S3 privado (docs/database-design.md §2.4).

Soportes (imagen) y archivos (PDF) de gastos, firmas y formatos de prestador. El contenido vive
en el almacenamiento (`STORAGE_BACKEND`); aquí solo la clave, el tipo detectado por contenido,
el tamaño y el SHA-256. Las filas son **inmutables**: reemplazar un soporte crea otra fila
(`trulab_app` no tiene `UPDATE` ni `DELETE`). La subida y la validación llegan en S2-07.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import PropositoArchivo, valores_sql
from app.core.models import Base, ConId

TAMANO_MAXIMO_BYTES = 10 * 1024 * 1024  # 10 MB (docs/architecture.md, RN-13)


class Archivo(ConId, Base):
    __tablename__ = "archivos"

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="RESTRICT"), index=True
    )
    storage_key: Mapped[str] = mapped_column(Text, unique=True)
    nombre_original: Mapped[str] = mapped_column(Text)
    mime_type: Mapped[str] = mapped_column(Text)
    tamano_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(Text)
    proposito: Mapped[str] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(f"proposito IN ({valores_sql(PropositoArchivo)})", name="proposito"),
        CheckConstraint(
            f"tamano_bytes > 0 AND tamano_bytes <= {TAMANO_MAXIMO_BYTES}", name="tamano_maximo"
        ),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
        CheckConstraint("btrim(storage_key) <> ''", name="storage_key_no_vacia"),
        CheckConstraint("btrim(nombre_original) <> ''", name="nombre_original_no_vacio"),
        CheckConstraint("mime_type ~ '^[a-z]+/[a-z0-9.+-]+$'", name="mime_type_formato"),
        Index("ix_archivos__sha256", "sha256"),
    )
