"""Integridad del archivo de tarifas oficiales (`app/modules/catalogos/datos/tarifas_viaticos.csv`).

No toca la BD: valida la forma del archivo que cargará el seed de S2-01 (ADR-030).
"""

import csv
from decimal import Decimal
from pathlib import Path

import pytest

ARCHIVO = Path(__file__).parents[1] / "app/modules/catalogos/datos/tarifas_viaticos.csv"
CONCEPTOS = (
    "vr_alimentacion",
    "otros_gastos",
    "transporte_aeropuerto",
    "transporte_intermunicipal",
    "trans_interno_dia_1",
    "trans_interno_varios_dias",
)
# En el código legado, solo estas ciudades distinguen 1 día de varios días para prestadores.
PRINCIPALES = {"Cali", "Bogota", "Medellin", "Barranquilla", "Buenaventura"}


@pytest.fixture(scope="module")
def filas() -> list[dict[str, str]]:
    with ARCHIVO.open(encoding="utf-8", newline="") as archivo:
        return list(csv.DictReader(archivo))


def test_tiene_22_destinos_por_cada_tipo_de_vinculacion(filas: list[dict[str, str]]) -> None:
    assert len(filas) == 44
    for tipo in ("false", "true"):
        ciudades = [f["clave_legado"] for f in filas if f["es_prestador_servicios"] == tipo]
        assert len(ciudades) == len(set(ciudades)) == 22
    assert "Otro" in {f["ciudad"] for f in filas}


def test_valores_son_enteros_no_negativos(filas: list[dict[str, str]]) -> None:
    for fila in filas:
        for concepto in CONCEPTOS:
            valor = Decimal(fila[concepto])
            assert valor >= 0 and valor == valor.to_integral_value(), (fila["ciudad"], concepto)


def test_prestador_fuera_de_ciudades_principales_no_distingue_dias(
    filas: list[dict[str, str]],
) -> None:
    # Equivalencia con la regla legada: la fórmula general (RN-29) da el mismo resultado.
    for fila in filas:
        if fila["es_prestador_servicios"] == "true" and fila["clave_legado"] not in PRINCIPALES:
            assert fila["trans_interno_dia_1"] == fila["trans_interno_varios_dias"], fila["ciudad"]
