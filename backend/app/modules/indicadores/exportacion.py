"""Exportación CSV del detalle de gastos (S2-09; docs/api-design.md §5.7).

- **Streaming:** el generador abre su propia sesión (`FabricaSesion`, con el contexto de RLS de
  quien exporta) y lee con un cursor de servidor en bloques; no carga todos los gastos en memoria.
- **Excel en Windows:** UTF-8 **con BOM** (tildes y eñes) y `;` como separador por defecto, el
  separador de listas de Excel con configuración regional de Colombia (con `,` abriría en una sola
  columna); `separador=,` da el CSV estándar. Los números salen con punto decimal (`45000.50`).
- **Inyección de fórmulas** (OWASP CSV injection): un texto que Excel interpretaría como fórmula
  (empieza por `=`, `+`, `-` o `@`, también tras espacios, o por tabulador o retorno) se antepone
  con `'`. Se aplica a **todos** los textos libres (viajero, motivo, proyecto, rubro, empresa,
  CC/NIT, concepto); los números, fechas y booleanos los formatea el servidor y no se tocan.
"""

import csv
import io
import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from app.core.db import FabricaSesion
from app.core.enums import Rol
from app.modules.catalogos.models import Celula, Proyecto, Rubro
from app.modules.gastos.models import Gasto
from app.modules.indicadores.service import Filtros, condiciones_dinero, sobre_gastos
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.models import Viatico

BOM = "﻿"
BLOQUE_FILAS = 200
ENCABEZADOS = (
    "folio",
    "modalidad",
    "estado",
    "estado_financiero",
    "viajero",
    "celula",
    "motivo_viaje",
    "fecha_factura",
    "proyecto",
    "fuera_de_catalogo",
    "rubro",
    "empresa",
    "cc_nit",
    "concepto",
    "valor",
    "con_comprobante",
)
_INICIOS_DE_FORMULA = frozenset({"=", "+", "-", "@"})
_CENTAVOS = Decimal("0.01")


def neutralizar_formula(valor: object) -> str:
    """El valor como celda de CSV, sin que Excel pueda tomarlo por una fórmula."""
    if valor is None:
        return ""
    if isinstance(valor, bool):
        return "SI" if valor else "NO"
    if isinstance(valor, Decimal):
        return format(valor.quantize(_CENTAVOS), "f")
    if isinstance(valor, date):
        return valor.isoformat()
    texto = str(valor)
    if texto and (texto[0] in "\t\r" or texto.lstrip()[:1] in _INICIOS_DE_FORMULA):
        return "'" + texto
    return texto


def _consulta(filtros: Filtros) -> Any:
    return (
        sobre_gastos(
            select(
                Viatico.folio,
                Viatico.modalidad,
                Viatico.estado,
                Viatico.estado_financiero,
                Usuario.nombre_completo,
                Celula.nombre,
                Viatico.motivo_viaje,
                Gasto.fecha_factura,
                Proyecto.nombre,
                Gasto.proyecto_otro,
                Rubro.nombre,
                Gasto.empresa,
                Gasto.cc_nit,
                Gasto.concepto,
                Gasto.valor,
                Gasto.soporte_id.is_not(None) | Gasto.archivo_id.is_not(None),
            )
        )
        .outerjoin(Celula, Celula.id == Usuario.celula_id)
        .outerjoin(Proyecto, Proyecto.id == Gasto.proyecto_id)
        .join(Rubro, Rubro.id == Gasto.rubro_id)
        .where(*condiciones_dinero(filtros))
        .order_by(Gasto.fecha_factura, Viatico.folio, Gasto.id)
        # `yield_per` abre un cursor de servidor: se lee por bloques, no todo de una vez.
        .execution_options(yield_per=BLOQUE_FILAS)
    )


def _celdas(fila: Any) -> list[str]:
    (
        folio,
        modalidad,
        estado,
        financiero,
        viajero,
        celula,
        motivo,
        fecha,
        proyecto_catalogo,
        proyecto_otro,
        rubro,
        empresa,
        cc_nit,
        concepto,
        valor,
        con_comprobante,
    ) = fila
    return [
        neutralizar_formula(c)
        for c in (
            folio,
            modalidad,
            estado,
            financiero,
            viajero,
            celula,
            motivo,
            fecha,
            proyecto_catalogo or proyecto_otro,
            proyecto_catalogo is None,
            rubro,
            empresa,
            cc_nit,
            concepto,
            valor,
            con_comprobante,
        )
    ]


def generar(
    fabrica: FabricaSesion,
    usuario_id: uuid.UUID,
    rol: Rol | str,
    filtros: Filtros,
    separador: str,
) -> Iterator[bytes]:
    """El CSV en bloques de bytes: BOM y encabezados, y después `BLOQUE_FILAS` filas a la vez."""
    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=separador, lineterminator="\r\n")
    escritor.writerow(ENCABEZADOS)

    def vaciar(prefijo: str = "") -> bytes:
        contenido = (prefijo + buffer.getvalue()).encode("utf-8")
        buffer.seek(0)
        buffer.truncate()
        return contenido

    yield vaciar(BOM)
    with fabrica(usuario_id, rol) as session:
        for n, fila in enumerate(session.execute(_consulta(filtros)), start=1):
            escritor.writerow(_celdas(fila))
            if n % BLOQUE_FILAS == 0:
                yield vaciar()
    if buffer.tell():
        yield vaciar()
