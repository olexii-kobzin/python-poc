from enum import StrEnum

# from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# from pathlib import Path


class AppEnv(StrEnum):
    LOCAL = "local"
    DEV = "dev"
    PROD = "prod"
    TEST = "test"


# project_root = Path(__file__).resolve().parents[2]
# app_env = AppEnv(os.getenv("APP_ENV", AppEnv.LOCAL))
# load_dotenv(project_root / f".env.{app_env.value}")


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
    log_level: str
    ledger_verify_accounts_per_run: int = 100
    ledger_verify_rows_per_account: int = 1000
    ledger_verify_max_checkpoint_age_seconds: int = 3600


settings = Settings()
