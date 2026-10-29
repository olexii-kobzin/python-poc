from typing import Any

import pytest
from pydantic import ValidationError

from statement.conf import AppEnv, Settings


def build_settings(**overrides: Any) -> Settings:
    """Settings from explicit values only, so the real environment cannot leak in."""
    values: dict[str, Any] = {
        "app_env": AppEnv.TEST,
        "database_sync_url": "postgresql://u:p@db/x",
        "database_async_url": "postgresql+asyncpg://u:p@db/x",
        "database_pgq_url": "postgresql://u:p@db/x",
        "amqp_dsn": "amqp://u:p@mq/",
        "jwt_issuers": {"https://issuer.test": ["statement."]},
        "jwt_audience": None,
        "jwt_local_private_key": None,
        "version_token_secret": "secret",
        "log_level": "INFO",
    }
    values.update(overrides)

    return Settings(**values)


def test_valid_settings() -> None:
    settings = build_settings()

    assert settings.app_env == AppEnv.TEST
    assert settings.jwt_issuers == {"https://issuer.test": ["statement."]}


@pytest.mark.parametrize(
    "missing",
    [
        "app_env",
        "database_async_url",
        "amqp_dsn",
        "jwt_issuers",
        "version_token_secret",
        "log_level",
    ],
)
def test_required_setting_missing(
    missing: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Settings falls back to the real environment, which the test run has set
    monkeypatch.delenv(missing.upper(), raising=False)
    values: dict[str, Any] = {
        "app_env": AppEnv.TEST,
        "database_sync_url": "x",
        "database_async_url": "x",
        "database_pgq_url": "x",
        "amqp_dsn": "x",
        "jwt_issuers": {},
        "version_token_secret": "x",
        "log_level": "INFO",
    }
    del values[missing]

    with pytest.raises(ValidationError):
        Settings(**values)


def test_unknown_app_env_is_rejected() -> None:
    with pytest.raises(ValidationError):
        build_settings(app_env="staging")


def test_malformed_jwt_issuers_is_rejected() -> None:
    with pytest.raises(ValidationError):
        build_settings(jwt_issuers=["https://issuer.test"])


@pytest.mark.parametrize("app_env", [AppEnv.DEV, AppEnv.PROD, AppEnv.TEST])
def test_local_private_key_is_refused_outside_local(app_env: AppEnv) -> None:
    with pytest.raises(ValidationError, match="only allowed in local"):
        build_settings(
            app_env=app_env,
            jwt_audience="statement-api",
            jwt_local_private_key="pem",
        )


def test_local_private_key_is_allowed_in_local() -> None:
    settings = build_settings(app_env=AppEnv.LOCAL, jwt_local_private_key="pem")

    assert settings.jwt_local_private_key == "pem"


@pytest.mark.parametrize("app_env", [AppEnv.DEV, AppEnv.PROD])
def test_audience_is_required_in_dev_and_prod(app_env: AppEnv) -> None:
    with pytest.raises(ValidationError, match="jwt_audience is required"):
        build_settings(app_env=app_env, jwt_audience=None)


@pytest.mark.parametrize("app_env", [AppEnv.DEV, AppEnv.PROD])
def test_audience_in_dev_and_prod_is_accepted(app_env: AppEnv) -> None:
    settings = build_settings(app_env=app_env, jwt_audience="statement-api")

    assert settings.jwt_audience == "statement-api"


@pytest.mark.parametrize("app_env", [AppEnv.LOCAL, AppEnv.TEST])
def test_audience_is_optional_in_local_and_test(app_env: AppEnv) -> None:
    assert build_settings(app_env=app_env).jwt_audience is None
