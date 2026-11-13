"""Modelo unificado (S2-02): catálogos, tarifas, archivos, viáticos, trayectos, eventos, gastos y
la vista `v_viatico_saldos` (docs/database-design.md §2.3–§2.9 y §2.14).

Corre como `trulab_app` (la conexión de la API) y todo se revierte al terminar. Cada caso que
viola una restricción es una prueba propia: tras el error, la transacción queda abortada.
"""

import csv
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from app.core.enums import AccionViatico, Etapa, Modalidad, PropositoArchivo
from app.modules.catalogos.models import CONCEPTOS_TARIFA, TarifaViatico
from app.modules.viaticos.models import ViaticoEvento, ViaticoTrayecto
from tests.fabricas import (
    crear_archivo,
    crear_gasto,
    crear_proyecto,
    crear_rubro,
    crear_usuario,
    crear_viatico,
)

CSV_TARIFAS = Path(__file__).parents[1] / "app/modules/catalogos/datos/tarifas_viaticos.csv"
CON, DIRECTA = Modalidad.CON_SOLICITUD, Modalidad.LEGALIZACION_DIRECTA


# --- tarifas (seed de la migración) -------------------------------------------------------------


def test_seed_carga_las_44_tarifas_del_csv(sesion: Session) -> None:
    with CSV_TARIFAS.open(encoding="utf-8", newline="") as archivo:
        esperadas = {
            (f["ciudad"], f["es_prestador_servicios"] == "true"): f for f in csv.DictReader(archivo)
        }
    tarifas = sesion.scalars(select(TarifaViatico).where(TarifaViatico.created_by.is_(None)))
    cargadas = {(t.ciudad, t.es_prestador_servicios): t for t in tarifas}

    assert set(cargadas) >= set(esperadas)
    assert len(esperadas) == 44
    for clave, fila in esperadas.items():
        tarifa = cargadas[clave]
        assert tarifa.migrado_de == fila["clave_legado"] and tarifa.activo, clave
        assert tarifa.orden == int(fila["orden"])
        for concepto in CONCEPTOS_TARIFA:
            assert getattr(tarifa, concepto) == Decimal(fila[concepto]), (clave, concepto)


def test_tarifa_unica_por_ciudad_y_tipo(sesion: Session) -> None:
    with pytest.raises(IntegrityError, match="uq_tarifas_viaticos__ciudad_tipo"):
        _tarifa(sesion, ciudad="BOGOTÁ", es_prestador_servicios=False)


def test_tarifa_no_admite_valores_negativos(sesion: Session) -> None:
    with pytest.raises(IntegrityError, match="ck_tarifas_viaticos__otros_gastos_no_negativo"):
        _tarifa(sesion, otros_gastos=Decimal("-1"))


def _tarifa(sesion: Session, **campos: Any) -> TarifaViatico:
    valores: dict[str, Any] = {
        "ciudad": f"Ciudad {uuid.uuid4().hex[:6]}",
        "es_prestador_servicios": False,
        **{concepto: Decimal("0") for concepto in CONCEPTOS_TARIFA},
    }
    valores.update(campos)
    tarifa = TarifaViatico(**valores)
    sesion.add(tarifa)
    sesion.flush()
    return tarifa


# --- catálogos ----------------------------------------------------------------------------------


def test_proyecto_con_codigo_y_formato_de_prestador(sesion: Session) -> None:
    proyecto = crear_proyecto(sesion, codigo=f"P-{uuid.uuid4().hex[:6]}")
    sesion.refresh(proyecto)

    assert proyecto.activo is True and proyecto.exige_formato_prestador is False


def test_proyecto_codigo_unico(sesion: Session) -> None:
    codigo = f"P-{uuid.uuid4().hex[:6]}"
    crear_proyecto(sesion, codigo=codigo)

    with pytest.raises(IntegrityError, match="uq_proyectos__codigo"):
        crear_proyecto(sesion, codigo=codigo)


