"""Recording AI token usage and reporting it for the admin area.

Every AI run writes one ``AIUsage`` row, also when it fails (the provider still
bills the requests that were made). Reports group these rows by activity, stage,
article, user, project, model, day or month.
"""

import csv
import io
import logging
from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic_ai.messages import ModelMessage, ModelResponse
from sqlalchemy import case, distinct, func
from sqlmodel import Session, select

from app.core.config import get_settings
from app.features.projects.models import Project
from app.features.research.models import Article
from app.features.users.models import User
from .models import AIActivity, AIUsage

logger = logging.getLogger(__name__)

GroupBy = Literal[
    "activity", "stage", "article", "user", "project", "model", "day", "month"
]

DELETED_PROJECT = "Deleted project"
UNKNOWN_USER = "Unknown or deleted user"
DELETED_ARTICLE = "Deleted article"
NO_STAGE = "No stage"


# --- Recording -------------------------------------------------------------------


def _configured_price(model_name: str) -> Optional[dict[str, float]]:
    """Prices from ``AI_MODEL_PRICES`` for the model: exact name, else the longest
    configured name it starts with (providers add date suffixes)."""
    prices = get_settings().ai_model_prices
    if model_name in prices:
        return prices[model_name]
    matches = [name for name in prices if model_name.startswith(name)]
    return prices[max(matches, key=len)] if matches else None


def price_response(response: ModelResponse) -> Optional[float]:
    """Estimated USD cost of one model response, or None if it cannot be priced."""
    usage = response.usage
    price = _configured_price(response.model_name or "")
    if price is not None:
        input_price = price.get("input", 0.0)
        cache_read = usage.cache_read_tokens
        cache_write = usage.cache_write_tokens
        uncached = max(usage.input_tokens - cache_read - cache_write, 0)
        return (
            uncached * input_price
            + cache_read * price.get("cache_read", input_price)
            + cache_write * price.get("cache_write", input_price)
            + usage.output_tokens * price.get("output", 0.0)
        ) / 1_000_000
    if usage.cost is not None:
        return float(usage.cost)
    try:
        return float(response.cost().total_price)
    except Exception:  # unknown model or provider, missing usage
        return None


def usage_from_messages(messages: Sequence[ModelMessage]) -> dict[str, Any]:
    """Token totals and estimated cost of the model responses in a run."""
    responses = [m for m in messages if isinstance(m, ModelResponse)]
    totals: dict[str, Any] = {
        "requests": len(responses),
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "cost_usd": 0.0 if responses else None,
        "model_name": next(
            (r.model_name for r in reversed(responses) if r.model_name), None
        ),
    }
    for response in responses:
        usage = response.usage
        totals["input_tokens"] += usage.input_tokens
        totals["output_tokens"] += usage.output_tokens
        totals["cache_read_tokens"] += usage.cache_read_tokens
        totals["cache_write_tokens"] += usage.cache_write_tokens
        cost = price_response(response) if totals["cost_usd"] is not None else None
        totals["cost_usd"] = None if cost is None else totals["cost_usd"] + cost
    return totals


def add_usage(
    session: Session,
    messages: Sequence[ModelMessage],
    *,
    activity: AIActivity,
    stage: Optional[str],
    project_id: Optional[int],
    article_id: Optional[int],
    user_id: Optional[int],
    succeeded: bool,
    decision_id: Optional[int] = None,
) -> Optional[AIUsage]:
    """Add the usage row of an AI run to the session (the caller commits).

    Never raises: losing a usage row must not fail the screening itself.
    """
    try:
        totals = usage_from_messages(messages)
        row = AIUsage(
            activity=activity.value,
            stage=stage,
            model_name=(totals.pop("model_name") or get_settings().default_llm_model)[
                :200
            ],
            project_id=project_id,
            article_id=article_id,
            user_id=user_id,
            decision_id=decision_id,
            succeeded=succeeded,
            **totals,
        )
        session.add(row)
        return row
    except Exception:
        logger.exception("Failed to record AI usage for article %s", article_id)
        return None


