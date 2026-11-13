"""`/indicadores/resumen` y `/indicadores/exportar.csv` (S2-09, docs/api-design.md §5.7).

Bases (documentadas en el contrato):
- **Dinero** (totales, por proyecto/rubro/célula/mes): gastos activos de legalizaciones
  **aprobadas**, con `fecha_factura` en el rango (RN-07, RN-18).
- **Estados**: viáticos de cualquier estado; con filtros de gasto, solo los que tienen al menos
  un gasto que los cumpla (S-07).

Las pruebas filtran por `usuario_id` para no mezclarse con datos reales de la BD local.
"""

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import EstadoFinanciero, EstadoOperativo, Etapa, Modalidad, Rol
from app.modules.catalogos.models import Celula, Proyecto, Rubro
from app.modules.indicadores.exportacion import neutralizar_formula
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.models import Viatico
from tests.fabricas import (
    bearer,
    crear_celula,
    crear_gasto,
    crear_proyecto,
    crear_rubro,
    crear_usuario,
    crear_viatico,
)

URL = "/api/v1/indicadores/resumen"
CSV = "/api/v1/indicadores/exportar.csv"
E, F = EstadoOperativo, EstadoFinanciero


def _actor(sesion: Session, rol: Rol, **campos: Any) -> tuple[Usuario, dict[str, str]]:
    usuario = crear_usuario(sesion, rol=rol, **campos)
    return usuario, bearer(sesion, usuario)


class Mundo:
    """Datos de una prueba: un viajero con viáticos y gastos conocidos."""

    def __init__(self, sesion: Session) -> None:
        self.celula: Celula = crear_celula(sesion, "Célula Campo")
        self.usuario: Usuario = crear_usuario(
            sesion, nombre_completo="Ana Viajera", celula_id=self.celula.id
        )
        self.proyecto: Proyecto = crear_proyecto(sesion, nombre="Conexión Agro")
        self.r1: Rubro = crear_rubro(sesion, "Alimentación")
        self.r2: Rubro = crear_rubro(sesion, "Transporte")

        # V1: legalización directa aprobada con 4 gastos activos y 1 eliminado.
        self.v1 = crear_viatico(
            sesion,
            usuario=self.usuario,
            estado=E.APROBADO,
            valor_asignado=Decimal("1000000"),
            estado_financiero=F.TRANSFERIDO,
        )
        self._gasto(sesion, self.v1, "2026-10-05", self.r1, "100000", proyecto=self.proyecto)
        self._gasto(sesion, self.v1, "2026-10-20", self.r2, "50000", otro="Proyecto Libre")
        self._gasto(sesion, self.v1, "2026-11-02", self.r1, "25000", otro="  proyecto libre ")
        self._gasto(sesion, self.v1, "2026-11-10", self.r1, "5000.50", otro="Otro Distinto")
        crear_gasto(
            sesion,
            self.v1,
            fecha_factura=date(2026, 10, 1),
            valor=Decimal("77777"),
            rubro_id=self.r1.id,
            deleted_at=_ahora(),
        )
        # V2: con solicitud, ya en legalización y aprobada.
        self.v2 = crear_viatico(
            sesion,
            usuario=self.usuario,
            modalidad=Modalidad.CON_SOLICITUD,
            etapa=Etapa.LEGALIZACION,
            legalizacion_habilitada_at=_ahora(),
            estado=E.APROBADO,
            presupuesto_solicitado=Decimal("400000"),
            valor_asignado=Decimal("300000"),
            estado_financiero=F.TRANSFERIDO,
        )
        self._gasto(sesion, self.v2, "2026-11-15", self.r2, "200000", proyecto=self.proyecto)
        # V3: legalización sin aprobar (su dinero no cuenta; sí su estado). Gasto fuera de rango.
        self.v3 = crear_viatico(sesion, usuario=self.usuario, estado=E.PENDIENTE)
        self._gasto(sesion, self.v3, "2026-09-01", self.r1, "999999", otro="No cuenta")
        # V4: solicitud aprobada, sin gastos.
        self.v4 = crear_viatico(
            sesion, usuario=self.usuario, modalidad=Modalidad.CON_SOLICITUD, estado=E.APROBADO
        )
        # V5: eliminado.
        crear_viatico(sesion, usuario=self.usuario, estado=E.APROBADO, deleted_at=_ahora())

    @staticmethod
    def _gasto(
        sesion: Session,
        viatico: Viatico,
        fecha: str,
        rubro: Rubro,
        valor: str,
        proyecto: Proyecto | None = None,
        otro: str | None = None,
    ) -> None:
        crear_gasto(
            sesion,
            viatico,
            fecha_factura=date.fromisoformat(fecha),
            rubro_id=rubro.id,
            valor=Decimal(valor),
            proyecto_id=proyecto.id if proyecto else None,
            proyecto_otro=None if proyecto else otro,
        )


