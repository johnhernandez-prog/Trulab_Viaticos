"""Enums fijos del sistema (docs/database-design.md §2.13).

En la BD son `TEXT` + `CHECK`; este es el único módulo del backend que los define. Las listas de
negocio (proyectos, rubros, células) NO van aquí: son tablas de catálogo (DP-14, ADR-022).
"""

from enum import StrEnum


class Rol(StrEnum):
    """Rol del usuario (uno por usuario). Determina los permisos (`app/core/permissions.py`)."""

    VIAJERO = "VIAJERO"
    FINANCIERO = "FINANCIERO"
    ADMIN = "ADMIN"
    SUPERADMIN = "SUPERADMIN"


class Modalidad(StrEnum):
    """Cómo nace el viático (ADR-029). Inmutable."""

    CON_SOLICITUD = "CON_SOLICITUD"
    LEGALIZACION_DIRECTA = "LEGALIZACION_DIRECTA"


class Etapa(StrEnum):
    SOLICITUD = "SOLICITUD"
    LEGALIZACION = "LEGALIZACION"


class EstadoOperativo(StrEnum):
    """`viaticos.estado` (AppSheet `Estado`): lo cambian ADMIN/SUPERADMIN (DP-13)."""

    PENDIENTE = "PENDIENTE"
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"


class EstadoFinanciero(StrEnum):
    """`viaticos.estado_financiero` (AppSheet `Estado_P`): FINANCIERO/SUPERADMIN (DP-13)."""

    PENDIENTE = "PENDIENTE"
    TRANSFERIDO = "TRANSFERIDO"
    PAGADO = "PAGADO"
    PROCESADO = "PROCESADO"


class PropositoArchivo(StrEnum):
    """Para qué se subió un archivo; el service valida el tipo MIME según el propósito (RN-13)."""

    SOPORTE = "SOPORTE"
    ARCHIVO = "ARCHIVO"
    FIRMA = "FIRMA"
    FORMATO_PRESTADOR = "FORMATO_PRESTADOR"


class AccionViatico(StrEnum):
    """Acciones del historial `viatico_eventos` (docs/database-design.md §2.9)."""

    CREAR = "CREAR"
    EDITAR_SOLICITUD = "EDITAR_SOLICITUD"
    APROBAR = "APROBAR"
    RECHAZAR = "RECHAZAR"
    DEVOLVER = "DEVOLVER"
    GESTIONAR_TIQUETES = "GESTIONAR_TIQUETES"
    HABILITAR_LEGALIZACION = "HABILITAR_LEGALIZACION"
    CAMBIAR_ESTADO_FINANCIERO = "CAMBIAR_ESTADO_FINANCIERO"
    EDITAR_VALOR_ASIGNADO = "EDITAR_VALOR_ASIGNADO"
    CAMBIAR_RECURSOS_PROPIOS = "CAMBIAR_RECURSOS_PROPIOS"
    LIQUIDAR = "LIQUIDAR"
    ELIMINAR = "ELIMINAR"


class DimensionEvento(StrEnum):
    OPERATIVO = "OPERATIVO"
    FINANCIERO = "FINANCIERO"
    ETAPA = "ETAPA"


def valores_sql(enum: type[StrEnum]) -> str:
    """`'A', 'B', …` para los `CHECK (col IN (…))` (la BD guarda `TEXT` + `CHECK`)."""
    return ", ".join(f"'{miembro.value}'" for miembro in enum)
