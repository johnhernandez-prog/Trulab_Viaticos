"""Validaciones de `Settings` para el acceso híbrido y AWS (S1-07b, ADR-027, ADR-028)."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

URL = "postgresql+psycopg://u:p@db:5432/x"


@pytest.fixture(autouse=True)
def sin_entorno(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aísla la prueba de las variables del contenedor (`.env` las inyecta en el entorno)."""
    for campo in Settings.model_fields:
        monkeypatch.delenv(campo.upper(), raising=False)


def _settings(**valores: object) -> Settings:
    # `model_validate` no lee el entorno: solo cuentan los valores de la prueba y los defaults.
    return Settings.model_validate({"database_url": URL, **valores})


def test_valores_por_defecto_seguros_para_local() -> None:
    settings = _settings()

    assert settings.google_workspace_domain == "trulab.co"
    assert settings.password_reset_ttl_minutes == 30
    assert (settings.login_max_failed_attempts, settings.login_lockout_minutes) == (5, 15)
    assert (settings.mail_backend, settings.storage_backend) == ("log", "local")


@pytest.mark.parametrize("minutos", [14, 31, 0])
def test_ttl_de_recuperacion_entre_15_y_30_minutos(minutos: int) -> None:
    with pytest.raises(ValidationError, match="password_reset_ttl_minutes"):
        _settings(password_reset_ttl_minutes=minutos)


@pytest.mark.parametrize("entorno", ["staging", "production"])
def test_correo_al_log_solo_en_local(entorno: str) -> None:
    # El log mostraría enlaces de restablecimiento: fuera de local se exige SES.
    with pytest.raises(ValidationError, match="MAIL_BACKEND=log"):
        _settings(env=entorno, mail_backend="log")


def test_ses_exige_remitente() -> None:
    with pytest.raises(ValidationError, match="AWS_SES_SENDER"):
        _settings(mail_backend="ses", aws_ses_sender="")


def test_s3_exige_bucket() -> None:
    with pytest.raises(ValidationError, match="AWS_S3_BUCKET"):
        _settings(storage_backend="s3", aws_s3_bucket="")


def test_configuracion_de_produccion_valida() -> None:
    settings = _settings(
        env="production",
        mail_backend="ses",
        aws_ses_sender="viaticos@trulab.co",
        storage_backend="s3",
        aws_s3_bucket="trulab-viaticos-prod",
        frontend_url="https://viaticos.trulab.co",
    )

    assert settings.frontend_url == "https://viaticos.trulab.co"


def test_superadmin_inicial_por_defecto_vacio_en_el_codigo() -> None:
    # El valor (john.hernandez@trulab.co) vive en `.env`/`.env.example`, no en el código.
    assert _settings().superadmin_email == ""
