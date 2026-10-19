from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PartnerProductMappingCreate(BaseModel):
    partner_id: int = Field(..., ge=1)
    erp_product_code: str = Field(..., min_length=1, max_length=60)
    customer_product_name: str = Field(..., min_length=1, max_length=200)
    customer_product_spec: str | None = Field(None, max_length=100)

    @field_validator("erp_product_code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        value = value.strip().upper()
        if not value or len(value) > 60:
            raise ValueError("ERP 품목코드는 1~60자여야 합니다.")
        return value

    @field_validator("customer_product_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("거래처 품명은 필수입니다.")
        return value.strip()

    @field_validator("customer_product_spec")
    @classmethod
    def normalize_spec(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class PartnerProductMappingOut(PartnerProductMappingCreate):
    model_config = ConfigDict(from_attributes=True)
    mapping_id: int
    product_id: int
    partner_name: str | None = None
    is_active: bool
    created_at: datetime


class PartnerProductMappingListOut(BaseModel):
    items: list[PartnerProductMappingOut]
    total: int
    page: int
    size: int
