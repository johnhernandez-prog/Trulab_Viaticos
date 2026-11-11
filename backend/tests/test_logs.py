import json
import logging

from app.core.logs import JsonFormatter, request_id_var


def test_log_json_incluye_request_id_y_campos_extra() -> None:
    token = request_id_var.set("abc-123")
    try:
        registro = logging.makeLogRecord(
            {"name": "app.prueba", "levelname": "INFO", "msg": "peticion", "status": 200}
        )
        registro.color_message = "\x1b[36mcolor\x1b[0m"

        evento = json.loads(JsonFormatter().format(registro))
    finally:
        request_id_var.reset(token)

    assert evento["message"] == "peticion"
    assert evento["request_id"] == "abc-123"
    assert evento["status"] == 200
    assert "color_message" not in evento
