"""Tipos Pydantic compartidos entre módulos.

- `Dinero` (ADR-012): el dinero viaja en JSON como **string** (`"150000.00"`), nunca como
  `float`, para no perder precisión decimal; en Python y en la BD sigue siendo `Decimal` /
  `NUMERIC(14,2)`. Acepta también un número de entrada (comodidad en pruebas y `curl`), pero
  siempre **serializa** como texto.
"""

from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import BeforeValidator, PlainSerializer


def _a_decimal(valor: object) -> object:
    if isinstance(valor, Decimal | int):
        return valor
    if isinstance(valor, str):
        try:
            return Decimal(valor)
        except InvalidOperation as error:
            raise ValueError("No es un valor monetario válido") from error
    return valor


Dinero = Annotated[
    Decimal,
    BeforeValidator(_a_decimal),
    PlainSerializer(lambda valor: format(valor, "f"), return_type=str, when_used="json"),
]
