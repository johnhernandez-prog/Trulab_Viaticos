"""CRUD de gastos de una legalización (S2-06, docs/api-design.md §5.5).

RN-01, RN-07, RN-08, RN-09, RN-13, RN-16, RN-21; un archivo por gasto; historial en
`viatico_eventos`; saldo recalculado por `v_viatico_saldos`.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.enums import (
    EstadoFinanciero,
    EstadoOperativo,
    Modalidad,
    PropositoArchivo,
    Rol,
)
from app.core.tiempo import hoy_colombia
from app.modules.archivos.models import Archivo
from app.modules.catalogos.models import Rubro
from app.modules.gastos.models import Gasto
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.models import Viatico, ViaticoEvento
from tests.fabricas import (
    bearer,
    crear_archivo,
    crear_gasto,
    crear_proyecto,
    crear_rubro,
    crear_usuario,
    crear_viatico,
)


def _url(viatico_id: uuid.UUID, gasto_id: uuid.UUID | None = None) -> str:
    base = f"/api/v1/viaticos/{viatico_id}/gastos"
    return f"{base}/{gasto_id}" if gasto_id else base


def _viajero(sesion: Session, rol: Rol = Rol.VIAJERO) -> tuple[Usuario, dict[str, str]]:
    usuario = crear_usuario(sesion, rol=rol)
    return usuario, bearer(sesion, usuario)


def _soporte(sesion: Session, dueno: Usuario) -> Archivo:
    return crear_archivo(sesion, created_by=dueno.id)


def _pdf(sesion: Session, dueno: Usuario) -> Archivo:
    return crear_archivo(
        sesion,
        created_by=dueno.id,
        proposito=PropositoArchivo.ARCHIVO,
        mime_type="application/pdf",
        nombre_original="factura.pdf",
    )


def _cuerpo(rubro: Rubro, **campos: object) -> dict[str, object]:
    cuerpo: dict[str, object] = {
        "fecha_factura": "2026-11-05",
        "rubro_id": str(rubro.id),
        "proyecto_otro": "Proyecto escrito",
        "concepto": "Almuerzo con el equipo",
        "valor": "45000.50",
    }
    cuerpo.update(campos)
    return cuerpo


def _saldo(sesion: Session, viatico_id: uuid.UUID) -> tuple[Decimal, Decimal, int]:
    fila = sesion.execute(
        text(
            "SELECT total_gastos, saldo, cantidad_gastos FROM v_viatico_saldos "
            "WHERE viatico_id = :id"
        ),
        {"id": viatico_id},
    ).one()
    return fila.total_gastos, fila.saldo, fila.cantidad_gastos


def _eventos(sesion: Session, viatico_id: uuid.UUID, accion: str) -> list[ViaticoEvento]:
    return list(
        sesion.scalars(
            select(ViaticoEvento).where(
                ViaticoEvento.viatico_id == viatico_id, ViaticoEvento.accion == accion
            )
        )
    )


# =================================================================================================
# POST
# =================================================================================================


def test_dueno_registra_un_gasto_con_soporte_y_archivo(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    rubro = crear_rubro(sesion)
    soporte, pdf = _soporte(sesion, viajero), _pdf(sesion, viajero)

    respuesta = api.post(
        _url(viatico.id),
        json=_cuerpo(
            rubro,
            soporte_id=str(soporte.id),
            archivo_id=str(pdf.id),
            cc_nit="900123456-7",
            empresa="Restaurante El Buen Sabor",
        ),
        headers=encabezados,
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["valor"] == "45000.50"
    assert cuerpo["rubro"] == {"id": str(rubro.id), "nombre": rubro.nombre}
    assert cuerpo["proyecto"] == {"id": None, "nombre": "Proyecto escrito", "en_catalogo": False}
    assert cuerpo["soporte"]["id"] == str(soporte.id)
    assert cuerpo["archivo"]["mime_type"] == "application/pdf"
    assert cuerpo["tiene_comprobante"] is True
    assert cuerpo["cc_nit"] == "900123456-7"
    assert respuesta.headers["Location"] == _url(viatico.id, uuid.UUID(cuerpo["id"]))
    gasto = sesion.get(Gasto, uuid.UUID(cuerpo["id"]))
    assert gasto is not None and gasto.created_by == viajero.id
    (evento,) = _eventos(sesion, viatico.id, "REGISTRAR_GASTO")
    assert evento.datos == {
        "gasto_id": cuerpo["id"],
        "concepto": "Almuerzo con el equipo",
        "valor": "45000.50",
    }
    assert _saldo(sesion, viatico.id) == (Decimal("45000.50"), Decimal("-45000.50"), 1)


def test_gasto_con_proyecto_del_catalogo_y_sin_comprobante(
    api: TestClient, sesion: Session
) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    proyecto = crear_proyecto(sesion)

    respuesta = api.post(
        _url(viatico.id),
        json=_cuerpo(crear_rubro(sesion), proyecto_otro=None, proyecto_id=str(proyecto.id)),
        headers=encabezados,
    )

    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["proyecto"] == {
        "id": str(proyecto.id),
        "nombre": proyecto.nombre,
        "en_catalogo": True,
    }
    # RN-21: se puede guardar sin comprobante; bloquea aprobar y liquidar.
    assert cuerpo["tiene_comprobante"] is False
    assert cuerpo["soporte"] is None and cuerpo["archivo"] is None


def test_admin_o_financiero_registran_gastos_en_su_propio_viatico(
    api: TestClient, sesion: Session
) -> None:
    financiero, encabezados = _viajero(sesion, Rol.FINANCIERO)
    viatico = crear_viatico(sesion, usuario=financiero)

    respuesta = api.post(_url(viatico.id), json=_cuerpo(crear_rubro(sesion)), headers=encabezados)

    assert respuesta.status_code == 201


def test_gasto_en_legalizacion_con_anticipo_transferido(api: TestClient, sesion: Session) -> None:
    """Paso 5 de docs/user-flows.md: legalización CON_SOLICITUD con `TRANSFERIDO` conservado."""
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(
        sesion,
        usuario=viajero,
        modalidad=Modalidad.CON_SOLICITUD,
        etapa="LEGALIZACION",
        legalizacion_habilitada_at=datetime.now(UTC),
        estado_financiero=EstadoFinanciero.TRANSFERIDO,
        valor_asignado=Decimal("100000"),
    )

    respuesta = api.post(_url(viatico.id), json=_cuerpo(crear_rubro(sesion)), headers=encabezados)

    assert respuesta.status_code == 201, respuesta.text
    assert _saldo(sesion, viatico.id)[1] == Decimal("54999.50")


# --- alcance y estado del viático ---------------------------------------------------------------


def test_otro_viajero_no_ve_el_viatico_404(api: TestClient, sesion: Session) -> None:
    viatico = crear_viatico(sesion)
    _, encabezados = _viajero(sesion)

    respuesta = api.post(_url(viatico.id), json=_cuerpo(crear_rubro(sesion)), headers=encabezados)

    assert respuesta.status_code == 404
    assert api.get(_url(viatico.id), headers=encabezados).status_code == 404


@pytest.mark.parametrize("rol", [Rol.ADMIN, Rol.FINANCIERO])
def test_admin_y_financiero_ven_pero_no_registran_gastos_ajenos(
    api: TestClient, sesion: Session, rol: Rol
) -> None:
    viatico = crear_viatico(sesion)
    crear_gasto(sesion, viatico)
    _, encabezados = _viajero(sesion, rol)

    respuesta = api.post(_url(viatico.id), json=_cuerpo(crear_rubro(sesion)), headers=encabezados)

    assert respuesta.status_code == 403
    listado = api.get(_url(viatico.id), headers=encabezados)
    assert listado.status_code == 200 and len(listado.json()) == 1


def test_superadmin_registra_gastos_en_viatico_ajeno(api: TestClient, sesion: Session) -> None:
    viatico = crear_viatico(sesion)
    superadmin, encabezados = _viajero(sesion, Rol.SUPERADMIN)
    soporte = _soporte(sesion, superadmin)

    respuesta = api.post(
        _url(viatico.id),
        json=_cuerpo(crear_rubro(sesion), soporte_id=str(soporte.id)),
        headers=encabezados,
    )

    assert respuesta.status_code == 201


def test_en_etapa_solicitud_es_409_etapa_invalida(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero, modalidad=Modalidad.CON_SOLICITUD)

    respuesta = api.post(_url(viatico.id), json=_cuerpo(crear_rubro(sesion)), headers=encabezados)

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "ETAPA_INVALIDA"


@pytest.mark.parametrize(
    ("estado", "estado_financiero"),
    [
        (EstadoOperativo.APROBADO, EstadoFinanciero.PENDIENTE),
        (EstadoOperativo.RECHAZADO, EstadoFinanciero.PENDIENTE),
        (EstadoOperativo.APROBADO, EstadoFinanciero.PAGADO),
        (EstadoOperativo.APROBADO, EstadoFinanciero.PROCESADO),
    ],
)
def test_fuera_de_pendiente_los_gastos_no_se_tocan(
    api: TestClient,
    sesion: Session,
    estado: EstadoOperativo,
    estado_financiero: EstadoFinanciero,
) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    gasto = crear_gasto(sesion, viatico)
    viatico.estado = estado
    viatico.estado_financiero = estado_financiero
    sesion.flush()

    creacion = api.post(_url(viatico.id), json=_cuerpo(crear_rubro(sesion)), headers=encabezados)
    edicion = api.patch(_url(viatico.id, gasto.id), json={"concepto": "X"}, headers=encabezados)
    borrado = api.delete(_url(viatico.id, gasto.id), headers=encabezados)

    for respuesta in (creacion, edicion, borrado):
        assert respuesta.status_code == 409
        assert respuesta.json()["code"] == "NO_EDITABLE"
    # Leer sí se puede.
    assert api.get(_url(viatico.id), headers=encabezados).status_code == 200


def test_viatico_eliminado_es_404(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero, deleted_at=datetime.now(UTC))

    respuesta = api.post(_url(viatico.id), json=_cuerpo(crear_rubro(sesion)), headers=encabezados)

    assert respuesta.status_code == 404


def test_sin_sesion_es_401(api: TestClient, sesion: Session) -> None:
    viatico = crear_viatico(sesion)

    assert api.get(_url(viatico.id)).status_code == 401


# --- validaciones de campo ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cambios", "codigo"),
    [
        ({"proyecto_otro": None}, "PROYECTO_REQUERIDO"),
        ({"proyecto_id": "__proyecto__"}, "PROYECTO_AMBIGUO"),
        ({"valor": "0"}, "VALIDACION"),
        ({"valor": "-10"}, "VALIDACION"),
        ({"valor": "10.123"}, "VALIDACION"),
        ({"valor": "abc"}, "VALIDACION"),
        ({"concepto": "   "}, "VALIDACION"),
        ({"proyecto_otro": "ab"}, "VALIDACION"),
        ({"usuario_id": "__proyecto__"}, "VALIDACION"),
        ({"deleted_at": "2026-01-01T00:00:00Z"}, "VALIDACION"),
    ],
)
def test_validaciones_del_cuerpo(
    api: TestClient, sesion: Session, cambios: dict[str, object], codigo: str
) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    proyecto = crear_proyecto(sesion)
    cambios = {k: (str(proyecto.id) if v == "__proyecto__" else v) for k, v in cambios.items()}

    respuesta = api.post(
        _url(viatico.id), json=_cuerpo(crear_rubro(sesion), **cambios), headers=encabezados
    )

    assert respuesta.status_code == 422, respuesta.text
    assert respuesta.json()["code"] == codigo


def test_fecha_de_factura_futura_es_422(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    manana = (hoy_colombia() + timedelta(days=1)).isoformat()

    respuesta = api.post(
        _url(viatico.id),
        json=_cuerpo(crear_rubro(sesion), fecha_factura=manana),
        headers=encabezados,
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["errors"][0] == {
        "field": "fecha_factura",
        "code": "FECHA_FUTURA",
        "message": "La fecha de la factura no puede ser futura",
    }


def test_fecha_de_factura_de_hoy_es_valida(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)

    respuesta = api.post(
        _url(viatico.id),
        json=_cuerpo(crear_rubro(sesion), fecha_factura=hoy_colombia().isoformat()),
        headers=encabezados,
    )

    assert respuesta.status_code == 201


@pytest.mark.parametrize("caso", ["inexistente", "inactivo"])
def test_rubro_inexistente_o_inactivo(api: TestClient, sesion: Session, caso: str) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    rubro = crear_rubro(sesion)
    if caso == "inactivo":
        rubro.activo = False
        sesion.flush()
    rubro_id = str(rubro.id) if caso == "inactivo" else str(uuid.uuid4())

    respuesta = api.post(
        _url(viatico.id), json=_cuerpo(rubro, rubro_id=rubro_id), headers=encabezados
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["errors"][0]["field"] == "rubro_id"


def test_proyecto_inactivo_es_422(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    proyecto = crear_proyecto(sesion, activo=False)

    respuesta = api.post(
        _url(viatico.id),
        json=_cuerpo(crear_rubro(sesion), proyecto_otro=None, proyecto_id=str(proyecto.id)),
        headers=encabezados,
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["errors"][0]["field"] == "proyecto_id"


# --- adjuntos (RN-13, 1:1) ----------------------------------------------------------------------


def test_pdf_como_soporte_o_imagen_como_archivo_es_415(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    rubro = crear_rubro(sesion)

    pdf_en_soporte = api.post(
        _url(viatico.id),
        json=_cuerpo(rubro, soporte_id=str(_pdf(sesion, viajero).id)),
        headers=encabezados,
    )
    imagen_en_archivo = api.post(
        _url(viatico.id),
        json=_cuerpo(rubro, archivo_id=str(_soporte(sesion, viajero).id)),
        headers=encabezados,
    )

    assert pdf_en_soporte.status_code == 415
    assert pdf_en_soporte.json()["errors"][0]["field"] == "soporte_id"
    assert imagen_en_archivo.status_code == 415
    assert imagen_en_archivo.json()["errors"][0]["field"] == "archivo_id"


@pytest.mark.parametrize("proposito", [PropositoArchivo.FIRMA, PropositoArchivo.FORMATO_PRESTADOR])
def test_otros_propositos_no_sirven_como_comprobante(
    api: TestClient, sesion: Session, proposito: PropositoArchivo
) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    archivo = crear_archivo(sesion, created_by=viajero.id, proposito=proposito)

    respuesta = api.post(
        _url(viatico.id),
        json=_cuerpo(crear_rubro(sesion), soporte_id=str(archivo.id)),
        headers=encabezados,
    )

    assert respuesta.status_code == 415


def test_adjunto_de_otro_usuario_o_inexistente_es_422(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    ajeno = _soporte(sesion, crear_usuario(sesion))
    rubro = crear_rubro(sesion)

    for archivo_id in (ajeno.id, uuid.uuid4()):
        respuesta = api.post(
            _url(viatico.id), json=_cuerpo(rubro, soporte_id=str(archivo_id)), headers=encabezados
        )
        assert respuesta.status_code == 422
        assert respuesta.json()["errors"][0] == {
            "field": "soporte_id",
            "code": "VALOR_NO_PERMITIDO",
            "message": "El archivo no existe",
        }


def test_mismo_archivo_en_soporte_y_archivo_es_422(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    soporte = _soporte(sesion, viajero)

    respuesta = api.post(
        _url(viatico.id),
        json=_cuerpo(crear_rubro(sesion), soporte_id=str(soporte.id), archivo_id=str(soporte.id)),
        headers=encabezados,
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["errors"][0]["field"] == "archivo_id"


@pytest.mark.parametrize("gasto_eliminado", [False, True])
def test_un_archivo_pertenece_a_un_solo_gasto(
    api: TestClient, sesion: Session, gasto_eliminado: bool
) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    soporte = _soporte(sesion, viajero)
    crear_gasto(
        sesion,
        viatico,
        soporte_id=soporte.id,
        deleted_at=datetime.now(UTC) if gasto_eliminado else None,
    )

    respuesta = api.post(
        _url(viatico.id),
        json=_cuerpo(crear_rubro(sesion), soporte_id=str(soporte.id)),
        headers=encabezados,
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "EN_USO"
    assert respuesta.json()["errors"][0]["field"] == "soporte_id"


# =================================================================================================
# GET
# =================================================================================================


def test_listado_solo_trae_los_activos_ordenados_por_fecha(
    api: TestClient, sesion: Session
) -> None:
    from datetime import date

    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    tardio = crear_gasto(sesion, viatico, fecha_factura=date(2026, 11, 8))
    temprano = crear_gasto(sesion, viatico, fecha_factura=date(2026, 11, 1))
    crear_gasto(sesion, viatico, deleted_at=datetime.now(UTC))

    respuesta = api.get(_url(viatico.id), headers=encabezados)

    assert respuesta.status_code == 200
    assert [g["id"] for g in respuesta.json()] == [str(temprano.id), str(tardio.id)]
    detalle = api.get(_url(viatico.id, tardio.id), headers=encabezados)
    assert detalle.status_code == 200 and detalle.json()["fecha_factura"] == "2026-11-08"


def test_gasto_de_otro_viatico_es_404(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    otro_viatico = crear_viatico(sesion, usuario=viajero)
    gasto = crear_gasto(sesion, otro_viatico)

    assert api.get(_url(viatico.id, gasto.id), headers=encabezados).status_code == 404
    assert (
        api.patch(_url(viatico.id, gasto.id), json={"concepto": "X"}, headers=encabezados)
    ).status_code == 404
    assert api.delete(_url(viatico.id, gasto.id), headers=encabezados).status_code == 404


# =================================================================================================
# PATCH
# =================================================================================================


def test_editar_campos_registra_antes_y_despues(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    gasto = crear_gasto(sesion, viatico, valor=Decimal("50000"))

    respuesta = api.patch(
        _url(viatico.id, gasto.id),
        json={"valor": "60000", "concepto": "Cena", "observaciones": "Con factura"},
        headers=encabezados,
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["valor"] == "60000.00"
    assert respuesta.json()["concepto"] == "Cena"
    (evento,) = _eventos(sesion, viatico.id, "EDITAR_GASTO")
    assert evento.datos is not None
    assert evento.datos["antes"]["valor"] == "50000.00"
    assert evento.datos["despues"] == {
        "valor": "60000.00",
        "concepto": "Cena",
        "observaciones": "Con factura",
    }
    assert _saldo(sesion, viatico.id)[0] == Decimal("60000.00")


def test_editar_sin_cambios_no_registra_evento(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    gasto = crear_gasto(sesion, viatico)

    respuesta = api.patch(
        _url(viatico.id, gasto.id), json={"concepto": gasto.concepto}, headers=encabezados
    )

    assert respuesta.status_code == 200
    assert _eventos(sesion, viatico.id, "EDITAR_GASTO") == []


def test_reemplazar_y_quitar_adjuntos(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    viejo = _soporte(sesion, viajero)
    nuevo = _soporte(sesion, viajero)
    gasto = crear_gasto(sesion, viatico, soporte_id=viejo.id)

    reemplazo = api.patch(
        _url(viatico.id, gasto.id), json={"soporte_id": str(nuevo.id)}, headers=encabezados
    )
    assert reemplazo.status_code == 200, reemplazo.text
    assert reemplazo.json()["soporte"]["id"] == str(nuevo.id)
    # El viejo queda libre (inmutable, sin gasto) y se puede volver a usar en otro gasto.
    assert sesion.get(Archivo, viejo.id) is not None

    quitado = api.patch(_url(viatico.id, gasto.id), json={"soporte_id": None}, headers=encabezados)
    assert quitado.status_code == 200
    assert quitado.json()["soporte"] is None
    assert quitado.json()["tiene_comprobante"] is False


def test_editar_con_adjunto_de_otro_gasto_es_409(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    pdf = _pdf(sesion, viajero)
    crear_gasto(sesion, viatico, archivo_id=pdf.id)
    gasto = crear_gasto(sesion, viatico)

    respuesta = api.patch(
        _url(viatico.id, gasto.id), json={"archivo_id": str(pdf.id)}, headers=encabezados
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "EN_USO"


def test_editar_conservando_el_mismo_adjunto_no_es_conflicto(
    api: TestClient, sesion: Session
) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    pdf = _pdf(sesion, viajero)
    gasto = crear_gasto(sesion, viatico, archivo_id=pdf.id)

    respuesta = api.patch(
        _url(viatico.id, gasto.id),
        json={"archivo_id": str(pdf.id), "concepto": "Hotel"},
        headers=encabezados,
    )

    assert respuesta.status_code == 200


def test_editar_proyecto_enviar_uno_borra_el_otro(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    gasto = crear_gasto(sesion, viatico)  # con proyecto_otro
    proyecto = crear_proyecto(sesion)

    respuesta = api.patch(
        _url(viatico.id, gasto.id), json={"proyecto_id": str(proyecto.id)}, headers=encabezados
    )

    assert respuesta.status_code == 200, respuesta.text
    sesion.refresh(gasto)
    assert gasto.proyecto_id == proyecto.id and gasto.proyecto_otro is None


@pytest.mark.parametrize("campo", ["valor", "concepto", "fecha_factura", "rubro_id"])
def test_editar_no_admite_null_en_obligatorios(
    api: TestClient, sesion: Session, campo: str
) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    gasto = crear_gasto(sesion, viatico)

    respuesta = api.patch(_url(viatico.id, gasto.id), json={campo: None}, headers=encabezados)

    assert respuesta.status_code == 422


def test_editar_fecha_futura_es_422(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    gasto = crear_gasto(sesion, viatico)
    manana = (hoy_colombia() + timedelta(days=1)).isoformat()

    respuesta = api.patch(
        _url(viatico.id, gasto.id), json={"fecha_factura": manana}, headers=encabezados
    )

    assert respuesta.status_code == 422


# =================================================================================================
# DELETE
# =================================================================================================


def test_eliminar_es_logico_y_recalcula_el_saldo(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    queda = crear_gasto(sesion, viatico, valor=Decimal("30000"))
    sale = crear_gasto(sesion, viatico, valor=Decimal("20000"))
    assert _saldo(sesion, viatico.id) == (Decimal("50000.00"), Decimal("-50000.00"), 2)

    respuesta = api.delete(_url(viatico.id, sale.id), headers=encabezados)

    assert respuesta.status_code == 204
    sesion.refresh(sale)
    assert sale.deleted_at is not None and sale.updated_by == viajero.id
    assert _saldo(sesion, viatico.id) == (Decimal("30000.00"), Decimal("-30000.00"), 1)
    (evento,) = _eventos(sesion, viatico.id, "ELIMINAR_GASTO")
    assert evento.datos is not None and evento.datos["gasto_id"] == str(sale.id)
    listado = api.get(_url(viatico.id), headers=encabezados).json()
    assert [g["id"] for g in listado] == [str(queda.id)]
    # Eliminarlo otra vez: ya no existe.
    assert api.delete(_url(viatico.id, sale.id), headers=encabezados).status_code == 404


def test_viajero_no_borra_gastos_ajenos(api: TestClient, sesion: Session) -> None:
    viatico = crear_viatico(sesion)
    gasto = crear_gasto(sesion, viatico)
    _, encabezados = _viajero(sesion)

    assert api.delete(_url(viatico.id, gasto.id), headers=encabezados).status_code == 404
    assert sesion.get(Gasto, gasto.id) is not None


def test_aprobar_tras_registrar_gastos_con_comprobante(api: TestClient, sesion: Session) -> None:
    """Integración con S2-05: los gastos registrados por la API habilitan la aprobación."""
    viajero, encabezados = _viajero(sesion)
    viatico = crear_viatico(sesion, usuario=viajero)
    soporte = _soporte(sesion, viajero)
    api.post(
        _url(viatico.id),
        json=_cuerpo(crear_rubro(sesion), soporte_id=str(soporte.id)),
        headers=encabezados,
    )
    _, encabezados_admin = _viajero(sesion, Rol.ADMIN)

    respuesta = api.post(
        f"/api/v1/viaticos/{viatico.id}/aprobar", json={}, headers=encabezados_admin
    )

    assert respuesta.status_code == 200, respuesta.text
    assert sesion.get(Viatico, viatico.id) is not None
