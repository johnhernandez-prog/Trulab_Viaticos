"""Errores de gastos con su `code` estable (docs/api-design.md §5.5 y §7)."""

from app.core.errors import ErrorDominio


class AdjuntoEnUso(ErrorDominio):
    # Un archivo pertenece a un solo gasto (`UNIQUE` en soporte_id y archivo_id).
    status = 409
    code = "EN_USO"
    title = "El archivo ya está adjunto a otro gasto"
