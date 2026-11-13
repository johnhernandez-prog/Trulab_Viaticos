"""Esquemas de `/viaticos/{viatico_id}/gastos` (docs/api-design.md §5.5; S2-06).

- Entrada JSON con `extra="forbid"`: los adjuntos se suben antes por `POST /archivos` y aquí solo
  se referencian por id (`soporte_id` = imagen, `archivo_id` = PDF; DP-15, RN-13).
- Proyecto híbrido (RN-16, ADR-031): exactamente uno de `proyecto_id` o `proyecto_otro`.
- `valor` > 0 (RN-08), como `Dinero` (string en la salida, ADR-012).
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

from app.core.types import Dinero, DineroPositivo
from app.modules.auth.schemas import Referencia
from app.modules.viaticos.schemas import ProyectoOtro, ProyectoRefSalida

Concepto = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
CcNit = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
Empresa = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Observaciones = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]


class GastoCrear(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fecha_factura: date
    rubro_id: uuid.UUID
    proyecto_id: uuid.UUID | None = None
    proyecto_otro: ProyectoOtro | None = None
    concepto: Concepto
    cc_nit: CcNit | None = None
    empresa: Empresa | None = None
    valor: DineroPositivo
    observaciones: Observaciones | None = None
    soporte_id: uuid.UUID | None = None
    archivo_id: uuid.UUID | None = None


_NO_NULOS = ("fecha_factura", "rubro_id", "concepto", "valor")


class GastoEditar(BaseModel):
    """Solo lo que se envía cambia. `soporte_id`/`archivo_id` en `null` quitan el adjunto (el
    gasto puede quedar sin comprobante, RN-21); un id nuevo lo reemplaza."""

    model_config = ConfigDict(extra="forbid")

    fecha_factura: date | None = None
    rubro_id: uuid.UUID | None = None
    proyecto_id: uuid.UUID | None = None
    proyecto_otro: ProyectoOtro | None = None
    concepto: Concepto | None = None
    cc_nit: CcNit | None = None
    empresa: Empresa | None = None
    valor: DineroPositivo | None = None
    observaciones: Observaciones | None = None
    soporte_id: uuid.UUID | None = None
    archivo_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def _obligatorios_no_nulos(self) -> Self:
        for campo in _NO_NULOS:
            if campo in self.model_fields_set and getattr(self, campo) is None:
                raise ValueError(f"'{campo}' no puede ser null")
        return self


class AdjuntoRef(BaseModel):
    id: uuid.UUID
    # `None` si el archivo no es visible para quien consulta (lo subió otro usuario, RLS).
    nombre: str | None
    mime_type: str | None


class GastoSalida(BaseModel):
    id: uuid.UUID
    viatico_id: uuid.UUID
    fecha_factura: date
    rubro: Referencia
    proyecto: ProyectoRefSalida
    concepto: str
    cc_nit: str | None
    empresa: str | None
    valor: Dinero
    observaciones: str | None
    soporte: AdjuntoRef | None
    archivo: AdjuntoRef | None
    # RN-21: al menos uno de soporte o archivo (exigido para aprobar y liquidar).
    tiene_comprobante: bool
    created_at: datetime
    updated_at: datetime
