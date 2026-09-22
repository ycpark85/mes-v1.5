"""Public compatibility metadata; contains no credentials or database details."""
import re
import hashlib
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel

from app.core.config import is_production_env, settings

INSPECTION_QUANTITY_RULE_VERSION = 2
MIN_WPF_CONTRACT_VERSION = 1
MAX_WPF_CONTRACT_VERSION = 1
CLIENT_CONTRACT_HEADER = "X-MES-Client-Contract"
CLIENT_VERSION_HEADER = "X-MES-Client-Version"
CLIENT_BUILD_HEADER = "X-MES-Client-Build"
SERVER_BUILD_HEADER = "X-MES-Server-Build"


def _source_build_id() -> str:
    """Fingerprint application source at process import, excluding configuration/data."""
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    try:
        for path in sorted(root.rglob("*.py")):
            digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
            digest.update(path.read_bytes() + b"\0")
        return "src-" + digest.hexdigest()[:40]
    except OSError:
        return "unknown"


SOURCE_BUILD_ID = _source_build_id()


def safe_build_identifier(value: str | None) -> str:
    return value if value and re.fullmatch(r"[A-Za-z0-9._-]{1,64}", value) else "unknown"


class RuntimeInfo(BaseModel):
    environment: str
    server_build: str
    min_wpf_contract_version: int
    max_wpf_contract_version: int
    inspection_quantity_rule_version: int


def get_runtime_info() -> RuntimeInfo:
    return RuntimeInfo(
        environment="Production" if is_production_env() else "Development",
        server_build=safe_build_identifier(settings.MES_SERVER_BUILD_ID
            if settings.MES_SERVER_BUILD_ID != "unknown" else SOURCE_BUILD_ID),
        min_wpf_contract_version=MIN_WPF_CONTRACT_VERSION,
        max_wpf_contract_version=MAX_WPF_CONTRACT_VERSION,
        inspection_quantity_rule_version=INSPECTION_QUANTITY_RULE_VERSION,
    )


def validate_inspection_client(contract: str | None, quantity_rule_version: int | None) -> None:
    if contract is None or not re.fullmatch(r"[0-9]{1,4}", contract) or not (
        MIN_WPF_CONTRACT_VERSION <= int(contract) <= MAX_WPF_CONTRACT_VERSION
    ) or quantity_rule_version != INSPECTION_QUANTITY_RULE_VERSION:
        # Old clients only understand a string detail. Keep the upgrade notice readable there.
        raise HTTPException(status_code=409,
            detail="실행 프로그램과 서버의 검수 규칙이 맞지 않습니다. 프로그램 업데이트 후 검수 화면을 다시 열어주세요.",
            headers={"X-MES-Error-Code": "CLIENT_UPDATE_REQUIRED"})
