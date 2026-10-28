"""Tests for AI token usage: recording every AI run and the admin usage reports."""

import csv
import io
import json
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage
from sqlmodel import Session, select

from app.core.config import get_settings
from app.features.ai_usage import services as ai_usage
from app.features.ai_usage.models import AIActivity, AIUsage
from app.features.criteria.models import Criterion, CriterionType
from app.features.projects.services import ProjectService
from app.features.research.agent import get_screening_agent, screen_article
from app.features.research.models import Article, ArticleStatus
from app.features.research.services import ArticleService
from app.features.screening import flows
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionType,
    ScreeningStage,
)

ADMIN = "api/v1/admin"
MODEL = "claude-test-1"
# USD per million tokens
PRICES = {MODEL: {"input": 3.0, "output": 15.0, "cache_read": 0.3}}


@pytest.fixture(autouse=True)
def prices(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_model_prices", PRICES)


@pytest.fixture
def project(session, a_user, a_project):
    project = a_project(a_user())
    project.review_question = "Does exercise help?"
    session.add(project)
    session.add(
        Criterion(
            project_id=project.id,
            type=CriterionType.inclusion,
            code="I1",
            description="Exercise",
            is_active=True,
        )
    )
    session.commit()
    return project


@pytest.fixture
def article(session, project):
    article = Article(project_id=project.id, title="Running and mood", abstract="Abs")
    session.add(article)
    session.commit()
    session.refresh(article)
    return article


def _criteria(session, project):
    return list(
        session.exec(select(Criterion).where(Criterion.project_id == project.id)).all()
    )


def _args(codes=("I1",)):
    return {
        "decision": "include",
        "confidence": 0.8,
        "criteria_evaluations": [
            {
                "criterion_code": c,
                "criterion_type": "inclusion" if c.startswith("I") else "exclusion",
                "met": True,
                "confidence": 0.8,
                "reasoning": "r",
            }
            for c in codes
        ],
        "primary_exclusion_reason": None,
        "summary_reasoning": "summary",
    }


def _model(responses, usage=None):
    """FunctionModel named MODEL that answers ``responses`` in order, each
    reporting ``usage`` (an Exception in ``responses`` is raised instead)."""
    calls = {"n": 0}

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        reply = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        if isinstance(reply, Exception):
            raise reply
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, json.dumps(reply))],
            usage=usage or RequestUsage(input_tokens=1000, output_tokens=100),
        )

    return FunctionModel(fn, model_name=MODEL)


async def _screen(session, project, article, model, **kwargs):
    with get_screening_agent().override(model=model):
        return await screen_article(
            article=article,
            criteria=_criteria(session, project),
            review_question=project.review_question,
            session=session,
            **kwargs,
        )


def _rows(session) -> list[AIUsage]:
    return list(session.exec(select(AIUsage).order_by(AIUsage.id)).all())


# --- Recording -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_run_records_tokens_cost_and_context(
    session, project, article
):
    user_id = project.owner_id
    decision = await _screen(
        session,
        project,
        article,
        _model([_args()]),
        activity=AIActivity.screening_batch,
        triggered_by=user_id,
    )

    [row] = _rows(session)
    assert row.succeeded is True
    assert row.activity == "screening_batch"
    assert row.stage == "title_abstract"
    assert row.model_name == MODEL
    assert (row.project_id, row.article_id, row.decision_id, row.user_id) == (
        project.id,
        article.id,
        decision.id,
        user_id,
    )
    assert (row.requests, row.input_tokens, row.output_tokens) == (1, 1000, 100)
    # 1000 * $3 + 100 * $15 per million tokens
    assert row.cost_usd == pytest.approx(0.0045)
    assert decision.reviewer_id is None  # AI decisions still never count as reviewers


@pytest.mark.asyncio
async def test_output_retries_add_up(session, project, article):
    session.add(
        Criterion(
            project_id=project.id,
            type=CriterionType.exclusion,
            code="E1",
            description="Children",
            is_active=True,
        )
    )
    session.commit()

    # First answer misses E1, so the validator makes the model try again
    model = _model([_args(("I1",)), _args(("I1", "E1"))])
    await _screen(session, project, article, model)

    [row] = _rows(session)
    assert row.succeeded is True
    assert (row.requests, row.input_tokens, row.output_tokens) == (2, 2000, 200)
    assert row.activity == "screening_single"  # the default
    assert row.user_id is None


