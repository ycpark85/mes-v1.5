import logging
import re
import time
from contextvars import ContextVar
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import event
from sqlalchemy.engine import Engine, ExceptionContext
from sqlalchemy.exc import OperationalError, TimeoutError as SQLAlchemyTimeoutError
from app.core.runtime_contract import (
    CLIENT_VERSION_HEADER, CLIENT_BUILD_HEADER, SERVER_BUILD_HEADER,
    get_runtime_info, safe_build_identifier,
)


REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_QUERY_TIMER_KEY = "mes_query_started_at"

request_id_context: ContextVar[str] = ContextVar(
    "request_id",
    default="-",
)
request_logger = logging.getLogger("mes.request")
database_logger = logging.getLogger("mes.database")


def _resolve_request_id(request: Request) -> str:
    candidate = request.headers.get(REQUEST_ID_HEADER, "").strip()
    if _REQUEST_ID_PATTERN.fullmatch(candidate):
        return candidate
    return uuid4().hex


def _route_path(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or request.url.path


def configure_request_observability(
    app: FastAPI,
    slow_request_threshold_ms: int,
) -> None:
    @app.middleware("http")
    async def request_observability_middleware(request: Request, call_next):
        return await observe_request(
            request,
            call_next,
            slow_request_threshold_ms,
        )


async def observe_request(
    request: Request,
    call_next,
    slow_request_threshold_ms: int,
):
    request_id = _resolve_request_id(request)
    client_version = safe_build_identifier(request.headers.get(CLIENT_VERSION_HEADER))
    client_build = safe_build_identifier(request.headers.get(CLIENT_BUILD_HEADER))
    server_build = get_runtime_info().server_build
    request.state.request_id = request_id
    context_token = request_id_context.set(request_id)
    started_at = time.perf_counter()

    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[SERVER_BUILD_HEADER] = server_build

        log_method = (
            request_logger.warning
            if elapsed_ms >= slow_request_threshold_ms or response.status_code >= 500
            else request_logger.info
        )
        log_method(
            "request_completed request_id=%s method=%s path=%s status=%s elapsed_ms=%.1f client_version=%s client_build=%s server_build=%s",
            request_id,
            request.method,
            _route_path(request),
            response.status_code,
            elapsed_ms,
            client_version, client_build, server_build,
        )
        return response
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        request_logger.error(
            "request_failed request_id=%s method=%s path=%s elapsed_ms=%.1f error_type=%s client_version=%s client_build=%s server_build=%s",
            request_id,
            request.method,
            _route_path(request),
            elapsed_ms,
            type(exc).__name__,
            client_version, client_build, server_build,
        )
        raise
    finally:
        request_id_context.reset(context_token)


def register_slow_query_logging(
    engine: Engine,
    slow_query_threshold_ms: int,
) -> None:
    @event.listens_for(engine, "before_cursor_execute")
    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        timers = conn.info.setdefault(_QUERY_TIMER_KEY, [])
        timers.append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        started_at = _pop_query_timer(conn)
        if started_at is None:
            return
        _log_slow_query(statement, started_at, slow_query_threshold_ms, failed=False)

    @event.listens_for(engine, "handle_error")
    def handle_error(exception_context: ExceptionContext):
        conn = exception_context.connection
        if conn is None:
            return
        started_at = _pop_query_timer(conn)
        if started_at is None:
            return
        statement = exception_context.statement or "UNKNOWN"
        _log_slow_query(statement, started_at, slow_query_threshold_ms, failed=True)


def _pop_query_timer(conn) -> float | None:
    timers = conn.info.get(_QUERY_TIMER_KEY)
    if not timers:
        return None
    return timers.pop()


def _log_slow_query(
    statement: str,
    started_at: float,
    threshold_ms: int,
    *,
    failed: bool,
) -> None:
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    if elapsed_ms < threshold_ms:
        return

    statement_type = statement.lstrip().split(maxsplit=1)[0].upper()[:20] or "UNKNOWN"
    database_logger.warning(
        "slow_query request_id=%s statement_type=%s elapsed_ms=%.1f failed=%s",
        request_id_context.get(),
        statement_type,
        elapsed_ms,
        failed,
    )


def _request_id_from_request(request: Request) -> str:
    return getattr(request.state, "request_id", request_id_context.get())


def _database_error_response(
    request: Request,
    *,
    status_code: int,
    detail: str,
) -> JSONResponse:
    request_id = _request_id_from_request(request)
    response = JSONResponse(
        status_code=status_code,
        content={"detail": detail, "request_id": request_id},
    )
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def _sqlstate(error: OperationalError) -> str | None:
    original = error.orig
    return getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)


async def database_pool_timeout_handler(
    request: Request,
    exc: SQLAlchemyTimeoutError,
) -> JSONResponse:
    database_logger.warning(
        "database_pool_timeout request_id=%s",
        _request_id_from_request(request),
    )
    return _database_error_response(
        request,
        status_code=503,
        detail="데이터베이스가 사용 중입니다. 잠시 후 다시 시도하세요.",
    )


async def database_operational_error_handler(
    request: Request,
    exc: OperationalError,
) -> JSONResponse:
    sqlstate = _sqlstate(exc)
    is_query_timeout = sqlstate == "57014"
    database_logger.warning(
        "database_operational_error request_id=%s sqlstate=%s query_timeout=%s",
        _request_id_from_request(request),
        sqlstate or "unknown",
        is_query_timeout,
    )
    return _database_error_response(
        request,
        status_code=504 if is_query_timeout else 503,
        detail=(
            "데이터베이스 처리 시간이 초과되었습니다. 처리 결과를 확인한 후 다시 시도하세요."
            if is_query_timeout
            else "데이터베이스에 연결할 수 없습니다. 잠시 후 다시 시도하세요."
        ),
    )


def configure_database_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        SQLAlchemyTimeoutError,
        database_pool_timeout_handler,
    )
    app.add_exception_handler(
        OperationalError,
        database_operational_error_handler,
    )
