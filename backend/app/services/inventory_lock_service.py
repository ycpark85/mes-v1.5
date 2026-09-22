from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.product_inventory import ProductInventory


def lock_product_inventory(db: Session, product_id: int) -> ProductInventory:
    # Lock the persistent product even when its inventory row has not been created yet.
    product = db.execute(select(Product).where(Product.product_id == product_id)
                         .with_for_update()).scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    inventory = db.execute(select(ProductInventory).where(
        ProductInventory.product_id == product_id,
    ).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if inventory is None:
        inventory = ProductInventory(product_id=product_id, current_qty=0)
        db.add(inventory)
        db.flush()
    return inventory
