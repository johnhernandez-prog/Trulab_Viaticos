"""Detección del tipo real por contenido (S2-06, RN-13): función pura, sin BD."""

import pytest

from app.core.enums import PropositoArchivo
from app.modules.archivos import deteccion
from tests import muestras

P = PropositoArchivo


@pytest.mark.parametrize(
    ("contenido", "esperado"),
    [
        (muestras.JPEG, deteccion.JPEG),
        (muestras.PNG, deteccion.PNG),
        (muestras.WEBP, deteccion.WEBP),
        (muestras.HEIC, deteccion.HEIC),
        (muestras.PDF, deteccion.PDF),
        (muestras.XLSX, deteccion.XLSX),
        (muestras.XLS, deteccion.XLS),
    ],
)
def test_reconoce_los_formatos_admitidos(contenido: bytes, esperado: str) -> None:
    assert deteccion.detectar_mime(contenido) == esperado


@pytest.mark.parametrize(
    "contenido",
    [
        muestras.EXE,
        muestras.HTML,
        muestras.SVG,
        muestras.ZIP,
        muestras.DOCX,
        muestras.DOC,
        b"",
        b"%PD",
        b"texto plano cualquiera",
        # Un ejecutable con "%PDF-" más adelante no es un PDF: la firma va al inicio.
        muestras.EXE + b"%PDF-1.4",
    ],
)
def test_rechaza_lo_que_no_es_un_formato_admitido(contenido: bytes) -> None:
    assert deteccion.detectar_mime(contenido) is None


@pytest.mark.parametrize(
    ("proposito", "mime", "permitido"),
    [
        (P.SOPORTE, deteccion.JPEG, True),
        (P.SOPORTE, deteccion.HEIC, True),
        (P.SOPORTE, deteccion.PDF, False),
        (P.ARCHIVO, deteccion.PDF, True),
        (P.ARCHIVO, deteccion.PNG, False),
        (P.ARCHIVO, deteccion.XLSX, False),
        (P.FIRMA, deteccion.PNG, True),
        (P.FIRMA, deteccion.HEIC, False),
        (P.FIRMA, deteccion.PDF, False),
        (P.FORMATO_PRESTADOR, deteccion.XLSX, True),
        (P.FORMATO_PRESTADOR, deteccion.XLS, True),
        (P.FORMATO_PRESTADOR, deteccion.PDF, True),
        (P.FORMATO_PRESTADOR, deteccion.JPEG, False),
        (P.SOPORTE, None, False),
    ],
)
def test_tipos_permitidos_por_proposito(
    proposito: PropositoArchivo, mime: str | None, permitido: bool
) -> None:
    assert deteccion.permitido(proposito, mime) is permitido


def test_cada_tipo_permitido_tiene_extension() -> None:
    for tipos in deteccion.PERMITIDOS.values():
        for mime in tipos:
            assert deteccion.EXTENSION[mime].startswith(".")
