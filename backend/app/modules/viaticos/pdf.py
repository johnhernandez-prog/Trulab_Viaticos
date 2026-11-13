"""PDF oficiales de un viático (S2-08; docs/api-design.md §5.4): solicitud y legalización.

- **Plantillas** Jinja2 en `app/templates/pdf/` con *autoescape* y `StrictUndefined` (un dato
  faltante falla en voz alta en vez de salir en blanco). El HTML se arma en `renderizar_html()`,
  separado de `a_pdf()`, para poder probar el contenido sin pagar el render.
- **Sin red:** WeasyPrint recibe un `url_fetcher` que solo admite `data:` (la firma va incrustada
  en base64); cualquier `http:`, `file:` u otro recurso se bloquea, así que ni un texto escrito por
  un usuario puede hacer que el servidor lea archivos o llame a otros servicios (SSRF).
- **Alcance:** nada de RLS aquí. Todo se lee con la sesión de la petición (`service.obtener`,
  `service.detalle`, `gastos.service.listar`): un viático ajeno es `404` para un VIAJERO.
- **Fechas:** hora de Colombia (UTC−5); dinero en COP con separador de miles.
"""

import base64
import hashlib
import logging
import uuid
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session
from weasyprint import HTML, default_url_fetcher

from app.core.enums import AccionViatico, Etapa, Modalidad
from app.core.tiempo import a_hora_colombia
from app.modules.archivos import deteccion
from app.modules.archivos.models import Archivo
from app.modules.archivos.storage import Almacenamiento
from app.modules.gastos import service as gastos_service
from app.modules.usuarios.models import Usuario
from app.modules.viaticos import service
from app.modules.viaticos.errores import EtapaInvalida, ModalidadInvalida
from app.modules.viaticos.models import Viatico, ViaticoEvento
from app.modules.viaticos.schemas import SolicitudSalida, ViaticoDetalle

logger = logging.getLogger("app.pdf")

PLANTILLAS = Path(__file__).resolve().parents[2] / "templates" / "pdf"
_IMAGENES_FIRMA = frozenset({deteccion.JPEG, deteccion.PNG, deteccion.WEBP})

ACCIONES_ES = {
    AccionViatico.CREAR: "Creación",
    AccionViatico.EDITAR_SOLICITUD: "Edición de la solicitud",
    AccionViatico.APROBAR: "Aprobación",
    AccionViatico.RECHAZAR: "Rechazo",
    AccionViatico.DEVOLVER: "Devolución",
    AccionViatico.GESTIONAR_TIQUETES: "Gestión de tiquetes",
    AccionViatico.HABILITAR_LEGALIZACION: "Legalización habilitada",
    AccionViatico.CAMBIAR_ESTADO_FINANCIERO: "Estado financiero",
    AccionViatico.EDITAR_VALOR_ASIGNADO: "Valor asignado",
    AccionViatico.CAMBIAR_RECURSOS_PROPIOS: "Recursos propios",
    AccionViatico.LIQUIDAR: "Liquidación",
    AccionViatico.ELIMINAR: "Eliminación",
    AccionViatico.REGISTRAR_GASTO: "Gasto registrado",
    AccionViatico.EDITAR_GASTO: "Gasto editado",
    AccionViatico.ELIMINAR_GASTO: "Gasto eliminado",
}
_EVENTOS_DE_GASTO = frozenset(
    {AccionViatico.REGISTRAR_GASTO, AccionViatico.EDITAR_GASTO, AccionViatico.ELIMINAR_GASTO}
)
MODALIDAD_ES = {
    Modalidad.CON_SOLICITUD: "Con solicitud previa",
    Modalidad.LEGALIZACION_DIRECTA: "Legalización directa",
}


# --- formato -------------------------------------------------------------------------------------


def formato_cop(valor: Decimal | int | float | str | None) -> str:
    """`$ 1.234.567` (COP); con centavos solo si los hay; negativo como `-$ 50.000`."""
    if valor is None:
        return "—"
    cuantizado = Decimal(str(valor)).quantize(Decimal("0.01"))
    entero, _, decimales = f"{abs(cuantizado):.2f}".partition(".")
    texto = "$ " + f"{int(entero):,}".replace(",", ".")
    if decimales != "00":
        texto += f",{decimales}"
    return f"-{texto}" if cuantizado < 0 else texto


