"""Reglas de `viaticos` (docs/api-design.md §5.4): cálculo tarifario, creación, listado, edición y
eliminación en `PENDIENTE`, y la máquina de estados operativa (S2-04a + S2-04b/S2-05).

Todas las transiciones (`aprobar`, `rechazar`, `devolver`, `habilitar_legalizacion`) pasan por
`transicionar()`: bloquea la fila (`FOR UPDATE`), aplica el cambio y registra el evento inmutable
en `viatico_eventos`, todo en la misma transacción (docs/architecture.md §3).
"""

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Select, delete, select, text, update
from sqlalchemy.orm import Session

from app.core.audit import AccionAuditoria, registrar
from app.core.enums import (
    AccionViatico,
    DimensionEvento,
    EstadoFinanciero,
    EstadoOperativo,
    Etapa,
    Modalidad,
    PropositoArchivo,
    Rol,
    TipoLiquidacion,
)
from app.core.errors import NoEncontrado, ValorNoPermitido, error_de_campo
from app.core.paginacion import ParametrosPagina, paginar, patron_busqueda
from app.core.permissions import SinPermiso
from app.modules.archivos import service as archivos
from app.modules.archivos.models import Archivo
from app.modules.auth.schemas import Referencia
from app.modules.auth.service import Contexto
from app.modules.cargos.models import Cargo
from app.modules.catalogos.models import Celula, Proyecto, TarifaViatico
from app.modules.gastos.models import Gasto
from app.modules.usuarios.models import Usuario
from app.modules.viaticos import acciones
from app.modules.viaticos.calculo import (
    CiudadSinTarifaError,
    ResultadoPresupuesto,
    TarifaConceptos,
    TrayectoEntrada,
    calcular_presupuesto,
)
from app.modules.viaticos.errores import (
    AutoaprobacionNoPermitida,
    ComentarioRequerido,
    ComprobanteFaltante,
    FechaNacimientoRequerida,
    FirmaRequerida,
    FormatoPrestadorRequerido,
    LegalizacionNoHabilitable,
    NoEditable,
    ProyectoAmbiguo,
    ProyectoRequerido,
    TransicionInvalida,
)
from app.modules.viaticos.models import Viatico as ViaticoModelo
from app.modules.viaticos.models import ViaticoEvento
from app.modules.viaticos.models import ViaticoTrayecto as ViaticoTrayectoModelo
from app.modules.viaticos.schemas import (
    ArchivoRefSalida,
    CalcularPresupuestoEntrada,
    ColaboradorSalida,
    EventoSalida,
    ProyectoRefSalida,
    SolicitudSalida,
    TrayectoEntradaSchema,
    TrayectoSalida,
    ViaticoCrear,
    ViaticoCrearConSolicitud,
    ViaticoCrearLegalizacionDirecta,
    ViaticoDetalle,
    ViaticoEditar,
    ViaticoResumen,
)

ENTIDAD = "viaticos"

# --- proyecto: exclusividad, existencia y la marca de "exige formato de prestador" (RN-16, RN-33) -


def validar_proyecto_exclusivo(proyecto_id: uuid.UUID | None, proyecto_otro: str | None) -> None:
    if proyecto_id is None and proyecto_otro is None:
        raise ProyectoRequerido()
    if proyecto_id is not None and proyecto_otro is not None:
        raise ProyectoAmbiguo()


def obtener_proyecto_activo(session: Session, proyecto_id: uuid.UUID) -> Proyecto:
    proyecto = session.scalar(select(Proyecto).where(Proyecto.id == proyecto_id, Proyecto.activo))
    if proyecto is None:
        raise ValorNoPermitido(
            errors=error_de_campo("proyecto_id", "El proyecto no existe o está inactivo")
        )
    return proyecto


def _exige_formato_prestador(session: Session, proyecto_id: uuid.UUID | None) -> bool:
    # "Otro" (proyecto_otro) nunca exige formato: no es una fila del catálogo (RN-33).
    if proyecto_id is None:
        return False
    return obtener_proyecto_activo(session, proyecto_id).exige_formato_prestador


# --- tarifas activas por ciudad de destino (RN-29) ----------------------------------------------


def _tarifas_por_ciudad(
    session: Session, ciudades: Sequence[str], es_prestador_servicios: bool
) -> dict[str, TarifaConceptos]:
    if not ciudades:
        return {}
    normalizadas = {c.strip().lower() for c in ciudades}
    filas = session.scalars(
        select(TarifaViatico).where(
            TarifaViatico.es_prestador_servicios == es_prestador_servicios,
            TarifaViatico.activo,
        )
    )
    return {
        tarifa.ciudad.strip().lower(): TarifaConceptos(
            tarifa_id=tarifa.id,
            vr_alimentacion=tarifa.vr_alimentacion,
            otros_gastos=tarifa.otros_gastos,
            transporte_aeropuerto=tarifa.transporte_aeropuerto,
            transporte_intermunicipal=tarifa.transporte_intermunicipal,
            trans_interno_dia_1=tarifa.trans_interno_dia_1,
            trans_interno_varios_dias=tarifa.trans_interno_varios_dias,
        )
        for tarifa in filas
        if tarifa.ciudad.strip().lower() in normalizadas
    }


def _a_trayecto_entrada(datos: TrayectoEntradaSchema) -> TrayectoEntrada:
    return TrayectoEntrada(
        orden=datos.orden,
        ciudad_origen=datos.ciudad_origen,
        ciudad_destino=datos.ciudad_destino,
        fecha_ida=datos.fecha_ida,
        fecha_regreso=datos.fecha_regreso,
        requiere_hospedaje=datos.requiere_hospedaje,
        dias_estadia=datos.dias_estadia,
    )


def calcular_presupuesto_bd(
    session: Session,
    *,
    proyecto_id: uuid.UUID | None,
    proyecto_otro: str | None,
    es_prestador_servicios: bool,
    requiere_gastos_viaje: bool,
    trayectos: Sequence[TrayectoEntradaSchema],
) -> ResultadoPresupuesto:
    """Resuelve el proyecto y las tarifas, y delega la aritmética a la función pura (RN-29)."""
    validar_proyecto_exclusivo(proyecto_id, proyecto_otro)
    exige_formato = _exige_formato_prestador(session, proyecto_id)
    entradas = [_a_trayecto_entrada(t) for t in trayectos]
    tarifas = (
        _tarifas_por_ciudad(session, [t.ciudad_destino for t in entradas], es_prestador_servicios)
        if requiere_gastos_viaje and not (es_prestador_servicios and exige_formato)
        else {}
    )
    try:
        return calcular_presupuesto(
            entradas,
            tarifas_por_ciudad=tarifas,
            requiere_gastos_viaje=requiere_gastos_viaje,
            es_prestador_servicios=es_prestador_servicios,
            exige_formato_prestador=exige_formato,
        )
    except CiudadSinTarifaError as error:
        raise ValorNoPermitido(
            errors=error_de_campo(
                "trayectos",
                f'No hay una tarifa activa para "{error}" con ese tipo de vinculación',
            )
        ) from error


