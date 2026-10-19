import hashlib

from fastapi import HTTPException
from sqlalchemy import func, select, update, text
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.models.partner import Partner
from app.models.product import Product
from app.models.partner_product_mapping import PartnerProductMapping, UnprintedProductCodeCounter
from app.schemas.partner_product_mapping import PartnerProductMappingCreate, PartnerProductMappingOut


def generate_unprinted_code(db: Session) -> str:
    # Atomic UPDATE serializes simultaneous registrations; rollback also rolls back the counter.
    while True:
        value = db.execute(update(UnprintedProductCodeCounter)
            .where(UnprintedProductCodeCounter.counter_id == 1)
            .values(next_value=UnprintedProductCodeCounter.next_value + 1)
            .returning(UnprintedProductCodeCounter.next_value - 1)).scalar_one_or_none()
        if value is None:
            raise HTTPException(status_code=409, detail="무지 내부코드 발급 설정이 없습니다. DB 업데이트를 확인하세요.")
        code = f"MES-U{value:06d}"
        if not db.scalar(select(Product.product_id).where(Product.product_code == code)):
            return code


def lock_erp_code(db: Session, code: str) -> None:
    # Serialize cross-table namespace checks on PostgreSQL, including bulk registration.
    if db.get_bind().dialect.name == "postgresql":
        key = int.from_bytes(hashlib.sha256(("erp-product:" + code.strip().upper()).encode()).digest()[:8], "big", signed=True)
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def ensure_legacy_code_available(db: Session, code: str) -> None:
    lock_erp_code(db, code)
    if db.scalar(select(PartnerProductMapping.mapping_id).where(
        PartnerProductMapping.erp_product_code == code.strip().upper()).limit(1)):
        raise HTTPException(status_code=409, detail="무지 거래처 연결에 사용된 ERP 코드입니다. 별도관리 품목으로 등록하세요.")


def create_mapping(db: Session, product_id: int, payload: PartnerProductMappingCreate, *, actor: str):
    lock_erp_code(db, payload.erp_product_code)
    product = db.scalar(select(Product).where(Product.product_id == product_id).with_for_update())
    if not product or not product.is_active or not product.is_unprinted_managed:
        raise HTTPException(status_code=409, detail="사용 중인 무지 별도관리 품목에만 거래처를 연결할 수 있습니다.")
    partner = db.scalar(select(Partner).where(Partner.partner_id == payload.partner_id).with_for_update(read=True))
    if not partner or not partner.is_active or partner.partner_type != "CUSTOMER":
        raise HTTPException(status_code=400, detail="사용 중인 고객 거래처를 선택하세요.")
    # Do not shadow an existing printed/legacy code. Conversion is an explicit separate action.
    if db.scalar(select(Product.product_id).where(
        func.upper(func.trim(Product.product_code)) == payload.erp_product_code,
        Product.is_unprinted_managed.is_(False)).limit(1)):
        raise HTTPException(status_code=409, detail="동일 코드의 기존 품목이 있습니다. 무지 품목인지 확인 후 해당 품목을 먼저 별도관리로 전환하세요.")
    if db.scalar(select(PartnerProductMapping.mapping_id).where(
        PartnerProductMapping.partner_id == payload.partner_id,
        PartnerProductMapping.erp_product_code == payload.erp_product_code,
        PartnerProductMapping.is_active.is_(True))):
        raise HTTPException(status_code=409, detail="이 거래처와 ERP 코드는 이미 연결되어 있습니다.")
    obj = PartnerProductMapping(product_id=product_id, **payload.model_dump(), created_by=actor)
    db.add(obj)
    db.flush()
    return obj


def deactivate_mapping(db: Session, product_id: int, mapping_id: int, *, actor: str):
    obj = db.scalar(select(PartnerProductMapping).where(
        PartnerProductMapping.mapping_id == mapping_id,
        PartnerProductMapping.product_id == product_id).with_for_update())
    if not obj:
        raise HTTPException(status_code=404, detail="거래처 연결을 찾을 수 없습니다.")
    if obj.is_active:
        obj.is_active = False
        obj.deactivated_by = actor
        obj.deactivated_at = utc_now()
        db.flush()
    return obj


def list_mappings(db: Session, product_id: int, *, page: int, size: int, is_active: bool | None):
    filters = [PartnerProductMapping.product_id == product_id]
    if is_active is not None:
        filters.append(PartnerProductMapping.is_active == is_active)
    total = db.scalar(select(func.count()).select_from(PartnerProductMapping).where(*filters))
    rows = db.execute(select(PartnerProductMapping, Partner.name)
        .join(Partner, Partner.partner_id == PartnerProductMapping.partner_id)
        .where(*filters).order_by(PartnerProductMapping.mapping_id.desc())
        .offset((page - 1) * size).limit(size)).all()
    items = []
    for mapping, name in rows:
        item = PartnerProductMappingOut.model_validate(mapping)
        item.partner_name = name
        items.append(item)
    return dict(items=items, total=total, page=page, size=size)


def resolve_erp_product(db: Session, partner_id: int | None, code: str, *, lock: bool = False):
    normalized = code.strip().upper()
    stmt = select(PartnerProductMapping).where(
        PartnerProductMapping.partner_id == partner_id,
        PartnerProductMapping.erp_product_code == normalized,
        PartnerProductMapping.is_active.is_(True))
    if lock:
        stmt = stmt.with_for_update(read=True)
    mapping = db.scalar(stmt.execution_options(populate_existing=True))
    if mapping:
        product_stmt = select(Product).where(Product.product_id == mapping.product_id)
        if lock:
            product_stmt = product_stmt.with_for_update(read=True)
        product = db.scalar(product_stmt.execution_options(populate_existing=True))
        if not product or not product.is_active or not product.is_unprinted_managed:
            raise HTTPException(status_code=409, detail="연결된 무지 품목이 미사용 상태입니다.")
        return product, mapping
    if db.scalar(select(PartnerProductMapping.mapping_id).where(
        PartnerProductMapping.erp_product_code == normalized).limit(1)):
        raise HTTPException(status_code=409, detail="무지 품목의 거래처별 연결이 필요합니다. 품목관리에서 연결 후 다시 검증하세요.")
    product_stmt = select(Product).where(Product.product_code == code, Product.is_active.is_(True))
    if lock:
        product_stmt = product_stmt.with_for_update()
    product = db.scalar(product_stmt.execution_options(populate_existing=True))
    if not product:
        raise HTTPException(status_code=409, detail="MES 품목코드 매핑 실패")
    if product.is_unprinted_managed:
        raise HTTPException(status_code=409, detail="무지 품목의 거래처별 ERP 코드 연결이 필요합니다.")
    return product, None


def manual_order_source(db: Session, product: Product, partner_id: int) -> dict:
    if not product.is_unprinted_managed:
        return {}
    mappings = db.scalars(select(PartnerProductMapping).where(
        PartnerProductMapping.product_id == product.product_id,
        PartnerProductMapping.partner_id == partner_id,
        PartnerProductMapping.is_active.is_(True)).with_for_update(read=True)).all()
    if len(mappings) != 1:
        raise HTTPException(status_code=409, detail="이 거래처의 품목 연결을 확인하세요. ERP 코드가 여러 개이면 엑셀 수주등록으로 구분하세요.")
    mapping = mappings[0]
    return dict(source_erp_product_code=mapping.erp_product_code,
                source_product_name=mapping.customer_product_name,
                source_product_spec=mapping.customer_product_spec)
