from datetime import datetime
from typing import Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class PlanSummary(BaseModel):
    tier: str
    fulltext_limit: int
    activated_at: datetime
    expires_at: datetime
    source: str
    amount_paid_cents: int
    active: bool


class AdminProject(BaseModel):
    id: int
    name: str
    owner_id: int
    owner_email: Optional[str]
    owner_name: Optional[str]
    created_at: Optional[datetime]
    article_count: int
    ai_fulltext_used: int
    plan: Optional[PlanSummary]
    state: Literal["free", "active", "expiring", "expired"]


class AdminUser(BaseModel):
    id: int
    email: str
    name: str
    is_active: bool
    is_superuser: bool
    is_verified: bool
    created_at: Optional[datetime]
    project_count: int
    active_passes: int
    ai_fulltext_used: int


class AdminUserDetail(AdminUser):
    projects: list[AdminProject]
    payments_total_cents: int


class UserUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None


class AdminPayment(BaseModel):
    id: int
    created_at: datetime
    project_id: Optional[int]
    project_name: str
    user_id: Optional[int]
    user_email: Optional[str]
    tier: str
    kind: str
    amount_cents: int
    refunded_cents: int
    currency: str
    status: str
    dashboard_url: Optional[str]


class GrantRequest(BaseModel):
    tier: str = Field(description="pass_250 | pass_1000 | custom")
    fulltext_limit: Optional[int] = Field(default=None, ge=1)
    days: int = Field(default=365, ge=1, le=3650)


class PlanUpdate(BaseModel):
    fulltext_limit: Optional[int] = Field(default=None, ge=1)
    expires_at: Optional[datetime] = None


class Overview(BaseModel):
    users_total: int
    users_new_30d: int
    projects_total: int
    active_passes: int
    expiring_30d: int
    revenue_month_cents: int
    revenue_total_cents: int
    payments_month: int
    ai_fulltext_month: int
    ai_title_abstract_month: int
    ai_tokens_month: int
    ai_cost_month_usd: float
    currency: str


class AIUsageTotals(BaseModel):
    runs: int
    failed_runs: int
    articles: int = Field(description="Distinct articles")
    requests: int
    input_tokens: int = Field(description="Cache reads and writes included")
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    total_tokens: int
    cost_usd: float = Field(description="Estimate, excluding unpriced runs")
    unpriced_runs: int


class AIUsageGroup(AIUsageTotals):
    key: Optional[str]
    label: str
    project_id: Optional[int] = Field(default=None, description="Article groups only")


class AIUsageReport(BaseModel):
    group_by: str
    totals: AIUsageTotals
    groups: list[AIUsageGroup]
    group_count: int