# --- Reporting -------------------------------------------------------------------


def _bucket(session: Session, fmt: Literal["day", "month"]):
    """created_at as a ``YYYY-MM-DD`` / ``YYYY-MM`` string (UTC on PostgreSQL)."""
    if session.get_bind().dialect.name == "postgresql":
        return func.to_char(
            func.timezone("UTC", AIUsage.created_at),
            "YYYY-MM-DD" if fmt == "day" else "YYYY-MM",
        )
    return func.strftime("%Y-%m-%d" if fmt == "day" else "%Y-%m", AIUsage.created_at)


def _group_column(session: Session, group_by: str):
    return {
        "activity": AIUsage.activity,
        "stage": AIUsage.stage,
        "article": AIUsage.article_id,
        "user": AIUsage.user_id,
        "project": AIUsage.project_id,
        "model": AIUsage.model_name,
        "day": _bucket(session, "day"),
        "month": _bucket(session, "month"),
    }[group_by]


def _filters(
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    project_id: Optional[int] = None,
    user_id: Optional[int] = None,
    activity: Optional[str] = None,
    stage: Optional[str] = None,
    model: Optional[str] = None,
) -> list:
    conditions = []
    if start is not None:
        conditions.append(AIUsage.created_at >= start)
    if end is not None:
        conditions.append(AIUsage.created_at < end)
    if project_id is not None:
        conditions.append(AIUsage.project_id == project_id)
    if user_id is not None:
        conditions.append(AIUsage.user_id == user_id)
    if activity:
        conditions.append(AIUsage.activity == activity)
    if stage:
        conditions.append(AIUsage.stage == stage)
    if model:
        conditions.append(AIUsage.model_name == model)
    return conditions


_AGGREGATES = (
    func.count(AIUsage.id).label("runs"),
    func.coalesce(func.sum(case((AIUsage.succeeded.is_(False), 1), else_=0)), 0).label(
        "failed_runs"
    ),
    func.count(distinct(AIUsage.article_id)).label("articles"),
    func.coalesce(func.sum(AIUsage.requests), 0).label("requests"),
    func.coalesce(func.sum(AIUsage.input_tokens), 0).label("input_tokens"),
    func.coalesce(func.sum(AIUsage.output_tokens), 0).label("output_tokens"),
    func.coalesce(func.sum(AIUsage.cache_read_tokens), 0).label("cache_read_tokens"),
    func.coalesce(func.sum(AIUsage.cache_write_tokens), 0).label("cache_write_tokens"),
    func.coalesce(func.sum(AIUsage.cost_usd), 0.0).label("cost_usd"),
    func.coalesce(
        func.sum(
            case(
                (AIUsage.cost_usd.is_(None) & (AIUsage.requests > 0), 1),
                else_=0,
            )
        ),
        0,
    ).label("unpriced_runs"),
)


def _totals(row: Any) -> dict[str, Any]:
    data = {name: getattr(row, name) for name in (a.name for a in _AGGREGATES)}
    data["total_tokens"] = data["input_tokens"] + data["output_tokens"]
    data["cost_usd"] = round(float(data["cost_usd"]), 6)
    return data


def _labels(session: Session, group_by: str, keys: list[Any]) -> dict[Any, dict]:
    """Display label (and the project of an article) for each group key."""
    ids = [k for k in keys if k is not None]
    if group_by == "project":
        rows = session.exec(select(Project.id, Project.name).where(Project.id.in_(ids)))
        return {pid: {"label": name} for pid, name in rows.all()}
    if group_by == "user":
        rows = session.exec(select(User.id, User.email).where(User.id.in_(ids)))
        return {uid: {"label": email} for uid, email in rows.all()}
    if group_by == "article":
        rows = session.exec(
            select(Article.id, Article.title, Article.project_id).where(
                Article.id.in_(ids)
            )
        )
        return {
            aid: {"label": title, "project_id": project_id}
            for aid, title, project_id in rows.all()
        }
    return {}


