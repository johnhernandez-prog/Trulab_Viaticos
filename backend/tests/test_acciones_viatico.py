"""Acciones permitidas sobre un viático (S2-05, `app/modules/viaticos/acciones.py`): función pura,
sin BD. Construye `Viatico`/`Usuario` en memoria (sin `session.add`/`flush`)."""

import uuid

import pytest

from app.core.enums import EstadoFinanciero, EstadoOperativo, Etapa, Modalidad, Rol
from app.modules.usuarios.models import Usuario
from app.modules.viaticos import acciones
from app.modules.viaticos.models import Viatico

V, F, A, S = Rol.VIAJERO, Rol.FINANCIERO, Rol.ADMIN, Rol.SUPERADMIN


def _usuario(rol: Rol) -> Usuario:
    return Usuario(id=uuid.uuid4(), nombre_completo="Prueba", correo="x@trulab.co", rol=rol)


def _viatico(dueno_id: uuid.UUID, **campos: object) -> Viatico:
    valores: dict[str, object] = {
        "id": uuid.uuid4(),
        "usuario_id": dueno_id,
        "modalidad": Modalidad.LEGALIZACION_DIRECTA,
        "etapa": Etapa.LEGALIZACION,
        "estado": EstadoOperativo.PENDIENTE,
        "estado_financiero": EstadoFinanciero.PENDIENTE,
        "requiere_gastos_viaje": False,
    }
    valores.update(campos)
    return Viatico(**valores)


# --- editar / eliminar (dueño o SUPERADMIN, PENDIENTE/PENDIENTE) --------------------------------


def test_dueno_puede_editar_y_eliminar_mientras_esta_pendiente() -> None:
    viajero = _usuario(V)
    viatico = _viatico(viajero.id)

    resultado = acciones.calcular(viatico, viajero)

    assert "editar" in resultado and "eliminar" in resultado


@pytest.mark.parametrize(
    ("estado", "estado_financiero"),
    [
        (EstadoOperativo.APROBADO, EstadoFinanciero.PENDIENTE),
        (EstadoOperativo.PENDIENTE, EstadoFinanciero.TRANSFERIDO),
    ],
)
def test_no_se_edita_ni_elimina_fuera_de_pendiente_pendiente(
    estado: EstadoOperativo, estado_financiero: EstadoFinanciero
) -> None:
    viajero = _usuario(V)
    viatico = _viatico(viajero.id, estado=estado, estado_financiero=estado_financiero)

    resultado = acciones.calcular(viatico, viajero)

    assert "editar" not in resultado and "eliminar" not in resultado


def test_otro_viajero_no_puede_editar_ni_eliminar() -> None:
    dueno = _usuario(V)
    otro = _usuario(V)
    viatico = _viatico(dueno.id)

    resultado = acciones.calcular(viatico, otro)

    assert "editar" not in resultado and "eliminar" not in resultado


def test_superadmin_puede_editar_cualquier_viatico_pendiente() -> None:
    dueno = _usuario(V)
    superadmin = _usuario(S)
    viatico = _viatico(dueno.id)

    resultado = acciones.calcular(viatico, superadmin)

    assert "editar" in resultado and "eliminar" in resultado


# --- aprobar / rechazar (ADMIN, SUPERADMIN; RN-27) ----------------------------------------------


@pytest.mark.parametrize("rol", [V, F])
def test_viajero_y_financiero_nunca_aprueban_ni_rechazan(rol: Rol) -> None:
    dueno = _usuario(V)
    actor = _usuario(rol)
    viatico = _viatico(dueno.id)

    resultado = acciones.calcular(viatico, actor)

    assert "aprobar" not in resultado and "rechazar" not in resultado


def test_admin_aprueba_y_rechaza_un_viatico_ajeno() -> None:
    dueno = _usuario(V)
    admin = _usuario(A)
    viatico = _viatico(dueno.id)

    resultado = acciones.calcular(viatico, admin)

    assert "aprobar" in resultado and "rechazar" in resultado


def test_admin_no_aprueba_su_propio_viatico_rn27() -> None:
    admin = _usuario(A)
    viatico = _viatico(admin.id)

    resultado = acciones.calcular(viatico, admin)

    assert "aprobar" not in resultado and "rechazar" not in resultado


def test_superadmin_si_aprueba_su_propio_viatico_rn27() -> None:
    superadmin = _usuario(S)
    viatico = _viatico(superadmin.id)

    resultado = acciones.calcular(viatico, superadmin)

    assert "aprobar" in resultado and "rechazar" in resultado


def test_no_se_aprueba_ni_rechaza_fuera_de_pendiente() -> None:
    dueno = _usuario(V)
    admin = _usuario(A)
    viatico = _viatico(dueno.id, estado=EstadoOperativo.APROBADO)

    resultado = acciones.calcular(viatico, admin)

    assert "aprobar" not in resultado and "rechazar" not in resultado


