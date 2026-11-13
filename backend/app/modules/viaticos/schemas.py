"""Esquemas de `/viaticos` (docs/api-design.md §5.4, §6; ADR-029, ADR-030, ADR-031).

- Entrada con `extra="forbid"`: el cliente nunca envía tarifas, totales ni los campos que §8
  prohíbe (`usuario_id`, `estado`, `etapa`, `folio`, `colaborador_*`, dinero calculado).
- `ViaticoCrear` es una unión discriminada por `modalidad` (ADR-029): el cuerpo de
  `CON_SOLICITUD` y el de `LEGALIZACION_DIRECTA` no comparten campos de solicitud.
- Dinero (`Dinero`, ADR-012): siempre sale como *string*.
"""

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.enums import EstadoFinanciero, EstadoOperativo, Etapa, Modalidad
from app.core.types import Dinero, DineroNoNegativo
from app.modules.auth.schemas import Referencia

Motivo = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=500)]
LiderProyecto = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]
Empresa = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Comentarios = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)
]
Ciudad = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ProyectoOtro = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=3, max_length=150)
]
Comentario = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


# --- trayectos (comunes al cálculo y a la solicitud) ----------------------------------------------


class TrayectoEntradaSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    orden: Annotated[int, Field(ge=1, le=5)]
    ciudad_origen: Ciudad
    ciudad_destino: Ciudad
    fecha_ida: datetime
    fecha_regreso: datetime
    requiere_hospedaje: bool = False
    dias_estadia: Annotated[int, Field(ge=1)]


class TrayectoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    orden: int
    ciudad_origen: str
    ciudad_destino: str
    fecha_ida: datetime
    fecha_regreso: datetime
    requiere_hospedaje: bool
    dias_estadia: int
    vr_alimentacion: Dinero | None
    otros_gastos: Dinero | None
    trans_interno: Dinero | None
    transporte_aeropuerto: Dinero | None
    transporte_intermunicipal: Dinero | None
    subtotal_estadia: Dinero | None


# --- POST /viaticos/calcular-presupuesto (vista previa, RN-29) ------------------------------------


class CalcularPresupuestoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proyecto_id: uuid.UUID | None = None
    proyecto_otro: ProyectoOtro | None = None
    requiere_gastos_viaje: bool
    trayectos: Annotated[list[TrayectoEntradaSchema], Field(min_length=1, max_length=5)]


class CalculoPresupuestoSalida(BaseModel):
    aplica: bool
    motivo_no_aplica: str | None
    trayectos: list[TrayectoSalida]
    presupuesto_solicitado: Dinero | None
    exige_formato_prestador: bool


# --- POST /viaticos: CON_SOLICITUD y LEGALIZACION_DIRECTA (ADR-029) -------------------------------


