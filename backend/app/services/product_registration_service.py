from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.partner_product_mapping_service import ensure_legacy_code_available, generate_unprinted_code


def prepare_product(db: Session, payload: ProductCreate) -> Product:
    data = payload.model_dump()
    if payload.is_unprinted_managed:
        data["product_code"] = generate_unprinted_code(db)
    else:
        ensure_legacy_code_available(db, payload.product_code)
    return Product(**data)


def validate_management_change(db: Session, obj: Product, payload: ProductUpdate) -> None:
    if obj.is_unprinted_managed:
        if payload.is_unprinted_managed is False:
            raise HTTPException(status_code=409, detail="무지 별도관리 품목은 기존 방식으로 되돌릴 수 없습니다.")
        if payload.drawing_id is not None and payload.drawing_id != obj.drawing_id:
            raise HTTPException(status_code=409, detail="무지 별도관리 품목의 도면은 교체할 수 없습니다. 다른 도면은 새 품목으로 등록하세요.")
    elif payload.is_unprinted_managed:
        # Explicit opt-in preserves this product's ID, code, drawing and existing orders.
        if payload.drawing_id is not None and payload.drawing_id != obj.drawing_id:
            raise HTTPException(status_code=409, detail="별도관리 전환과 도면 변경을 동시에 할 수 없습니다.")
        obj.is_unprinted_managed = True