def calcular_presupuesto_preview(
    session: Session, usuario: Usuario, datos: CalcularPresupuestoEntrada
) -> ResultadoPresupuesto:
    return calcular_presupuesto_bd(
        session,
        proyecto_id=datos.proyecto_id,
        proyecto_otro=datos.proyecto_otro,
        es_prestador_servicios=usuario.es_prestador_servicios,
        requiere_gastos_viaje=datos.requiere_gastos_viaje,
        trayectos=datos.trayectos,
    )


# --- instantánea del colaborador (RN-17) ------------------------------------------------------


def _nombre_cargo(session: Session, cargo_id: uuid.UUID | None) -> str | None:
    if cargo_id is None:
        return None
    cargo = session.get(Cargo, cargo_id)
    return cargo.nombre if cargo is not None else None


def _nombre_celula(session: Session, celula_id: uuid.UUID | None) -> str | None:
    if celula_id is None:
        return None
    celula = session.get(Celula, celula_id)
    return celula.nombre if celula is not None else None


def _instantanea_colaborador(session: Session, usuario: Usuario) -> dict[str, object]:
    return {
        "colaborador_nombre": usuario.nombre_completo,
        "colaborador_cargo": _nombre_cargo(session, usuario.cargo_id),
        "colaborador_cedula": usuario.cedula,
        "colaborador_celula": _nombre_celula(session, usuario.celula_id),
        "colaborador_es_prestador": usuario.es_prestador_servicios,
        "colaborador_fecha_nacimiento": usuario.fecha_nacimiento,
    }


# --- firma y formato de prestador de la solicitud (RN-32, RN-33) --------------------------------


def _validar_firma(session: Session, firma_id: uuid.UUID, actor: Usuario) -> None:
    archivos.validar_adjunto(session, firma_id, actor, PropositoArchivo.FIRMA, "firma_archivo_id")


def _validar_formato(session: Session, formato_id: uuid.UUID, actor: Usuario) -> None:
    archivos.validar_adjunto(
        session, formato_id, actor, PropositoArchivo.FORMATO_PRESTADOR, "formato_adjunto_id"
    )


def _referencias_archivos(
    session: Session, ids: Sequence[uuid.UUID | None]
) -> dict[uuid.UUID, Archivo]:
    buscados = {i for i in ids if i is not None}
    if not buscados:
        return {}
    # RLS de `archivos`: un archivo que subió otro usuario puede no ser visible (→ sin nombre).
    return {a.id: a for a in session.scalars(select(Archivo).where(Archivo.id.in_(buscados)))}


def _ref_archivo(
    archivo_id: uuid.UUID | None, visibles: dict[uuid.UUID, Archivo]
) -> ArchivoRefSalida | None:
    if archivo_id is None:
        return None
    archivo = visibles.get(archivo_id)
    return ArchivoRefSalida(
        id=archivo_id,
        nombre=archivo.nombre_original if archivo is not None else None,
        mime_type=archivo.mime_type if archivo is not None else None,
    )


# --- crear (ADR-029: dos modalidades) ----------------------------------------------------------


def _crear_evento_inicial(session: Session, viatico: ViaticoModelo, actor: Usuario) -> None:
    session.add(
        ViaticoEvento(
            viatico_id=viatico.id,
            etapa=viatico.etapa,
            accion=AccionViatico.CREAR,
            usuario_id=actor.id,
        )
    )


def _crear_con_solicitud(
    session: Session, datos: ViaticoCrearConSolicitud, actor: Usuario
) -> ViaticoModelo:
    validar_proyecto_exclusivo(datos.proyecto_id, datos.proyecto_otro)
    if datos.proyecto_id is not None:
        obtener_proyecto_activo(session, datos.proyecto_id)
    if datos.requiere_tiquete and actor.fecha_nacimiento is None:
        raise FechaNacimientoRequerida()
    # Firma: la enviada (propia, imagen) o, si no, la del perfil (RN-32).
    if datos.firma_archivo_id is not None:
        _validar_firma(session, datos.firma_archivo_id, actor)
    firma_id = datos.firma_archivo_id or actor.firma_archivo_id
    if datos.formato_adjunto_id is not None:
        _validar_formato(session, datos.formato_adjunto_id, actor)

    resultado = calcular_presupuesto_bd(
        session,
        proyecto_id=datos.proyecto_id,
        proyecto_otro=datos.proyecto_otro,
        es_prestador_servicios=actor.es_prestador_servicios,
        requiere_gastos_viaje=datos.requiere_gastos_viaje,
        trayectos=datos.trayectos,
    )

    viatico = ViaticoModelo(
        modalidad=Modalidad.CON_SOLICITUD,
        etapa=Etapa.SOLICITUD,
        usuario_id=actor.id,
        motivo_viaje=datos.motivo_viaje,
        proyecto_id=datos.proyecto_id,
        proyecto_otro=datos.proyecto_otro,
        lider_proyecto=datos.lider_proyecto,
        empresa=datos.empresa,
        requiere_tiquete=datos.requiere_tiquete,
        requiere_gastos_viaje=datos.requiere_gastos_viaje,
        presupuesto_solicitado=resultado.presupuesto_solicitado,
        comentarios=datos.comentarios,
        firma_archivo_id=firma_id,
        formato_adjunto_id=datos.formato_adjunto_id,
        created_by=actor.id,
        updated_by=actor.id,
        **_instantanea_colaborador(session, actor),
    )
    session.add(viatico)
    session.flush()

    for trayecto in resultado.trayectos:
        session.add(
            ViaticoTrayectoModelo(
                viatico_id=viatico.id,
                orden=trayecto.orden,
                ciudad_origen=trayecto.ciudad_origen,
                ciudad_destino=trayecto.ciudad_destino,
                fecha_ida=trayecto.fecha_ida,
                fecha_regreso=trayecto.fecha_regreso,
                requiere_hospedaje=trayecto.requiere_hospedaje,
                dias_estadia=trayecto.dias_estadia,
                tarifa_id=trayecto.tarifa_id,
                vr_alimentacion=trayecto.vr_alimentacion,
                otros_gastos=trayecto.otros_gastos,
                trans_interno=trayecto.trans_interno,
                transporte_aeropuerto=trayecto.transporte_aeropuerto,
                transporte_intermunicipal=trayecto.transporte_intermunicipal,
                subtotal_estadia=trayecto.subtotal_estadia,
            )
        )

    _crear_evento_inicial(session, viatico, actor)
    session.commit()
    session.refresh(viatico)
    return viatico