@pytest.mark.asyncio
async def test_failed_run_still_records_the_tokens_it_used(session, project, article):
    # Never answers all criteria: the run gives up after its output retries
    session.add(
        Criterion(
            project_id=project.id,
            type=CriterionType.exclusion,
            code="E1",
            description="Children",
            is_active=True,
        )
    )
    session.commit()

    with pytest.raises(UnexpectedModelBehavior):
        await _screen(session, project, article, _model([_args(("I1",))]))

    [row] = _rows(session)
    assert row.succeeded is False
    assert row.decision_id is None
    assert row.requests == 3  # first try and two retries
    assert row.input_tokens == 3000
    assert row.cost_usd == pytest.approx(3 * 0.0045)
    assert article.ai_check_status == "error"


@pytest.mark.asyncio
async def test_provider_error_records_a_failed_run_without_tokens(
    session, project, article
):
    with pytest.raises(RuntimeError):
        await _screen(
            session, project, article, _model([RuntimeError("provider down")])
        )

    [row] = _rows(session)
    assert row.succeeded is False
    assert (row.requests, row.input_tokens, row.output_tokens) == (0, 0, 0)
    assert row.cost_usd is None
    assert row.model_name == get_settings().default_llm_model


@pytest.mark.asyncio
async def test_full_text_run_is_recorded_at_full_text(session, project, article):
    article.full_text_content = "Full text of the study."
    article.current_stage = ScreeningStage.full_text
    article.status = ArticleStatus.full_text_retrieved
    session.add(article)
    session.commit()

    await _screen(session, project, article, _model([_args()]))

    assert _rows(session)[0].stage == "full_text"


def test_price_uses_cache_prices_and_matches_dated_model_names():
    response = ModelResponse(
        parts=[],
        model_name=f"{MODEL}-20261001",
        usage=RequestUsage(
            input_tokens=1_000_000 + 2_000_000 + 500_000,
            cache_read_tokens=2_000_000,
            cache_write_tokens=500_000,
            output_tokens=1_000_000,
        ),
    )
    # uncached input 1M * 3 + cache reads 2M * 0.3 + cache writes 0.5M * 3
    # (no cache_write price: input price) + output 1M * 15
    assert ai_usage.price_response(response) == pytest.approx(3 + 0.6 + 1.5 + 15)


def test_unknown_model_is_not_priced():
    response = ModelResponse(
        parts=[],
        model_name="function:fn:",
        usage=RequestUsage(input_tokens=10, output_tokens=10),
    )
    assert ai_usage.price_response(response) is None
    totals = ai_usage.usage_from_messages([response, response])
    assert totals["cost_usd"] is None
    assert totals["input_tokens"] == 20


def test_builtin_price_table_is_used_for_unconfigured_models(monkeypatch):
    monkeypatch.setattr(get_settings(), "ai_model_prices", {})
    response = ModelResponse(
        parts=[],
        model_name="claude-sonnet-4-5",
        provider_name="anthropic",
        usage=RequestUsage(input_tokens=1_000_000, output_tokens=0),
    )
    assert ai_usage.price_response(response) > 0


# --- Who started the run ----------------------------------------------------------


def test_screen_ai_endpoint_records_the_user(
    session, auth_as, project, article, monkeypatch
):
    from app.features.users.models import User

    owner = session.get(User, project.owner_id)
    client, _ = auth_as(owner)
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "sk-test")
    seen = {}

    async def fake(**kwargs):
        seen.update(kwargs)
        decision = ScreeningDecision(
            article_id=article.id,
            stage=ScreeningStage.title_abstract,
            decision=ScreeningDecisionType.include,
            source=DecisionSource.ai_agent,
        )
        session.add(decision)
        session.commit()
        session.refresh(decision)
        return decision

    monkeypatch.setattr("app.features.screening.routers.screen_article", fake)
    res = client.post(
        f"api/v1/projects/{project.id}/screening/articles/{article.id}/screen-ai"
    )
    assert res.status_code == 200
    assert seen["activity"] == AIActivity.screening_single
    assert seen["triggered_by"] == owner.id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("targeted", "activity"),
    [(False, AIActivity.screening_batch), (True, AIActivity.screening_lookahead)],
)
async def test_batch_flow_records_activity_and_user(
    session, project, article, monkeypatch, targeted, activity
):
    monkeypatch.setattr(flows, "Session", lambda _engine: nullcontext(session))
    monkeypatch.setattr(
        flows.NotificationService, "notify_room", AsyncMock(return_value=1)
    )
    monkeypatch.setattr(
        flows.NotificationService, "notify_user_in_room", AsyncMock(return_value=True)
    )
    article.status = ArticleStatus.screening
    session.add(article)
    session.commit()

    real_screen = flows.screen_article

    async def with_model(**kwargs):
        with get_screening_agent().override(model=_model([_args()])):
            return await real_screen(**kwargs)

    monkeypatch.setattr(flows, "screen_article", with_model)
    await flows.batch_ai_screening_flow.fn(
        project.id, [article.id], project.owner_id, targeted
    )

    [row] = _rows(session)
    assert row.activity == activity.value
    assert row.user_id == project.owner_id


