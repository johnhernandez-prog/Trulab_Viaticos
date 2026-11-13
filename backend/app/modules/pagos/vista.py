"""`v_viatico_saldos` (ADR-008) como tabla de solo lectura para las consultas de `/pagos`.

Vive en un `MetaData` **aparte** de `Base.metadata`: así Alembic no la toma por una tabla que falta
(`alembic check` seguiría limpio) y el ORM puede unirla con `viaticos`. La vista es
`security_invoker`, de modo que RLS de las tablas base se aplica a quien consulta.
"""

from sqlalchemy import Column, Integer, MetaData, Numeric, Table, Uuid

_metadata_vistas = MetaData()

saldos = Table(
    "v_viatico_saldos",
    _metadata_vistas,
    Column("viatico_id", Uuid),
    Column("total_gastos", Numeric(14, 2)),
    Column("cantidad_gastos", Integer),
    Column("gastos_sin_comprobante", Integer),
    Column("saldo", Numeric(14, 2)),
)
