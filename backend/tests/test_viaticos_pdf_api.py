"""PDF oficiales (S2-08): `GET /viaticos/{id}/pdf-solicitud` y `/pdf-legalizacion`.

Se leen con `pypdf` (texto e imágenes reales, no solo la cabecera `%PDF-`). RLS, modalidad y etapa.
"""

import hashlib
import io
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.core.enums import EstadoFinanciero, Etapa, Modalidad, PropositoArchivo, Rol
from app.modules.archivos.storage import AlmacenamientoLocal
from app.modules.usuarios.models import Usuario
from app.modules.viaticos import pdf
from tests import muestras
from tests.fabricas import (
    bearer,
    crear_archivo,
    crear_gasto,
    crear_proyecto,
    crear_rubro,
    crear_usuario,
    crear_viatico,
)

URL = "/api/v1/viaticos"
IDA = datetime(2026, 12, 1, 8, tzinfo=UTC)
FORMATOS_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _actor(
    sesion: Session, rol: Rol = Rol.VIAJERO, **campos: Any
) -> tuple[Usuario, dict[str, str]]:
    usuario = crear_usuario(sesion, rol=rol, **campos)
    return usuario, bearer(sesion, usuario)


def _lector(contenido: bytes) -> PdfReader:
    return PdfReader(io.BytesIO(contenido))


class _Texto(str):
    """Texto de un PDF. `in` ignora los espacios: al extraer, `pypdf` junta o separa a su gusto
    las palabras de celdas distintas ("Liquidó (financiero)Laura"), y eso no es lo que se prueba."""

    def __contains__(self, item: object) -> bool:
        return "".join(str(item).split()) in "".join(self.split())


def _texto(contenido: bytes) -> _Texto:
    lector = _lector(contenido)
    return _Texto(" ".join(" ".join(p.extract_text().split()) for p in lector.pages))


def _imagenes(contenido: bytes) -> int:
    return sum(len(p.images) for p in _lector(contenido).pages)


def _firma(
    sesion: Session, almacen: AlmacenamientoLocal, dueno: Usuario, contenido: bytes | None = None
) -> Any:
    contenido = contenido if contenido is not None else muestras.png_real()
    clave = f"firma/pruebas/{uuid.uuid4()}.png"
    almacen.guardar(clave, contenido, "image/png")
    return crear_archivo(
        sesion,
        created_by=dueno.id,
        proposito=PropositoArchivo.FIRMA,
        mime_type="image/png",
        nombre_original="firma.png",
        storage_key=clave,
        tamano_bytes=len(contenido),
        sha256=hashlib.sha256(muestras.png_real()).hexdigest(),
    )


def _cuerpo_solicitud(proyecto_id: uuid.UUID, **campos: Any) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "modalidad": "CON_SOLICITUD",
        "motivo_viaje": "Taller de campo",
        "proyecto_id": str(proyecto_id),
        "lider_proyecto": "María Gómez",
        "empresa": "Aliado S.A.S.",
        "requiere_gastos_viaje": True,
        "comentarios": "Se necesita transporte extra",
        "trayectos": [
            {
                "orden": 1,
                "ciudad_origen": "Medellín",
                "ciudad_destino": "Bogotá",
                "fecha_ida": IDA.isoformat(),
                "fecha_regreso": (IDA + timedelta(days=2)).isoformat(),
                "requiere_hospedaje": True,
                "dias_estadia": 3,
            }
        ],
    }
    cuerpo.update(campos)
    return cuerpo


def _pedir(
    api: TestClient, viatico_id: uuid.UUID | str, tipo: str, encabezados: dict[str, str]
) -> Any:
    return api.get(f"{URL}/{viatico_id}/pdf-{tipo}", headers=encabezados)


# =================================================================================================
# pdf-solicitud
# =================================================================================================