# --- Deletes keep the cost record -----------------------------------------------------


def _usage(session, **kwargs) -> AIUsage:
    defaults = {
        "activity": "screening_single",
        "stage": "title_abstract",
        "model_name": MODEL,
        "requests": 1,
        "input_tokens": 1000,
        "output_tokens": 100,
        "cost_usd": 0.0045,
    }
    row = AIUsage(**{**defaults, **kwargs})
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def test_deleting_an_article_keeps_its_usage(session, project, article):
    row = _usage(session, project_id=project.id, article_id=article.id)
    ArticleService(session).delete_article(article)
    session.refresh(row)
    assert row.article_id is None
    assert row.project_id == project.id


def test_deleting_a_project_keeps_its_usage(session, project, article):
    row = _usage(session, project_id=project.id, article_id=article.id)
    ProjectService(session).delete_project(project)
    session.refresh(row)
    assert (row.project_id, row.article_id) == (None, None)
    assert row.input_tokens == 1000


# --- Admin reports ---------------------------------------------------------------


@pytest.fixture
def usage_data(session, a_user, a_project, project, article):
    """Two projects, two users, mixed activities, stages and days."""
    other_user = a_user()
    other = a_project(other_user)
    other_article = Article(project_id=other.id, title="Other article")
    session.add(other_article)
    session.commit()
    now = datetime.now(timezone.utc)
    rows = [
        _usage(
            session,
            project_id=project.id,
            article_id=article.id,
            user_id=project.owner_id,
            created_at=now,
        ),
        _usage(
            session,
            project_id=project.id,
            article_id=article.id,
            user_id=project.owner_id,
            activity="screening_batch",
            stage="full_text",
            input_tokens=5000,
            output_tokens=500,
            cost_usd=0.0225,
            created_at=now,
        ),
        _usage(
            session,
            project_id=other.id,
            article_id=other_article.id,
            user_id=other_user.id,
            activity="screening_batch",
            succeeded=False,
            requests=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=None,
            created_at=now - timedelta(days=40),
        ),
        _usage(
            session,
            project_id=other.id,
            article_id=other_article.id,
            user_id=other_user.id,
            model_name="unpriced-model",
            cost_usd=None,
            created_at=now - timedelta(days=40),
        ),
    ]
    return {"project": project, "other": other, "other_user": other_user, "rows": rows}


def test_report_requires_admin(auth_client):
    assert auth_client.get(f"{ADMIN}/ai-usage").status_code == 403
    assert auth_client.get(f"{ADMIN}/ai-usage/export").status_code == 403


def test_report_totals_and_groups_by_project(admin_client, usage_data):
    res = admin_client.get(f"{ADMIN}/ai-usage", params={"group_by": "project"})
    assert res.status_code == 200
    body = res.json()

    totals = body["totals"]
    assert totals["runs"] == 4
    assert totals["failed_runs"] == 1
    assert totals["articles"] == 2
    assert totals["requests"] == 3
    assert totals["input_tokens"] == 7000
    assert totals["output_tokens"] == 700
    assert totals["total_tokens"] == 7700
    assert totals["cost_usd"] == pytest.approx(0.027)  # unpriced runs left out
    assert totals["unpriced_runs"] == 1  # the failed run made no requests

    assert body["group_count"] == 2
    first, second = body["groups"]  # most tokens first
    assert first["key"] == str(usage_data["project"].id)
    assert first["label"] == usage_data["project"].name
    assert first["total_tokens"] == 6600
    assert second["label"] == usage_data["other"].name
    assert second["runs"] == 2


@pytest.mark.parametrize(
    ("group_by", "expected"),
    [
        ("activity", {"screening_single": 2200, "screening_batch": 5500}),
        ("stage", {"title_abstract": 2200, "full_text": 5500}),
        ("model", {MODEL: 6600, "unpriced-model": 1100}),
    ],
)
def test_report_groups(admin_client, usage_data, group_by, expected):
    body = admin_client.get(f"{ADMIN}/ai-usage", params={"group_by": group_by}).json()
    assert {g["key"]: g["total_tokens"] for g in body["groups"]} == expected


