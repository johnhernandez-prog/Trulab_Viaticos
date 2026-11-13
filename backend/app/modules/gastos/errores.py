"""Errores de gastos con su `code` estable (docs/api-design.md §5.5 y §7)."""

from app.core.errors import ErrorDominio


class EtapaInvalida(ErrorDominio):
    # Los gastos solo existen en la etapa LEGALIZACION (docs/database-design.md §2.8).
    status = 409
    code = "ETAPA_INVALIDA"
    title = "La acción no corresponde a la etapa actual del viático"


class AdjuntoEnUso(ErrorDominio):
    # Un archivo pertenece a un solo gasto (`UNIQUE` en soporte_id y archivo_id).
    status = 409
    code = "EN_USO"
    title = "El archivo ya está adjunto a otro gasto"
