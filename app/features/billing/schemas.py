from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class Usage(BaseModel):
    used: int
    limit: int
    scope: Literal["project", "account"]


class PassOption(BaseModel):
    tier: str
    label: str
    fulltext_limit: int
    amount_cents: int
    kind: Literal["new", "renewal", "upgrade"]


class BillingStatus(BaseModel):
    billing_enabled: bool
    plan: str
    plan_label: str
    active: bool
    read_only: bool
    expires_at: Optional[datetime]
    full_text: Usage
    title_abstract: Usage
    dual_screening_allowed: bool
    currency: str
    options: list[PassOption]
    online_payment: bool


class PublicTier(BaseModel):
    tier: str
    label: str
    fulltext_limit: int
    price_cents: int


class FreeTier(BaseModel):
    fulltext_limit: int


class PublicPlans(BaseModel):
    billing_enabled: bool
    currency: str
    pass_duration_days: int
    free: FreeTier
    tiers: list[PublicTier]


class CheckoutRequest(BaseModel):
    tier: str


class CheckoutResponse(BaseModel):
    url: str
