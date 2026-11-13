"""Reglas de los gastos de una legalización (S2-06; docs/api-design.md §5.5).

- **Alcance:** leer, quien ve el viático (RLS: dueño o FINANCIERO/ADMIN/SUPERADMIN; ajeno →
  `404`). Crear, editar y eliminar: solo el dueño del viático o SUPERADMIN (visible pero ajeno →
  `403`), con el viático en etapa `LEGALIZACION` (si no, `409 ETAPA_INVALIDA`), `estado =
  PENDIENTE` y sin liquidar (`estado_financiero` ∉ {`PAGADO`, `PROCESADO`}; si no, `409
  NO_EDITABLE`). `TRANSFERIDO` se admite: es el estado normal de una legalización `CON_SOLICITUD`
  que recibió el anticipo (S-12, docs/user-flows.md paso 5).
- **Concurrencia:** cada escritura bloquea el viático padre (`FOR UPDATE`), igual que
  `transicionar()`: no se puede agregar un gasto mientras ADMIN aprueba.
- **Reglas:** proyecto exclusivo y activo (RN-16), rubro activo, `valor > 0` (RN-08, en el
  esquema), `fecha_factura` no futura en hora de Colombia (RN-07). Adjuntos: subidos por quien
  adjunta, con el propósito correcto (`SOPORTE` imagen, `ARCHIVO` PDF; RN-13 → `415`), distintos
  entre sí y no adjuntos a otro gasto (`409 EN_USO`).
- **Historial:** `REGISTRAR_GASTO`, `EDITAR_GASTO` y `ELIMINAR_GASTO` en `viatico_eventos`, en la
  misma transacción. El saldo no se guarda: lo recalcula `v_viatico_saldos` (ADR-008).
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.enums import (
    AccionViatico,
    EstadoFinanciero,
    EstadoOperativo,
    Etapa,
    PropositoArchivo,
)
from app.core.errors import NoEncontrado, ValorNoPermitido, error_de_campo
from app.core.tiempo import hoy_colombia
from app.modules.archivos import service as archivos
from app.modules.archivos.models import Archivo
from app.modules.auth.schemas import Referencia
from app.modules.catalogos.models import Proyecto, Rubro
from app.modules.gastos.errores import AdjuntoEnUso
from app.modules.gastos.models import Gasto
from app.modules.gastos.schemas import AdjuntoRef, GastoCrear, GastoEditar, GastoSalida
from app.modules.usuarios.models import Usuario
from app.modules.viaticos import service as viaticos
from app.modules.viaticos.errores import EtapaInvalida, NoEditable
from app.modules.viaticos.models import Viatico, ViaticoEvento
from app.modules.viaticos.schemas import ProyectoRefSalida

_LIQUIDADO = frozenset({EstadoFinanciero.PAGADO, EstadoFinanciero.PROCESADO})


# --- alcance y estado del viático padre ----------------------------------------------------------


def _viatico_para_escribir(session: Session, viatico_id: uuid.UUID, actor: Usuario) -> Viatico:
    viatico = viaticos.obtener(session, viatico_id, bloquear=True)
    viaticos.exigir_dueno_o_superadmin(viatico, actor)
    if viatico.etapa != Etapa.LEGALIZACION:
        raise EtapaInvalida(detail="Los gastos se registran en la etapa LEGALIZACION")
    if viatico.estado != EstadoOperativo.PENDIENTE or viatico.estado_financiero in _LIQUIDADO:
        raise NoEditable(detail="Los gastos solo se gestionan con la legalización pendiente")
    return viatico


def _obtener_gasto(session: Session, viatico: Viatico, gasto_id: uuid.UUID) -> Gasto:
    gasto = session.scalar(
        select(Gasto).where(
            Gasto.id == gasto_id, Gasto.viatico_id == viatico.id, Gasto.deleted_at.is_(None)
        )
    )
    if gasto is None:
        raise NoEncontrado()
    return gasto


# --- validaciones de campo -----------------------------------------------------------------------


def _validar_rubro(session: Session, rubro_id: uuid.UUID) -> None:
    if session.scalar(select(Rubro.id).where(Rubro.id == rubro_id, Rubro.activo)) is None:
        raise ValorNoPermitido(
            errors=error_de_campo("rubro_id", "El rubro no existe o está inactivo")
        )


def _validar_fecha(fecha_factura: date) -> None:
    if fecha_factura > hoy_colombia():
        raise ValorNoPermitido(
            errors=error_de_campo(
                "fecha_factura", "La fecha de la factura no puede ser futura", "FECHA_FUTURA"
            )
        )


def _validar_proyecto(
    session: Session, proyecto_id: uuid.UUID | None, proyecto_otro: str | None
) -> None:
    viaticos.validar_proyecto_exclusivo(proyecto_id, proyecto_otro)
    if proyecto_id is not None:
        viaticos.obtener_proyecto_activo(session, proyecto_id)


def _exigir_libre(
    session: Session, archivo_id: uuid.UUID, gasto_id: uuid.UUID | None, campo: str
) -> None:
    """Un archivo pertenece a un solo gasto, también si ese gasto se eliminó (lógicamente): el
    `UNIQUE` de la BD lo exige y así el gasto eliminado conserva su comprobante."""
    consulta = select(Gasto.id).where(
        or_(Gasto.soporte_id == archivo_id, Gasto.archivo_id == archivo_id)
    )
    if gasto_id is not None:
        consulta = consulta.where(Gasto.id != gasto_id)
    if session.scalar(consulta.limit(1)) is not None:
        raise AdjuntoEnUso(
            errors=error_de_campo(campo, "El archivo ya está adjunto a otro gasto", "EN_USO")
        )


def _validar_adjunto(
    session: Session,
    actor: Usuario,
    archivo_id: uuid.UUID,
    proposito: PropositoArchivo,
    campo: str,
    gasto_id: uuid.UUID | None,
) -> None:
    archivos.validar_adjunto(session, archivo_id, actor, proposito, campo)
    _exigir_libre(session, archivo_id, gasto_id, campo)


def _validar_distintos(soporte_id: uuid.UUID | None, archivo_id: uuid.UUID | None) -> None:
    if soporte_id is not None and soporte_id == archivo_id:
        raise ValorNoPermitido(
            errors=error_de_campo("archivo_id", "El soporte y el archivo deben ser distintos")
        )


# --- historial -----------------------------------------------------------------------------------


def _evento(
    session: Session,
    viatico: Viatico,
    actor: Usuario,
    accion: AccionViatico,
    datos: dict[str, object],
) -> None:
    session.add(
        ViaticoEvento(
            viatico_id=viatico.id,
            etapa=viatico.etapa,
            accion=accion,
            usuario_id=actor.id,
            datos=viaticos.serializable(datos),
        )
    )


def _resumen(gasto: Gasto) -> dict[str, object]:
    return {"gasto_id": gasto.id, "concepto": gasto.concepto, "valor": gasto.valor}


# --- salida --------------------------------------------------------------------------------------


def salidas(session: Session, gastos: Sequence[Gasto]) -> list[GastoSalida]:
    rubro_ids = {g.rubro_id for g in gastos}
    proyecto_ids = {g.proyecto_id for g in gastos if g.proyecto_id is not None}
    archivo_ids = {a for g in gastos for a in (g.soporte_id, g.archivo_id) if a is not None}
    rubros = (
        {r.id: r for r in session.scalars(select(Rubro).where(Rubro.id.in_(rubro_ids)))}
        if rubro_ids
        else {}
    )
    proyectos = (
        {p.id: p for p in session.scalars(select(Proyecto).where(Proyecto.id.in_(proyecto_ids)))}
        if proyecto_ids
        else {}
    )
    # RLS de `archivos`: un archivo que subió otro usuario puede no ser visible (→ sin nombre).
    adjuntos = (
        {a.id: a for a in session.scalars(select(Archivo).where(Archivo.id.in_(archivo_ids)))}
        if archivo_ids
        else {}
    )

    def _adjunto(archivo_id: uuid.UUID | None) -> AdjuntoRef | None:
        if archivo_id is None:
            return None
        archivo = adjuntos.get(archivo_id)
        return AdjuntoRef(
            id=archivo_id,
            nombre=archivo.nombre_original if archivo is not None else None,
            mime_type=archivo.mime_type if archivo is not None else None,
        )

    resultado: list[GastoSalida] = []
    for gasto in gastos:
        rubro = rubros[gasto.rubro_id]
        if gasto.proyecto_id is not None:
            proyecto = ProyectoRefSalida(
                id=gasto.proyecto_id, nombre=proyectos[gasto.proyecto_id].nombre, en_catalogo=True
            )
        else:
            proyecto = ProyectoRefSalida(
                id=None, nombre=gasto.proyecto_otro or "", en_catalogo=False
            )
        resultado.append(
            GastoSalida(
                id=gasto.id,
                viatico_id=gasto.viatico_id,
                fecha_factura=gasto.fecha_factura,
                rubro=Referencia(id=rubro.id, nombre=rubro.nombre),
                proyecto=proyecto,
                concepto=gasto.concepto,
                cc_nit=gasto.cc_nit,
                empresa=gasto.empresa,
                valor=gasto.valor,
                observaciones=gasto.observaciones,
                soporte=_adjunto(gasto.soporte_id),
                archivo=_adjunto(gasto.archivo_id),
                tiene_comprobante=gasto.soporte_id is not None or gasto.archivo_id is not None,
                created_at=gasto.created_at,
                updated_at=gasto.updated_at,
            )
        )
    return resultado


# --- lectura -------------------------------------------------------------------------------------


def listar(session: Session, viatico_id: uuid.UUID) -> list[GastoSalida]:
    viatico = viaticos.obtener(session, viatico_id)  # RLS: ajeno → 404
    gastos = session.scalars(
        select(Gasto)
        .where(Gasto.viatico_id == viatico.id, Gasto.deleted_at.is_(None))
        .order_by(Gasto.fecha_factura, Gasto.created_at, Gasto.id)
    ).all()
    return salidas(session, gastos)


def obtener(session: Session, viatico_id: uuid.UUID, gasto_id: uuid.UUID) -> GastoSalida:
    viatico = viaticos.obtener(session, viatico_id)
    return salidas(session, [_obtener_gasto(session, viatico, gasto_id)])[0]


# --- escritura -----------------------------------------------------------------------------------


def crear(
    session: Session, viatico_id: uuid.UUID, datos: GastoCrear, actor: Usuario
) -> GastoSalida:
    viatico = _viatico_para_escribir(session, viatico_id, actor)
    _validar_proyecto(session, datos.proyecto_id, datos.proyecto_otro)
    _validar_rubro(session, datos.rubro_id)
    _validar_fecha(datos.fecha_factura)
    _validar_distintos(datos.soporte_id, datos.archivo_id)
    if datos.soporte_id is not None:
        _validar_adjunto(
            session, actor, datos.soporte_id, PropositoArchivo.SOPORTE, "soporte_id", None
        )
    if datos.archivo_id is not None:
        _validar_adjunto(
            session, actor, datos.archivo_id, PropositoArchivo.ARCHIVO, "archivo_id", None
        )

    gasto = Gasto(
        viatico_id=viatico.id,
        **datos.model_dump(),
        created_by=actor.id,
        updated_by=actor.id,
    )
    session.add(gasto)
    session.flush()
    _evento(session, viatico, actor, AccionViatico.REGISTRAR_GASTO, _resumen(gasto))
    session.commit()
    session.refresh(gasto)
    return salidas(session, [gasto])[0]


_CAMPOS_SIMPLES = (
    "fecha_factura",
    "rubro_id",
    "concepto",
    "cc_nit",
    "empresa",
    "valor",
    "observaciones",
    "soporte_id",
    "archivo_id",
)


def _nuevo_proyecto(gasto: Gasto, cambios: dict[str, Any]) -> tuple[uuid.UUID | None, str | None]:
    """Igual que en `PATCH /viaticos`: enviar uno solo borra el otro; los dos juntos se validan
    tal cual (RN-16, ADR-031)."""
    tiene_id, tiene_otro = "proyecto_id" in cambios, "proyecto_otro" in cambios
    proyecto_id = cambios["proyecto_id"] if tiene_id else gasto.proyecto_id
    proyecto_otro = cambios["proyecto_otro"] if tiene_otro else gasto.proyecto_otro
    if tiene_id and not tiene_otro and proyecto_id is not None:
        proyecto_otro = None
    elif tiene_otro and not tiene_id and proyecto_otro is not None:
        proyecto_id = None
    return proyecto_id, proyecto_otro


def editar(
    session: Session,
    viatico_id: uuid.UUID,
    gasto_id: uuid.UUID,
    datos: GastoEditar,
    actor: Usuario,
) -> GastoSalida:
    viatico = _viatico_para_escribir(session, viatico_id, actor)
    gasto = _obtener_gasto(session, viatico, gasto_id)
    cambios = datos.model_dump(exclude_unset=True)

    nuevos: dict[str, Any] = {c: cambios[c] for c in _CAMPOS_SIMPLES if c in cambios}
    if "proyecto_id" in cambios or "proyecto_otro" in cambios:
        proyecto_id, proyecto_otro = _nuevo_proyecto(gasto, cambios)
        _validar_proyecto(session, proyecto_id, proyecto_otro)
        nuevos["proyecto_id"], nuevos["proyecto_otro"] = proyecto_id, proyecto_otro
    if "rubro_id" in nuevos and nuevos["rubro_id"] != gasto.rubro_id:
        _validar_rubro(session, nuevos["rubro_id"])
    if "fecha_factura" in nuevos:
        _validar_fecha(nuevos["fecha_factura"])

    soporte_id = nuevos.get("soporte_id", gasto.soporte_id)
    archivo_id = nuevos.get("archivo_id", gasto.archivo_id)
    _validar_distintos(soporte_id, archivo_id)
    # Solo se validan los adjuntos nuevos: reemplazar vincula otro archivo (inmutable); el
    # anterior queda en `archivos` sin gasto.
    if soporte_id is not None and soporte_id != gasto.soporte_id:
        _validar_adjunto(
            session, actor, soporte_id, PropositoArchivo.SOPORTE, "soporte_id", gasto.id
        )
    if archivo_id is not None and archivo_id != gasto.archivo_id:
        _validar_adjunto(
            session, actor, archivo_id, PropositoArchivo.ARCHIVO, "archivo_id", gasto.id
        )

    antes: dict[str, object] = {}
    despues: dict[str, object] = {}
    for campo, valor in nuevos.items():
        actual = getattr(gasto, campo)
        if actual != valor:
            antes[campo], despues[campo] = actual, valor
            setattr(gasto, campo, valor)

    if despues:
        gasto.updated_by = actor.id
        session.flush()
        _evento(
            session,
            viatico,
            actor,
            AccionViatico.EDITAR_GASTO,
            {"gasto_id": gasto.id, "antes": antes, "despues": despues},
        )
    session.commit()
    session.refresh(gasto)
    return salidas(session, [gasto])[0]


def eliminar(session: Session, viatico_id: uuid.UUID, gasto_id: uuid.UUID, actor: Usuario) -> None:
    viatico = _viatico_para_escribir(session, viatico_id, actor)
    gasto = _obtener_gasto(session, viatico, gasto_id)
    gasto.deleted_at = datetime.now(UTC)
    gasto.updated_by = actor.id
    _evento(session, viatico, actor, AccionViatico.ELIMINAR_GASTO, _resumen(gasto))
    session.commit()
