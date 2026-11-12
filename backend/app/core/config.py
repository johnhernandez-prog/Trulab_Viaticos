"""Configuración por variables de entorno (12-factor). Ver `/.env.example`."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    env: Literal["local", "staging", "production"] = "local"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Obligatoria: sin ella la API no arranca. Nunca se registra en logs (contiene la contraseña).
    database_url: str

    # --- Acceso híbrido (ADR-027) ---------------------------------------------------------------
    # Dominio corporativo: claim `hd` del login con Google y correo de todo SUPERADMIN (RN-12).
    google_workspace_domain: str = "trulab.co"
    # Primer SUPERADMIN (S1-07): lo crea `python -m app.modules.usuarios.seed` si no hay ninguno.
    # El valor real (john.hernandez@trulab.co) vive en `.env`, no en el código.
    superadmin_email: str = ""
    superadmin_nombre: str = "Superadministrador"
    # Vigencia del enlace de restablecimiento de contraseña (RN-15: 15 a 30 minutos).
    password_reset_ttl_minutes: int = Field(default=30, ge=15, le=30)
    # Bloqueo temporal por intentos fallidos de login (S-14).
    login_max_failed_attempts: int = Field(default=5, ge=1)
    login_lockout_minutes: int = Field(default=15, ge=1)

    # --- Correo transaccional y archivos (ADR-028) ----------------------------------------------
    # `log` escribe el correo en el log (solo local); `ses` usa Amazon SES.
    mail_backend: Literal["log", "ses"] = "log"
    aws_ses_sender: str = ""
    # URL pública de la SPA: enlaces de los correos y CORS en producción.
    frontend_url: str = "http://localhost:5173"
    storage_backend: Literal["local", "s3"] = "local"
    aws_region: str = "us-east-1"
    aws_s3_bucket: str = ""

    @model_validator(mode="after")
    def _validar_entorno(self) -> Self:
        # Fuera de local, el log mostraría enlaces de restablecimiento de contraseña.
        if self.env != "local" and self.mail_backend == "log":
            raise ValueError("MAIL_BACKEND=log solo se permite con ENV=local; use ses")
        if self.mail_backend == "ses" and not self.aws_ses_sender.strip():
            raise ValueError("MAIL_BACKEND=ses exige AWS_SES_SENDER (identidad verificada en SES)")
        if self.storage_backend == "s3" and not self.aws_s3_bucket.strip():
            raise ValueError("STORAGE_BACKEND=s3 exige AWS_S3_BUCKET")
        return self

    @property
    def docs_habilitada(self) -> bool:
        """La documentación interactiva no se publica en producción."""
        return self.env != "production"


@lru_cache
def get_settings() -> Settings:
    # Los valores vienen del entorno; si falta DATABASE_URL, falla aquí con un error claro.
    return Settings()
