"""Tipos Pydantic compartidos entre módulos.

- `Dinero` (ADR-012): el dinero viaja en JSON como **string** (`"150000.00"`), nunca como
  `float`, para no perder precisión decimal; en Python y en la BD sigue siendo `Decimal` /
  `NUMERIC(14,2)`. Acepta también un número de entrada (comodidad en pruebas y `curl`), pero
  siempre **serializa** como texto.
"""

from decimal import Decimal, InvalidOperation
from typing import Annotated

from pydantic import AfterValidator, BeforeValidator, PlainSerializer


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


# `NUMERIC(14,2)`: hasta 12 dígitos enteros y 2 decimales.
_MAXIMO = Decimal("1e12")


def _monto(valor: Decimal, *, positivo: bool) -> Decimal:
    if not valor.is_finite():
        raise ValueError("No es un valor monetario válido")
    exponente = valor.as_tuple().exponent
    if isinstance(exponente, int) and exponente < -2:
        raise ValueError("Máximo 2 decimales")
    if abs(valor) >= _MAXIMO:
        raise ValueError("El valor es demasiado grande")
    if positivo and valor <= 0:
        raise ValueError("Debe ser mayor que 0")
    if not positivo and valor < 0:
        raise ValueError("No puede ser negativo")
    return valor


def _positivo(valor: Decimal) -> Decimal:
    return _monto(valor, positivo=True)


def _no_negativo(valor: Decimal) -> Decimal:
    return _monto(valor, positivo=False)


# RN-08: `> 0` en gastos y `>= 0` en valor asignado y tarifas.
DineroPositivo = Annotated[Dinero, AfterValidator(_positivo)]
DineroNoNegativo = Annotated[Dinero, AfterValidator(_no_negativo)]
