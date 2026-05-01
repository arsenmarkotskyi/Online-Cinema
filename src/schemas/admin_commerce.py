from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.database.models import OrderStatus, PaymentStatus
from src.schemas.orders import OrderItemOut
from src.schemas.payments import PaymentItemOut


class AdminOrderOut(BaseModel):
    """Order row for admin listing (includes owner)."""

    model_config = ConfigDict(use_enum_values=True)

    id: int
    user_id: int
    user_email: str
    created_at: datetime
    status: OrderStatus
    total_amount: Optional[float] = None
    items: List[OrderItemOut] = Field(default_factory=list)


class AdminPaymentOut(BaseModel):
    """Payment row for admin listing (includes payer)."""

    model_config = ConfigDict(use_enum_values=True)

    id: int
    user_id: int
    user_email: str
    order_id: int
    created_at: datetime
    status: PaymentStatus
    amount: float
    external_payment_id: Optional[str] = None
    items: List[PaymentItemOut] = Field(default_factory=list)


class AdminCartItemOut(BaseModel):
    """Single line in a user's cart (moderator view)."""

    movie_id: int
    name: str
    year: int
    price: float
    added_at: Optional[datetime] = None


class AdminCartOut(BaseModel):
    """Cart snapshot for moderator listing."""

    user_id: int
    user_email: str
    item_count: int
    subtotal: float
    items: List[AdminCartItemOut] = Field(default_factory=list)
