from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.database.models import PaymentStatus


class PaymentItemOut(BaseModel):
    order_item_id: int
    movie_name: str
    price_at_payment: float


class PaymentOut(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: int
    order_id: int
    created_at: datetime
    status: PaymentStatus
    amount: float
    external_payment_id: Optional[str] = None
    items: List[PaymentItemOut] = Field(default_factory=list)


class CheckoutSessionResponse(BaseModel):
    checkout_url: str
    session_id: str
