from typing import Optional

from pydantic import BaseModel

from src.database.models import UserGroupEnum


class UserGroupPatch(BaseModel):
    group: UserGroupEnum


class GroupOut(BaseModel):
    id: int
    name: UserGroupEnum

    class Config:
        from_attributes = True


class UserAdminOut(BaseModel):
    id: int
    email: str
    is_active: bool
    group: Optional[UserGroupEnum] = None


class AdminBootstrapInfo(BaseModel):
    """Shows whether optional startup bootstrap is configured (no secrets)."""

    bootstrap_configured: bool
    admin_exists: bool
