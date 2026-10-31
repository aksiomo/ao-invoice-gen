from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class PurchaseItem(BaseModel):
    """规范化后的一条采购明细。name 必须与输入文件单元格逐字符一致。"""

    receipt_no: str = ""
    receipt_date: str = ""
    supplier: str = ""
    item_code: str = ""
    name: str
    spec_input: str = ""
    unit: str = ""
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class ExtractResult(BaseModel):
    items: list[PurchaseItem] = Field(default_factory=list)


class ClassifiedItem(BaseModel):
    name: str
    code: str
    category_name: str
    short_name: str = ""
    from_cache: bool = False


class FinalRow(BaseModel):
    name: str
    code: str
    category_name: str
    unit: str
    quantity: Decimal | None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    tax_rate: Decimal
    from_cache: bool = False
    receipt_no: str = ""
    amount_warning: bool = False