class ViaticoCrearConSolicitud(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modalidad: Literal[Modalidad.CON_SOLICITUD] = Modalidad.CON_SOLICITUD
    motivo_viaje: Motivo
    proyecto_id: uuid.UUID | None = None
    proyecto_otro: ProyectoOtro | None = None
    lider_proyecto: LiderProyecto
    empresa: Empresa | None = None
    requiere_tiquete: bool = False
    requiere_gastos_viaje: bool = False
    comentarios: Comentarios | None = None
    trayectos: Annotated[list[TrayectoEntradaSchema], Field(min_length=1, max_length=5)]


class ViaticoCrearLegalizacionDirecta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    modalidad: Literal[Modalidad.LEGALIZACION_DIRECTA] = Modalidad.LEGALIZACION_DIRECTA
    motivo_viaje: Motivo
    recursos_propios: bool = False


ViaticoCrear = Annotated[
    ViaticoCrearConSolicitud | ViaticoCrearLegalizacionDirecta,
    Field(discriminator="modalidad"),
]


# --- GET /viaticos/{id} (detalle) -----------------------------------------------------------------


class ColaboradorSalida(BaseModel):
    nombre: str
    cargo: str | None
    celula: str | None
    es_prestador_servicios: bool


class ProyectoRefSalida(BaseModel):
    id: uuid.UUID | None
    nombre: str
    en_catalogo: bool


class SolicitudSalida(BaseModel):
    proyecto: ProyectoRefSalida
    lider_proyecto: str
    empresa: str | None
    requiere_tiquete: bool
    requiere_gastos_viaje: bool
    presupuesto_solicitado: Dinero | None
    comentarios: str | None
    trayectos: list[TrayectoSalida]


class EventoSalida(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    etapa: Etapa
    accion: str
    dimension: str | None
    estado_anterior: str | None
    estado_nuevo: str | None
    comentario: str | None
    usuario_id: uuid.UUID
    created_at: datetime


class ViaticoDetalle(BaseModel):
    id: uuid.UUID
    folio: str
    modalidad: Modalidad
    etapa: Etapa
    estado: EstadoOperativo
    estado_financiero: EstadoFinanciero
    devuelta_at: datetime | None
    usuario: Referencia
    colaborador: ColaboradorSalida
    motivo_viaje: str
    solicitud: SolicitudSalida | None
    fecha_legalizacion: date
    recursos_propios: bool
    valor_asignado: Dinero
    valor_transferido: Dinero
    total_gastos: Dinero
    saldo: Dinero
    acciones_permitidas: list[str]
    eventos: list[EventoSalida]
    created_at: datetime
    updated_at: datetime


# --- GET /viaticos (listado paginado, S2-05) ----------------------------------------------------


class ViaticoResumen(BaseModel):
    id: uuid.UUID
    folio: str
    modalidad: Modalidad
    etapa: Etapa
    estado: EstadoOperativo
    estado_financiero: EstadoFinanciero
    usuario: Referencia
    motivo_viaje: str
    fecha_legalizacion: date
    recursos_propios: bool
    valor_asignado: Dinero
    valor_transferido: Dinero
    presupuesto_solicitado: Dinero | None
    total_gastos: Dinero
    saldo: Dinero
    acciones_permitidas: list[str]
    created_at: datetime


# --- PATCH /viaticos/{id} (S2-05: dueño o SUPERADMIN, PENDIENTE/PENDIENTE, RN-09/S-05) -----------


class ViaticoEditar(BaseModel):
    """Edición parcial: solo cambian los campos enviados. El service decide, según la etapa
    actual del viático, cuáles aplican (`422 VALOR_NO_PERMITIDO` para el resto)."""

    model_config = ConfigDict(extra="forbid")

    motivo_viaje: Motivo | None = None
    proyecto_id: uuid.UUID | None = None
    proyecto_otro: ProyectoOtro | None = None
    lider_proyecto: LiderProyecto | None = None
    empresa: Empresa | None = None
    requiere_tiquete: bool | None = None
    requiere_gastos_viaje: bool | None = None
    comentarios: Comentarios | None = None
    trayectos: Annotated[list[TrayectoEntradaSchema], Field(min_length=1, max_length=5)] | None = (
        None
    )
    recursos_propios: bool | None = None


# --- acciones de la máquina de estados (S2-05) ----------------------------------------------------


class AccionEntrada(BaseModel):
    """Cuerpo de `aprobar`/`rechazar`/`devolver`: el comentario es obligatorio solo para rechazar
    y devolver (el service lo valida, `422 COMENTARIO_REQUERIDO`, para dar ese código exacto)."""

    model_config = ConfigDict(extra="forbid")

    comentario: Comentario | None = None


# --- tiquetes y dinero (S2-07) --------------------------------------------------------------------

Referencia200 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]


class GestionarTiquetesEntrada(BaseModel):
    """S-10: registro de la emisión de tiquetes; comentario y referencia opcionales."""

    model_config = ConfigDict(extra="forbid")

    comentario: Comentario | None = None
    referencia: Referencia200 | None = None


class ValorAsignadoEntrada(BaseModel):
    """RN-19: lo registra FINANCIERO/SUPERADMIN; `>= 0` (RN-08). `valor_transferido` no se
    acepta nunca: lo calcula la BD (RN-14)."""

    model_config = ConfigDict(extra="forbid")

    valor_asignado: DineroNoNegativo
    comentario: Comentario | None = None


class EstadoFinancieroEntrada(BaseModel):
    """S-03: se envía el estado destino; las transiciones válidas las decide el service."""

    model_config = ConfigDict(extra="forbid")

    estado_financiero: EstadoFinanciero
    comentario: Comentario | None = None
