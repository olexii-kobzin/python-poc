from enum import StrEnum
from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings


class AppEnv(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"
    TEST = "test"


class Settings(BaseSettings):
    app_env: AppEnv
    database_sync_url: str
    database_async_url: str
    database_pgq_url: str
    amqp_dsn: str
    jwt_issuers: dict[str, list[str]]
    jwt_audience: str | None = None
    # local-only: fixed RSA private key (PEM) for minting/verifying dev tokens
    jwt_local_private_key: str | None = None
    version_token_secret: str
    log_level: str
    ledger_verify_accounts_per_run: int = 100
    ledger_verify_rows_per_account: int = 1000
    ledger_verify_max_checkpoint_age_seconds: int = 3600
    amqp_graceful_timeout: int = 10

    @model_validator(mode="after")
    def _local_key_only_in_local(self) -> Self:
        if self.jwt_local_private_key and self.app_env != AppEnv.LOCAL:
            raise ValueError(
                "jwt_local_private_key is only allowed in local environment"
            )

        return self


settings = Settings()