def _crear_legalizacion_directa(
    session: Session, datos: ViaticoCrearLegalizacionDirecta, actor: Usuario
) -> ViaticoModelo:
    viatico = ViaticoModelo(
        modalidad=Modalidad.LEGALIZACION_DIRECTA,
        etapa=Etapa.LEGALIZACION,
        usuario_id=actor.id,
        motivo_viaje=datos.motivo_viaje,
        recursos_propios=datos.recursos_propios,
        created_by=actor.id,
        updated_by=actor.id,
        **_instantanea_colaborador(session, actor),
    )
    session.add(viatico)
    session.flush()
    _crear_evento_inicial(session, viatico, actor)
    session.commit()
    session.refresh(viatico)
    return viatico


def crear(session: Session, datos: ViaticoCrear, actor: Usuario) -> ViaticoModelo:
    if datos.modalidad == Modalidad.CON_SOLICITUD:
        return _crear_con_solicitud(session, datos, actor)
    return _crear_legalizacion_directa(session, datos, actor)


# --- lectura individual (el alcance por dueño lo aplica RLS, S2-03; ADR-007) -------------------


def obtener(session: Session, viatico_id: uuid.UUID, *, bloquear: bool = False) -> ViaticoModelo:
    """Sin filtrar por dueño a propósito: RLS ya excluye lo ajeno para un VIAJERO (defensa en
    profundidad, docs/database-design.md §6); sin fila visible, es un 404 como cualquier ajeno."""
    consulta = select(ViaticoModelo).where(
        ViaticoModelo.id == viatico_id, ViaticoModelo.deleted_at.is_(None)
    )
    if bloquear:
        consulta = consulta.with_for_update()
    viatico = session.scalar(consulta)
    if viatico is None:
        raise NoEncontrado()
    return viatico


def _saldo(session: Session, viatico_id: uuid.UUID) -> tuple[Decimal, Decimal]:
    fila = session.execute(
        text("SELECT total_gastos, saldo FROM v_viatico_saldos WHERE viatico_id = :id"),
        {"id": viatico_id},
    ).first()
    if fila is None:  # el viático no tiene fila en la vista (eliminado lógicamente)
        return Decimal("0"), Decimal("0")
    return fila.total_gastos, fila.saldo


def detalle(session: Session, viatico: ViaticoModelo, actor: Usuario) -> ViaticoDetalle:
    usuario = session.get(Usuario, viatico.usuario_id)
    if usuario is None:
        raise RuntimeError(f"El usuario {viatico.usuario_id} no existe (FK RESTRICT)")
    total_gastos, saldo = _saldo(session, viatico.id)

    solicitud: SolicitudSalida | None = None
    if viatico.modalidad == Modalidad.CON_SOLICITUD:
        if viatico.proyecto_id is not None:
            proyecto = session.get(Proyecto, viatico.proyecto_id)
            if proyecto is None:
                raise RuntimeError(f"El proyecto {viatico.proyecto_id} no existe (FK RESTRICT)")
            proyecto_ref = ProyectoRefSalida(
                id=proyecto.id, nombre=proyecto.nombre, en_catalogo=True
            )
        else:
            proyecto_ref = ProyectoRefSalida(
                id=None, nombre=viatico.proyecto_otro or "", en_catalogo=False
            )
        trayectos = session.scalars(
            select(ViaticoTrayectoModelo)
            .where(ViaticoTrayectoModelo.viatico_id == viatico.id)
            .order_by(ViaticoTrayectoModelo.orden)
        ).all()
        visibles = _referencias_archivos(
            session, [viatico.firma_archivo_id, viatico.formato_adjunto_id]
        )
        solicitud = SolicitudSalida(
            proyecto=proyecto_ref,
            lider_proyecto=viatico.lider_proyecto or "",
            empresa=viatico.empresa,
            requiere_tiquete=viatico.requiere_tiquete,
            requiere_gastos_viaje=viatico.requiere_gastos_viaje,
            presupuesto_solicitado=viatico.presupuesto_solicitado,
            comentarios=viatico.comentarios,
            firma=_ref_archivo(viatico.firma_archivo_id, visibles),
            formato_adjunto=_ref_archivo(viatico.formato_adjunto_id, visibles),
            trayectos=[TrayectoSalida.model_validate(t) for t in trayectos],
        )

    eventos = session.scalars(
        select(ViaticoEvento)
        .where(ViaticoEvento.viatico_id == viatico.id)
        .order_by(ViaticoEvento.created_at, ViaticoEvento.id)
    ).all()

    return ViaticoDetalle(
        id=viatico.id,
        folio=viatico.folio,
        modalidad=viatico.modalidad,
        etapa=viatico.etapa,
        estado=viatico.estado,
        estado_financiero=viatico.estado_financiero,
        devuelta_at=viatico.devuelta_at,
        usuario=Referencia(id=usuario.id, nombre=usuario.nombre_completo),
        colaborador=ColaboradorSalida(
            nombre=viatico.colaborador_nombre,
            cargo=viatico.colaborador_cargo,
            celula=viatico.colaborador_celula,
            es_prestador_servicios=viatico.colaborador_es_prestador,
        ),
        motivo_viaje=viatico.motivo_viaje,
        solicitud=solicitud,
        fecha_legalizacion=viatico.fecha_legalizacion,
        recursos_propios=viatico.recursos_propios,
        valor_asignado=viatico.valor_asignado,
        valor_transferido=viatico.valor_transferido,
        total_gastos=total_gastos,
        saldo=saldo,
        acciones_permitidas=acciones.calcular(viatico, actor),
        eventos=[EventoSalida.model_validate(e) for e in eventos],
        created_at=viatico.created_at,
        updated_at=viatico.updated_at,
    )


# =================================================================================================
# GET /viaticos (listado paginado con filtros, S2-05)
# =================================================================================================


def _construir_filtro_listado(
    *,
    etapa: Etapa | None,
    estado: EstadoOperativo | None,
    estado_financiero: EstadoFinanciero | None,
    modalidad: Modalidad | None,
    proyecto_id: uuid.UUID | None,
    usuario_id: uuid.UUID | None,
    desde: date | None,
    hasta: date | None,
    q: str | None,
) -> Select[tuple[ViaticoModelo]]:
    consulta = select(ViaticoModelo).where(ViaticoModelo.deleted_at.is_(None))
    filtros: dict[str, Any] = {
        "etapa": etapa,
        "estado": estado,
        "estado_financiero": estado_financiero,
        "modalidad": modalidad,
        "proyecto_id": proyecto_id,
        "usuario_id": usuario_id,
    }
    for campo, valor in filtros.items():
        if valor is not None:
            consulta = consulta.where(getattr(ViaticoModelo, campo) == valor)
    if desde is not None:
        consulta = consulta.where(ViaticoModelo.fecha_legalizacion >= desde)
    if hasta is not None:
        consulta = consulta.where(ViaticoModelo.fecha_legalizacion <= hasta)
    if q and q.strip():
        patron = patron_busqueda(q.strip())
        consulta = consulta.where(
            (ViaticoModelo.folio.ilike(patron)) | (ViaticoModelo.motivo_viaje.ilike(patron))
        )
    return consulta.order_by(ViaticoModelo.created_at.desc(), ViaticoModelo.id.desc())


