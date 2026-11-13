"""Detección del tipo real de un archivo por su contenido (*magic bytes*, RN-13).

Función **pura**: no confía en la extensión ni en el `Content-Type` que manda el cliente. Lo que
no se reconoce devuelve `None` y se rechaza (`415`): así quedan fuera ejecutables disfrazados de
PDF o JPG, SVG, HTML y cualquier otro formato no admitido.

Tipos admitidos por propósito (RN-13, DP-15, RN-32, RN-33):

| Propósito | Tipos |
| :--- | :--- |
| `SOPORTE` (gasto) | JPEG, PNG, WEBP, HEIC |
| `ARCHIVO` (gasto) | PDF |
| `FIRMA` | JPEG, PNG, WEBP |
| `FORMATO_PRESTADOR` | PDF, XLSX, XLS |
"""

import io
import zipfile
from collections.abc import Mapping
from types import MappingProxyType

from app.core.enums import PropositoArchivo

JPEG = "image/jpeg"
PNG = "image/png"
WEBP = "image/webp"
HEIC = "image/heic"
PDF = "application/pdf"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLS = "application/vnd.ms-excel"

IMAGENES = frozenset({JPEG, PNG, WEBP, HEIC})

PERMITIDOS: Mapping[PropositoArchivo, frozenset[str]] = MappingProxyType(
    {
        PropositoArchivo.SOPORTE: frozenset({JPEG, PNG, WEBP, HEIC}),
        PropositoArchivo.ARCHIVO: frozenset({PDF}),
        PropositoArchivo.FIRMA: frozenset({JPEG, PNG, WEBP}),
        PropositoArchivo.FORMATO_PRESTADOR: frozenset({PDF, XLSX, XLS}),
    }
)

EXTENSION: Mapping[str, str] = MappingProxyType(
    {
        JPEG: ".jpg",
        PNG: ".png",
        WEBP: ".webp",
        HEIC: ".heic",
        PDF: ".pdf",
        XLSX: ".xlsx",
        XLS: ".xls",
    }
)

_FIRMA_PNG = b"\x89PNG\r\n\x1a\n"
_FIRMA_OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"  # Compound File Binary (Excel 97-2003)
_FIRMA_ZIP = b"PK\x03\x04"
_MARCAS_HEIC = frozenset({b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"mif1", b"msf1"})


def _es_xlsx(contenido: bytes) -> bool:
    """Un XLSX es un ZIP con `[Content_Types].xml` y la carpeta `xl/`. Solo se lee el índice del
    ZIP (sin descomprimir nada), así que un ZIP bomba no cuesta memoria aquí."""
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as zip_:
            nombres = zip_.namelist()
    except (zipfile.BadZipFile, ValueError):
        return False
    return "[Content_Types].xml" in nombres and any(n.startswith("xl/") for n in nombres)


def _es_xls(contenido: bytes) -> bool:
    """El contenedor OLE2 también lo usan `.doc`, `.ppt` y `.msi`: se exige además el flujo del
    libro de Excel (`Workbook` o `Book`, en UTF-16LE en el directorio del contenedor)."""
    return contenido.startswith(_FIRMA_OLE2) and (
        "Workbook".encode("utf-16-le") in contenido or "Book\x00".encode("utf-16-le") in contenido
    )


def detectar_mime(contenido: bytes) -> str | None:
    """Tipo MIME según el contenido, o `None` si no es un formato admitido."""
    if contenido.startswith(b"\xff\xd8\xff"):
        return JPEG
    if contenido.startswith(_FIRMA_PNG):
        return PNG
    if len(contenido) >= 12 and contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return WEBP
    if len(contenido) >= 12 and contenido[4:8] == b"ftyp" and contenido[8:12] in _MARCAS_HEIC:
        return HEIC
    if contenido.startswith(b"%PDF-"):
        return PDF
    if contenido.startswith(_FIRMA_ZIP) and _es_xlsx(contenido):
        return XLSX
    if _es_xls(contenido):
        return XLS
    return None


def permitido(proposito: PropositoArchivo, mime_type: str | None) -> bool:
    return mime_type is not None and mime_type in PERMITIDOS[proposito]
