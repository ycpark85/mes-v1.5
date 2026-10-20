from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.order_line import OrderLine
from app.models.product import Product


def preserve_legacy_order_product_snapshots(db: Session, product: Product) -> None:
    """Caller holds the product write lock; preserve current values before editing.

    This is a baseline capture, not a reconstruction of an unavailable ERP file.
    Existing snapshots, order identities and business timestamps stay untouched.
    """
    db.execute(
        update(OrderLine)
        .where(
            OrderLine.product_id == product.product_id,
            OrderLine.source_erp_product_code.is_(None),
        )
        .values(
            source_erp_product_code=product.product_code,
            source_product_name=product.product_name,
            source_product_spec=product.product_spec,
            updated_at=OrderLine.updated_at,
        )
    )