def _ahora() -> Any:
    from datetime import UTC, datetime

    return datetime.now(UTC)


@pytest.fixture
def mundo(sesion: Session) -> Mundo:
    return Mundo(sesion)


def _resumen(api: TestClient, encabezados: dict[str, str], mundo: Mundo, **params: Any) -> Any:
    return api.get(URL, params={"usuario_id": str(mundo.usuario.id), **params}, headers=encabezados)


# =================================================================================================
# permisos
# =================================================================================================


@pytest.mark.parametrize("url", [URL, CSV])
def test_el_viajero_no_ve_indicadores(api: TestClient, sesion: Session, url: str) -> None:
    _, encabezados = _actor(sesion, Rol.VIAJERO)

    respuesta = api.get(url, headers=encabezados)

    assert respuesta.status_code == 403 and respuesta.json()["code"] == "SIN_PERMISO"


@pytest.mark.parametrize("url", [URL, CSV])
def test_indicadores_sin_sesion_es_401(api: TestClient, url: str) -> None:
    assert api.get(url).status_code == 401


@pytest.mark.parametrize("rol", [Rol.ADMIN, Rol.FINANCIERO, Rol.SUPERADMIN])
@pytest.mark.parametrize("url", [URL, CSV])
def test_admin_financiero_y_superadmin_ven_indicadores(
    api: TestClient, sesion: Session, rol: Rol, url: str
) -> None:
    _, encabezados = _actor(sesion, rol)

    assert api.get(url, headers=encabezados).status_code == 200


# =================================================================================================
# totales
# =================================================================================================


def test_totales_exactos(api: TestClient, sesion: Session, mundo: Mundo) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _resumen(api, encabezados, mundo)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["totales"] == {
        "total_solicitado": "400000.00",  # V1 no tiene presupuesto; V2, 400.000
        "total_transferido": "1300000.00",  # V1 1.000.000 + V2 300.000
        "total_gastado": "380000.50",  # 100.000 + 50.000 + 25.000 + 5.000,50 + 200.000
        "saldo_neto": "919999.50",  # transferido − gastado
        "cantidad_viaticos": 2,
        "cantidad_gastos": 5,
    }


def test_sin_datos_todo_en_cero(api: TestClient, sesion: Session) -> None:
    vacio = Mundo.__new__(Mundo)
    vacio.usuario = crear_usuario(sesion)
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    cuerpo = _resumen(api, encabezados, vacio).json()

    assert cuerpo["totales"] == {
        "total_solicitado": "0.00",
        "total_transferido": "0.00",
        "total_gastado": "0.00",
        "saldo_neto": "0.00",
        "cantidad_viaticos": 0,
        "cantidad_gastos": 0,
    }
    for lista in ("por_proyecto", "por_rubro", "por_celula", "por_mes"):
        assert cuerpo[lista] == []
    assert {e["cantidad"] for e in cuerpo["por_estado"]} == {0}
    assert [e["estado"] for e in cuerpo["por_estado"]] == ["PENDIENTE", "APROBADO", "RECHAZADO"]
    assert [e["estado"] for e in cuerpo["por_estado_financiero"]] == [
        "PENDIENTE",
        "TRANSFERIDO",
        "PAGADO",
        "PROCESADO",
    ]


