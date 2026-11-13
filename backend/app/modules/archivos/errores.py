"""Errores de archivos con su `code` estable (docs/api-design.md §7)."""

from app.core.errors import ErrorDominio


class ArchivoMuyGrande(ErrorDominio):
    status = 413
    code = "ARCHIVO_MUY_GRANDE"
    title = "El archivo supera el tamaño máximo permitido"


class TipoArchivoNoPermitido(ErrorDominio):
    # RN-13: el tipo real (por contenido) no se admite para ese propósito o campo.
    status = 415
    code = "TIPO_ARCHIVO_NO_PERMITIDO"
    title = "El tipo de archivo no está permitido"
