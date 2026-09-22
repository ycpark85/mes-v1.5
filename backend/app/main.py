from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware
from app.api.v1.router import router as v1_router
from app.core.db import SessionLocal, engine
from app.core.observability import (
    configure_database_exception_handlers,
    configure_request_observability,
)
from app.services.auth_seed import ensure_auth_seed_data
from app.core.config import is_production_env, settings, validate_runtime_settings
from app.core.runtime_contract import get_runtime_info

@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_runtime_settings()
    # startup 영역
    # DB 연결 체크 (실패 시 서버 자체가 안 뜸)
    with engine.connect() as conn:
        pass

    # 인증/권한 기본 seed
    db = SessionLocal()
    try:
        ensure_auth_seed_data(db)
    finally:
        db.close()

    yield

    # shutdown 영역
    # 지금은 정리할 자원 없음 (나중에 캐시, 메시지큐 등)
    pass


openapi_enabled = not is_production_env()

app = FastAPI(
    title="MES API",
    version=get_runtime_info().server_build,
    lifespan=lifespan,
    docs_url="/docs" if openapi_enabled else None,
    redoc_url="/redoc" if openapi_enabled else None,
    openapi_url="/openapi.json" if openapi_enabled else None,
)
configure_request_observability(app, settings.SLOW_REQUEST_THRESHOLD_MS)
configure_database_exception_handlers(app)
if settings.BACKEND_ALLOWED_HOSTS:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=sorted(settings.BACKEND_ALLOWED_HOSTS),
    )
app.include_router(v1_router, prefix="/api/v1")
