"""Acciones de gastos en `viatico_eventos` (S2-06).

El historial del viático registra el alta, la edición y la eliminación (lógica) de cada gasto de
la legalización: se amplía `ck_viatico_eventos__accion` con `REGISTRAR_GASTO`, `EDITAR_GASTO` y
`ELIMINAR_GASTO` (`app/core/enums.py::AccionViatico`). Sin cambios de datos.

Revision ID: 3b9e51c0d2a4
Revises: 7d7db0ebc91e
Create Date: 2026-11-13 19:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "3b9e51c0d2a4"
down_revision: str | None = "7d7db0ebc91e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NOMBRE = "ck_viatico_eventos__accion"
_ANTERIORES = (
    "'CREAR', 'EDITAR_SOLICITUD', 'APROBAR', 'RECHAZAR', 'DEVOLVER', "
    "'GESTIONAR_TIQUETES', 'HABILITAR_LEGALIZACION', 'CAMBIAR_ESTADO_FINANCIERO', "
    "'EDITAR_VALOR_ASIGNADO', 'CAMBIAR_RECURSOS_PROPIOS', 'LIQUIDAR', 'ELIMINAR'"
)
_NUEVAS = "'REGISTRAR_GASTO', 'EDITAR_GASTO', 'ELIMINAR_GASTO'"


def upgrade() -> None:
    op.drop_constraint(op.f(_NOMBRE), "viatico_eventos", type_="check")
    op.create_check_constraint(
        op.f(_NOMBRE), "viatico_eventos", f"accion IN ({_ANTERIORES}, {_NUEVAS})"
    )


def downgrade() -> None:
    # Falla a propósito si ya hay eventos de gastos: el historial es de solo inserción.
    op.drop_constraint(op.f(_NOMBRE), "viatico_eventos", type_="check")
    op.create_check_constraint(op.f(_NOMBRE), "viatico_eventos", f"accion IN ({_ANTERIORES})")