# --- devolver (ADMIN, SUPERADMIN; PENDIENTE o APROBADO sin PAGADO/PROCESADO) ---------------------


@pytest.mark.parametrize("estado", [EstadoOperativo.PENDIENTE, EstadoOperativo.APROBADO])
def test_admin_devuelve_desde_pendiente_o_aprobado(estado: EstadoOperativo) -> None:
    dueno = _usuario(V)
    admin = _usuario(A)
    viatico = _viatico(dueno.id, estado=estado)

    assert "devolver" in acciones.calcular(viatico, admin)


def test_no_se_devuelve_rechazado() -> None:
    dueno = _usuario(V)
    admin = _usuario(A)
    viatico = _viatico(dueno.id, estado=EstadoOperativo.RECHAZADO)

    assert "devolver" not in acciones.calcular(viatico, admin)


@pytest.mark.parametrize("estado_financiero", [EstadoFinanciero.PAGADO, EstadoFinanciero.PROCESADO])
def test_no_se_devuelve_si_ya_esta_pagado_o_procesado(
    estado_financiero: EstadoFinanciero,
) -> None:
    dueno = _usuario(V)
    admin = _usuario(A)
    viatico = _viatico(
        dueno.id, estado=EstadoOperativo.APROBADO, estado_financiero=estado_financiero
    )

    assert "devolver" not in acciones.calcular(viatico, admin)


def test_admin_no_devuelve_su_propio_viatico_rn27() -> None:
    admin = _usuario(A)
    viatico = _viatico(admin.id)

    assert "devolver" not in acciones.calcular(viatico, admin)


# --- habilitar_legalizacion (dueño o SUPERADMIN) -------------------------------------------------


def test_dueno_habilita_legalizacion_sin_gastos_de_viaje() -> None:
    viajero = _usuario(V)
    viatico = _viatico(
        viajero.id,
        modalidad=Modalidad.CON_SOLICITUD,
        etapa=Etapa.SOLICITUD,
        estado=EstadoOperativo.APROBADO,
        requiere_gastos_viaje=False,
    )

    assert "habilitar_legalizacion" in acciones.calcular(viatico, viajero)


def test_dueno_no_habilita_sin_transferido_si_requiere_gastos_de_viaje() -> None:
    viajero = _usuario(V)
    viatico = _viatico(
        viajero.id,
        modalidad=Modalidad.CON_SOLICITUD,
        etapa=Etapa.SOLICITUD,
        estado=EstadoOperativo.APROBADO,
        requiere_gastos_viaje=True,
        estado_financiero=EstadoFinanciero.PENDIENTE,
    )

    assert "habilitar_legalizacion" not in acciones.calcular(viatico, viajero)


def test_dueno_habilita_con_transferido_si_requiere_gastos_de_viaje() -> None:
    viajero = _usuario(V)
    viatico = _viatico(
        viajero.id,
        modalidad=Modalidad.CON_SOLICITUD,
        etapa=Etapa.SOLICITUD,
        estado=EstadoOperativo.APROBADO,
        requiere_gastos_viaje=True,
        estado_financiero=EstadoFinanciero.TRANSFERIDO,
    )

    assert "habilitar_legalizacion" in acciones.calcular(viatico, viajero)


def test_otro_viajero_no_habilita_legalizacion_ajena() -> None:
    dueno = _usuario(V)
    otro = _usuario(V)
    viatico = _viatico(
        dueno.id,
        modalidad=Modalidad.CON_SOLICITUD,
        etapa=Etapa.SOLICITUD,
        estado=EstadoOperativo.APROBADO,
    )

    assert "habilitar_legalizacion" not in acciones.calcular(viatico, otro)


def test_no_se_habilita_legalizacion_directa() -> None:
    viajero = _usuario(V)
    viatico = _viatico(
        viajero.id, modalidad=Modalidad.LEGALIZACION_DIRECTA, etapa=Etapa.LEGALIZACION
    )

    assert "habilitar_legalizacion" not in acciones.calcular(viatico, viajero)


# --- gestionar_gastos (dueño o SUPERADMIN, etapa LEGALIZACION, PENDIENTE) ------------------------


def test_dueno_gestiona_gastos_en_legalizacion_pendiente() -> None:
    viajero = _usuario(V)
    viatico = _viatico(viajero.id, etapa=Etapa.LEGALIZACION, estado=EstadoOperativo.PENDIENTE)

    assert "gestionar_gastos" in acciones.calcular(viatico, viajero)


def test_no_se_gestionan_gastos_en_etapa_solicitud() -> None:
    viajero = _usuario(V)
    viatico = _viatico(
        viajero.id,
        modalidad=Modalidad.CON_SOLICITUD,
        etapa=Etapa.SOLICITUD,
        estado=EstadoOperativo.PENDIENTE,
    )

    assert "gestionar_gastos" not in acciones.calcular(viatico, viajero)


# --- tiquetes y dinero (S2-07) -------------------------------------------------------------------


