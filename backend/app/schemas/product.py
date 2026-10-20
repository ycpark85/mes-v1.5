from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional


class ProductCreate(BaseModel):
    product_code: Optional[str] = Field(None, max_length=60)
    is_unprinted_managed: bool = False
    product_name: str = Field(..., max_length=200)
    uom: str = Field(..., max_length=10)

    drawing_id: int = Field(..., ge=1)
    routing_template_id: int = Field(..., ge=1)

    panel_width_mm: Optional[int] = Field(None, ge=0)
    panel_length_mm: Optional[int] = Field(None, ge=0)
    product_spec: Optional[str] = Field(None, max_length=100)
    cut_qty_per_panel: Optional[int] = Field(None, ge=0)

    is_active: bool = True
    memo: Optional[str] = None

    @model_validator(mode="after")
    def validate_code_mode(self):
        if self.is_unprinted_managed:
            if self.product_code and self.product_code.strip():
                raise ValueError("무지 별도관리 품목코드는 서버에서 자동 발급합니다.")
        elif not self.product_code or not self.product_code.strip():
            raise ValueError("product_code is required")
        if not self.product_name.strip() or not self.uom.strip():
            raise ValueError("product_name and uom are required")
        return self


class ProductUpdate(BaseModel):
    is_unprinted_managed: Optional[bool] = None
    product_name: Optional[str] = Field(None, max_length=200)
    uom: Optional[str] = Field(None, max_length=10)

    drawing_id: Optional[int] = Field(None, ge=1)
    routing_template_id: Optional[int] = Field(None, ge=1)

    panel_width_mm: Optional[int] = Field(None, ge=0)
    panel_length_mm: Optional[int] = Field(None, ge=0)
    product_spec: Optional[str] = Field(None, max_length=100)
    cut_qty_per_panel: Optional[int] = Field(None, ge=0)

    is_active: Optional[bool] = None
    memo: Optional[str] = None

    @model_validator(mode="after")
    def validate_product_name(self):
        if self.product_name is not None and not self.product_name.strip():
            raise ValueError("product_name must not be blank")
        return self


class ProductOut(BaseModel):
    is_unprinted_managed: bool = False
    product_id: int
    product_code: str
    product_name: str
    uom: str

    drawing_id: int
    routing_template_id: int
    drawing_no: Optional[str] = None
    routing_template_name: Optional[str] = None

    panel_width_mm: Optional[int] = None
    panel_length_mm: Optional[int] = None
    product_spec: Optional[str] = None
    cut_qty_per_panel: Optional[int] = None

    is_active: bool
    memo: Optional[str] = None
    current_stock_qty: int = 0
    model_config = ConfigDict(from_attributes=True)


class ProductListOut(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    size: int

class ProductBulkItem(BaseModel):
    row_number: int = Field(..., ge=1)
    product_code: str = Field(..., max_length=60)
    product_name: str = Field(..., max_length=200)
    uom: str = Field(..., max_length=10)
    drawing_no: str = Field(..., max_length=60)
    template_code: str = Field(..., max_length=50)
    panel_width_mm: Optional[int] = Field(None, ge=0)
    panel_length_mm: Optional[int] = Field(None, ge=0)
    product_spec: Optional[str] = Field(None, max_length=100)
    cut_qty_per_panel: Optional[int] = Field(None, ge=0)
    is_active: bool = True
    memo: Optional[str] = None


class ProductBulkCreateRequest(BaseModel):
    items: list[ProductBulkItem] = Field(..., min_length=1)


class ProductBulkError(BaseModel):
    row_number: int
    field: str
    message: str


class ProductBulkCreateResult(BaseModel):
    total_count: int
    success_count: int
    failure_count: int
    created_items: list[ProductOut]
    errors: list[ProductBulkError]
