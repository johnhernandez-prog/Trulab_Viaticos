"""Acciones disponibles sobre un viático, para el usuario autenticado (S2-05).

Función **pura** (sin BD): recibe el viático y el actor ya cargados y devuelve la lista exacta de
acciones que puede ejecutar ahora mismo, para que el frontend no duplique reglas de negocio. La
autorización real de cada endpoint sigue viviendo en el service (RN-27, alcance por dueño); esta
lista es solo para que la UI muestre u oculte botones (`acciones_permitidas`,
docs/api-design.md §5.4).
"""

from app.core.enums import EstadoFinanciero, EstadoOperativo, Etapa, Modalidad, Rol
from app.modules.usuarios.models import Usuario
from app.modules.viaticos.models import Viatico

_ROLES_OPERATIVOS = frozenset({Rol.ADMIN, Rol.SUPERADMIN})
_FINANCIERO_BLOQUEA_DEVOLVER = frozenset({EstadoFinanciero.PAGADO, EstadoFinanciero.PROCESADO})


def _es_dueno_o_superadmin(viatico: Viatico, actor: Usuario) -> bool:
    return viatico.usuario_id == actor.id or actor.rol == Rol.SUPERADMIN


def _puede_operar(viatico: Viatico, actor: Usuario) -> bool:
    """RN-27: nadie aprueba, rechaza ni devuelve su propio viático, salvo SUPERADMIN."""
    if actor.rol not in _ROLES_OPERATIVOS:
        return False
    return actor.rol == Rol.SUPERADMIN or viatico.usuario_id != actor.id


def calcular(viatico: Viatico, actor: Usuario) -> list[str]:
    acciones: list[str] = []
    editable = (
        viatico.estado == EstadoOperativo.PENDIENTE
        and viatico.estado_financiero == EstadoFinanciero.PENDIENTE
    )

    if _es_dueno_o_superadmin(viatico, actor) and editable:
        acciones.append("editar")
        acciones.append("eliminar")

    if _puede_operar(viatico, actor):
        if viatico.estado == EstadoOperativo.PENDIENTE:
            acciones.append("aprobar")
            acciones.append("rechazar")
        if (
            viatico.estado in (EstadoOperativo.PENDIENTE, EstadoOperativo.APROBADO)
            and viatico.estado_financiero not in _FINANCIERO_BLOQUEA_DEVOLVER
        ):
            acciones.append("devolver")

    if (
        _es_dueno_o_superadmin(viatico, actor)
        and viatico.modalidad == Modalidad.CON_SOLICITUD
        and viatico.etapa == Etapa.SOLICITUD
        and viatico.estado == EstadoOperativo.APROBADO
        and (
            not viatico.requiere_gastos_viaje
            or viatico.estado_financiero == EstadoFinanciero.TRANSFERIDO
        )
    ):
        acciones.append("habilitar_legalizacion")

    if (
        _es_dueno_o_superadmin(viatico, actor)
        and viatico.etapa == Etapa.LEGALIZACION
        and viatico.estado == EstadoOperativo.PENDIENTE
    ):
        acciones.append("gestionar_gastos")

    return acciones