def test_pdf_de_la_solicitud_con_todo_su_contenido(
    api: TestClient, sesion: Session, almacen: AlmacenamientoLocal
) -> None:
    viajero, encabezados = _actor(
        sesion,
        nombre_completo="Ana Pérez Quintero",
        cedula="1020304050",
        fecha_nacimiento=datetime(1990, 5, 17).date(),
    )
    proyecto = crear_proyecto(sesion, nombre="Conexión Agro")
    firma = _firma(sesion, almacen, viajero)
    creada = api.post(
        URL,
        json=_cuerpo_solicitud(proyecto.id, requiere_tiquete=True, firma_archivo_id=str(firma.id)),
        headers=encabezados,
    )
    assert creada.status_code == 201, creada.text
    cuerpo = creada.json()

    respuesta = _pedir(api, cuerpo["id"], "solicitud", encabezados)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.headers["content-type"] == "application/pdf"
    assert respuesta.headers["content-disposition"].startswith(
        f'attachment; filename="{cuerpo["folio"]}-solicitud.pdf"'
    )
    assert respuesta.headers["cache-control"] == "private, no-store"
    assert respuesta.content.startswith(b"%PDF-")
    texto = _texto(respuesta.content)
    for esperado in (
        cuerpo["folio"],
        "TRULAB",
        "Solicitud de viáticos y tiquetes",
        "Ana Pérez Quintero",
        "1020304050",
        "17/05/1990",
        "Empleado",
        "Conexión Agro",
        "María Gómez",
        "Aliado S.A.S.",
        "Taller de campo",
        "Medellín",
        "Bogotá",
        "Se necesita transporte extra",
        "Presupuesto solicitado",
        pdf.formato_cop(Decimal(cuerpo["solicitud"]["presupuesto_solicitado"])),
        "Creación",
    ):
        assert esperado in texto, esperado
    assert "SIN FIRMA" not in texto
    assert _imagenes(respuesta.content) == 1  # la firma, incrustada


def test_pdf_de_la_solicitud_sin_firma_sale_marcado_como_borrador(
    api: TestClient, sesion: Session, almacen: AlmacenamientoLocal
) -> None:
    _, encabezados = _actor(sesion)
    cuerpo = api.post(
        URL, json=_cuerpo_solicitud(crear_proyecto(sesion).id), headers=encabezados
    ).json()

    respuesta = _pedir(api, cuerpo["id"], "solicitud", encabezados)

    assert respuesta.status_code == 200
    assert "SIN FIRMA" in _texto(respuesta.content)
    assert _imagenes(respuesta.content) == 0


def test_pdf_usa_la_firma_del_perfil_si_el_viatico_aun_no_la_tiene(
    api: TestClient, sesion: Session, almacen: AlmacenamientoLocal
) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero, modalidad=Modalidad.CON_SOLICITUD)
    viajero.firma_archivo_id = _firma(sesion, almacen, viajero).id
    sesion.flush()

    respuesta = _pedir(api, viatico.id, "solicitud", encabezados)

    assert respuesta.status_code == 200
    assert _imagenes(respuesta.content) == 1


def test_una_firma_alterada_no_se_incrusta_ni_rompe_el_pdf(
    api: TestClient, sesion: Session, almacen: AlmacenamientoLocal
) -> None:
    viajero, encabezados = _actor(sesion)
    alterada = _firma(sesion, almacen, viajero, contenido=muestras.png_real() + b"alterado")
    viatico = crear_viatico(
        sesion, usuario=viajero, modalidad=Modalidad.CON_SOLICITUD, firma_archivo_id=alterada.id
    )

    respuesta = _pedir(api, viatico.id, "solicitud", encabezados)

    assert respuesta.status_code == 200
    assert _imagenes(respuesta.content) == 0 and "SIN FIRMA" in _texto(respuesta.content)


def test_una_firma_que_el_almacenamiento_no_encuentra_no_da_500(
    api: TestClient, sesion: Session, almacen: AlmacenamientoLocal
) -> None:
    viajero, encabezados = _actor(sesion)
    huerfana = crear_archivo(
        sesion,
        created_by=viajero.id,
        proposito=PropositoArchivo.FIRMA,
        mime_type="image/png",
        storage_key="firma/no-existe.png",
    )
    viatico = crear_viatico(
        sesion, usuario=viajero, modalidad=Modalidad.CON_SOLICITUD, firma_archivo_id=huerfana.id
    )

    respuesta = _pedir(api, viatico.id, "solicitud", encabezados)

    assert respuesta.status_code == 200
    assert "SIN FIRMA" in _texto(respuesta.content)