# =================================================================================================
# desgloses
# =================================================================================================


def test_proyectos_del_catalogo_y_otro_se_agrupan_por_separado(
    api: TestClient, sesion: Session, mundo: Mundo
) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    items = _resumen(api, encabezados, mundo).json()["por_proyecto"]

    # Más gasto primero.
    assert [i["total_gastado"] for i in items] == ["300000.00", "75000.00", "5000.50"]
    catalogo, libre, distinto = items
    assert catalogo == {
        "proyecto_id": str(mundo.proyecto.id),
        "proyecto": "Conexión Agro",
        "es_fuera_catalogo": False,
        "total_gastado": "300000.00",
        "cantidad_gastos": 2,
    }
    # "Proyecto Libre" y "  proyecto libre " son el mismo (nombre normalizado, ADR-031).
    assert libre["proyecto_id"] is None and libre["es_fuera_catalogo"] is True
    assert libre["proyecto"].strip().lower() == "proyecto libre" and libre["cantidad_gastos"] == 2
    assert distinto["proyecto"] == "Otro Distinto" and distinto["es_fuera_catalogo"] is True


def test_un_otro_con_el_nombre_de_un_proyecto_del_catalogo_no_se_mezcla(
    api: TestClient, sesion: Session, mundo: Mundo
) -> None:
    Mundo._gasto(sesion, mundo.v1, "2026-11-11", mundo.r1, "1000", otro="Conexión Agro")
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    items = _resumen(api, encabezados, mundo).json()["por_proyecto"]

    de_catalogo = [i for i in items if not i["es_fuera_catalogo"]]
    assert len(de_catalogo) == 1 and de_catalogo[0]["total_gastado"] == "300000.00"
    assert any(i["es_fuera_catalogo"] and i["proyecto"] == "Conexión Agro" for i in items)


def test_por_rubro_por_celula_y_por_mes(api: TestClient, sesion: Session, mundo: Mundo) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    cuerpo = _resumen(api, encabezados, mundo).json()

    assert cuerpo["por_rubro"] == [
        {
            "rubro_id": str(mundo.r2.id),
            "rubro": "Transporte",
            "total_gastado": "250000.00",
            "cantidad_gastos": 2,
        },
        {
            "rubro_id": str(mundo.r1.id),
            "rubro": "Alimentación",
            "total_gastado": "130000.50",
            "cantidad_gastos": 3,
        },
    ]
    assert cuerpo["por_celula"] == [
        {
            "celula_id": str(mundo.celula.id),
            "celula": "Célula Campo",
            "total_gastado": "380000.50",
            "cantidad_gastos": 5,
        }
    ]
    assert cuerpo["por_mes"] == [
        {"mes": "2026-10", "total_gastado": "150000.00", "cantidad_gastos": 2},
        {"mes": "2026-11", "total_gastado": "230000.50", "cantidad_gastos": 3},
    ]


def test_un_viajero_sin_celula_aparece_como_sin_celula(api: TestClient, sesion: Session) -> None:
    usuario = crear_usuario(sesion)
    viatico = crear_viatico(sesion, usuario=usuario, estado=E.APROBADO)
    crear_gasto(sesion, viatico, valor=Decimal("1000"))
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    cuerpo = api.get(URL, params={"usuario_id": str(usuario.id)}, headers=encabezados).json()

    assert cuerpo["por_celula"] == [
        {
            "celula_id": None,
            "celula": "Sin célula",
            "total_gastado": "1000.00",
            "cantidad_gastos": 1,
        }
    ]