def formato_fecha(valor: date | datetime | None) -> str:
    if valor is None:
        return "—"
    if isinstance(valor, datetime):
        valor = a_hora_colombia(valor)
    return valor.strftime("%d/%m/%Y")


def formato_fecha_hora(valor: datetime | None) -> str:
    if valor is None:
        return "—"
    return a_hora_colombia(valor).strftime("%d/%m/%Y %H:%M")


# --- render --------------------------------------------------------------------------------------


@lru_cache
def _entorno() -> Environment:
    entorno = Environment(
        loader=FileSystemLoader(PLANTILLAS),
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
    )
    entorno.filters["cop"] = formato_cop
    entorno.filters["fecha"] = formato_fecha
    entorno.filters["fecha_hora"] = formato_fecha_hora
    return entorno


def renderizar_html(plantilla: str, contexto: dict[str, Any]) -> str:
    return _entorno().get_template(plantilla).render(**contexto)


def solo_datos(url: str, *args: Any, **kwargs: Any) -> Any:
    """`url_fetcher` de WeasyPrint: solo `data:` (la firma incrustada). Todo lo demás se bloquea."""
    if url.startswith("data:"):
        return default_url_fetcher(url, *args, **kwargs)
    raise ValueError(f"Recurso externo bloqueado en el PDF: {url[:80]}")


def a_pdf(html: str) -> bytes:
    contenido: bytes = HTML(string=html, url_fetcher=solo_datos).write_pdf()
    return contenido


# --- datos ---------------------------------------------------------------------------------------


def _colaborador(viatico: Viatico) -> dict[str, Any]:
    return {
        "nombre": viatico.colaborador_nombre,
        "cedula": viatico.colaborador_cedula,
        "cargo": viatico.colaborador_cargo,
        "celula": viatico.colaborador_celula,
        "vinculacion": (
            "Prestador de servicios" if viatico.colaborador_es_prestador else "Empleado"
        ),
        "fecha_nacimiento": viatico.colaborador_fecha_nacimiento,
    }


def _nombres(session: Session, eventos: Sequence[ViaticoEvento]) -> dict[uuid.UUID, str]:
    ids = {e.usuario_id for e in eventos}
    if not ids:
        return {}
    return {
        u.id: u.nombre_completo for u in session.scalars(select(Usuario).where(Usuario.id.in_(ids)))
    }


def _detalle_evento(evento: ViaticoEvento) -> str:
    partes: list[str] = []
    if evento.estado_anterior or evento.estado_nuevo:
        partes.append(f"{evento.estado_anterior or '—'} → {evento.estado_nuevo or '—'}")
    if evento.comentario:
        partes.append(evento.comentario)
    return " · ".join(partes)


def _eventos(
    session: Session, viatico_id: uuid.UUID, *, etapa: Etapa | None, sin_gastos: bool
) -> list[ViaticoEvento]:
    consulta = (
        select(ViaticoEvento)
        .where(ViaticoEvento.viatico_id == viatico_id)
        .order_by(ViaticoEvento.created_at, ViaticoEvento.id)
    )
    if etapa is not None:
        consulta = consulta.where(ViaticoEvento.etapa == etapa)
    filas = list(session.scalars(consulta))
    if sin_gastos:
        filas = [e for e in filas if e.accion not in _EVENTOS_DE_GASTO]
    return filas


def _filas_trazabilidad(session: Session, eventos: Sequence[ViaticoEvento]) -> list[dict[str, Any]]:
    nombres = _nombres(session, eventos)
    return [
        {
            "fecha": e.created_at,
            "accion": ACCIONES_ES.get(AccionViatico(e.accion), e.accion),
            "usuario": nombres.get(e.usuario_id, "—"),
            "detalle": _detalle_evento(e),
        }
        for e in eventos
    ]