_MISSING = {
    "project": DELETED_PROJECT,
    "user": UNKNOWN_USER,
    "article": DELETED_ARTICLE,
    "stage": NO_STAGE,
}


def report(
    session: Session,
    group_by: str,
    limit: Optional[int] = 100,
    **filters: Any,
) -> dict[str, Any]:
    """Usage totals and the usage of each group, largest token use first (oldest
    first by day and month)."""
    conditions = _filters(**filters)
    totals = session.exec(select(*_AGGREGATES).where(*conditions)).one()
    key = _group_column(session, group_by).label("key")
    group_count = session.exec(
        select(func.count()).select_from(
            select(key).where(*conditions).group_by(key).subquery()
        )
    ).one()
    stmt = select(key, *_AGGREGATES).where(*conditions).group_by(key)
    if group_by in ("day", "month"):
        stmt = stmt.order_by(key)
    else:
        stmt = stmt.order_by(
            (func.sum(AIUsage.input_tokens) + func.sum(AIUsage.output_tokens)).desc(),
            key,
        )
    if limit:
        stmt = stmt.limit(limit)
    rows = session.exec(stmt).all()
    labels = _labels(session, group_by, [r.key for r in rows])
    groups = []
    for r in rows:
        info = labels.get(r.key, {})
        if info.get("label"):
            label = info["label"]
        elif r.key is None or group_by in ("project", "user", "article"):
            label = _MISSING.get(group_by, "-")
        else:
            label = str(r.key)
        groups.append(
            {
                "key": None if r.key is None else str(r.key),
                "label": label,
                "project_id": info.get("project_id"),
                **_totals(r),
            }
        )
    return {
        "group_by": group_by,
        "totals": _totals(totals),
        "groups": groups,
        "group_count": group_count,
    }


GROUP_CSV_FIELDS = (
    "key",
    "label",
    "runs",
    "failed_runs",
    "articles",
    "requests",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "total_tokens",
    "cost_usd",
    "unpriced_runs",
)

RUN_CSV_FIELDS = (
    "id",
    "created_at",
    "activity",
    "stage",
    "model_name",
    "project_id",
    "project_name",
    "article_id",
    "decision_id",
    "user_id",
    "user_email",
    "succeeded",
    "requests",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "cost_usd",
)


def _csv(fields: Sequence[str], rows: Iterator[dict[str, Any]]) -> Iterator[str]:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    yield buffer.getvalue()
    for row in rows:
        buffer.seek(0)
        buffer.truncate()
        writer.writerow(row)
        yield buffer.getvalue()


def iter_groups_csv(session: Session, group_by: str, **filters: Any) -> Iterator[str]:
    """The report's groups as CSV (all of them)."""
    groups = report(session, group_by, limit=None, **filters)["groups"]
    return _csv(GROUP_CSV_FIELDS, iter(groups))


def iter_runs_csv(session: Session, **filters: Any) -> Iterator[str]:
    """Every AI run as CSV, oldest first (read before streaming starts)."""
    rows = session.exec(
        select(AIUsage, Project.name, User.email)
        .outerjoin(Project, Project.id == AIUsage.project_id)
        .outerjoin(User, User.id == AIUsage.user_id)
        .where(*_filters(**filters))
        .order_by(AIUsage.created_at, AIUsage.id)
    ).all()
    return _csv(
        RUN_CSV_FIELDS,
        (
            {
                **usage.model_dump(),
                "created_at": usage.created_at.isoformat(),
                "project_name": project_name,
                "user_email": email,
            }
            for usage, project_name, email in rows
        ),
    )


def month_totals(session: Session, since: datetime) -> dict[str, Any]:
    """Tokens and estimated cost since ``since`` (admin overview)."""
    return _totals(
        session.exec(select(*_AGGREGATES).where(AIUsage.created_at >= since)).one()
    )
