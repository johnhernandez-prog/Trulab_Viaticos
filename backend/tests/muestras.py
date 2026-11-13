"""Contenidos mínimos de archivos para las pruebas de detección por *magic bytes* (RN-13)."""

import io
import zipfile

JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 64
HEIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 64
PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n%%EOF\n"
# Ejecutable de Windows (cabecera MZ) que se hace pasar por PDF o JPG.
EXE = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff" + b"\x00" * 64
HTML = b"<!DOCTYPE html><html><script>alert(1)</script></html>"
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
XLS = OLE2 + b"\x00" * 64 + "Workbook".encode("utf-16-le") + b"\x00" * 64
DOC = OLE2 + b"\x00" * 64 + "WordDocument".encode("utf-16-le") + b"\x00" * 64


def _zip(nombres: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zip_:
        for nombre in nombres:
            zip_.writestr(nombre, "<x/>")
    return buffer.getvalue()


XLSX = _zip(["[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml"])
DOCX = _zip(["[Content_Types].xml", "word/document.xml"])
ZIP = _zip(["leeme.txt"])


def png_real() -> bytes:
    """Un PNG decodificable (para probar que la firma se incrusta de verdad en el PDF)."""
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (120, 40), (20, 20, 120)).save(buffer, "PNG")
    return buffer.getvalue()