def test_distribucion_por_estado_cuenta_todos_los_viaticos(
    api: TestClient, sesion: Session, mundo: Mundo
) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    cuerpo = _resumen(api, encabezados, mundo).json()

    # V1, V2 y V4 aprobados; V3 pendiente; V5 eliminado no cuenta.
    assert cuerpo["por_estado"] == [
        {"estado": "PENDIENTE", "cantidad": 1},
        {"estado": "APROBADO", "cantidad": 3},
        {"estado": "RECHAZADO", "cantidad": 0},
    ]
    assert cuerpo["por_estado_financiero"] == [
        {"estado": "PENDIENTE", "cantidad": 2},
        {"estado": "TRANSFERIDO", "cantidad": 2},
        {"estado": "PAGADO", "cantidad": 0},
        {"estado": "PROCESADO", "cantidad": 0},
    ]


# =================================================================================================
# filtros
# =================================================================================================


def test_filtro_por_fechas_de_factura(api: TestClient, sesion: Session, mundo: Mundo) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    desde = _resumen(api, encabezados, mundo, desde="2026-11-01").json()
    hasta = _resumen(api, encabezados, mundo, hasta="2026-10-31").json()
    exacto = _resumen(api, encabezados, mundo, desde="2026-10-20", hasta="2026-10-20").json()

    assert desde["totales"]["total_gastado"] == "230000.50"
    assert desde["totales"]["cantidad_gastos"] == 3 and desde["totales"]["cantidad_viaticos"] == 2
    assert hasta["totales"]["total_gastado"] == "150000.00"
    assert hasta["totales"]["cantidad_viaticos"] == 1
    assert exacto["totales"]["total_gastado"] == "50000.00"  # límites inclusivos
    assert [m["mes"] for m in desde["por_mes"]] == ["2026-11"]


def test_con_rango_los_estados_cuentan_viaticos_con_gasto_en_el_rango(
    api: TestClient, sesion: Session, mundo: Mundo
) -> None:
    """S-07: V3 (gasto de septiembre) y V4 (sin gastos) quedan fuera del rango de noviembre."""
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    cuerpo = _resumen(api, encabezados, mundo, desde="2026-11-01").json()

    assert cuerpo["por_estado"] == [
        {"estado": "PENDIENTE", "cantidad": 0},
        {"estado": "APROBADO", "cantidad": 2},
        {"estado": "RECHAZADO", "cantidad": 0},
    ]
    septiembre = _resumen(api, encabezados, mundo, hasta="2026-09-30").json()
    assert septiembre["por_estado"][0] == {"estado": "PENDIENTE", "cantidad": 1}  # V3
    assert septiembre["totales"]["total_gastado"] == "0.00"  # V3 no está aprobado


def test_filtro_por_proyecto_del_catalogo_excluye_los_otro(
    api: TestClient, sesion: Session, mundo: Mundo
) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    cuerpo = _resumen(api, encabezados, mundo, proyecto_id=str(mundo.proyecto.id)).json()

    assert cuerpo["totales"]["total_gastado"] == "300000.00"
    assert cuerpo["totales"]["cantidad_gastos"] == 2 and cuerpo["totales"]["cantidad_viaticos"] == 2
    assert [p["proyecto"] for p in cuerpo["por_proyecto"]] == ["Conexión Agro"]


def test_filtro_por_rubro(api: TestClient, sesion: Session, mundo: Mundo) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    cuerpo = _resumen(api, encabezados, mundo, rubro_id=str(mundo.r2.id)).json()

    assert cuerpo["totales"]["total_gastado"] == "250000.00"
    assert [r["rubro"] for r in cuerpo["por_rubro"]] == ["Transporte"]


def test_filtro_por_modalidad(api: TestClient, sesion: Session, mundo: Mundo) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    con = _resumen(api, encabezados, mundo, modalidad="CON_SOLICITUD").json()
    directa = _resumen(api, encabezados, mundo, modalidad="LEGALIZACION_DIRECTA").json()

    assert con["totales"]["total_gastado"] == "200000.00"
    assert con["totales"]["total_solicitado"] == "400000.00"
    assert directa["totales"]["total_gastado"] == "180000.50"
    assert _resumen(api, encabezados, mundo, modalidad="OTRA").status_code == 422


