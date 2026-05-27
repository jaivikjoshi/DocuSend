from typing import List, Optional

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    description: str = ""
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    total: Optional[float] = None
    confidence: float = 0.0


class ExtractedDocument(BaseModel):
    file_name: str
    status: str = "processed"
    document_type: str = "unknown"
    vendor: str = ""
    date: str = ""
    invoice_number: Optional[str] = None
    currency: str = "USD"
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    tip: Optional[float] = None
    discount: Optional[float] = None
    total: Optional[float] = None
    payment_method: Optional[str] = None
    line_items: List[LineItem] = Field(default_factory=list)
    raw_text: str = ""
    confidence: float = 0.0
    warnings: List[str] = Field(default_factory=list)


EDITABLE_DOCUMENT_COLUMNS = [
    "file_name",
    "status",
    "document_type",
    "vendor",
    "date",
    "invoice_number",
    "currency",
    "subtotal",
    "tax",
    "tip",
    "discount",
    "total",
    "payment_method",
    "confidence",
    "warnings",
]


LINE_ITEM_COLUMNS = [
    "file_name",
    "description",
    "quantity",
    "unit_price",
    "total",
    "confidence",
]
