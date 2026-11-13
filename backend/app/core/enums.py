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