def test_filtro_por_celula_y_usuario(api: TestClient, sesion: Session, mundo: Mundo) -> None:
    otra_celula = crear_celula(sesion, "Otra célula")
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    propia = _resumen(api, encabezados, mundo, celula_id=str(mundo.celula.id)).json()
    ajena = _resumen(api, encabezados, mundo, celula_id=str(otra_celula.id)).json()
    otro_usuario = api.get(
        URL, params={"usuario_id": str(crear_usuario(sesion).id)}, headers=encabezados
    ).json()

    assert propia["totales"]["total_gastado"] == "380000.50"
    assert ajena["totales"]["total_gastado"] == "0.00" and ajena["por_proyecto"] == []
    assert otro_usuario["totales"]["cantidad_gastos"] == 0


def test_rango_invertido_es_422(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = api.get(
        URL, params={"desde": "2026-12-01", "hasta": "2026-11-01"}, headers=encabezados
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["errors"][0]["field"] == "hasta"


@pytest.mark.parametrize("parametro", ["proyecto_id", "rubro_id", "celula_id", "usuario_id"])
def test_ids_mal_formados_son_422(api: TestClient, sesion: Session, parametro: str) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    assert api.get(URL, params={parametro: "no-es-uuid"}, headers=encabezados).status_code == 422


# =================================================================================================
# CSV
# =================================================================================================

ENCABEZADOS = [
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
]


def _leer_csv(contenido: bytes, delimitador: str = ";") -> list[dict[str, str]]:
    texto = contenido.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(texto, newline=""), delimiter=delimitador))


def _pedir_csv(api: TestClient, encabezados: dict[str, str], mundo: Mundo, **params: Any) -> Any:
    return api.get(CSV, params={"usuario_id": str(mundo.usuario.id), **params}, headers=encabezados)


def test_el_csv_llega_con_bom_utf8_y_encabezados_de_descarga(
    api: TestClient, sesion: Session, mundo: Mundo
) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _pedir_csv(api, encabezados, mundo)

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "text/csv; charset=utf-8"
    assert respuesta.headers["content-disposition"].startswith('attachment; filename="indicadores-')
    assert (
        respuesta.headers["content-disposition"].split('filename="')[1].startswith("indicadores-")
    )
    assert ".csv" in respuesta.headers["content-disposition"]
    assert respuesta.headers["cache-control"] == "private, no-store"
    assert respuesta.content.startswith(b"\xef\xbb\xbf")  # BOM: Excel abre tildes y eñes
    primera_linea = respuesta.content.decode("utf-8-sig").splitlines()[0]
    assert primera_linea == ";".join(ENCABEZADOS)


def test_el_csv_trae_un_gasto_por_fila_solo_de_legalizaciones_aprobadas(
    api: TestClient, sesion: Session, mundo: Mundo
) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    filas = _leer_csv(_pedir_csv(api, encabezados, mundo).content)

    assert len(filas) == 5  # V3 (sin aprobar) y el gasto eliminado no salen
    assert sum(Decimal(f["valor"]) for f in filas) == Decimal("380000.50")
    # Orden estable: fecha de factura, folio.
    assert [f["fecha_factura"] for f in filas] == sorted(f["fecha_factura"] for f in filas)
    primera = filas[0]
    assert primera["folio"] == mundo.v1.folio and primera["viajero"] == "Ana Viajera"
    assert primera["celula"] == "Célula Campo" and primera["rubro"] == "Alimentación"
    assert primera["proyecto"] == "Conexión Agro" and primera["fuera_de_catalogo"] == "NO"
    assert primera["valor"] == "100000.00" and primera["modalidad"] == "LEGALIZACION_DIRECTA"
    assert primera["estado"] == "APROBADO" and primera["estado_financiero"] == "TRANSFERIDO"
    assert any(f["fuera_de_catalogo"] == "SI" and f["proyecto"] == "Otro Distinto" for f in filas)
    assert "999999.00" not in {f["valor"] for f in filas}