def _firma_data_uri(
    session: Session, almacenamiento: Almacenamiento, archivo_id: uuid.UUID | None
) -> str | None:
    """La firma como `data:` URI, o `None` si no hay, no se ve (RLS) o no es íntegra. Un fallo
    del almacenamiento no tumba el PDF: sale con el aviso "SIN FIRMA"."""
    if archivo_id is None:
        return None
    archivo = session.scalar(select(Archivo).where(Archivo.id == archivo_id))
    if archivo is None or archivo.mime_type not in _IMAGENES_FIRMA:
        return None
    try:
        contenido = almacenamiento.leer(archivo.storage_key)
    except Exception:
        logger.warning("firma_no_disponible", extra={"archivo_id": str(archivo_id)}, exc_info=True)
        return None
    if hashlib.sha256(contenido).hexdigest() != archivo.sha256:
        logger.error("firma_alterada", extra={"archivo_id": str(archivo_id)})
        return None
    return f"data:{archivo.mime_type};base64,{base64.b64encode(contenido).decode('ascii')}"


def _trayectos(detalle: ViaticoDetalle) -> list[dict[str, Any]]:
    if detalle.solicitud is None:
        return []
    filas: list[dict[str, Any]] = []
    for t in detalle.solicitud.trayectos:
        datos = t.model_dump()
        partes = (t.subtotal_estadia, t.transporte_aeropuerto, t.transporte_intermunicipal)
        datos["total_trayecto"] = (
            None if t.subtotal_estadia is None else sum((p or Decimal(0)) for p in partes)
        )
        filas.append(datos)
    return filas


def _presupuesto(solicitud: SolicitudSalida) -> dict[str, Any]:
    if not solicitud.requiere_gastos_viaje:
        return {"modo": "sin_gastos"}
    if solicitud.presupuesto_solicitado is None:
        formato = solicitud.formato_adjunto
        return {"modo": "formato", "formato_nombre": formato.nombre if formato else None}
    return {"modo": "tabla", "total": solicitud.presupuesto_solicitado}


def contexto_solicitud(
    session: Session, almacenamiento: Almacenamiento, viatico: Viatico, detalle: ViaticoDetalle
) -> dict[str, Any]:
    solicitud = detalle.solicitud
    if solicitud is None:  # solo la modalidad CON_SOLICITUD la tiene
        raise ModalidadInvalida(detail="Una legalización directa no tiene solicitud")
    # Firma del viático; si aún no la tiene, la del perfil del dueño (se copia al aprobar).
    firma_id = viatico.firma_archivo_id
    if firma_id is None:
        dueno = session.get(Usuario, viatico.usuario_id)
        firma_id = dueno.firma_archivo_id if dueno is not None else None
    return {
        "folio": viatico.folio,
        "generado": datetime.now().astimezone(),
        "creado": viatico.created_at,
        "estado": viatico.estado,
        "colaborador": _colaborador(viatico),
        "motivo": viatico.motivo_viaje,
        "proyecto": solicitud.proyecto.model_dump(),
        "lider": solicitud.lider_proyecto,
        "empresa": solicitud.empresa,
        "requiere_tiquete": solicitud.requiere_tiquete,
        "requiere_gastos_viaje": solicitud.requiere_gastos_viaje,
        "comentarios": solicitud.comentarios,
        "trayectos": _trayectos(detalle),
        "presupuesto": _presupuesto(solicitud),
        "firma_uri": _firma_data_uri(session, almacenamiento, firma_id),
        "eventos": _filas_trazabilidad(
            session, _eventos(session, viatico.id, etapa=Etapa.SOLICITUD, sin_gastos=True)
        ),
    }


def _liquidacion(detalle: ViaticoDetalle) -> dict[str, Any]:
    saldo = detalle.saldo
    if saldo > 0:
        sentido, clase = "a reintegrar por el viajero a la empresa", "reintegro"
    elif saldo < 0:
        sentido, clase = "a reembolsar por la empresa al viajero", "reembolso"
    else:
        sentido, clase = "sin saldo pendiente", ""
    presupuesto = detalle.solicitud.presupuesto_solicitado if detalle.solicitud else None
    return {
        "presupuesto_solicitado": presupuesto,
        "valor_asignado": detalle.valor_asignado,
        "valor_transferido": detalle.valor_transferido,
        "total_gastos": detalle.total_gastos,
        "saldo": saldo,
        "sentido": sentido,
        "clase": clase,
    }


