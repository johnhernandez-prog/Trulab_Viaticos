"""Consulta de la auditoría (docs/api-design.md §5.8): solo SUPERADMIN (`auditoria:leer`).

Solo lectura: la tabla es de solo inserción. La UI llega después del MVP.
"""

import ipaddress
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import select

from app.core.audit import Auditoria
from app.core.paginacion import Pagina, Paginacion, paginar
from app.core.permissions import Permiso, require_permission
from app.modules.auth.dependencias import DB, Autenticado

router = APIRouter(prefix="/auditoria", tags=["auditoria"])

Auditor = Annotated[Autenticado, Depends(require_permission(Permiso.AUDITORIA_LEER))]


class EventoAuditoria(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    usuario_id: uuid.UUID | None
    accion: str
    entidad: str
    entidad_id: uuid.UUID | None
    datos: dict[str, Any]
    ip: str | None
    created_at: datetime

    @field_validator("ip", mode="before")
    @classmethod
    def _ip_como_texto(cls, valor: object) -> object:
        # psycopg devuelve INET como objeto de `ipaddress`.
        if isinstance(valor, ipaddress.IPv4Address | ipaddress.IPv6Address):
            return str(valor)
        return valor


@router.get("", summary="Consultar la auditoría (más reciente primero)")
def listar(
    _: Auditor,
    session: DB,
    paginacion: Paginacion,
    entidad: str | None = None,
    entidad_id: uuid.UUID | None = None,
    usuario_id: uuid.UUID | None = None,
    accion: str | None = None,
    desde: date | None = None,
    hasta: date | None = None,
) -> Pagina[EventoAuditoria]:
    consulta = select(Auditoria)
    if entidad:
        consulta = consulta.where(Auditoria.entidad == entidad)
    if entidad_id:
        consulta = consulta.where(Auditoria.entidad_id == entidad_id)
    if usuario_id:
        consulta = consulta.where(Auditoria.usuario_id == usuario_id)
    if accion:
        consulta = consulta.where(Auditoria.accion == accion.upper())
    # Fechas en UTC; `hasta` es inclusivo (todo el día).
    if desde:
        consulta = consulta.where(
            Auditoria.created_at >= datetime.combine(desde, time.min, tzinfo=UTC)
        )
    if hasta:
        limite = datetime.combine(hasta + timedelta(days=1), time.min, tzinfo=UTC)
        consulta = consulta.where(Auditoria.created_at < limite)
    filas, total = paginar(session, consulta.order_by(Auditoria.id.desc()), paginacion)
    return Pagina[EventoAuditoria](
        items=[EventoAuditoria.model_validate(e) for e in filas],
        total=total,
        page=paginacion.page,
        size=paginacion.size,
    )
