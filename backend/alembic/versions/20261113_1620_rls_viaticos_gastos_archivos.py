"""RLS sobre viaticos, viatico_trayectos, viatico_eventos, gastos y archivos (S2-03, ADR-007).

Objetivo: que RN-01 (aislamiento por dueño) se cumpla aunque falle el código de la aplicación,
con `trulab_app` (el único rol que usa la API) como defensa en profundidad.

- `viaticos`: visible para su `usuario_id` o para FINANCIERO/ADMIN/SUPERADMIN
  (`current_setting('app.rol', true)`).
- `viatico_trayectos`, `viatico_eventos` y `gastos`: siguen la visibilidad de su `viaticos` padre
  (`EXISTS` sobre `viatico_id`), igual para FINANCIERO/ADMIN/SUPERADMIN.
- `archivos`: no tiene `viatico_id`/`usuario_id` directo (lo referencian `viaticos`, `gastos` y
  `usuarios.firma_archivo_id`); se usa `created_by` (quien lo subió) en vez de recorrer las tres
  tablas que lo referencian. Coincide con quien puede subirlo en el service.
- `usuarios`, `sesiones`, `tokens_recuperacion_password`, `proyectos`, `rubros`, `celulas` y
  `tarifas_viaticos` **no** llevan RLS (docs/database-design.md §6: el login consulta `usuarios`
  antes de tener contexto; los catálogos y las tarifas los lee cualquier rol autenticado y los
  escribe solo SUPERADMIN, controlado en el service).

**Decisión de S2-03 (sin `FORCE ROW LEVEL SECURITY`):** se usa solo `ENABLE`. `trulab_owner` —el
dueño de las tablas, nunca usado por la API (`DATABASE_URL_MIGRATIONS` no llega a `app`)— sigue
sin RLS, como cualquier dueño de tabla en PostgreSQL; así `test_migraciones.py` (S2-02) conserva
la capacidad de insertar filas de prueba en `viaticos`/`viatico_eventos` desde `trulab_owner` para
probar el trigger de solo inserción, y el ETL (F10) podrá escribir sin pelear con las políticas.
`trulab_app` —el único rol que la API usa— **siempre** queda sujeto a las políticas, con o sin
`FORCE`: ese es el actor real que había que proteger (ADR-007). `FORCE` solo añade protección
contra un uso directo de `trulab_owner` fuera de las migraciones y las pruebas, que no es parte
del modelo de amenaza del MVP. Si se necesita en el futuro, se agrega en un ADR aparte.

Revision ID: 7d7db0ebc91e
Revises: 2c36be2a3312
Create Date: 2026-11-13 16:20:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7d7db0ebc91e"
down_revision: str | None = "2c36be2a3312"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRIVILEGIADO = "current_setting('app.rol', true) IN ('FINANCIERO', 'ADMIN', 'SUPERADMIN')"
# `NULLIF(..., '')`: una variable `app.*` que nunca se fijó en esta conexión (o una ya fuera de su
# `SET LOCAL`) da cadena vacía, no `NULL` (particularidad de los GUC de marcador de posición de
# PostgreSQL); sin el `NULLIF`, `''::uuid` lanza un error en vez de simplemente negar el acceso.
_PROPIO_USUARIO = "usuario_id = NULLIF(current_setting('app.usuario_id', true), '')::uuid"
_PROPIO_CREADOR = "created_by = NULLIF(current_setting('app.usuario_id', true), '')::uuid"


def _condicion_viatico(tabla: str) -> str:
    """`EXISTS` sobre el viático padre: ven la fila quienes ven ese viático (RN-01).

    `tabla` siempre es uno de los cinco nombres fijos de este módulo (nunca dato de usuario).
    """
    # `tabla` es uno de los cinco nombres fijos de este módulo, nunca un dato de usuario.
    return (
        f"{_PRIVILEGIADO} OR EXISTS (\n"  # noqa: S608
        f"    SELECT 1 FROM viaticos v\n"
        f"    WHERE v.id = {tabla}.viatico_id AND v.{_PROPIO_USUARIO}\n"
        f"  )"
    )


def _crear_politica(tabla: str, condicion: str) -> None:
    op.execute(f"ALTER TABLE {tabla} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY ver_propios_o_privilegiado ON {tabla} FOR ALL TO trulab_app\n"
        f"  USING ({condicion})\n"
        f"  WITH CHECK ({condicion})"
    )


def _borrar_politica(tabla: str) -> None:
    op.execute(f"DROP POLICY ver_propios_o_privilegiado ON {tabla}")
    op.execute(f"ALTER TABLE {tabla} DISABLE ROW LEVEL SECURITY")


def upgrade() -> None:
    _crear_politica("viaticos", f"{_PRIVILEGIADO} OR {_PROPIO_USUARIO}")
    _crear_politica("viatico_trayectos", _condicion_viatico("viatico_trayectos"))
    _crear_politica("viatico_eventos", _condicion_viatico("viatico_eventos"))
    _crear_politica("gastos", _condicion_viatico("gastos"))
    _crear_politica("archivos", f"{_PRIVILEGIADO} OR {_PROPIO_CREADOR}")


def downgrade() -> None:
    _borrar_politica("archivos")
    _borrar_politica("gastos")
    _borrar_politica("viatico_eventos")
    _borrar_politica("viatico_trayectos")
    _borrar_politica("viaticos")