def test_report_by_user_and_article(admin_client, usage_data, article):
    by_user = admin_client.get(f"{ADMIN}/ai-usage", params={"group_by": "user"}).json()
    labels = {g["label"] for g in by_user["groups"]}
    assert usage_data["other_user"].email in labels

    by_article = admin_client.get(
        f"{ADMIN}/ai-usage", params={"group_by": "article"}
    ).json()
    top = by_article["groups"][0]
    assert top["label"] == article.title
    assert top["project_id"] == usage_data["project"].id


def test_report_by_day_and_month_is_chronological(admin_client, usage_data):
    by_day = admin_client.get(f"{ADMIN}/ai-usage", params={"group_by": "day"}).json()
    days = [g["key"] for g in by_day["groups"]]
    assert days == sorted(days) and len(days) == 2
    assert len(days[0]) == len("2026-10-28")

    by_month = admin_client.get(
        f"{ADMIN}/ai-usage", params={"group_by": "month"}
    ).json()
    assert all(len(g["key"]) == len("2026-10") for g in by_month["groups"])


def test_report_filters(admin_client, usage_data):
    today = datetime.now(timezone.utc).date()
    recent = admin_client.get(
        f"{ADMIN}/ai-usage", params={"start": str(today - timedelta(days=7))}
    ).json()
    assert recent["totals"]["runs"] == 2

    old = admin_client.get(
        f"{ADMIN}/ai-usage", params={"end": str(today - timedelta(days=7))}
    ).json()
    assert old["totals"]["runs"] == 2

    one_day = admin_client.get(
        f"{ADMIN}/ai-usage", params={"start": str(today), "end": str(today)}
    ).json()
    assert one_day["totals"]["runs"] == 2

    project = admin_client.get(
        f"{ADMIN}/ai-usage", params={"project_id": usage_data["other"].id}
    ).json()
    assert project["totals"]["runs"] == 2

    user = admin_client.get(
        f"{ADMIN}/ai-usage", params={"user_id": usage_data["other_user"].id}
    ).json()
    assert user["totals"]["runs"] == 2

    batch = admin_client.get(
        f"{ADMIN}/ai-usage",
        params={"activity": "screening_batch", "stage": "full_text", "model": MODEL},
    ).json()
    assert batch["totals"]["runs"] == 1

    assert (
        admin_client.get(f"{ADMIN}/ai-usage", params={"group_by": "nope"}).status_code
        == 422
    )


def test_report_limit_keeps_the_group_count(admin_client, usage_data):
    body = admin_client.get(
        f"{ADMIN}/ai-usage", params={"group_by": "model", "limit": 1}
    ).json()
    assert len(body["groups"]) == 1
    assert body["group_count"] == 2


def test_report_labels_deleted_projects(admin_client, session, usage_data):
    ProjectService(session).delete_project(usage_data["other"])
    body = admin_client.get(f"{ADMIN}/ai-usage", params={"group_by": "project"}).json()
    labels = {g["key"]: g["label"] for g in body["groups"]}
    assert labels[None] == ai_usage.DELETED_PROJECT
    assert body["totals"]["runs"] == 4


def _csv_rows(res) -> list[dict]:
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    return list(csv.DictReader(io.StringIO(res.text)))


def test_export_runs(admin_client, usage_data):
    res = admin_client.get(f"{ADMIN}/ai-usage/export")
    assert "ai-usage-runs.csv" in res.headers["content-disposition"]
    rows = _csv_rows(res)
    assert len(rows) == 4
    assert rows[0]["project_name"] == usage_data["other"].name  # oldest first
    assert rows[0]["user_email"] == usage_data["other_user"].email
    assert set(ai_usage.RUN_CSV_FIELDS) == set(rows[0])


def test_export_groups(admin_client, usage_data):
    res = admin_client.get(
        f"{ADMIN}/ai-usage/export",
        params={"group_by": "activity", "project_id": usage_data["project"].id},
    )
    assert "ai-usage-by-activity.csv" in res.headers["content-disposition"]
    rows = _csv_rows(res)
    assert {r["key"]: int(r["total_tokens"]) for r in rows} == {
        "screening_single": 1100,
        "screening_batch": 5500,
    }


def test_overview_shows_this_months_tokens_and_cost(admin_client, usage_data):
    body = admin_client.get(f"{ADMIN}/overview").json()
    assert body["ai_tokens_month"] >= 6600
    assert body["ai_cost_month_usd"] >= 0.027


def test_report_runs_on_an_empty_table(session: Session):
    body = ai_usage.report(session, "day")
    assert body["totals"]["runs"] == 0
    assert body["groups"] == []
