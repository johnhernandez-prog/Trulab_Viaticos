"""Logs estructurados en JSON (una línea por evento) con el id de petición (RNF-10).

Nunca se registran tokens, cookies, contenido de archivos ni la cédula (RNF-09).
"""

import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Id de la petición en curso; lo fija el middleware de `X-Request-ID`.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Atributos estándar de LogRecord que no se copian como campos extra
# (`color_message` lo agrega uvicorn con códigos de color ANSI).
_ATRIBUTOS_ESTANDAR = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "color_message"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        evento: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
        for clave, valor in vars(record).items():
            if clave not in _ATRIBUTOS_ESTANDAR and not clave.startswith("_"):
                evento[clave] = valor
        if record.exc_info:
            evento["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(evento, ensure_ascii=False, default=str)


def configurar_logging(nivel: str) -> None:
    """Un único handler JSON en stdout para la app y para uvicorn."""
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    raiz = logging.getLogger()
    raiz.handlers = [handler]
    raiz.setLevel(nivel)

    for nombre in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(nombre)
        logger.handlers = []
        logger.propagate = True
    # El acceso lo registra el middleware de la app (con request_id y duración).
    logging.getLogger("uvicorn.access").disabled = True
