"""Matriz RBAC (SPEC.md §6, docs/api-design.md §4) y la dependencia `require_permission`.

- El rol es lo único que determina los permisos (uno por usuario). La matriz se escribe rol por
  rol, de forma explícita, para que una revisión de seguridad la lea sin derivar nada.
- Un permiso dice **qué acción** puede intentar un rol; el **alcance** (dueño → 404), el estado
  (→ 409) y RN-27 (sin autoaprobación) los aplica el service de cada dominio.
- El rol se lee de la BD en cada petición (`UsuarioActual`), no del JWT: un cambio de rol surte
  efecto de inmediato.
- Sin permiso → `403 SIN_PERMISO`, sin revelar cuál faltó (el detalle va solo al log).
"""

import logging
from collections.abc import Callable, Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING

from app.core.enums import Rol
from app.core.errors import ErrorDominio

if TYPE_CHECKING:
    from app.modules.auth.dependencias import Autenticado

logger = logging.getLogger("app.permisos")


class Permiso(StrEnum):
    """Permisos con formato `recurso:accion`. Es el catálogo completo: `/me` los expone tal cual."""

    # Lo propio (el service limita al dueño).
    VIATICOS_LEER_PROPIOS = "viaticos:leer_propios"
    VIATICOS_CREAR = "viaticos:crear"
    VIATICOS_CALCULAR_PRESUPUESTO = "viaticos:calcular_presupuesto"
    VIATICOS_HABILITAR_LEGALIZACION = "viaticos:habilitar_legalizacion"
    GASTOS_GESTIONAR_PROPIOS = "gastos:gestionar_propios"
    CATALOGOS_LEER = "catalogos:leer"
    # Lectura de lo ajeno.
    VIATICOS_LEER_TODOS = "viaticos:leer_todos"
    COMPROBANTES_LEER_TODOS = "comprobantes:leer_todos"
    PAGOS_LEER = "pagos:leer"
    CARGOS_LEER = "cargos:leer"
    TARIFAS_LEER = "tarifas:leer"
    INDICADORES_LEER = "indicadores:leer"
    # Estado operativo (ADMIN; DP-13, DP-18).
    VIATICOS_APROBAR = "viaticos:aprobar"
    VIATICOS_RECHAZAR = "viaticos:rechazar"
    VIATICOS_DEVOLVER = "viaticos:devolver"
    VIATICOS_GESTIONAR_TIQUETES = "viaticos:gestionar_tiquetes"
    # Dinero (FINANCIERO; DP-04, DP-13).
    VIATICOS_REGISTRAR_VALOR_ASIGNADO = "viaticos:registrar_valor_asignado"
    VIATICOS_CAMBIAR_ESTADO_FINANCIERO = "viaticos:cambiar_estado_financiero"
    # Administración.
    CARGOS_GESTIONAR = "cargos:gestionar"
    USUARIOS_GESTIONAR_OPERATIVOS = "usuarios:gestionar_operativos"
    USUARIOS_GESTIONAR_SUPERADMIN = "usuarios:gestionar_superadmin"
    CATALOGOS_GESTIONAR = "catalogos:gestionar"
    TARIFAS_GESTIONAR = "tarifas:gestionar"
    AUDITORIA_LEER = "auditoria:leer"


P = Permiso

_VIAJERO = frozenset(
    {
        P.VIATICOS_LEER_PROPIOS,
        P.VIATICOS_CREAR,
        P.VIATICOS_CALCULAR_PRESUPUESTO,
        P.VIATICOS_HABILITAR_LEGALIZACION,
        P.GASTOS_GESTIONAR_PROPIOS,
        P.CATALOGOS_LEER,
    }
)

# Lectura de lo ajeno común a FINANCIERO y ADMIN (ADMIN ve pagos en solo lectura, DP-18).
_LECTURA_INTERNA = frozenset(
    {
        P.VIATICOS_LEER_TODOS,
        P.COMPROBANTES_LEER_TODOS,
        P.PAGOS_LEER,
        P.CARGOS_LEER,
        P.TARIFAS_LEER,
        P.INDICADORES_LEER,
    }
)

_FINANCIERO = (
    _VIAJERO
    | _LECTURA_INTERNA
    | {P.VIATICOS_REGISTRAR_VALOR_ASIGNADO, P.VIATICOS_CAMBIAR_ESTADO_FINANCIERO}
)

_ADMIN = (
    _VIAJERO
    | _LECTURA_INTERNA
    | {
        P.VIATICOS_APROBAR,
        P.VIATICOS_RECHAZAR,
        P.VIATICOS_DEVOLVER,
        P.VIATICOS_GESTIONAR_TIQUETES,
        P.CARGOS_GESTIONAR,
        P.USUARIOS_GESTIONAR_OPERATIVOS,
    }
)

MATRIZ: Mapping[Rol, frozenset[Permiso]] = MappingProxyType(
    {
        Rol.VIAJERO: _VIAJERO,
        Rol.FINANCIERO: frozenset(_FINANCIERO),
        Rol.ADMIN: frozenset(_ADMIN),
        Rol.SUPERADMIN: frozenset(Permiso),
    }
)


def permisos_de(rol: Rol | str) -> frozenset[Permiso]:
    return MATRIZ[Rol(rol)]


def tiene_permiso(rol: Rol | str, permiso: Permiso) -> bool:
    return permiso in permisos_de(rol)


class SinPermiso(ErrorDominio):
    status = 403
    code = "SIN_PERMISO"
    title = "No tiene permiso para realizar esta acción"


def require_permission(permiso: Permiso) -> Callable[..., "Autenticado"]:
    """Dependencia de FastAPI: exige `UsuarioActual` (sesión vigente, sin cambio de contraseña
    pendiente) con un rol que tenga `permiso`. Devuelve el `Autenticado` para usarlo en la ruta.

    Uso: `autenticado: Annotated[Autenticado, Depends(require_permission(Permiso.CARGOS_LEER))]`
    o `dependencies=[Depends(require_permission(...))]`.
    """
    # Importación diferida: `auth.service` usa `permisos_de` para `/me`, y `auth.dependencias`
    # importa `auth.service`; importarlo arriba crearía un ciclo.
    from app.modules.auth.dependencias import Autenticado, UsuarioActual

    def dependencia(autenticado: UsuarioActual) -> Autenticado:
        usuario = autenticado.usuario
        if not tiene_permiso(usuario.rol, permiso):
            logger.warning(
                "permiso_denegado",
                extra={"usuario_id": str(usuario.id), "rol": usuario.rol, "permiso": permiso.value},
            )
            raise SinPermiso()
        return autenticado

    dependencia.__name__ = f"require_permission[{permiso.value}]"
    return dependencia
