"""Firma y formato de prestador de la solicitud (S2-08; RN-32, RN-33): asociarlos al crear y
editar (`firma_archivo_id`, `formato_adjunto_id`) y exigirlos al aprobar la solicitud.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import EstadoOperativo, Etapa, Modalidad, PropositoArchivo, Rol
from app.modules.archivos.models import Archivo
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.models import Viatico, ViaticoEvento
from tests.fabricas import (
    bearer,
    crear_archivo,
    crear_gasto,
    crear_proyecto,
    crear_usuario,
    crear_viatico,
)

URL = "/api/v1/viaticos"
IDA = datetime(2026, 12, 1, 8, tzinfo=UTC)


def _actor(
    sesion: Session, rol: Rol = Rol.VIAJERO, **campos: Any
) -> tuple[Usuario, dict[str, str]]:
    usuario = crear_usuario(sesion, rol=rol, **campos)
    return usuario, bearer(sesion, usuario)


def _firma(sesion: Session, dueno: Usuario, **campos: Any) -> Archivo:
    valores: dict[str, Any] = {
        "created_by": dueno.id,
        "proposito": PropositoArchivo.FIRMA,
        "mime_type": "image/png",
        "nombre_original": "firma.png",
    }
    valores.update(campos)
    return crear_archivo(sesion, **valores)


def _formato(
    sesion: Session, dueno: Usuario, mime: str = "application/pdf", **campos: Any
) -> Archivo:
    valores: dict[str, Any] = {
        "created_by": dueno.id,
        "proposito": PropositoArchivo.FORMATO_PRESTADOR,
        "mime_type": mime,
        "nombre_original": "formato.pdf",
    }
    valores.update(campos)
    return crear_archivo(sesion, **valores)


def _cuerpo(proyecto_id: uuid.UUID, **campos: Any) -> dict[str, Any]:
    cuerpo: dict[str, Any] = {
        "modalidad": "CON_SOLICITUD",
        "motivo_viaje": "Taller de campo",
        "proyecto_id": str(proyecto_id),
        "lider_proyecto": "María Gómez",
        "requiere_gastos_viaje": True,
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


def _solicitud(sesion: Session, dueno: Usuario, **campos: Any) -> Viatico:
    return crear_viatico(sesion, usuario=dueno, modalidad=Modalidad.CON_SOLICITUD, **campos)


def _eventos(sesion: Session, viatico_id: uuid.UUID, accion: str) -> list[ViaticoEvento]:
    return list(
        sesion.scalars(
            select(ViaticoEvento).where(
                ViaticoEvento.viatico_id == viatico_id, ViaticoEvento.accion == accion
            )
        )
    )


# =================================================================================================
# POST /viaticos
# =================================================================================================


def test_crear_con_firma_y_formato_propios(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    proyecto = crear_proyecto(sesion)
    firma, formato = _firma(sesion, viajero), _formato(sesion, viajero)

    respuesta = api.post(
        URL,
        json=_cuerpo(
            proyecto.id, firma_archivo_id=str(firma.id), formato_adjunto_id=str(formato.id)
        ),
        headers=encabezados,
    )

    assert respuesta.status_code == 201, respuesta.text
    solicitud = respuesta.json()["solicitud"]
    assert solicitud["firma"] == {
        "id": str(firma.id),
        "nombre": "firma.png",
        "mime_type": "image/png",
    }
    assert solicitud["formato_adjunto"]["id"] == str(formato.id)
    viatico = sesion.get(Viatico, uuid.UUID(respuesta.json()["id"]))
    assert viatico is not None
    assert viatico.firma_archivo_id == firma.id and viatico.formato_adjunto_id == formato.id


def test_crear_sin_firma_toma_la_del_perfil(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    firma_perfil = _firma(sesion, viajero)
    viajero.firma_archivo_id = firma_perfil.id
    sesion.flush()

    respuesta = api.post(URL, json=_cuerpo(crear_proyecto(sesion).id), headers=encabezados)

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["solicitud"]["firma"]["id"] == str(firma_perfil.id)
    assert respuesta.json()["solicitud"]["formato_adjunto"] is None


def test_la_firma_enviada_gana_sobre_la_del_perfil(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viajero.firma_archivo_id = _firma(sesion, viajero).id
    nueva = _firma(sesion, viajero)
    sesion.flush()

    respuesta = api.post(
        URL,
        json=_cuerpo(crear_proyecto(sesion).id, firma_archivo_id=str(nueva.id)),
        headers=encabezados,
    )

    assert respuesta.json()["solicitud"]["firma"]["id"] == str(nueva.id)


def test_crear_sin_firma_ni_perfil_la_deja_vacia(api: TestClient, sesion: Session) -> None:
    _, encabezados = _actor(sesion)

    respuesta = api.post(URL, json=_cuerpo(crear_proyecto(sesion).id), headers=encabezados)

    assert respuesta.status_code == 201
    assert respuesta.json()["solicitud"]["firma"] is None


@pytest.mark.parametrize("campo", ["firma_archivo_id", "formato_adjunto_id"])
def test_crear_con_archivo_ajeno_o_inexistente_es_422(
    api: TestClient, sesion: Session, campo: str
) -> None:
    _, encabezados = _actor(sesion)
    otro = crear_usuario(sesion)
    ajeno = _firma(sesion, otro) if campo == "firma_archivo_id" else _formato(sesion, otro)
    proyecto = crear_proyecto(sesion)

    for archivo_id in (ajeno.id, uuid.uuid4()):
        respuesta = api.post(
            URL, json=_cuerpo(proyecto.id, **{campo: str(archivo_id)}), headers=encabezados
        )
        assert respuesta.status_code == 422, respuesta.text
        assert respuesta.json()["errors"][0]["field"] == campo


@pytest.mark.parametrize(
    ("campo", "proposito", "mime"),
    [
        # La firma debe ser imagen de propósito FIRMA; el formato, de propósito FORMATO_PRESTADOR.
        ("firma_archivo_id", PropositoArchivo.SOPORTE, "image/jpeg"),
        ("firma_archivo_id", PropositoArchivo.FIRMA, "application/pdf"),
        ("firma_archivo_id", PropositoArchivo.FORMATO_PRESTADOR, "application/pdf"),
        ("formato_adjunto_id", PropositoArchivo.FIRMA, "image/png"),
        ("formato_adjunto_id", PropositoArchivo.ARCHIVO, "application/pdf"),
        ("formato_adjunto_id", PropositoArchivo.FORMATO_PRESTADOR, "image/png"),
    ],
)
def test_crear_con_archivo_de_otro_tipo_es_415(
    api: TestClient, sesion: Session, campo: str, proposito: PropositoArchivo, mime: str
) -> None:
    viajero, encabezados = _actor(sesion)
    archivo = crear_archivo(sesion, created_by=viajero.id, proposito=proposito, mime_type=mime)

    respuesta = api.post(
        URL,
        json=_cuerpo(crear_proyecto(sesion).id, **{campo: str(archivo.id)}),
        headers=encabezados,
    )

    assert respuesta.status_code == 415, respuesta.text
    assert respuesta.json()["code"] == "TIPO_ARCHIVO_NO_PERMITIDO"
    assert respuesta.json()["errors"][0]["field"] == campo


@pytest.mark.parametrize(
    "mime",
    [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    ],
)
def test_el_formato_admite_pdf_y_excel(api: TestClient, sesion: Session, mime: str) -> None:
    viajero, encabezados = _actor(sesion)
    formato = _formato(sesion, viajero, mime)

    respuesta = api.post(
        URL,
        json=_cuerpo(crear_proyecto(sesion).id, formato_adjunto_id=str(formato.id)),
        headers=encabezados,
    )

    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["solicitud"]["formato_adjunto"]["mime_type"] == mime


def test_legalizacion_directa_no_acepta_firma_ni_formato(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)

    for campo, archivo in (
        ("firma_archivo_id", _firma(sesion, viajero)),
        ("formato_adjunto_id", _formato(sesion, viajero)),
    ):
        respuesta = api.post(
            URL,
            json={
                "modalidad": "LEGALIZACION_DIRECTA",
                "motivo_viaje": "Viaje",
                campo: str(archivo.id),
            },
            headers=encabezados,
        )
        assert respuesta.status_code == 422
        assert respuesta.json()["code"] == "VALIDACION"


# =================================================================================================
# PATCH /viaticos/{id}
# =================================================================================================


def test_editar_agrega_reemplaza_y_quita_la_firma(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = _solicitud(sesion, viajero)
    primera, segunda = _firma(sesion, viajero), _firma(sesion, viajero)

    agregada = api.patch(
        f"{URL}/{viatico.id}", json={"firma_archivo_id": str(primera.id)}, headers=encabezados
    )
    reemplazada = api.patch(
        f"{URL}/{viatico.id}", json={"firma_archivo_id": str(segunda.id)}, headers=encabezados
    )
    quitada = api.patch(f"{URL}/{viatico.id}", json={"firma_archivo_id": None}, headers=encabezados)

    assert agregada.json()["solicitud"]["firma"]["id"] == str(primera.id)
    assert reemplazada.json()["solicitud"]["firma"]["id"] == str(segunda.id)
    assert quitada.status_code == 200 and quitada.json()["solicitud"]["firma"] is None
    cambios = _eventos(sesion, viatico.id, "EDITAR_SOLICITUD")
    assert [e.datos["despues"]["firma_archivo_id"] for e in cambios if e.datos] == [
        str(primera.id),
        str(segunda.id),
        None,
    ]
    assert cambios[1].datos is not None
    assert cambios[1].datos["antes"]["firma_archivo_id"] == str(primera.id)


def test_editar_el_formato_y_no_recalcula_el_presupuesto(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = _solicitud(sesion, viajero, presupuesto_solicitado=None)
    formato = _formato(sesion, viajero)

    respuesta = api.patch(
        f"{URL}/{viatico.id}", json={"formato_adjunto_id": str(formato.id)}, headers=encabezados
    )

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["solicitud"]["formato_adjunto"]["id"] == str(formato.id)
    assert respuesta.json()["solicitud"]["presupuesto_solicitado"] is None


def test_editar_con_el_mismo_adjunto_no_genera_evento(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    firma = _firma(sesion, viajero)
    viatico = _solicitud(sesion, viajero, firma_archivo_id=firma.id)

    respuesta = api.patch(
        f"{URL}/{viatico.id}", json={"firma_archivo_id": str(firma.id)}, headers=encabezados
    )

    assert respuesta.status_code == 200
    assert _eventos(sesion, viatico.id, "EDITAR_SOLICITUD") == []


def test_editar_con_archivo_invalido(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = _solicitud(sesion, viajero)
    ajeno = _firma(sesion, crear_usuario(sesion))
    soporte = crear_archivo(sesion, created_by=viajero.id)

    ajeno_r = api.patch(
        f"{URL}/{viatico.id}", json={"firma_archivo_id": str(ajeno.id)}, headers=encabezados
    )
    tipo_r = api.patch(
        f"{URL}/{viatico.id}", json={"formato_adjunto_id": str(soporte.id)}, headers=encabezados
    )

    assert ajeno_r.status_code == 422
    assert tipo_r.status_code == 415


def test_editar_adjuntos_fuera_de_pendiente_es_409(api: TestClient, sesion: Session) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = _solicitud(sesion, viajero, estado=EstadoOperativo.APROBADO)

    respuesta = api.patch(
        f"{URL}/{viatico.id}",
        json={"firma_archivo_id": str(_firma(sesion, viajero).id)},
        headers=encabezados,
    )

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "NO_EDITABLE"


def test_en_legalizacion_no_se_editan_los_adjuntos_de_la_solicitud(
    api: TestClient, sesion: Session
) -> None:
    viajero, encabezados = _actor(sesion)
    viatico = _solicitud(
        sesion, viajero, etapa=Etapa.LEGALIZACION, legalizacion_habilitada_at=datetime.now(UTC)
    )

    respuesta = api.patch(
        f"{URL}/{viatico.id}",
        json={"firma_archivo_id": str(_firma(sesion, viajero).id)},
        headers=encabezados,
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "VALOR_NO_PERMITIDO"


# =================================================================================================
# POST /viaticos/{id}/aprobar (etapa SOLICITUD): RN-32 y RN-33
# =================================================================================================


def _aprobar(api: TestClient, viatico: Viatico, encabezados: dict[str, str]) -> Any:
    return api.post(f"{URL}/{viatico.id}/aprobar", json={}, headers=encabezados)


def test_sin_firma_no_se_aprueba_la_solicitud(api: TestClient, sesion: Session) -> None:
    _, admin = _actor(sesion, Rol.ADMIN)
    viatico = _solicitud(sesion, crear_usuario(sesion))

    respuesta = _aprobar(api, viatico, admin)

    assert respuesta.status_code == 409
    assert respuesta.json()["code"] == "FIRMA_REQUERIDA"
    assert respuesta.json()["errors"][0]["field"] == "firma_archivo_id"
    sesion.refresh(viatico)
    assert viatico.estado == EstadoOperativo.PENDIENTE


def test_con_la_firma_del_viatico_se_aprueba(api: TestClient, sesion: Session) -> None:
    _, admin = _actor(sesion, Rol.ADMIN)
    dueno = crear_usuario(sesion)
    viatico = _solicitud(sesion, dueno, firma_archivo_id=_firma(sesion, dueno).id)

    respuesta = _aprobar(api, viatico, admin)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["estado"] == "APROBADO"
    (evento,) = _eventos(sesion, viatico.id, "APROBAR")
    assert evento.datos is None  # no hubo que copiar la firma del perfil


def test_con_la_firma_del_perfil_se_aprueba_y_se_copia_al_viatico(
    api: TestClient, sesion: Session
) -> None:
    """El dueño guardó su firma después de crear la solicitud: sirve y queda congelada."""
    _, admin = _actor(sesion, Rol.ADMIN)
    dueno = crear_usuario(sesion)
    viatico = _solicitud(sesion, dueno)
    perfil = _firma(sesion, dueno)
    dueno.firma_archivo_id = perfil.id
    sesion.flush()

    respuesta = _aprobar(api, viatico, admin)

    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["solicitud"]["firma"]["id"] == str(perfil.id)
    sesion.refresh(viatico)
    assert viatico.firma_archivo_id == perfil.id
    (evento,) = _eventos(sesion, viatico.id, "APROBAR")
    assert evento.datos == {"firma_desde_perfil": str(perfil.id)}
    # Si el perfil cambia después, la solicitud conserva la firma con la que se aprobó.
    dueno.firma_archivo_id = _firma(sesion, dueno).id
    sesion.flush()
    assert viatico.firma_archivo_id == perfil.id


def test_rechazar_no_exige_firma(api: TestClient, sesion: Session) -> None:
    _, admin = _actor(sesion, Rol.ADMIN)
    viatico = _solicitud(sesion, crear_usuario(sesion))

    respuesta = api.post(
        f"{URL}/{viatico.id}/rechazar", json={"comentario": "No procede"}, headers=admin
    )

    assert respuesta.status_code == 200


@pytest.mark.parametrize(
    ("prestador", "exige", "con_formato", "otro", "esperado"),
    [
        (True, True, False, False, 409),  # RN-33: prestador + proyecto que lo exige, sin formato
        (True, True, True, False, 200),
        (True, False, False, False, 200),  # el proyecto no lo exige
        (False, True, False, False, 200),  # no es prestador: se calcula por tarifa
        (True, True, False, True, 200),  # "Otro" nunca exige formato
    ],
)
def test_formato_de_prestador_al_aprobar(
    api: TestClient,
    sesion: Session,
    prestador: bool,
    exige: bool,
    con_formato: bool,
    otro: bool,
    esperado: int,
) -> None:
    _, admin = _actor(sesion, Rol.ADMIN)
    dueno = crear_usuario(sesion, es_prestador_servicios=prestador)
    proyecto = crear_proyecto(sesion, exige_formato_prestador=exige, nombre="P-CONEXI-002")
    campos: dict[str, Any] = {"firma_archivo_id": _firma(sesion, dueno).id}
    if otro:
        campos["proyecto_otro"] = "Proyecto escrito"
    else:
        campos.update(proyecto_otro=None, proyecto_id=proyecto.id)
    if con_formato:
        campos["formato_adjunto_id"] = _formato(sesion, dueno).id
    viatico = _solicitud(sesion, dueno, **campos)

    respuesta = _aprobar(api, viatico, admin)

    assert respuesta.status_code == esperado, respuesta.text
    if esperado == 409:
        assert respuesta.json()["code"] == "FORMATO_PRESTADOR_REQUERIDO"
        assert "P-CONEXI-002" in respuesta.json()["detail"]
        assert respuesta.json()["errors"][0]["field"] == "formato_adjunto_id"


def test_se_usa_la_vinculacion_de_la_instantanea_no_la_actual(
    api: TestClient, sesion: Session
) -> None:
    """RN-17: lo que cuenta es la vinculación con la que se creó la solicitud."""
    _, admin = _actor(sesion, Rol.ADMIN)
    dueno = crear_usuario(sesion, es_prestador_servicios=True)
    proyecto = crear_proyecto(sesion, exige_formato_prestador=True)
    viatico = _solicitud(
        sesion,
        dueno,
        proyecto_otro=None,
        proyecto_id=proyecto.id,
        firma_archivo_id=_firma(sesion, dueno).id,
    )
    dueno.es_prestador_servicios = False  # cambió de vinculación después
    sesion.flush()

    assert _aprobar(api, viatico, admin).json()["code"] == "FORMATO_PRESTADOR_REQUERIDO"


def test_un_proyecto_desactivado_despues_sigue_exigiendo_el_formato(
    api: TestClient, sesion: Session
) -> None:
    _, admin = _actor(sesion, Rol.ADMIN)
    dueno = crear_usuario(sesion, es_prestador_servicios=True)
    proyecto = crear_proyecto(sesion, exige_formato_prestador=True)
    viatico = _solicitud(
        sesion,
        dueno,
        proyecto_otro=None,
        proyecto_id=proyecto.id,
        firma_archivo_id=_firma(sesion, dueno).id,
    )
    proyecto.activo = False
    sesion.flush()

    assert _aprobar(api, viatico, admin).status_code == 409


def test_formato_se_valida_antes_que_la_firma(api: TestClient, sesion: Session) -> None:
    _, admin = _actor(sesion, Rol.ADMIN)
    dueno = crear_usuario(sesion, es_prestador_servicios=True)
    proyecto = crear_proyecto(sesion, exige_formato_prestador=True)
    viatico = _solicitud(sesion, dueno, proyecto_otro=None, proyecto_id=proyecto.id)

    assert _aprobar(api, viatico, admin).json()["code"] == "FORMATO_PRESTADOR_REQUERIDO"


def test_aprobar_la_legalizacion_no_exige_firma_ni_formato(
    api: TestClient, sesion: Session
) -> None:
    """Las reglas RN-32/RN-33 son de la etapa SOLICITUD."""
    _, admin = _actor(sesion, Rol.ADMIN)
    dueno = crear_usuario(sesion, es_prestador_servicios=True)
    proyecto = crear_proyecto(sesion, exige_formato_prestador=True)
    viatico = _solicitud(
        sesion,
        dueno,
        etapa=Etapa.LEGALIZACION,
        legalizacion_habilitada_at=datetime.now(UTC),
        proyecto_otro=None,
        proyecto_id=proyecto.id,
    )
    crear_gasto(sesion, viatico, soporte_id=crear_archivo(sesion, created_by=dueno.id).id)

    assert _aprobar(api, viatico, admin).status_code == 200


def test_el_error_no_deja_cambios_a_medias(api: TestClient, sesion: Session) -> None:
    """Un 409 por firma no marca la solicitud aprobada ni deja eventos."""
    _, admin = _actor(sesion, Rol.ADMIN)
    viatico = _solicitud(sesion, crear_usuario(sesion))

    _aprobar(api, viatico, admin)

    sesion.refresh(viatico)
    assert viatico.aprobada_at is None
    assert _eventos(sesion, viatico.id, "APROBAR") == []
