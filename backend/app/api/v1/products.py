from fastapi import APIRouter, Depends, Query, Path, status, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.session import get_db, set_local_statement_timeout
from app.models.product import Product
from app.models.drawing import Drawing
from app.models.routing_template import RoutingTemplate
from app.models.product_inventory import ProductInventory
from app.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductOut,
    ProductListOut,
    ProductBulkCreateRequest,
    ProductBulkCreateResult,
)
from app.crud.product import product_crud
from app.services.bulk.product_bulk_service import product_bulk_service
from app.services.product_query import list_products_for_grid



router = APIRouter(prefix="/products", tags=["Product"])





def _to_product_out(db: Session, obj: Product) -> ProductOut:
    out = ProductOut.model_validate(obj, from_attributes=True)

    if obj.drawing is not None:
        out.drawing_no = obj.drawing.drawing_no
    else:
        out.drawing_no = None

    if obj.routing_template is not None:
        out.routing_template_name = obj.routing_template.template_name
    else:
        out.routing_template_name = None

    current_qty = db.execute(
        select(func.coalesce(ProductInventory.current_qty, 0))
        .where(ProductInventory.product_id == obj.product_id)
    ).scalar_one_or_none()

    out.current_stock_qty = int(current_qty or 0)

    return out

def _ensure_drawing_exists(db: Session, drawing_id: int):
    if not db.query(Drawing.drawing_id).filter(Drawing.drawing_id == drawing_id, Drawing.is_active == True).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="drawing_id not found")


def _ensure_routing_template_exists(db: Session, routing_template_id: int):
    if not db.query(RoutingTemplate.routing_template_id).filter(
        RoutingTemplate.routing_template_id == routing_template_id,
        RoutingTemplate.is_active == True,
    ).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="routing_template_id not found")


def _ensure_fk_exists(db: Session, drawing_id: int, routing_template_id: int):
    _ensure_drawing_exists(db, drawing_id)
    _ensure_routing_template_exists(db, routing_template_id)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    _ensure_fk_exists(db, payload.drawing_id, payload.routing_template_id)

    obj = Product(
        product_code=payload.product_code,
        product_name=payload.product_name,
        uom=payload.uom,
        drawing_id=payload.drawing_id,
        routing_template_id=payload.routing_template_id,
        panel_width_mm=payload.panel_width_mm,
        panel_length_mm=payload.panel_length_mm,
        product_spec=payload.product_spec,
        cut_qty_per_panel=payload.cut_qty_per_panel,
        is_active=payload.is_active,
        memo=payload.memo,
    )

    try:
        created = product_crud.create(db, obj)
        db.refresh(created, attribute_names=["drawing", "routing_template"])
        return _to_product_out(db, created)
    except IntegrityError:
        db.rollback()

        # 1) product_code 중복
        if db.query(Product.product_id).filter(Product.product_code == payload.product_code).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="product_code already exists")

        # 2) drawing_id 1:1 중복
        if db.query(Product.product_id).filter(Product.drawing_id == payload.drawing_id).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="drawing_id already assigned to another product")

        # 그 외
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")
    

@router.post("/bulk", response_model=ProductBulkCreateResult, status_code=status.HTTP_201_CREATED)
def create_products_bulk(
    payload: ProductBulkCreateRequest,
    db: Session = Depends(get_db),
):
    set_local_statement_timeout(db)
    return product_bulk_service.create_bulk(db, payload)    


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int = Path(..., ge=1), db: Session = Depends(get_db)):
    obj = product_crud.get_or_404(db, product_id, active_only=True)
    return _to_product_out(db, obj)


@router.get("", response_model=ProductListOut)
def list_products(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    q: str | None = Query(None),
    partner_q: str | None = Query(None),
    is_active: bool | None = Query(True),
    db: Session = Depends(get_db),
):
    items, total = list_products_for_grid(
        db,
        page=page,
        size=size,
        q=q,
        partner_q=partner_q,
        is_active=is_active,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
    }


@router.patch("/{product_id}", response_model=ProductOut)
def update_product(
    product_id: int = Path(..., ge=1),
    payload: ProductUpdate = None,
    db: Session = Depends(get_db),
):
    obj = product_crud.get_or_404(db, product_id, active_only=False)

    # FK 변경이 들어오는 경우만 검증
    new_drawing_id = payload.drawing_id if payload.drawing_id is not None else obj.drawing_id
    new_rt_id = payload.routing_template_id if payload.routing_template_id is not None else obj.routing_template_id
    if payload.drawing_id is not None or payload.routing_template_id is not None:
        _ensure_fk_exists(db, new_drawing_id, new_rt_id)

    # 필드 반영
    if payload.product_name is not None:
        obj.product_name = payload.product_name
    if payload.uom is not None:
        obj.uom = payload.uom
    if payload.drawing_id is not None:
        obj.drawing_id = payload.drawing_id
    if payload.routing_template_id is not None:
        obj.routing_template_id = payload.routing_template_id

    if payload.panel_width_mm is not None:
        obj.panel_width_mm = payload.panel_width_mm
    if payload.panel_length_mm is not None:
        obj.panel_length_mm = payload.panel_length_mm
    if payload.product_spec is not None:
        obj.product_spec = payload.product_spec
    if payload.cut_qty_per_panel is not None:
        obj.cut_qty_per_panel = payload.cut_qty_per_panel

    if payload.is_active is not None:
        obj.is_active = payload.is_active
    if payload.memo is not None:
        obj.memo = payload.memo

    try:
        updated = product_crud.commit(db, obj)
        db.refresh(updated, attribute_names=["drawing", "routing_template"])
        return _to_product_out(db, updated)
    except IntegrityError:
        db.rollback()

        # drawing_id 1:1 위반 체크 (본인 제외)
        if payload.drawing_id is not None:
            exists = (
                db.query(Product.product_id)
                .filter(Product.drawing_id == payload.drawing_id, Product.product_id != obj.product_id)
                .first()
            )
            if exists:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="drawing_id already assigned to another product",
                )

        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="conflict")


@router.delete("/{product_id}", response_model=ProductOut)
def delete_product(product_id: int = Path(..., ge=1), db: Session = Depends(get_db)):
    # soft delete
    deleted = product_crud.soft_delete(db, product_id)
    db.refresh(deleted, attribute_names=["drawing", "routing_template"])
    return _to_product_out(db, deleted)
