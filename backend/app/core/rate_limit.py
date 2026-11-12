"""Límite de peticiones por IP para `/auth/*` (docs/api-design.md §3 y §8).

Ventana fija en memoria del proceso: suficiente con una sola instancia de la API. Con varias
instancias en AWS cada una cuenta por separado (el límite real se multiplica); si se escala
horizontalmente, se reemplaza por un contador compartido o por AWS WAF (ADR futuro). El bloqueo
por usuario tras intentos fallidos (S-14) sí vive en la BD y no depende de esto.
"""

import math
import threading
import time
from collections.abc import Callable

from fastapi import Request

from app.core.errors import ErrorDominio


class DemasiadasSolicitudes(ErrorDominio):
    status = 429
    code = "DEMASIADAS_SOLICITUDES"
    title = "Demasiadas solicitudes. Intente de nuevo en unos minutos"


class _Contador:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # (clave) -> (inicio de la ventana, peticiones en la ventana)
        self._ventanas: dict[str, tuple[float, int]] = {}

    def registrar(self, clave: str, maximo: int, ventana: float) -> float | None:
        """Cuenta una petición. Devuelve los segundos de espera si se superó el máximo."""
        ahora = time.monotonic()
        with self._lock:
            inicio, cantidad = self._ventanas.get(clave, (ahora, 0))
            if ahora - inicio >= ventana:
                inicio, cantidad = ahora, 0
            cantidad += 1
            self._ventanas[clave] = (inicio, cantidad)
            if cantidad > maximo:
                return ventana - (ahora - inicio)
            return None

    def reiniciar(self) -> None:
        with self._lock:
            self._ventanas.clear()


contador = _Contador()


def ip_cliente(request: Request) -> str:
    # Detrás del balanceador de AWS, uvicorn debe correr con `--proxy-headers` para que esto sea
    # la IP real del cliente (S3-07).
    return request.client.host if request.client else "desconocida"


def limitar(nombre: str, maximo: int, ventana_segundos: int) -> Callable[[Request], None]:
    """Dependencia de FastAPI: `Depends(limitar("auth.login", 10, 60))`."""

    def dependencia(request: Request) -> None:
        espera = contador.registrar(f"{nombre}:{ip_cliente(request)}", maximo, ventana_segundos)
        if espera is not None:
            raise DemasiadasSolicitudes(
                f"Espere {math.ceil(espera)} segundos antes de volver a intentarlo."
            )

    return dependencia