def test_rubro_nombre_unico_sin_distinguir_mayusculas(sesion: Session) -> None:
    nombre = f"Alimentación {uuid.uuid4().hex[:6]}"
    crear_rubro(sesion, nombre)

    with pytest.raises(IntegrityError, match="uq_rubros__nombre"):
        crear_rubro(sesion, nombre.upper())


@pytest.mark.parametrize(
    "tabla", ["proyectos", "rubros", "tarifas_viaticos", "viaticos", "gastos", "archivos"]
)
def test_trulab_app_no_borra_fisicamente(sesion: Session, tabla: str) -> None:
    with pytest.raises(ProgrammingError, match="permission denied"):
        sesion.execute(text(f"DELETE FROM {tabla} WHERE false"))  # noqa: S608 (tabla fija)


# --- archivos -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("campos", "restriccion"),
    [
        ({"proposito": "OTRO"}, "ck_archivos__proposito"),
        ({"tamano_bytes": 10 * 1024 * 1024 + 1}, "ck_archivos__tamano_maximo"),
        ({"tamano_bytes": 0}, "ck_archivos__tamano_maximo"),
        ({"sha256": "no-es-un-hash"}, "ck_archivos__sha256_hex"),
        ({"mime_type": "imagen"}, "ck_archivos__mime_type_formato"),
    ],
)
def test_archivo_rechaza_metadatos_invalidos(
    sesion: Session, campos: dict[str, Any], restriccion: str
) -> None:
    with pytest.raises(IntegrityError, match=restriccion):
        crear_archivo(sesion, **campos)


def test_archivo_es_inmutable_para_trulab_app(sesion: Session) -> None:
    archivo = crear_archivo(sesion)

    with pytest.raises(ProgrammingError, match="permission denied"):
        sesion.execute(
            text("UPDATE archivos SET nombre_original = 'x' WHERE id = :id"), {"id": archivo.id}
        )


def test_firma_del_perfil_referencia_un_archivo(sesion: Session) -> None:
    firma = crear_archivo(sesion, proposito=PropositoArchivo.FIRMA, mime_type="image/png")
    usuario = crear_usuario(sesion, firma_archivo_id=firma.id)

    assert usuario.firma_archivo_id == firma.id


# --- viáticos -----------------------------------------------------------------------------------


def test_viatico_recibe_folio_vt_y_valores_por_defecto(sesion: Session) -> None:
    primero = crear_viatico(sesion, modalidad=CON)
    segundo = crear_viatico(sesion)
    sesion.refresh(primero)
    sesion.refresh(segundo)

    assert re.fullmatch(r"VT-\d{6,}", primero.folio)
    assert int(segundo.folio[3:]) > int(primero.folio[3:])
    assert (primero.etapa, primero.estado, primero.estado_financiero) == (
        "SOLICITUD",
        "PENDIENTE",
        "PENDIENTE",
    )
    assert primero.valor_asignado == 0 and primero.valor_transferido == 0
    assert primero.fecha_legalizacion == sesion.scalar(select(func.current_date()))


def test_valor_transferido_es_el_asignado_salvo_recursos_propios(sesion: Session) -> None:
    normal = crear_viatico(sesion, valor_asignado=Decimal("1500000"))
    propios = crear_viatico(sesion, recursos_propios=True, valor_asignado=Decimal("900000"))
    sesion.refresh(normal)
    sesion.refresh(propios)

    assert normal.valor_transferido == Decimal("1500000.00")
    assert propios.valor_transferido == Decimal("0.00")  # RN-14: la empresa reembolsa


def test_valor_transferido_no_se_puede_escribir(sesion: Session) -> None:
    viatico = crear_viatico(sesion)

    with pytest.raises(ProgrammingError, match="valor_transferido"):
        sesion.execute(
            text("UPDATE viaticos SET valor_transferido = 1 WHERE id = :id"), {"id": viatico.id}
        )


