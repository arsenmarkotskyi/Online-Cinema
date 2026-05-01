from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.database.models import OrderStatus


class OrderItemOut(BaseModel):
    movie_id: int
    movie_name: str
    price_at_order: float


class OrderOut(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: int
    created_at: datetime
    status: OrderStatus
    total_amount: Optional[float] = None
    items: List[OrderItemOut] = Field(default_factory=list)


class OrderCreateResult(BaseModel):
    order: OrderOut
    excluded_already_purchased: List[int] = Field(default_factory=list)
    excluded_pending_order: List[int] = Field(default_factory=list)
    messages: List[str] = Field(default_factory=list)