def _solicitud(dueno_id: uuid.UUID, **campos: object) -> Viatico:
    valores: dict[str, object] = {
        "modalidad": Modalidad.CON_SOLICITUD,
        "etapa": Etapa.SOLICITUD,
        "estado": EstadoOperativo.APROBADO,
        "requiere_tiquete": True,
        "recursos_propios": False,
        "valor_asignado": 0,
    }
    valores.update(campos)
    return _viatico(dueno_id, **valores)


@pytest.mark.parametrize(("rol", "puede"), [(A, True), (S, True), (F, False), (V, False)])
def test_gestionar_tiquetes_por_rol(rol: Rol, puede: bool) -> None:
    viatico = _solicitud(uuid.uuid4())

    assert ("gestionar_tiquetes" in acciones.calcular(viatico, _usuario(rol))) is puede


@pytest.mark.parametrize(
    "campos",
    [
        {"requiere_tiquete": False},
        {"estado": EstadoOperativo.PENDIENTE},
        {"etapa": Etapa.LEGALIZACION},
    ],
)
def test_gestionar_tiquetes_solo_en_solicitud_aprobada_con_tiquete(
    campos: dict[str, object],
) -> None:
    viatico = _solicitud(uuid.uuid4(), **campos)

    assert "gestionar_tiquetes" not in acciones.calcular(viatico, _usuario(A))


def test_admin_no_gestiona_tiquetes_de_lo_propio() -> None:
    admin = _usuario(A)

    assert "gestionar_tiquetes" not in acciones.calcular(_solicitud(admin.id), admin)


@pytest.mark.parametrize(("rol", "puede"), [(F, True), (S, True), (A, False), (V, False)])
def test_valor_asignado_por_rol(rol: Rol, puede: bool) -> None:
    viatico = _solicitud(uuid.uuid4())

    assert ("registrar_valor_asignado" in acciones.calcular(viatico, _usuario(rol))) is puede


@pytest.mark.parametrize(
    "campos",
    [
        {"estado": EstadoOperativo.PENDIENTE},
        {"estado_financiero": EstadoFinanciero.PAGADO, "etapa": Etapa.LEGALIZACION},
    ],
)
def test_valor_asignado_no_disponible(campos: dict[str, object]) -> None:
    viatico = _solicitud(uuid.uuid4(), **campos)

    assert "registrar_valor_asignado" not in acciones.calcular(viatico, _usuario(F))


def test_valor_asignado_no_disponible_con_recursos_propios() -> None:
    viatico = _viatico(uuid.uuid4(), estado=EstadoOperativo.APROBADO, recursos_propios=True)

    assert "registrar_valor_asignado" not in acciones.calcular(viatico, _usuario(F))


def test_financiero_no_toca_el_dinero_de_lo_propio() -> None:
    financiero = _usuario(F)
    viatico = _solicitud(financiero.id, valor_asignado=100)

    resultado = acciones.calcular(viatico, financiero)

    assert "registrar_valor_asignado" not in resultado
    assert "cambiar_estado_financiero" not in resultado


@pytest.mark.parametrize(
    ("campos", "destinos"),
    [
        # Solicitud aprobada: solo transferir, y solo con valor asignado.
        ({}, []),
        ({"valor_asignado": 100}, [EstadoFinanciero.TRANSFERIDO]),
        ({"estado": EstadoOperativo.PENDIENTE, "valor_asignado": 100}, []),
        # Legalización aprobada: transferir (si hay valor) y liquidar.
        (
            {"etapa": Etapa.LEGALIZACION, "valor_asignado": 100},
            [EstadoFinanciero.TRANSFERIDO, EstadoFinanciero.PAGADO, EstadoFinanciero.PROCESADO],
        ),
        (
            {"etapa": Etapa.LEGALIZACION, "estado_financiero": EstadoFinanciero.TRANSFERIDO},
            [EstadoFinanciero.PAGADO, EstadoFinanciero.PROCESADO],
        ),
        (
            {"etapa": Etapa.LEGALIZACION, "estado_financiero": EstadoFinanciero.PAGADO},
            [EstadoFinanciero.PROCESADO],
        ),
        ({"etapa": Etapa.LEGALIZACION, "estado_financiero": EstadoFinanciero.PROCESADO}, []),
    ],
)
def test_destinos_financieros(campos: dict[str, object], destinos: list[EstadoFinanciero]) -> None:
    viatico = _solicitud(uuid.uuid4(), **campos)

    assert acciones.destinos_financieros(viatico) == destinos
    puede = "cambiar_estado_financiero" in acciones.calcular(viatico, _usuario(F))
    assert puede is bool(destinos)


def test_recursos_propios_no_se_transfiere_pero_se_liquida() -> None:
    viatico = _viatico(uuid.uuid4(), estado=EstadoOperativo.APROBADO, recursos_propios=True)

    assert acciones.destinos_financieros(viatico) == [
        EstadoFinanciero.PAGADO,
        EstadoFinanciero.PROCESADO,
    ]
