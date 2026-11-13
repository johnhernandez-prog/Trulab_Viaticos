"""Hora de Colombia (America/Bogotá): UTC−5 fijo, sin horario de verano.

Se usa un desfase fijo en vez de `zoneinfo` para no depender de `tzdata` en el contenedor. Lo usan
la regla "factura no futura" (RN-07) y los PDF (fechas que ve el usuario, docs/api-design.md §6).
"""

from datetime import UTC, date, datetime, timedelta, timezone

ZONA_COLOMBIA = timezone(timedelta(hours=-5), "America/Bogota")


def hoy_colombia() -> date:
    return datetime.now(ZONA_COLOMBIA).date()


def a_hora_colombia(momento: datetime) -> datetime:
    """Un instante (con o sin zona; sin zona se toma como UTC) en hora de Colombia."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(ZONA_COLOMBIA)
