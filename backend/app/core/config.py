from typing import Set

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_AUTH_SECRET_KEY = "mes-dev-auth-secret-key-change-me"
PRODUCTION_ENVS = {"prod", "production"}

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="forbid",
    )

    app_env: str = "dev"
    MES_SERVER_BUILD_ID: str = Field(default="unknown", pattern=r"^[A-Za-z0-9._-]{1,64}$")
    database_url: str

    DB_POOL_SIZE: int = Field(default=5, ge=1, le=50)
    DB_MAX_OVERFLOW: int = Field(default=5, ge=0, le=100)
    DB_POOL_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=120)
    DB_POOL_RECYCLE_SECONDS: int = Field(default=1800, ge=60, le=86400)
    DB_CONNECT_TIMEOUT_SECONDS: int = Field(default=5, ge=1, le=60)
    DB_STATEMENT_TIMEOUT_SECONDS: int = Field(default=30, ge=1, le=600)
    DB_BULK_STATEMENT_TIMEOUT_SECONDS: int = Field(default=120, ge=1, le=1800)
    DB_LOCK_TIMEOUT_SECONDS: int = Field(default=5, ge=1, le=120)
    DB_IDLE_TRANSACTION_TIMEOUT_SECONDS: int = Field(default=60, ge=1, le=600)
    DB_APPLICATION_NAME: str = Field(default="mes-api", min_length=1, max_length=63)
    SLOW_QUERY_THRESHOLD_MS: int = Field(default=1000, ge=100, le=60000)
    SLOW_REQUEST_THRESHOLD_MS: int = Field(default=2000, ge=100, le=300000)

    AUTH_SECRET_KEY: str = Field(default="mes-dev-auth-secret-key-change-me")
    AUTH_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=720, ge=1, le=1440)

    AUTH_LOGIN_MAX_FAILED_ATTEMPTS: int = Field(default=5, ge=1, le=20)
    AUTH_LOGIN_FAILURE_WINDOW_MINUTES: int = Field(default=10, ge=1, le=1440)
    AUTH_LOGIN_LOCKOUT_MINUTES: int = Field(default=3, ge=1, le=60)

    MES_ADMIN_LOGIN_ID: str = Field(default="admin")
    MES_ADMIN_PASSWORD: str | None = Field(default=None)

    VENDOR_PORTAL_BOHYUN_PARTNER_ID: int | None = Field(default=None)
    
    BACKEND_ALLOWED_HOSTS: Set[str] = Field(default_factory=set)

    DRAWING_STORAGE_ROOT: str = Field(default=r"C:\mes_storage")
    DRAWING_MAX_MB: int = Field(default=50, ge=1, le=500)
    DRAWING_ALLOWED_EXT: Set[str] = Field(default_factory=set)

    DEFECT_PHOTO_STORAGE_ROOT: str = Field(default=r"C:\mes_storage")
    DEFECT_PHOTO_MAX_MB: int = Field(default=20, ge=1, le=500)
    DEFECT_PHOTO_ALLOWED_EXT: Set[str] = Field(default_factory=set)

    PLATE_DATA_STORAGE_ROOT: str = Field(default=r"C:\mes_storage")
    PLATE_DATA_MAX_MB: int = Field(default=100, ge=1, le=1000)
    PLATE_DATA_ALLOWED_EXT: Set[str] = Field(default_factory=set)

    @field_validator("DRAWING_ALLOWED_EXT", "DEFECT_PHOTO_ALLOWED_EXT","PLATE_DATA_ALLOWED_EXT", mode="before")
    @classmethod
    def _normalize_allowed_ext(cls, v):
        if isinstance(v, (list, set, tuple)):
            normalized: Set[str] = set()

            for x in v:
                ext = str(x).strip().lower()

                if not ext:
                    continue

                if not ext.startswith("."):
                    ext = f".{ext}"

                normalized.add(ext)

            return normalized
        return v


settings = Settings()

def is_production_env() -> bool:
    return settings.app_env.strip().lower() in PRODUCTION_ENVS


def validate_runtime_settings() -> None:
    if not is_production_env():
        return

    secret_key = settings.AUTH_SECRET_KEY.strip()

    if secret_key == DEFAULT_AUTH_SECRET_KEY or len(secret_key) < 32:
        raise RuntimeError(
            "운영 환경에서는 AUTH_SECRET_KEY를 32자 이상의 안전한 값으로 설정해야 합니다."
        )

    if not settings.BACKEND_ALLOWED_HOSTS:
        raise RuntimeError(
            "운영 환경에서는 BACKEND_ALLOWED_HOSTS를 설정해야 합니다."
        )