@pytest.mark.parametrize(
    ("modalidad", "campos", "restriccion"),
    [
        (DIRECTA, {"etapa": Etapa.SOLICITUD}, "etapa_segun_modalidad"),
        (DIRECTA, {"estado_financiero": "ANULADO"}, "ck_viaticos__estado_financiero"),
        (DIRECTA, {"estado": "DEVUELTO"}, "ck_viaticos__estado"),
        (DIRECTA, {"motivo_viaje": "  x "}, "motivo_viaje_longitud"),
        (DIRECTA, {"colaborador_nombre": " "}, "colaborador_nombre_no_vacio"),
        (DIRECTA, {"valor_asignado": Decimal("-1")}, "valor_asignado_no_negativo"),
        # Recursos propios solo en legalización directa (DP-17).
        (CON, {"recursos_propios": True}, "recursos_propios_directa"),
        # Proyecto: exactamente uno en la solicitud; ninguno en la legalización directa.
        (CON, {"proyecto_otro": None}, "proyecto_exclusivo"),
        (CON, {"proyecto_otro": "Ab"}, "proyecto_otro_longitud"),
        (DIRECTA, {"proyecto_otro": "Proyecto suelto"}, "proyecto_exclusivo"),
        (CON, {"lider_proyecto": None}, "lider_en_solicitud"),
        # Los datos de la solicitud no existen en la legalización directa.
        (DIRECTA, {"requiere_tiquete": True}, "solicitud_solo_con_solicitud"),
        (DIRECTA, {"presupuesto_solicitado": Decimal("1")}, "solicitud_solo_con_solicitud"),
        # Pasar a LEGALIZACION en CON_SOLICITUD exige haberla habilitado.
        (CON, {"etapa": Etapa.LEGALIZACION}, "legalizacion_habilitada"),
        # RN-03: PAGADO/PROCESADO exigen la legalización aprobada.
        (DIRECTA, {"estado_financiero": "PAGADO"}, "liquidacion_requiere_aprobado"),
        (CON, {"estado": "APROBADO", "estado_financiero": "PROCESADO"}, "liquidacion_requiere"),
    ],
)
def test_viatico_rechaza_estados_incoherentes(
    sesion: Session, modalidad: Modalidad, campos: dict[str, Any], restriccion: str
) -> None:
    with pytest.raises(IntegrityError, match=restriccion):
        crear_viatico(sesion, modalidad=modalidad, **campos)


def test_solicitud_con_proyecto_del_catalogo(sesion: Session) -> None:
    proyecto = crear_proyecto(sesion)

    viatico = crear_viatico(sesion, modalidad=CON, proyecto_id=proyecto.id, proyecto_otro=None)

    assert viatico.proyecto_id == proyecto.id


def test_solicitud_habilitada_pasa_a_legalizacion_y_puede_liquidarse(sesion: Session) -> None:
    viatico = crear_viatico(sesion, modalidad=CON, estado="APROBADO")

    sesion.execute(
        update(type(viatico))
        .where(type(viatico).id == viatico.id)
        .values(
            etapa=Etapa.LEGALIZACION,
            legalizacion_habilitada_at=datetime.now(UTC),
            estado_financiero="PAGADO",
        )
    )
    sesion.refresh(viatico)

    assert (viatico.etapa, viatico.estado_financiero) == ("LEGALIZACION", "PAGADO")


# --- trayectos ----------------------------------------------------------------------------------


def _trayecto(sesion: Session, viatico_id: uuid.UUID, **campos: Any) -> ViaticoTrayecto:
    ida = datetime(2026, 11, 20, 8, tzinfo=UTC)
    valores: dict[str, Any] = {
        "viatico_id": viatico_id,
        "orden": 1,
        "ciudad_origen": "Cali",
        "ciudad_destino": "Bogotá",
        "fecha_ida": ida,
        "fecha_regreso": ida + timedelta(days=2),
        "dias_estadia": 3,
    }
    valores.update(campos)
    trayecto = ViaticoTrayecto(**valores)
    sesion.add(trayecto)
    sesion.flush()
    return trayecto


