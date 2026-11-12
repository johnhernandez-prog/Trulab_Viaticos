"""`python -m app.modules.usuarios.seed`: crea el primer SUPERADMIN desde `SUPERADMIN_EMAIL`.

Lo ejecuta el servicio `migrate` después de `alembic upgrade head`. Se conecta como `trulab_app`
(`DATABASE_URL`): crear un usuario es una operación de la aplicación, no del esquema.
Idempotente: ver `asegurar_superadmin_inicial`. El correo no se escribe en el log.
"""

import logging
import sys

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_engine
from app.core.logs import configurar_logging
from app.modules.usuarios.service import ErrorConfiguracion, asegurar_superadmin_inicial

logger = logging.getLogger("app.seed")


def main() -> int:
    settings = get_settings()
    configurar_logging(settings.log_level)
    try:
        with Session(get_engine()) as session, session.begin():
            resultado = asegurar_superadmin_inicial(
                session,
                settings.superadmin_email,
                settings.superadmin_nombre,
                settings.google_workspace_domain,
            )
    except ErrorConfiguracion as error:
        logger.error("seed_superadmin_invalido", extra={"motivo": str(error)})
        return 1
    logger.info("seed_superadmin", extra={"resultado": resultado.value})
    return 0


if __name__ == "__main__":
    sys.exit(main())