def test_pdf_de_prestador_con_formato_no_muestra_tabla_de_presupuesto(
    api: TestClient, sesion: Session, almacen: AlmacenamientoLocal
) -> None:
    viajero, encabezados = _actor(sesion, es_prestador_servicios=True)
    formato = crear_archivo(
        sesion,
        created_by=viajero.id,
        proposito=PropositoArchivo.FORMATO_PRESTADOR,
        mime_type=FORMATOS_XLSX,
        nombre_original="formato-conexi.xlsx",
    )
    viatico = crear_viatico(
        sesion,
        usuario=viajero,
        modalidad=Modalidad.CON_SOLICITUD,
        requiere_gastos_viaje=True,
        presupuesto_solicitado=None,
        formato_adjunto_id=formato.id,
    )

    texto = _texto(_pedir(api, viatico.id, "solicitud", encabezados).content)

    assert "Prestador de servicios" in texto
    assert "formato-conexi.xlsx" in texto
    assert "No se calcula presupuesto por tabla" in texto
    assert "Presupuesto solicitado" not in texto


def test_pdf_sin_gastos_de_viaje(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(
        sesion, usuario=viajero, modalidad=Modalidad.CON_SOLICITUD, requiere_tiquete=True
    )

    texto = _texto(_pedir(api, viatico.id, "solicitud", encabezados).content)

    assert "no incluye gastos de viaje" in texto


def test_pdf_de_la_solicitud_incluye_la_aprobacion_en_la_trazabilidad(
    api: TestClient, sesion: Session, almacen: AlmacenamientoLocal
) -> None:
    viajero, encabezados = _actor(sesion)
    admin = crear_usuario(sesion, rol=Rol.ADMIN, nombre_completo="Carlos Revisor")
    viatico = crear_viatico(
        sesion,
        usuario=viajero,
        modalidad=Modalidad.CON_SOLICITUD,
        firma_archivo_id=_firma(sesion, almacen, viajero).id,
    )
    aprobada = api.post(
        f"{URL}/{viatico.id}/aprobar",
        json={"comentario": "Procede el viaje"},
        headers=bearer(sesion, admin),
    )
    assert aprobada.status_code == 200, aprobada.text

    texto = _texto(_pedir(api, viatico.id, "solicitud", encabezados).content)

    assert "Aprobación" in texto and "Carlos Revisor" in texto
    assert "PENDIENTE → APROBADO" in texto and "Procede el viaje" in texto


def test_la_solicitud_de_una_legalizacion_directa_es_409(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)

    respuesta = _pedir(api, viatico.id, "solicitud", encabezados)

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "MODALIDAD_INVALIDA"


def test_la_solicitud_tambien_sale_ya_en_etapa_de_legalizacion(
    api: TestClient, sesion: Session
) -> None:
    """La solicitud queda congelada y su PDF sigue disponible (docs/user-flows.md F-12)."""
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(
        sesion,
        usuario=viajero,
        modalidad=Modalidad.CON_SOLICITUD,
        etapa=Etapa.LEGALIZACION,
        legalizacion_habilitada_at=datetime.now(UTC),
    )

    assert _pedir(api, viatico.id, "solicitud", encabezados).status_code == 200


# =================================================================================================
# acceso (RLS) — comunes a los dos PDF
# =================================================================================================


@pytest.mark.parametrize("tipo", ["solicitud", "legalizacion"])
def test_otro_viajero_no_ve_el_pdf_404(api: TestClient, sesion: Session, tipo: str) -> None:
    dueno = crear_usuario(sesion)
    viatico = crear_viatico(
        sesion,
        usuario=dueno,
        modalidad=Modalidad.CON_SOLICITUD
        if tipo == "solicitud"
        else Modalidad.LEGALIZACION_DIRECTA,
    )
    _, encabezados = _actor(sesion)

    assert _pedir(api, viatico.id, tipo, encabezados).status_code == 404


@pytest.mark.parametrize("tipo", ["solicitud", "legalizacion"])
@pytest.mark.parametrize("rol", [Rol.FINANCIERO, Rol.ADMIN, Rol.SUPERADMIN])
def test_roles_privilegiados_descargan_el_pdf_ajeno(
    api: TestClient, sesion: Session, tipo: str, rol: Rol
) -> None:
    dueno = crear_usuario(sesion)
    viatico = crear_viatico(
        sesion,
        usuario=dueno,
        modalidad=Modalidad.CON_SOLICITUD
        if tipo == "solicitud"
        else Modalidad.LEGALIZACION_DIRECTA,
    )
    _, encabezados = _actor(sesion, rol)

    respuesta = _pedir(api, viatico.id, tipo, encabezados)

    assert respuesta.status_code == 200 and respuesta.content.startswith(b"%PDF-")


@pytest.mark.parametrize("tipo", ["solicitud", "legalizacion"])
def test_pdf_sin_sesion_es_401_e_inexistente_404(
    api: TestClient, sesion: Session, tipo: str
) -> None:
    _, encabezados = _actor(sesion)

    assert api.get(f"{URL}/{uuid.uuid4()}/pdf-{tipo}").status_code == 401
    assert _pedir(api, uuid.uuid4(), tipo, encabezados).status_code == 404


def test_un_viatico_eliminado_no_genera_pdf(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero, deleted_at=datetime.now(UTC))

    assert _pedir(api, viatico.id, "legalizacion", encabezados).status_code == 404


# =================================================================================================
# pdf-legalizacion
# =================================================================================================


def test_la_legalizacion_en_etapa_solicitud_es_409(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero, modalidad=Modalidad.CON_SOLICITUD)

    respuesta = _pedir(api, viatico.id, "legalizacion", encabezados)

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "ETAPA_INVALIDA"


def test_pdf_de_legalizacion_con_gastos_y_reembolso(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion, nombre_completo="Ana Pérez Quintero", cedula="1020304050")
    viatico = crear_viatico(
        sesion, usuario=viajero, recursos_propios=True, colaborador_cedula="1020304050"
    )
    rubro = crear_rubro(sesion, "Alimentación")
    crear_gasto(
        sesion,
        viatico,
        rubro_id=rubro.id,
        empresa="Restaurante El Buen Sabor",
        cc_nit="900123456-7",
        concepto="Almuerzo con el equipo",
        valor=Decimal("45000.50"),
        proyecto_otro="Proyecto escrito",
    )
    crear_gasto(sesion, viatico, rubro_id=rubro.id, valor=Decimal("30000"), concepto="Taxi")
    crear_gasto(sesion, viatico, concepto="Eliminado", deleted_at=datetime.now(UTC))

    respuesta = _pedir(api, viatico.id, "legalizacion", encabezados)

    assert respuesta.status_code == 200
    assert respuesta.headers["content-disposition"].startswith(
        f'attachment; filename="{viatico.folio}-legalizacion.pdf"'
    )
    texto = _texto(respuesta.content)
    for esperado in (
        viatico.folio,
        "Legalización de gastos",
        "Legalización directa",
        "Ana Pérez Quintero",
        "1020304050",
        "Restaurante El Buen Sabor",
        "900123456-7",
        "Alimentación",
        "Almuerzo con el equipo",
        "Proyecto escrito",
        "$ 45.000,50",
        "Total de gastos (2)",
        "$ 75.000,50",
        "recursos propios",
        "a reembolsar por la empresa al viajero",
        "-$ 75.000,50",
    ):
        assert esperado in texto, esperado
    assert "Eliminado" not in texto
    assert "Presupuesto solicitado" not in texto  # directa: no hay presupuesto


def test_pdf_de_legalizacion_con_anticipo_y_reintegro(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(
        sesion,
        usuario=viajero,
        modalidad=Modalidad.CON_SOLICITUD,
        etapa=Etapa.LEGALIZACION,
        legalizacion_habilitada_at=datetime.now(UTC),
        presupuesto_solicitado=Decimal("980000"),
        valor_asignado=Decimal("1000000"),
        estado_financiero=EstadoFinanciero.TRANSFERIDO,
    )
    crear_gasto(sesion, viatico, valor=Decimal("400000"))

    texto = _texto(_pedir(api, viatico.id, "legalizacion", encabezados).content)

    for esperado in (
        "Con solicitud previa",
        "Presupuesto solicitado (referencia)",
        "$ 980.000",
        "$ 1.000.000",
        "$ 600.000",
        "a reintegrar por el viajero a la empresa",
        "TRANSFERIDO",
    ):
        assert esperado in texto, esperado


def test_pdf_de_legalizacion_sin_gastos_ni_saldo(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)

    texto = _texto(_pedir(api, viatico.id, "legalizacion", encabezados).content)

    assert "No hay gastos registrados" in texto
    assert "sin saldo pendiente" in texto
    assert "Pendiente" in texto  # nadie ha aprobado ni liquidado


def test_pdf_de_legalizacion_trae_quien_creo_aprobo_y_liquido(
    api: TestClient, sesion: Session
) -> None:
    viajero, enc_viajero = _actor(sesion, nombre_completo="Ana Viajera")
    admin = crear_usuario(sesion, rol=Rol.ADMIN, nombre_completo="Carlos Aprobador")
    financiero = crear_usuario(sesion, rol=Rol.FINANCIERO, nombre_completo="Laura Tesorera")
    viatico = crear_viatico(sesion, usuario=viajero, recursos_propios=True)
    crear_gasto(sesion, viatico, soporte_id=crear_archivo(sesion, created_by=viajero.id).id)
    assert (
        api.post(f"{URL}/{viatico.id}/aprobar", json={}, headers=bearer(sesion, admin)).status_code
        == 200
    )
    pagado = api.post(
        f"{URL}/{viatico.id}/estado-financiero",
        json={"estado_financiero": "PAGADO", "comentario": "Reembolso enviado"},
        headers=bearer(sesion, financiero),
    )
    assert pagado.status_code == 200, pagado.text

    texto = _texto(_pedir(api, viatico.id, "legalizacion", enc_viajero).content)

    for esperado in (
        "Aprobó (operativo) Carlos Aprobador",
        "Liquidó (financiero) Laura Tesorera",
        "Reembolso enviado",
        "Liquidación",
        "PENDIENTE → APROBADO",
        "PENDIENTE → PAGADO",
    ):
        assert esperado in texto, esperado


def test_pdf_de_legalizacion_con_muchos_gastos_pagina_y_repite_el_encabezado(
    api: TestClient, sesion: Session
) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    rubro = crear_rubro(sesion)
    for i in range(90):
        crear_gasto(sesion, viatico, rubro_id=rubro.id, concepto=f"Gasto número {i}")

    contenido = _pedir(api, viatico.id, "legalizacion", encabezados).content

    lector = _lector(contenido)
    assert len(lector.pages) >= 2
    texto = _texto(contenido)
    assert f"Página 2 de {len(lector.pages)}" in texto
    assert "Gasto número 89" in texto
    # El encabezado de la tabla se repite en cada página que la continúa.
    assert " ".join(lector.pages[1].extract_text().split()).count("CC / NIT") >= 1


# =================================================================================================
# seguridad del render
# =================================================================================================


def test_el_texto_del_usuario_sale_escapado_en_el_html() -> None:
    hostil = '<script>alert(1)</script><img src="http://evil.test/x.png">'

    html = pdf.renderizar_html(
        "legalizacion.html",
        {
            "folio": "VT-000001",
            "generado": datetime.now(UTC),
            "creado": datetime.now(UTC),
            "modalidad": "Legalización directa",
            "estado": "PENDIENTE",
            "estado_financiero": "PENDIENTE",
            "colaborador": {
                "nombre": hostil,
                "cedula": None,
                "cargo": None,
                "celula": None,
                "vinculacion": "Empleado",
                "fecha_nacimiento": None,
            },
            "motivo": hostil,
            "proyecto": None,
            "lider": None,
            "recursos_propios": False,
            "gastos": [],
            "liquidacion": {
                "presupuesto_solicitado": None,
                "valor_asignado": Decimal(0),
                "valor_transferido": Decimal(0),
                "total_gastos": Decimal(0),
                "saldo": Decimal(0),
                "sentido": "sin saldo pendiente",
                "clase": "",
            },
            "responsables": {"creo": "—", "aprobo": "Pendiente", "liquido": "Pendiente"},
            "eventos": [],
        },
    )

    assert "<script>" not in html and "<img src=" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_un_texto_hostil_no_hace_que_el_servidor_pida_recursos(
    api: TestClient, sesion: Session
) -> None:
    """El `<img>` escrito en el motivo se muestra como texto y, aunque llegara a interpretarse,
    el `url_fetcher` solo admite `data:`."""
    viajero, encabezados = _actor(sesion)
    viatico = crear_viatico(
        sesion, usuario=viajero, motivo_viaje='<img src="file:///etc/passwd"> taller'
    )

    respuesta = _pedir(api, viatico.id, "legalizacion", encabezados)

    assert respuesta.status_code == 200
    assert '<img src="file:///etc/passwd"> taller' in _texto(respuesta.content)
    assert _imagenes(respuesta.content) == 0


@pytest.mark.parametrize(
    "url",
    [
        "http://evil.test/x.png",
        "https://evil.test/x.css",
        "file:///etc/passwd",
        "ftp://x/y",
        "/etc/passwd",
    ],
)
def test_el_fetcher_bloquea_todo_lo_que_no_sea_data(url: str) -> None:
    with pytest.raises(ValueError, match="bloqueado"):
        pdf.solo_datos(url)


def test_el_fetcher_admite_data_uri() -> None:
    resultado = pdf.solo_datos("data:image/png;base64,iVBORw0KGgo=")

    assert resultado is not None


def test_plantilla_con_dato_faltante_falla_en_voz_alta() -> None:
    from jinja2 import UndefinedError

    with pytest.raises(UndefinedError):
        pdf.renderizar_html("solicitud.html", {"folio": "VT-000001", "generado": datetime.now(UTC)})


# =================================================================================================
# formato (puro)
# =================================================================================================


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (None, "—"),
        (Decimal("0"), "$ 0"),
        (Decimal("1234567"), "$ 1.234.567"),
        (Decimal("45000.50"), "$ 45.000,50"),
        (Decimal("-50000"), "-$ 50.000"),
        (Decimal("-0.01"), "-$ 0,01"),
        ("980000.00", "$ 980.000"),
        (1000000, "$ 1.000.000"),
    ],
)
def test_formato_cop(valor: Any, esperado: str) -> None:
    assert pdf.formato_cop(valor) == esperado


def test_fechas_en_hora_de_colombia() -> None:
    momento = datetime(2026, 12, 1, 3, 30, tzinfo=UTC)  # 22:30 del día anterior en Bogotá

    assert pdf.formato_fecha(momento) == "30/11/2026"
    assert pdf.formato_fecha_hora(momento) == "30/11/2026 22:30"
    assert pdf.formato_fecha(None) == "—" and pdf.formato_fecha_hora(None) == "—"


def test_las_plantillas_existen() -> None:
    for nombre in ("base.html", "_comunes.html", "solicitud.html", "legalizacion.html"):
        assert (pdf.PLANTILLAS / nombre).is_file()


def test_generar_el_pdf_no_modifica_el_viatico(sesion: Session) -> None:
    """Generar el PDF es de solo lectura."""
    viatico = crear_viatico(sesion)
    dueno = sesion.get(Usuario, viatico.usuario_id)
    assert dueno is not None
    antes = (viatico.estado, viatico.estado_financiero, viatico.updated_at)

    pdf.generar_legalizacion(sesion, viatico.id, dueno)

    sesion.refresh(viatico)
    assert (viatico.estado, viatico.estado_financiero, viatico.updated_at) == antes