def test_trayectos_con_instantanea_de_tarifa(sesion: Session) -> None:
    viatico = crear_viatico(sesion, modalidad=CON)
    tarifa = sesion.scalars(
        select(TarifaViatico).where(
            TarifaViatico.ciudad == "Bogotá", TarifaViatico.es_prestador_servicios.is_(False)
        )
    ).one()

    trayecto = _trayecto(
        sesion,
        viatico.id,
        tarifa_id=tarifa.id,
        vr_alimentacion=tarifa.vr_alimentacion,
        trans_interno=tarifa.trans_interno_varios_dias,
        otros_gastos=tarifa.otros_gastos,
        subtotal_estadia=Decimal("495000"),
    )
    _trayecto(sesion, viatico.id, orden=2, ciudad_origen="Bogotá", ciudad_destino="Cali")

    assert trayecto.tarifa_id == tarifa.id


@pytest.mark.parametrize(
    ("campos", "restriccion"),
    [
        ({"orden": 6}, "ck_viatico_trayectos__orden_rango"),
        ({"orden": 0}, "ck_viatico_trayectos__orden_rango"),
        ({"ciudad_destino": "Cali"}, "destino_distinto_de_origen"),
        ({"dias_estadia": 0}, "dias_estadia_minimo"),
        ({"fecha_regreso": datetime(2026, 11, 19, tzinfo=UTC)}, "regreso_despues_de_ida"),
        ({"subtotal_estadia": Decimal("-1")}, "subtotal_estadia_no_negativo"),
    ],
)
def test_trayecto_rechaza_datos_invalidos(
    sesion: Session, campos: dict[str, Any], restriccion: str
) -> None:
    viatico = crear_viatico(sesion, modalidad=CON)

    with pytest.raises(IntegrityError, match=restriccion):
        _trayecto(sesion, viatico.id, **campos)


def test_destino_otro_puede_coincidir_con_el_origen(sesion: Session) -> None:
    viatico = crear_viatico(sesion, modalidad=CON)

    assert _trayecto(sesion, viatico.id, ciudad_origen="Otro", ciudad_destino="Otro").id


def test_orden_de_trayecto_unico_por_viatico(sesion: Session) -> None:
    viatico = crear_viatico(sesion, modalidad=CON)
    _trayecto(sesion, viatico.id)

    with pytest.raises(IntegrityError, match="uq_viatico_trayectos__viatico_orden"):
        _trayecto(sesion, viatico.id, ciudad_destino="Medellín")


# --- eventos (solo inserción) --------------------------------------------------------------------


def test_evento_se_inserta_pero_no_se_modifica_ni_borra(sesion: Session) -> None:
    viatico = crear_viatico(sesion)
    evento = ViaticoEvento(
        viatico_id=viatico.id,
        etapa=Etapa.LEGALIZACION,
        accion=AccionViatico.CREAR,
        usuario_id=viatico.usuario_id,
        datos={"origen": "prueba"},
    )
    sesion.add(evento)
    sesion.flush()

    with pytest.raises(ProgrammingError, match="permission denied"):
        sesion.execute(
            text("UPDATE viatico_eventos SET comentario = 'x' WHERE id = :id"), {"id": evento.id}
        )


@pytest.mark.parametrize(
    ("campos", "restriccion"),
    [
        ({"accion": "BORRAR_TODO"}, "ck_viatico_eventos__accion"),
        ({"dimension": "OTRA"}, "ck_viatico_eventos__dimension"),
        ({"datos": [1, 2]}, "ck_viatico_eventos__datos_objeto"),
    ],
)
def test_evento_rechaza_valores_fuera_del_catalogo(
    sesion: Session, campos: dict[str, Any], restriccion: str
) -> None:
    viatico = crear_viatico(sesion)
    valores: dict[str, Any] = {
        "viatico_id": viatico.id,
        "etapa": Etapa.LEGALIZACION,
        "accion": AccionViatico.CREAR,
        "usuario_id": viatico.usuario_id,
    }
    valores.update(campos)
    sesion.add(ViaticoEvento(**valores))

    with pytest.raises(IntegrityError, match=restriccion):
        sesion.flush()