def _saldos_de(
    session: Session, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
    if not ids:
        return {}
    filas = session.execute(
        text(
            "SELECT viatico_id, total_gastos, saldo FROM v_viatico_saldos "
            "WHERE viatico_id = ANY(:ids)"
        ),
        {"ids": list(ids)},
    ).all()
    return {fila.viatico_id: (fila.total_gastos, fila.saldo) for fila in filas}


def listar(
    session: Session,
    actor: Usuario,
    parametros: ParametrosPagina,
    *,
    etapa: Etapa | None = None,
    estado: EstadoOperativo | None = None,
    estado_financiero: EstadoFinanciero | None = None,
    modalidad: Modalidad | None = None,
    proyecto_id: uuid.UUID | None = None,
    usuario_id: uuid.UUID | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    q: str | None = None,
) -> tuple[list[ViaticoResumen], int]:
    """RLS ya limita lo que ve un VIAJERO (solo lo propio); los filtros son los mismos para
    cualquier rol, sin duplicar esa restricción aquí (docs/database-design.md §6)."""
    consulta = _construir_filtro_listado(
        etapa=etapa,
        estado=estado,
        estado_financiero=estado_financiero,
        modalidad=modalidad,
        proyecto_id=proyecto_id,
        usuario_id=usuario_id,
        desde=desde,
        hasta=hasta,
        q=q,
    )
    filas, total = paginar(session, consulta, parametros)
    ids = [v.id for v in filas]
    saldos = _saldos_de(session, ids)
    usuario_ids = {v.usuario_id for v in filas}
    usuarios = (
        {u.id: u for u in session.scalars(select(Usuario).where(Usuario.id.in_(usuario_ids)))}
        if usuario_ids
        else {}
    )

    items: list[ViaticoResumen] = []
    for viatico in filas:
        total_gastos, saldo = saldos.get(viatico.id, (Decimal("0"), Decimal("0")))
        propietario = usuarios.get(viatico.usuario_id)
        nombre_propietario = propietario.nombre_completo if propietario is not None else ""
        items.append(
            ViaticoResumen(
                id=viatico.id,
                folio=viatico.folio,
                modalidad=viatico.modalidad,
                etapa=viatico.etapa,
                estado=viatico.estado,
                estado_financiero=viatico.estado_financiero,
                usuario=Referencia(id=viatico.usuario_id, nombre=nombre_propietario),
                motivo_viaje=viatico.motivo_viaje,
                fecha_legalizacion=viatico.fecha_legalizacion,
                recursos_propios=viatico.recursos_propios,
                valor_asignado=viatico.valor_asignado,
                valor_transferido=viatico.valor_transferido,
                presupuesto_solicitado=viatico.presupuesto_solicitado,
                total_gastos=total_gastos,
                saldo=saldo,
                acciones_permitidas=acciones.calcular(viatico, actor),
                created_at=viatico.created_at,
            )
        )
    return items, total


# =================================================================================================
# PATCH /viaticos/{id} y DELETE /viaticos/{id} (S2-05: dueño o SUPERADMIN, PENDIENTE/PENDIENTE)
# =================================================================================================


def exigir_dueno_o_superadmin(viatico: ViaticoModelo, actor: Usuario) -> None:
    if viatico.usuario_id != actor.id and actor.rol != Rol.SUPERADMIN:
        raise SinPermiso()


def _exigir_editable(viatico: ViaticoModelo) -> None:
    if (
        viatico.estado != EstadoOperativo.PENDIENTE
        or viatico.estado_financiero != EstadoFinanciero.PENDIENTE
    ):
        raise NoEditable()


def _trayectos_actuales_como_entrada(
    session: Session, viatico_id: uuid.UUID
) -> list[TrayectoEntradaSchema]:
    filas = session.scalars(
        select(ViaticoTrayectoModelo)
        .where(ViaticoTrayectoModelo.viatico_id == viatico_id)
        .order_by(ViaticoTrayectoModelo.orden)
    ).all()
    return [
        TrayectoEntradaSchema(
            orden=t.orden,
            ciudad_origen=t.ciudad_origen,
            ciudad_destino=t.ciudad_destino,
            fecha_ida=t.fecha_ida,
            fecha_regreso=t.fecha_regreso,
            requiere_hospedaje=t.requiere_hospedaje,
            dias_estadia=t.dias_estadia,
        )
        for t in filas
    ]


_CAMPOS_DISPARAN_RECALCULO = frozenset(
    {"proyecto_id", "proyecto_otro", "requiere_gastos_viaje", "trayectos"}
)
_CAMPOS_SOLICITUD = frozenset(
    {
        "motivo_viaje",
        "proyecto_id",
        "proyecto_otro",
        "lider_proyecto",
        "empresa",
        "requiere_tiquete",
        "requiere_gastos_viaje",
        "comentarios",
        "trayectos",
        "firma_archivo_id",
        "formato_adjunto_id",
    }
)
_ADJUNTOS_SOLICITUD = (
    ("firma_archivo_id", PropositoArchivo.FIRMA),
    ("formato_adjunto_id", PropositoArchivo.FORMATO_PRESTADOR),
)


def _editar_solicitud(
    session: Session, viatico: ViaticoModelo, cambios: dict[str, Any], actor: Usuario
) -> dict[str, object]:
    no_permitidos = set(cambios) - _CAMPOS_SOLICITUD
    if no_permitidos:
        campo = sorted(no_permitidos)[0]
        raise ValorNoPermitido(
            errors=error_de_campo(campo, f"'{campo}' no se puede editar en la etapa SOLICITUD")
        )

    tiene_proyecto_id = "proyecto_id" in cambios
    tiene_proyecto_otro = "proyecto_otro" in cambios
    nuevo_proyecto_id = cambios["proyecto_id"] if tiene_proyecto_id else viatico.proyecto_id
    nuevo_proyecto_otro = cambios["proyecto_otro"] if tiene_proyecto_otro else viatico.proyecto_otro
    if tiene_proyecto_id and not tiene_proyecto_otro and nuevo_proyecto_id is not None:
        nuevo_proyecto_otro = None  # enviar uno borra el otro (RN-16, ADR-031)
    elif tiene_proyecto_otro and not tiene_proyecto_id and nuevo_proyecto_otro is not None:
        nuevo_proyecto_id = None
    # Si llegan los dos en la misma petición, no se "borra" ninguno: se valida tal cual (ambiguo
    # si los dos no son nulos, requerido si los dos lo son).
    validar_proyecto_exclusivo(nuevo_proyecto_id, nuevo_proyecto_otro)
    if nuevo_proyecto_id is not None:
        obtener_proyecto_activo(session, nuevo_proyecto_id)

    nuevo_requiere_tiquete = cambios.get("requiere_tiquete", viatico.requiere_tiquete)
    if nuevo_requiere_tiquete and actor.fecha_nacimiento is None:
        raise FechaNacimientoRequerida()
    nuevo_requiere_gastos_viaje = cambios.get(
        "requiere_gastos_viaje", viatico.requiere_gastos_viaje
    )
    # Adjuntos (RN-32, RN-33): solo se validan los que cambian; `null` quita el adjunto.
    nuevos_adjuntos: dict[str, uuid.UUID | None] = {}
    for campo, proposito in _ADJUNTOS_SOLICITUD:
        if campo in cambios and cambios[campo] != getattr(viatico, campo):
            if cambios[campo] is not None:
                archivos.validar_adjunto(session, cambios[campo], actor, proposito, campo)
            nuevos_adjuntos[campo] = cambios[campo]

    antes: dict[str, object] = {}
    despues: dict[str, object] = {}
    for campo in ("motivo_viaje", "lider_proyecto", "empresa", "comentarios"):
        if campo in cambios and cambios[campo] != getattr(viatico, campo):
            antes[campo] = getattr(viatico, campo)
            despues[campo] = cambios[campo]
    if nuevo_proyecto_id != viatico.proyecto_id or nuevo_proyecto_otro != viatico.proyecto_otro:
        antes["proyecto_id"], despues["proyecto_id"] = viatico.proyecto_id, nuevo_proyecto_id
        antes["proyecto_otro"], despues["proyecto_otro"] = (
            viatico.proyecto_otro,
            nuevo_proyecto_otro,
        )
    if "requiere_tiquete" in cambios and nuevo_requiere_tiquete != viatico.requiere_tiquete:
        antes["requiere_tiquete"], despues["requiere_tiquete"] = (
            viatico.requiere_tiquete,
            nuevo_requiere_tiquete,
        )
    if (
        "requiere_gastos_viaje" in cambios
        and nuevo_requiere_gastos_viaje != viatico.requiere_gastos_viaje
    ):
        antes["requiere_gastos_viaje"], despues["requiere_gastos_viaje"] = (
            viatico.requiere_gastos_viaje,
            nuevo_requiere_gastos_viaje,
        )

    for campo, nuevo in nuevos_adjuntos.items():
        antes[campo], despues[campo] = getattr(viatico, campo), nuevo
        setattr(viatico, campo, nuevo)

    if _CAMPOS_DISPARAN_RECALCULO & set(cambios):
        # `model_dump()` ya convirtió los trayectos nuevos en dicts; se reconstruyen los esquemas.
        trayectos_entrada = (
            [TrayectoEntradaSchema(**t) for t in cambios["trayectos"]]
            if "trayectos" in cambios
            else _trayectos_actuales_como_entrada(session, viatico.id)
        )
        resultado = calcular_presupuesto_bd(
            session,
            proyecto_id=nuevo_proyecto_id,
            proyecto_otro=nuevo_proyecto_otro,
            es_prestador_servicios=actor.es_prestador_servicios,
            requiere_gastos_viaje=nuevo_requiere_gastos_viaje,
            trayectos=trayectos_entrada,
        )
        session.execute(
            delete(ViaticoTrayectoModelo).where(ViaticoTrayectoModelo.viatico_id == viatico.id)
        )
        for trayecto in resultado.trayectos:
            session.add(
                ViaticoTrayectoModelo(
                    viatico_id=viatico.id,
                    orden=trayecto.orden,
                    ciudad_origen=trayecto.ciudad_origen,
                    ciudad_destino=trayecto.ciudad_destino,
                    fecha_ida=trayecto.fecha_ida,
                    fecha_regreso=trayecto.fecha_regreso,
                    requiere_hospedaje=trayecto.requiere_hospedaje,
                    dias_estadia=trayecto.dias_estadia,
                    tarifa_id=trayecto.tarifa_id,
                    vr_alimentacion=trayecto.vr_alimentacion,
                    otros_gastos=trayecto.otros_gastos,
                    trans_interno=trayecto.trans_interno,
                    transporte_aeropuerto=trayecto.transporte_aeropuerto,
                    transporte_intermunicipal=trayecto.transporte_intermunicipal,
                    subtotal_estadia=trayecto.subtotal_estadia,
                )
            )
        if resultado.presupuesto_solicitado != viatico.presupuesto_solicitado:
            antes["presupuesto_solicitado"] = viatico.presupuesto_solicitado
            despues["presupuesto_solicitado"] = resultado.presupuesto_solicitado
        viatico.presupuesto_solicitado = resultado.presupuesto_solicitado

    for campo in ("motivo_viaje", "lider_proyecto", "empresa", "comentarios"):
        if campo in cambios:
            setattr(viatico, campo, cambios[campo])
    viatico.proyecto_id = nuevo_proyecto_id
    viatico.proyecto_otro = nuevo_proyecto_otro
    viatico.requiere_tiquete = nuevo_requiere_tiquete
    viatico.requiere_gastos_viaje = nuevo_requiere_gastos_viaje
    return {"antes": antes, "despues": despues} if despues else {}


def _editar_legalizacion(viatico: ViaticoModelo, cambios: dict[str, Any]) -> dict[str, object]:
    permitidos = {"motivo_viaje", "comentarios"}
    if viatico.modalidad == Modalidad.LEGALIZACION_DIRECTA:
        permitidos.add("recursos_propios")
    no_permitidos = set(cambios) - permitidos
    if no_permitidos:
        campo = sorted(no_permitidos)[0]
        raise ValorNoPermitido(
            errors=error_de_campo(campo, f"'{campo}' no se puede editar en esta modalidad o etapa")
        )

    datos_recursos: dict[str, object] = {}
    if "recursos_propios" in cambios and cambios["recursos_propios"] != viatico.recursos_propios:
        datos_recursos = {
            "antes": {"recursos_propios": viatico.recursos_propios},
            "despues": {"recursos_propios": cambios["recursos_propios"]},
        }
    for campo in ("motivo_viaje", "comentarios", "recursos_propios"):
        if campo in cambios:
            setattr(viatico, campo, cambios[campo])
    return datos_recursos


def editar(
    session: Session, viatico_id: uuid.UUID, datos: ViaticoEditar, actor: Usuario
) -> ViaticoModelo:
    viatico = obtener(session, viatico_id, bloquear=True)
    exigir_dueno_o_superadmin(viatico, actor)
    _exigir_editable(viatico)
    cambios = datos.model_dump(exclude_unset=True)
    if not cambios:
        return viatico

    if viatico.etapa == Etapa.SOLICITUD:
        datos_evento = _editar_solicitud(session, viatico, cambios, actor)
        accion_evento = AccionViatico.EDITAR_SOLICITUD
    else:
        datos_evento = _editar_legalizacion(viatico, cambios)
        accion_evento = AccionViatico.CAMBIAR_RECURSOS_PROPIOS

    viatico.updated_by = actor.id
    session.flush()
    if datos_evento:
        session.add(
            ViaticoEvento(
                viatico_id=viatico.id,
                etapa=viatico.etapa,
                accion=accion_evento,
                usuario_id=actor.id,
                datos=serializable(datos_evento),
            )
        )
    session.commit()
    session.refresh(viatico)
    return viatico


def eliminar(session: Session, viatico_id: uuid.UUID, actor: Usuario, ctx: Contexto) -> None:
    viatico = obtener(session, viatico_id, bloquear=True)
    exigir_dueno_o_superadmin(viatico, actor)
    _exigir_editable(viatico)

    ahora = datetime.now(UTC)
    viatico.deleted_at = ahora
    viatico.updated_by = actor.id
    session.execute(
        update(Gasto)
        .where(Gasto.viatico_id == viatico.id, Gasto.deleted_at.is_(None))
        .values(deleted_at=ahora, updated_by=actor.id)
    )
    session.add(
        ViaticoEvento(
            viatico_id=viatico.id,
            etapa=viatico.etapa,
            accion=AccionViatico.ELIMINAR,
            usuario_id=actor.id,
        )
    )
    registrar(
        session,
        AccionAuditoria.VIATICO_ELIMINAR,
        ENTIDAD,
        viatico.id,
        usuario_id=actor.id,
        datos={"folio": viatico.folio},
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )
    session.commit()


def serializable(datos: dict[str, object]) -> dict[str, object]:
    """`JSONB` no admite `Decimal`/`UUID`/fechas: los vuelve texto antes de guardarlos."""

    def _valor(v: object) -> object:
        if isinstance(v, dict):
            return {k: _valor(x) for k, x in v.items()}
        if isinstance(v, Decimal):
            # Todo el dinero es NUMERIC(14,2): siempre con 2 decimales, venga de la BD o no.
            return format(v.quantize(Decimal("0.01")), "f")
        if isinstance(v, uuid.UUID | date):
            return str(v)
        return v

    return {k: _valor(v) for k, v in datos.items()}


# =================================================================================================
# Máquina de estados operativa (S2-05): transicionar(), aprobar, rechazar, devolver,
# habilitar_legalizacion. RN-20, RN-27, RN-28, RN-06/RN-21.
# =================================================================================================


def _exigir_no_autoaprobacion(
    session: Session,
    viatico: ViaticoModelo,
    actor: Usuario,
    ctx: Contexto,
    *,
    accion: AccionViatico | None = None,
    detalle: str | None = None,
) -> None:
    """RN-27: nadie aprueba, rechaza, devuelve, gestiona tiquetes, valida financieramente ni
    liquida su propio viático, salvo SUPERADMIN (auditado)."""
    if viatico.usuario_id != actor.id:
        return
    if actor.rol != Rol.SUPERADMIN:
        raise AutoaprobacionNoPermitida(detail=detalle)
    datos: dict[str, object] = {"folio": viatico.folio}
    if accion is not None:
        datos["accion"] = accion.value
    registrar(
        session,
        AccionAuditoria.AUTOAPROBACION_SUPERADMIN,
        ENTIDAD,
        viatico.id,
        usuario_id=actor.id,
        datos=datos,
        ip=ctx.ip,
        user_agent=ctx.user_agent,
    )


def _exigir_comentario(comentario: str | None) -> str:
    if comentario is None or not comentario.strip():
        raise ComentarioRequerido()
    return comentario.strip()


def _exigir_gastos_con_comprobante(session: Session, viatico: ViaticoModelo) -> None:
    """RN-06/RN-21: para aprobar la legalización, al menos un gasto y todos con comprobante."""
    gastos = session.scalars(
        select(Gasto).where(Gasto.viatico_id == viatico.id, Gasto.deleted_at.is_(None))
    ).all()
    if not gastos:
        raise ComprobanteFaltante(detail="El viático no tiene gastos registrados")
    sin_comprobante = [g for g in gastos if g.soporte_id is None and g.archivo_id is None]
    if sin_comprobante:
        raise ComprobanteFaltante(
            errors=[
                error_de_campo(
                    f"gastos[{g.id}]",
                    "El gasto no tiene soporte ni archivo",
                    "COMPROBANTE_FALTANTE",
                )[0]
                for g in sin_comprobante
            ]
        )


_CAMPO_ESTADO = {
    DimensionEvento.OPERATIVO: "estado",
    DimensionEvento.ETAPA: "estado",
    DimensionEvento.FINANCIERO: "estado_financiero",
}


def _exigir_adjuntos_solicitud(
    session: Session, viatico: ViaticoModelo
) -> dict[str, object] | None:
    """Aprobar una solicitud exige, además de lo que ya valida su creación:

    - **RN-33:** si el solicitante era prestador de servicios (instantánea RN-17) y el proyecto del
      catálogo tiene `exige_formato_prestador`, el formato diligenciado. Un proyecto escrito con
      "Otro" nunca lo exige.
    - **RN-32:** la firma del solicitante: la del viático o, si no tiene, la guardada en el perfil
      del dueño, que se copia al viático (así el PDF y el historial no cambian si el perfil sí).
    """
    if viatico.colaborador_es_prestador and viatico.proyecto_id is not None:
        proyecto = session.get(Proyecto, viatico.proyecto_id)
        if (
            proyecto is not None
            and proyecto.exige_formato_prestador
            and viatico.formato_adjunto_id is None
        ):
            raise FormatoPrestadorRequerido(
                detail=f"El proyecto {proyecto.nombre} exige el formato diligenciado del prestador",
                errors=error_de_campo(
                    "formato_adjunto_id",
                    "Adjunte el formato de prestador (PDF o Excel)",
                    "FORMATO_PRESTADOR_REQUERIDO",
                ),
            )
    if viatico.firma_archivo_id is not None:
        return None
    dueno = session.get(Usuario, viatico.usuario_id)
    if dueno is None or dueno.firma_archivo_id is None:
        raise FirmaRequerida(
            errors=error_de_campo(
                "firma_archivo_id", "Falta la firma del solicitante", "FIRMA_REQUERIDA"
            )
        )
    viatico.firma_archivo_id = dueno.firma_archivo_id
    return {"firma_desde_perfil": dueno.firma_archivo_id}


def transicionar(
    session: Session,
    viatico_id: uuid.UUID,
    actor: Usuario,
    *,
    accion: AccionViatico,
    dimension: DimensionEvento | None,
    comentario: str | None,
    mutar: Callable[[ViaticoModelo], dict[str, object] | None],
    registrar_estados: bool = True,
    eventos_adicionales: Callable[[ViaticoModelo], list[ViaticoEvento]] | None = None,
) -> ViaticoModelo:
    """Núcleo común de toda transición: bloquea la fila (`FOR UPDATE`), aplica `mutar` (que valida
    y cambia el estado) y registra el evento, todo en la misma transacción.

    El estado anterior/nuevo del evento es el de la dimensión (`estado_financiero` para
    `FINANCIERO`, `estado` para las demás); `registrar_estados=False` los omite (acciones que no
    cambian ningún estado: tiquetes, valor asignado). `eventos_adicionales` agrega otros eventos
    en la misma transacción (p. ej. `LIQUIDAR` junto con el cambio de estado financiero)."""
    viatico = obtener(session, viatico_id, bloquear=True)
    campo = _CAMPO_ESTADO[dimension] if registrar_estados and dimension is not None else None
    estado_anterior = getattr(viatico, campo) if campo else None
    datos = mutar(viatico)
    viatico.updated_by = actor.id
    evento = ViaticoEvento(
        viatico_id=viatico.id,
        etapa=viatico.etapa,
        accion=accion,
        dimension=dimension,
        estado_anterior=estado_anterior,
        estado_nuevo=getattr(viatico, campo) if campo else None,
        comentario=comentario,
        usuario_id=actor.id,
    )
    # `datos` es JSONB sin `none_as_null`: pasar `None` explícito guardaría un JSON `null` (no
    # SQL `NULL`) y violaría `ck_viatico_eventos__datos_objeto`. Se omite el atributo si no hay
    # nada que guardar, igual que hace `_crear_evento_inicial`.
    if datos:
        evento.datos = serializable(datos)
    session.add(evento)
    if eventos_adicionales is not None:
        session.add_all(eventos_adicionales(viatico))
    session.commit()
    session.refresh(viatico)
    return viatico


def aprobar(
    session: Session, viatico_id: uuid.UUID, actor: Usuario, comentario: str | None, ctx: Contexto
) -> ViaticoModelo:
    def mutar(viatico: ViaticoModelo) -> dict[str, object] | None:
        _exigir_no_autoaprobacion(session, viatico, actor, ctx)
        if viatico.estado != EstadoOperativo.PENDIENTE:
            raise TransicionInvalida(detail="El viático no está pendiente de aprobación")
        datos: dict[str, object] | None = None
        if viatico.etapa == Etapa.LEGALIZACION:
            _exigir_gastos_con_comprobante(session, viatico)
        else:
            datos = _exigir_adjuntos_solicitud(session, viatico)
        viatico.estado = EstadoOperativo.APROBADO
        viatico.aprobada_at = datetime.now(UTC)
        if comentario:
            viatico.observaciones = comentario
        return datos

    return transicionar(
        session,
        viatico_id,
        actor,
        accion=AccionViatico.APROBAR,
        dimension=DimensionEvento.OPERATIVO,
        comentario=comentario,
        mutar=mutar,
    )


def rechazar(
    session: Session, viatico_id: uuid.UUID, actor: Usuario, comentario: str | None, ctx: Contexto
) -> ViaticoModelo:
    comentario_valido = _exigir_comentario(comentario)

    def mutar(viatico: ViaticoModelo) -> None:
        _exigir_no_autoaprobacion(session, viatico, actor, ctx)
        if viatico.estado != EstadoOperativo.PENDIENTE:
            raise TransicionInvalida(detail="El viático no está pendiente de revisión")
        viatico.estado = EstadoOperativo.RECHAZADO
        viatico.observaciones = comentario_valido
        return None

    return transicionar(
        session,
        viatico_id,
        actor,
        accion=AccionViatico.RECHAZAR,
        dimension=DimensionEvento.OPERATIVO,
        comentario=comentario_valido,
        mutar=mutar,
    )


_FINANCIERO_BLOQUEA_DEVOLVER = frozenset({EstadoFinanciero.PAGADO, EstadoFinanciero.PROCESADO})


def devolver(
    session: Session, viatico_id: uuid.UUID, actor: Usuario, comentario: str | None, ctx: Contexto
) -> ViaticoModelo:
    comentario_valido = _exigir_comentario(comentario)

    def mutar(viatico: ViaticoModelo) -> None:
        _exigir_no_autoaprobacion(session, viatico, actor, ctx)
        if viatico.estado not in (EstadoOperativo.PENDIENTE, EstadoOperativo.APROBADO):
            raise TransicionInvalida(detail="El viático no se puede devolver en este estado")
        if viatico.estado_financiero in _FINANCIERO_BLOQUEA_DEVOLVER:
            raise TransicionInvalida(detail="No se puede devolver un viático ya pagado o procesado")
        viatico.estado = EstadoOperativo.PENDIENTE
        viatico.devuelta_at = datetime.now(UTC)
        viatico.observaciones = comentario_valido
        return None

    return transicionar(
        session,
        viatico_id,
        actor,
        accion=AccionViatico.DEVOLVER,
        dimension=DimensionEvento.OPERATIVO,
        comentario=comentario_valido,
        mutar=mutar,
    )


def habilitar_legalizacion(
    session: Session, viatico_id: uuid.UUID, actor: Usuario
) -> ViaticoModelo:
    def mutar(viatico: ViaticoModelo) -> None:
        exigir_dueno_o_superadmin(viatico, actor)
        if viatico.modalidad != Modalidad.CON_SOLICITUD or viatico.etapa != Etapa.SOLICITUD:
            raise LegalizacionNoHabilitable(detail="Solo aplica a una solicitud sin habilitar")
        if viatico.estado != EstadoOperativo.APROBADO:
            raise LegalizacionNoHabilitable(detail="La solicitud todavía no está aprobada")
        if (
            viatico.requiere_gastos_viaje
            and viatico.estado_financiero != EstadoFinanciero.TRANSFERIDO
        ):
            raise LegalizacionNoHabilitable(
                detail="Falta transferir los viáticos antes de habilitar la legalización"
            )
        viatico.etapa = Etapa.LEGALIZACION
        viatico.estado = EstadoOperativo.PENDIENTE
        viatico.legalizacion_habilitada_at = datetime.now(UTC)
        return None

    return transicionar(
        session,
        viatico_id,
        actor,
        accion=AccionViatico.HABILITAR_LEGALIZACION,
        dimension=DimensionEvento.ETAPA,
        comentario=None,
        mutar=mutar,
    )


# =================================================================================================
# Tiquetes y dinero (S2-07): gestionar-tiquetes (ADMIN), valor-asignado y estado-financiero
# (FINANCIERO). RN-03, RN-14, RN-19, RN-22, RN-27, S-03, S-10.
# =================================================================================================

_ORDEN_FINANCIERO = {
    EstadoFinanciero.PENDIENTE: 0,
    EstadoFinanciero.TRANSFERIDO: 1,
    EstadoFinanciero.PAGADO: 2,
    EstadoFinanciero.PROCESADO: 3,
}
_LIQUIDADO = frozenset({EstadoFinanciero.PAGADO, EstadoFinanciero.PROCESADO})


def gestionar_tiquetes(
    session: Session,
    viatico_id: uuid.UUID,
    actor: Usuario,
    comentario: str | None,
    referencia: str | None,
    ctx: Contexto,
) -> ViaticoModelo:
    """S-10: ADMIN registra la emisión de los tiquetes como evento, sin estado propio. Se puede
    repetir (reexpedición, cambios de vuelo): cada registro queda en el historial."""

    def mutar(viatico: ViaticoModelo) -> dict[str, object] | None:
        _exigir_no_autoaprobacion(
            session,
            viatico,
            actor,
            ctx,
            accion=AccionViatico.GESTIONAR_TIQUETES,
            detalle="No puede gestionar los tiquetes de su propio viático",
        )
        if viatico.modalidad != Modalidad.CON_SOLICITUD or not viatico.requiere_tiquete:
            raise TransicionInvalida(detail="La solicitud no requiere tiquete")
        if viatico.etapa != Etapa.SOLICITUD or viatico.estado != EstadoOperativo.APROBADO:
            raise TransicionInvalida(detail="Los tiquetes se gestionan con la solicitud aprobada")
        return {"referencia": referencia} if referencia else None

    return transicionar(
        session,
        viatico_id,
        actor,
        accion=AccionViatico.GESTIONAR_TIQUETES,
        dimension=DimensionEvento.OPERATIVO,
        comentario=comentario or None,
        mutar=mutar,
        registrar_estados=False,
    )


def registrar_valor_asignado(
    session: Session,
    viatico_id: uuid.UUID,
    actor: Usuario,
    valor: Decimal,
    comentario: str | None,
    ctx: Contexto,
) -> ViaticoModelo:
    """RN-19: solo FINANCIERO/SUPERADMIN, con el viático `APROBADO`, sin recursos propios (RN-14:
    el transferido sería 0) y sin liquidar. `valor_transferido` lo recalcula la BD."""

    def mutar(viatico: ViaticoModelo) -> dict[str, object]:
        _exigir_no_autoaprobacion(
            session,
            viatico,
            actor,
            ctx,
            accion=AccionViatico.EDITAR_VALOR_ASIGNADO,
            detalle="No puede registrar el valor asignado de su propio viático",
        )
        if viatico.recursos_propios:
            raise TransicionInvalida(
                detail="Con recursos propios no hay valor asignado: el transferido es 0 (RN-14)"
            )
        if viatico.estado != EstadoOperativo.APROBADO:
            raise TransicionInvalida(detail="El viático debe estar APROBADO")
        if viatico.estado_financiero in _LIQUIDADO:
            raise TransicionInvalida(detail="El viático ya está liquidado")
        anterior = viatico.valor_asignado
        viatico.valor_asignado = valor
        return {
            "antes": {"valor_asignado": anterior},
            "despues": {"valor_asignado": valor},
            "presupuesto_solicitado": viatico.presupuesto_solicitado,
        }

    return transicionar(
        session,
        viatico_id,
        actor,
        accion=AccionViatico.EDITAR_VALOR_ASIGNADO,
        dimension=DimensionEvento.FINANCIERO,
        comentario=comentario or None,
        mutar=mutar,
        registrar_estados=False,
    )


def sentido_liquidacion(saldo: Decimal) -> TipoLiquidacion:
    """RN-02: `saldo > 0` el viajero reintegra; `saldo < 0` la empresa reembolsa."""
    if saldo > 0:
        return TipoLiquidacion.REINTEGRO
    if saldo < 0:
        return TipoLiquidacion.REEMBOLSO
    return TipoLiquidacion.SALDADO


def cambiar_estado_financiero(
    session: Session,
    viatico_id: uuid.UUID,
    actor: Usuario,
    destino: EstadoFinanciero,
    comentario: str | None,
    ctx: Contexto,
) -> ViaticoModelo:
    """Solo hacia adelante (`PENDIENTE → TRANSFERIDO → PAGADO → PROCESADO`; S-03 permite saltar
    pasos, p. ej. recursos propios: `PENDIENTE → PAGADO`). Siempre con el viático `APROBADO`.
    `TRANSFERIDO` exige un valor asignado > 0 y sin recursos propios; `PAGADO`/`PROCESADO`
    exigen RN-03 (etapa `LEGALIZACION`, gastos con comprobante). Al liquidar (primera llegada a
    `PAGADO`/`PROCESADO`) se registra además `LIQUIDAR` con el saldo y su sentido (RN-10)."""
    anterior: dict[str, EstadoFinanciero] = {}

    def mutar(viatico: ViaticoModelo) -> None:
        _exigir_no_autoaprobacion(
            session,
            viatico,
            actor,
            ctx,
            accion=AccionViatico.CAMBIAR_ESTADO_FINANCIERO,
            detalle="No puede validar financieramente ni liquidar su propio viático",
        )
        actual = EstadoFinanciero(viatico.estado_financiero)
        if _ORDEN_FINANCIERO[destino] <= _ORDEN_FINANCIERO[actual]:
            raise TransicionInvalida(detail=f"No se puede pasar de {actual} a {destino}")
        if viatico.estado != EstadoOperativo.APROBADO:
            raise TransicionInvalida(detail="El viático debe estar APROBADO")
        if destino == EstadoFinanciero.TRANSFERIDO:
            if viatico.recursos_propios:
                raise TransicionInvalida(detail="Con recursos propios no hay desembolso (RN-14)")
            if viatico.valor_asignado <= 0:
                raise TransicionInvalida(detail="Registre primero el valor asignado")
        else:
            if viatico.etapa != Etapa.LEGALIZACION:
                raise TransicionInvalida(detail="Solo se liquida en la etapa LEGALIZACION (RN-03)")
            _exigir_gastos_con_comprobante(session, viatico)
        anterior["estado"] = actual
        viatico.estado_financiero = destino
        viatico.estado_financiero_at = datetime.now(UTC)
        return None

    def liquidacion(viatico: ViaticoModelo) -> list[ViaticoEvento]:
        if destino not in _LIQUIDADO or anterior["estado"] in _LIQUIDADO:
            return []
        total_gastos, saldo = _saldo(session, viatico.id)
        return [
            ViaticoEvento(
                viatico_id=viatico.id,
                etapa=viatico.etapa,
                accion=AccionViatico.LIQUIDAR,
                dimension=DimensionEvento.FINANCIERO,
                comentario=comentario or None,
                usuario_id=actor.id,
                datos=serializable(
                    {
                        "valor_transferido": viatico.valor_transferido,
                        "total_gastos": total_gastos,
                        "saldo": saldo,
                        "sentido": sentido_liquidacion(saldo).value,
                    }
                ),
            )
        ]

    return transicionar(
        session,
        viatico_id,
        actor,
        accion=AccionViatico.CAMBIAR_ESTADO_FINANCIERO,
        dimension=DimensionEvento.FINANCIERO,
        comentario=comentario or None,
        mutar=mutar,
        eventos_adicionales=liquidacion,
    )