def _responsable(filas: Sequence[ViaticoEvento], nombres: dict[uuid.UUID, str], vacio: str) -> str:
    if not filas:
        return vacio
    ultimo = filas[-1]
    return f"{nombres.get(ultimo.usuario_id, '—')} · {formato_fecha_hora(ultimo.created_at)}"


def _responsables(session: Session, eventos: Sequence[ViaticoEvento]) -> dict[str, str]:
    nombres = _nombres(session, eventos)
    creacion = [e for e in eventos if e.accion == AccionViatico.CREAR]
    aprobacion = [
        e for e in eventos if e.accion == AccionViatico.APROBAR and e.etapa == Etapa.LEGALIZACION
    ]
    liquidacion = [e for e in eventos if e.accion == AccionViatico.LIQUIDAR]
    return {
        "creo": _responsable(creacion, nombres, "—"),
        "aprobo": _responsable(aprobacion, nombres, "Pendiente"),
        "liquido": _responsable(liquidacion, nombres, "Pendiente"),
    }


def contexto_legalizacion(
    session: Session, viatico: Viatico, detalle: ViaticoDetalle
) -> dict[str, Any]:
    gastos = gastos_service.listar(session, viatico.id)
    eventos = _eventos(session, viatico.id, etapa=None, sin_gastos=True)
    solicitud = detalle.solicitud
    return {
        "folio": viatico.folio,
        "generado": datetime.now().astimezone(),
        "creado": viatico.created_at,
        "modalidad": MODALIDAD_ES[Modalidad(viatico.modalidad)],
        "estado": viatico.estado,
        "estado_financiero": viatico.estado_financiero,
        "colaborador": _colaborador(viatico),
        "motivo": viatico.motivo_viaje,
        "proyecto": solicitud.proyecto.model_dump() if solicitud else None,
        "lider": solicitud.lider_proyecto if solicitud else None,
        "recursos_propios": viatico.recursos_propios,
        "gastos": [
            {
                "fecha": g.fecha_factura,
                "empresa": g.empresa,
                "cc_nit": g.cc_nit,
                "proyecto": g.proyecto.nombre,
                "en_catalogo": g.proyecto.en_catalogo,
                "rubro": g.rubro.nombre,
                "concepto": g.concepto,
                "valor": g.valor,
            }
            for g in gastos
        ],
        "liquidacion": _liquidacion(detalle),
        "responsables": _responsables(session, eventos),
        "eventos": _filas_trazabilidad(session, eventos),
    }


# --- casos de uso --------------------------------------------------------------------------------


def generar_solicitud(
    session: Session, almacenamiento: Almacenamiento, viatico_id: uuid.UUID, actor: Usuario
) -> tuple[bytes, str]:
    viatico = service.obtener(session, viatico_id)  # RLS: ajeno → 404
    if viatico.modalidad != Modalidad.CON_SOLICITUD:
        raise ModalidadInvalida(detail="Una legalización directa no tiene solicitud")
    detalle = service.detalle(session, viatico, actor)
    html = renderizar_html(
        "solicitud.html", contexto_solicitud(session, almacenamiento, viatico, detalle)
    )
    return a_pdf(html), f"{viatico.folio}-solicitud.pdf"


def generar_legalizacion(
    session: Session, viatico_id: uuid.UUID, actor: Usuario
) -> tuple[bytes, str]:
    viatico = service.obtener(session, viatico_id)
    if viatico.etapa != Etapa.LEGALIZACION:
        raise EtapaInvalida(detail="El viático todavía no está en la etapa LEGALIZACION")
    detalle = service.detalle(session, viatico, actor)
    html = renderizar_html("legalizacion.html", contexto_legalizacion(session, viatico, detalle))
    return a_pdf(html), f"{viatico.folio}-legalizacion.pdf"
