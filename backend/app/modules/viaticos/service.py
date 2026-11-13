"""Reglas de `viaticos` (S2-04a, docs/api-design.md §5.4): cálculo tarifario, creación base y
lectura individual. La máquina de estados (aprobar, rechazar, habilitar legalización, RN-27…)
llega después (S2-05); este módulo cubre `POST /viaticos`, `POST /viaticos/calcular-presupuesto`
y `GET /viaticos/{id}`.
"""

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.enums import AccionViatico, Etapa, Modalidad
from app.core.errors import NoEncontrado, ValorNoPermitido, error_de_campo
from app.modules.auth.schemas import Referencia
from app.modules.cargos.models import Cargo
from app.modules.catalogos.models import Celula, Proyecto, TarifaViatico
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.calculo import (
    CiudadSinTarifaError,
    ResultadoPresupuesto,
    TarifaConceptos,
    TrayectoEntrada,
    calcular_presupuesto,
)
from app.modules.viaticos.errores import (
    FechaNacimientoRequerida,
    ProyectoAmbiguo,
    ProyectoRequerido,
)
from app.modules.viaticos.models import Viatico as ViaticoModelo
from app.modules.viaticos.models import ViaticoEvento
from app.modules.viaticos.models import ViaticoTrayecto as ViaticoTrayectoModelo
from app.modules.viaticos.schemas import (
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
)

# --- proyecto: exclusividad, existencia y la marca de "exige formato de prestador" (RN-16, RN-33) -


def validar_proyecto_exclusivo(proyecto_id: uuid.UUID | None, proyecto_otro: str | None) -> None:
    if proyecto_id is None and proyecto_otro is None:
        raise ProyectoRequerido()
    if proyecto_id is not None and proyecto_otro is not None:
        raise ProyectoAmbiguo()


def _obtener_proyecto_activo(session: Session, proyecto_id: uuid.UUID) -> Proyecto:
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
    return _obtener_proyecto_activo(session, proyecto_id).exige_formato_prestador


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
        _obtener_proyecto_activo(session, datos.proyecto_id)
    if datos.requiere_tiquete and actor.fecha_nacimiento is None:
        raise FechaNacimientoRequerida()

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


def obtener(session: Session, viatico_id: uuid.UUID) -> ViaticoModelo:
    """Sin filtrar por dueño a propósito: RLS ya excluye lo ajeno para un VIAJERO (defensa en
    profundidad, docs/database-design.md §6); sin fila visible, es un 404 como cualquier ajeno."""
    viatico = session.scalar(
        select(ViaticoModelo).where(
            ViaticoModelo.id == viatico_id, ViaticoModelo.deleted_at.is_(None)
        )
    )
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


def detalle(session: Session, viatico: ViaticoModelo) -> ViaticoDetalle:
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
        solicitud = SolicitudSalida(
            proyecto=proyecto_ref,
            lider_proyecto=viatico.lider_proyecto or "",
            empresa=viatico.empresa,
            requiere_tiquete=viatico.requiere_tiquete,
            requiere_gastos_viaje=viatico.requiere_gastos_viaje,
            presupuesto_solicitado=viatico.presupuesto_solicitado,
            comentarios=viatico.comentarios,
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
        acciones_permitidas=[],  # se completa en S2-05 (transicionar)
        eventos=[EventoSalida.model_validate(e) for e in eventos],
        created_at=viatico.created_at,
        updated_at=viatico.updated_at,
    )
