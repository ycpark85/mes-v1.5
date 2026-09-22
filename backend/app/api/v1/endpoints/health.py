import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import engine
from app.core.runtime_contract import RuntimeInfo, get_runtime_info

router = APIRouter()
logger = logging.getLogger("mes.health")

@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/runtime-info", response_model=RuntimeInfo)
def runtime_info():
    return get_runtime_info()


@router.get("/ready")
def readiness():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning(
            "readiness_failed error_type=%s",
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable"},
        )

    return {"status": "ready"}