def test_el_csv_conserva_tildes_y_enes(api: TestClient, sesion: Session) -> None:
    usuario = crear_usuario(sesion, nombre_completo="Ñandú Pérez Gómez")
    viatico = crear_viatico(sesion, usuario=usuario, estado=E.APROBADO)
    crear_gasto(
        sesion,
        viatico,
        concepto="Almuerzo año nuevo – café",
        empresa="Peña & Cía",
        valor=Decimal("1"),
    )
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = api.get(CSV, params={"usuario_id": str(usuario.id)}, headers=encabezados)

    (fila,) = _leer_csv(respuesta.content)
    assert fila["viajero"] == "Ñandú Pérez Gómez"
    assert fila["concepto"] == "Almuerzo año nuevo – café" and fila["empresa"] == "Peña & Cía"


def test_el_separador_se_puede_elegir(api: TestClient, sesion: Session, mundo: Mundo) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = _pedir_csv(api, encabezados, mundo, separador=",")

    assert respuesta.content.decode("utf-8-sig").splitlines()[0] == ",".join(ENCABEZADOS)
    assert len(_leer_csv(respuesta.content, ",")) == 5
    assert _pedir_csv(api, encabezados, mundo, separador="|").status_code == 422


def test_el_csv_respeta_los_filtros(api: TestClient, sesion: Session, mundo: Mundo) -> None:
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    noviembre = _leer_csv(_pedir_csv(api, encabezados, mundo, desde="2026-11-01").content)
    del_proyecto = _leer_csv(
        _pedir_csv(api, encabezados, mundo, proyecto_id=str(mundo.proyecto.id)).content
    )
    vacio = _pedir_csv(api, encabezados, mundo, rubro_id="00000000-0000-0000-0000-000000000000")

    assert len(noviembre) == 3 and len(del_proyecto) == 2
    assert vacio.status_code == 200 and _leer_csv(vacio.content) == []
    assert vacio.content.decode("utf-8-sig").strip() == ";".join(ENCABEZADOS)  # solo encabezados
    assert (
        api.get(CSV, params={"desde": "2026-12-01", "hasta": "2026-11-01"}, headers=encabezados)
    ).status_code == 422


# --- inyección de fórmulas (OWASP CSV injection) --------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "salida"),
    [
        ("=1+1", "'=1+1"),
        ('=HYPERLINK("http://evil.test","clic")', '\'=HYPERLINK("http://evil.test","clic")'),
        ("+cmd|' /C calc'!A0", "'+cmd|' /C calc'!A0"),
        ("-2+3", "'-2+3"),
        ("@SUM(A1:A9)", "'@SUM(A1:A9)"),
        ("\t=1+1", "'\t=1+1"),
        ("\r=1+1", "'\r=1+1"),
        ("   =1+1", "'   =1+1"),  # los espacios delante no lo salvan
        ("\n=1+1", "'\n=1+1"),
        ("Almuerzo", "Almuerzo"),
        ("a=b", "a=b"),
        ("100-200", "100-200"),
        ("", ""),
        ("Peña", "Peña"),
    ],
)
def test_neutralizar_formula(entrada: str, salida: str) -> None:
    assert neutralizar_formula(entrada) == salida


def test_neutralizar_formula_solo_toca_textos() -> None:
    assert neutralizar_formula(None) == ""
    assert neutralizar_formula(Decimal("-50.00")) == "-50.00"  # un número negativo no es fórmula
    assert neutralizar_formula(date(2026, 1, 2)) == "2026-01-02"
    assert neutralizar_formula(True) == "SI" and neutralizar_formula(False) == "NO"


