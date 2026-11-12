"""Configuración por variables de entorno (12-factor). Ver `/.env.example`."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    env: Literal["local", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Obligatoria: sin ella la API no arranca. Nunca se registra en logs (contiene la contraseña).
    database_url: str
    # Dominio de Google Workspace de Trulab (RN-12): solo esos correos pueden ser usuarios.
    google_workspace_domain: str = "trulab.co"
    # Primer SUPERADMIN (S1-07): lo crea `python -m app.modules.usuarios.seed` si no hay ninguno.
    superadmin_email: str = ""
    superadmin_nombre: str = "Superadministrador"

    @property
    def docs_habilitada(self) -> bool:
        """La documentación interactiva no se publica en producción."""
        return self.env != "production"


@lru_cache
def get_settings() -> Settings:
    # Los valores vienen del entorno; si falta DATABASE_URL, falla aquí con un error claro.
    return Settings()
