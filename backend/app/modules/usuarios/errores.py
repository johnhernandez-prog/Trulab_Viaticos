"""Errores de la gestión de usuarios con su `code` estable (docs/api-design.md §5.1 y §7)."""

from app.core.errors import ErrorDominio


class UltimoSuperadmin(ErrorDominio):
    # RN-12: siempre debe quedar al menos un SUPERADMIN activo.
    status = 409
    code = "ULTIMO_SUPERADMIN"
    title = "Debe existir al menos un superadministrador activo"


class SuperadminSinPassword(ErrorDominio):
    status = 409
    code = "SUPERADMIN_SIN_PASSWORD"
    title = "Un superadministrador entra con Google y no tiene contraseña"


class AccionSobreSiMismo(ErrorDominio):
    status = 409
    code = "ACCION_SOBRE_SI_MISMO"
    title = "No puede realizar esta acción sobre su propio usuario"