def test_el_csv_neutraliza_formulas_en_todos_los_textos_libres(
    api: TestClient, sesion: Session
) -> None:
    usuario = crear_usuario(sesion, nombre_completo="=cmd|' /C calc'!A0")
    viatico = crear_viatico(
        sesion, usuario=usuario, estado=E.APROBADO, motivo_viaje="@motivo hostil"
    )
    rubro = crear_rubro(sesion, "+rubro")
    crear_gasto(
        sesion,
        viatico,
        rubro_id=rubro.id,
        concepto='=HYPERLINK("http://evil.test","x")',
        empresa="-empresa",
        cc_nit="\t=1+1",
        proyecto_otro="@SUM(1,1)",
        valor=Decimal("1500"),
    )
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    for separador in (";", ","):
        respuesta = api.get(
            CSV,
            params={"usuario_id": str(usuario.id), "separador": separador},
            headers=encabezados,
        )
        (fila,) = _leer_csv(respuesta.content, separador)
        assert fila["viajero"] == "'=cmd|' /C calc'!A0"
        assert fila["motivo_viaje"] == "'@motivo hostil"
        assert fila["rubro"] == "'+rubro" and fila["empresa"] == "'-empresa"
        assert fila["cc_nit"] == "'\t=1+1" and fila["proyecto"] == "'@SUM(1,1)"
        assert fila["concepto"] == '\'=HYPERLINK("http://evil.test","x")'
        assert fila["valor"] == "1500.00"  # los números no se tocan


def test_el_csv_respeta_comillas_saltos_de_linea_y_delimitadores_en_los_textos(
    api: TestClient, sesion: Session
) -> None:
    usuario = crear_usuario(sesion)
    viatico = crear_viatico(sesion, usuario=usuario, estado=E.APROBADO)
    concepto = 'Línea 1\nLínea 2; "citado", fin'
    crear_gasto(sesion, viatico, concepto=concepto, valor=Decimal("10"))
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    respuesta = api.get(CSV, params={"usuario_id": str(usuario.id)}, headers=encabezados)

    (fila,) = _leer_csv(respuesta.content)
    assert fila["concepto"] == concepto


def test_un_valor_negativo_o_normal_de_texto_no_se_altera_en_el_csv(
    api: TestClient, sesion: Session
) -> None:
    usuario = crear_usuario(sesion, nombre_completo="Ana-María Pérez")
    viatico = crear_viatico(sesion, usuario=usuario, estado=E.APROBADO)
    crear_gasto(sesion, viatico, concepto="Taxi 5-6 pm", valor=Decimal("1"))
    _, encabezados = _actor(sesion, Rol.FINANCIERO)

    (fila,) = _leer_csv(
        api.get(CSV, params={"usuario_id": str(usuario.id)}, headers=encabezados).content
    )

    assert fila["viajero"] == "Ana-María Pérez" and fila["concepto"] == "Taxi 5-6 pm"


# --- streaming -----------------------------------------------------------------------------------


def test_el_csv_se_genera_por_bloques(sesion: Session) -> None:
    """Con muchas filas la respuesta sale en varios bloques, no de una sola vez."""
    from contextlib import nullcontext

    from app.modules.indicadores import exportacion
    from app.modules.indicadores.service import Filtros

    usuario = crear_usuario(sesion)
    viatico = crear_viatico(sesion, usuario=usuario, estado=E.APROBADO)
    for i in range(450):
        crear_gasto(sesion, viatico, concepto=f"Gasto {i}", valor=Decimal("1"))

    bloques = list(
        exportacion.generar(
            lambda _usuario_id, _rol: nullcontext(sesion),
            usuario.id,
            Rol.FINANCIERO,
            Filtros(usuario_id=usuario.id),
            ";",
        )
    )

    assert len(bloques) > 2
    assert bloques[0].startswith(b"\xef\xbb\xbf")
    assert len(_leer_csv(b"".join(bloques))) == 450


def test_la_sesion_del_streaming_lleva_el_contexto_de_rls_y_se_cierra() -> None:
    """FastAPI cierra la sesión de la petición antes del cuerpo: el generador usa la suya."""
    import uuid

    from sqlalchemy import text

    from app.core.db import sesion_independiente

    usuario_id = uuid.uuid4()
    with sesion_independiente(usuario_id, Rol.FINANCIERO) as session:
        rol, quien = session.execute(
            text("SELECT current_setting('app.rol', true), current_setting('app.usuario_id', true)")
        ).one()
        assert (rol, quien) == ("FINANCIERO", str(usuario_id))
        assert session.in_transaction()

    assert not session.in_transaction()  # cerrada: devolvió su conexión al pool