# --- gastos -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("campos", "restriccion"),
    [
        ({"valor": Decimal("0")}, "ck_gastos__valor_positivo"),
        ({"concepto": "  "}, "ck_gastos__concepto_no_vacio"),
        ({"proyecto_otro": None}, "ck_gastos__proyecto_exclusivo"),
        ({"proyecto_otro": "x"}, "ck_gastos__proyecto_otro_longitud"),
    ],
)
def test_gasto_rechaza_datos_invalidos(
    sesion: Session, campos: dict[str, Any], restriccion: str
) -> None:
    viatico = crear_viatico(sesion)

    with pytest.raises(IntegrityError, match=restriccion):
        crear_gasto(sesion, viatico, **campos)


def test_gasto_no_admite_proyecto_del_catalogo_y_otro_a_la_vez(sesion: Session) -> None:
    viatico = crear_viatico(sesion)

    with pytest.raises(IntegrityError, match="ck_gastos__proyecto_exclusivo"):
        crear_gasto(sesion, viatico, proyecto_id=crear_proyecto(sesion).id)


def test_un_archivo_pertenece_a_un_solo_gasto(sesion: Session) -> None:
    viatico = crear_viatico(sesion)
    soporte = crear_archivo(sesion)
    crear_gasto(sesion, viatico, soporte_id=soporte.id)

    with pytest.raises(IntegrityError, match="uq_gastos__soporte_id"):
        crear_gasto(sesion, viatico, soporte_id=soporte.id)


# --- vista de saldos ----------------------------------------------------------------------------


def _saldo(sesion: Session, viatico_id: uuid.UUID) -> dict[str, Any]:
    fila = (
        sesion.execute(
            text("SELECT * FROM v_viatico_saldos WHERE viatico_id = :id"), {"id": viatico_id}
        )
        .mappings()
        .one_or_none()
    )
    return dict(fila) if fila else {}


def test_saldo_es_transferido_menos_gastos_vigentes(sesion: Session) -> None:
    viatico = crear_viatico(sesion, valor_asignado=Decimal("1500000"))
    crear_gasto(sesion, viatico, valor=Decimal("1000000"), soporte_id=crear_archivo(sesion).id)
    crear_gasto(sesion, viatico, valor=Decimal("620000"))  # sin comprobante
    borrado = crear_gasto(sesion, viatico, valor=Decimal("999999"))
    borrado.deleted_at = datetime.now(UTC)
    sesion.flush()

    saldo = _saldo(sesion, viatico.id)

    assert saldo["valor_transferido"] == Decimal("1500000.00")
    assert saldo["total_gastos"] == Decimal("1620000.00")
    assert saldo["saldo"] == Decimal("-120000.00")  # reembolso al viajero (RN-02)
    assert (saldo["cantidad_gastos"], saldo["gastos_sin_comprobante"]) == (2, 1)


def test_saldo_sin_gastos_y_con_recursos_propios(sesion: Session) -> None:
    sin_gastos = crear_viatico(sesion, valor_asignado=Decimal("300000"))
    propios = crear_viatico(sesion, recursos_propios=True)
    crear_gasto(sesion, propios, valor=Decimal("80000"))

    assert _saldo(sesion, sin_gastos.id)["saldo"] == Decimal("300000.00")  # reintegro
    assert _saldo(sesion, propios.id)["saldo"] == Decimal("-80000.00")


def test_viatico_eliminado_no_aparece_en_los_saldos(sesion: Session) -> None:
    viatico = crear_viatico(sesion)
    viatico.deleted_at = datetime.now(UTC)
    sesion.flush()

    assert _saldo(sesion, viatico.id) == {}


@pytest.mark.parametrize(
    ("privilegio", "esperado"),
    [("SELECT", True), ("INSERT", False), ("UPDATE", False), ("DELETE", False)],
)
def test_la_vista_de_saldos_es_de_solo_lectura(
    sesion: Session, privilegio: str, esperado: bool
) -> None:
    concedido = sesion.scalar(
        text("SELECT has_table_privilege('v_viatico_saldos', :p)"), {"p": privilegio}
    )

    assert concedido is esperado
