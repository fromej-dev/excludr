"""Tests for the AI screening agent."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic_ai.exceptions import UnexpectedModelBehavior
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel
from sqlmodel import Session

from app.features.criteria.models import Criterion, CriterionType
from app.features.projects.models import Project
from app.core.config import Settings
from app.features.research.agent import (
    PROMPT_VERSION,
    _build_article_text,
    _prepare_criteria_list,
    get_screening_agent,
    screen_article,
)
from app.features.research.models import Article, ArticleStatus, FinalDecision
from app.features.research.schemas import CriterionEvaluation, ScreeningResult
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecisionType,
    ScreeningStage,
)


def _settings(**overrides) -> Settings:
    """Build Settings without reading .env."""
    return Settings(_env_file=None, secret_key="x", **overrides)


@pytest.fixture
def sample_project(session: Session, a_user) -> Project:
    """Create a sample project with review question."""
    user = a_user()
    project = Project(
        name="Test Systematic Review",
        description="Testing the screening agent",
        review_question="What are the effects of exercise on mental health?",
        owner_id=user.id,
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


@pytest.fixture
def sample_criteria(session: Session, sample_project: Project) -> list[Criterion]:
    """Create sample inclusion and exclusion criteria."""
    criteria = [
        Criterion(
            project_id=sample_project.id,
            type=CriterionType.inclusion,
            code="I1",
            description="Study investigates the effects of exercise on mental health",
            rationale="Must be directly relevant to our research question",
            is_active=True,
            order=1,
        ),
        Criterion(
            project_id=sample_project.id,
            type=CriterionType.inclusion,
            code="I2",
            description="Study uses quantitative or qualitative methods",
            rationale="We need empirical evidence",
            is_active=True,
            order=2,
        ),
        Criterion(
            project_id=sample_project.id,
            type=CriterionType.exclusion,
            code="E1",
            description="Study focuses on children under 12 years old",
            rationale="Our review focuses on adults",
            is_active=True,
            order=1,
        ),
        Criterion(
            project_id=sample_project.id,
            type=CriterionType.exclusion,
            code="E2",
            description="Study is not peer-reviewed (opinion pieces, editorials)",
            rationale="We need rigorous scientific evidence",
            is_active=True,
            order=2,
        ),
    ]
    for criterion in criteria:
        session.add(criterion)
    session.commit()
    for criterion in criteria:
        session.refresh(criterion)
    return criteria


@pytest.fixture
def sample_article(session: Session, sample_project: Project) -> Article:
    """Create a sample article with title and abstract."""
    article = Article(
        project_id=sample_project.id,
        title="The Impact of Aerobic Exercise on Depression in Adults",
        authors=["Smith, J.", "Jones, A."],
        abstract="This randomized controlled trial examines the effects of 12 weeks of aerobic exercise on depression symptoms in 100 adults aged 25-65. Results showed significant improvements in depression scores.",
        year=2023,
        doi="10.1234/example.2023.001",
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    return article


class TestBuildArticleText:
    """Tests for the _build_article_text helper function."""

    def test_builds_text_with_title_and_abstract(
        self, session: Session, sample_article: Article
    ):
        """Test building article text with title and abstract."""
        text = _build_article_text(sample_article)

        assert sample_article.title in text
        assert sample_article.abstract in text
        assert "Smith, J., Jones, A." in text
        assert "2023" in text

    def test_builds_text_with_full_text(
        self, session: Session, sample_article: Article
    ):
        """Full text comes from full_text_content (extracted from the PDF)."""
        full_text_content = "This is the full text content of the article."
        sample_article.full_text_retrieved = True
        sample_article.current_stage = ScreeningStage.full_text
        sample_article.full_text_content = full_text_content
        session.add(sample_article)
        session.commit()

        text = _build_article_text(sample_article)

        assert sample_article.title in text
        assert sample_article.abstract in text
        assert full_text_content in text

    def test_does_not_read_pdf_at_full_text_path(
        self, session: Session, sample_article: Article, tmp_path: Path
    ):
        """full_text_path is a PDF; its raw bytes must never be read as text."""
        pdf = tmp_path / "article.pdf"
        pdf.write_bytes(b"%PDF-1.7 RAW-PDF-BYTES-MARKER")
        sample_article.full_text_retrieved = True
        sample_article.current_stage = ScreeningStage.full_text
        sample_article.full_text_path = str(pdf)
        sample_article.full_text_content = None
        session.add(sample_article)
        session.commit()

        text = _build_article_text(sample_article)

        assert "RAW-PDF-BYTES-MARKER" not in text
        assert "## Full Text" not in text

    def test_full_text_not_used_at_title_abstract_stage(
        self, session: Session, sample_article: Article
    ):
        """Title/abstract screening must not see full text, even if stored."""
        sample_article.full_text_content = "SECRET FULL TEXT"
        sample_article.current_stage = ScreeningStage.title_abstract
        assert "SECRET FULL TEXT" not in _build_article_text(sample_article)

    def test_long_full_text_is_truncated_and_marked(
        self, session: Session, sample_article: Article, monkeypatch
    ):
        """Full text beyond the character budget is cut with a clear marker."""
        monkeypatch.setattr(
            "app.features.research.agent.get_settings",
            lambda: _settings(screening_max_fulltext_chars=100),
        )
        sample_article.current_stage = ScreeningStage.full_text
        sample_article.full_text_content = "A" * 100 + "B" * 400

        text = _build_article_text(sample_article)

        assert "A" * 100 in text
        assert "B" not in text.split("## Full Text")[1].split("[")[0]
        assert "FULL TEXT TRUNCATED" in text
        assert "100 of 500" in text

    def test_short_full_text_has_no_truncation_marker(
        self, session: Session, sample_article: Article
    ):
        sample_article.current_stage = ScreeningStage.full_text
        sample_article.full_text_content = "short"
        assert "TRUNCATED" not in _build_article_text(sample_article)

    def test_max_fulltext_chars_setting_default(self):
        assert _settings().screening_max_fulltext_chars == 150_000


class TestPrepareCriteriaList:
    """Tests for the _prepare_criteria_list helper function."""

    def test_converts_criteria_to_dict_list(self, sample_criteria: list[Criterion]):
        """Test converting Criterion models to dictionaries."""
        criteria_dicts = _prepare_criteria_list(sample_criteria)

        assert len(criteria_dicts) == 4
        assert all(isinstance(c, dict) for c in criteria_dicts)

        # Check first criterion
        i1 = next(c for c in criteria_dicts if c["code"] == "I1")
        assert i1["type"] == "inclusion"
        assert (
            i1["description"]
            == "Study investigates the effects of exercise on mental health"
        )
        assert "directly relevant" in i1["rationale"]

    def test_filters_inactive_criteria(
        self, session: Session, sample_criteria: list[Criterion]
    ):
        """Test that inactive criteria are excluded."""
        # Make one criterion inactive
        sample_criteria[0].is_active = False
        session.add(sample_criteria[0])
        session.commit()

        criteria_dicts = _prepare_criteria_list(sample_criteria)

        assert len(criteria_dicts) == 3
        assert not any(c["code"] == "I1" for c in criteria_dicts)


class TestScreenArticle:
    """Tests for the screen_article function."""

    @pytest.mark.asyncio
    async def test_screen_article_include_decision(
        self,
        session: Session,
        sample_article: Article,
        sample_criteria: list[Criterion],
        sample_project: Project,
    ):
        """Test successful screening with include decision."""
        # Mock the agent result
        mock_result = ScreeningResult(
            decision="include",
            confidence=0.9,
            criteria_evaluations=[
                CriterionEvaluation(
                    criterion_code="I1",
                    criterion_type="inclusion",
                    met=True,
                    confidence=0.95,
                    reasoning="The study directly investigates exercise effects on depression.",
                ),
                CriterionEvaluation(
                    criterion_code="I2",
                    criterion_type="inclusion",
                    met=True,
                    confidence=0.9,
                    reasoning="This is a randomized controlled trial, a quantitative method.",
                ),
                CriterionEvaluation(
                    criterion_code="E1",
                    criterion_type="exclusion",
                    met=False,
                    confidence=0.95,
                    reasoning="The study focuses on adults aged 25-65, not children.",
                ),
                CriterionEvaluation(
                    criterion_code="E2",
                    criterion_type="exclusion",
                    met=False,
                    confidence=0.9,
                    reasoning="This appears to be a peer-reviewed research article.",
                ),
            ],
            primary_exclusion_reason=None,
            summary_reasoning="The article meets all inclusion criteria and does not trigger any exclusion criteria.",
        )

        mock_run_result = MagicMock()
        mock_run_result.output = mock_result

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_run_result)
        with patch(
            "app.features.research.agent.get_screening_agent",
            return_value=mock_agent,
        ):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
            )

            # Verify decision was created
            assert decision.id is not None
            assert decision.article_id == sample_article.id
            assert decision.reviewer_id is None  # AI agent
            assert decision.source == DecisionSource.ai_agent
            assert decision.decision == ScreeningDecisionType.include
            assert decision.confidence_score == 0.9
            assert decision.stage == ScreeningStage.title_abstract
            assert decision.primary_exclusion_reason is None

            # Verify criteria evaluations
            assert decision.criteria_evaluations is not None
            assert "I1" in decision.criteria_evaluations
            assert decision.criteria_evaluations["I1"]["met"] is True

            # Verify article was updated
            session.refresh(sample_article)
            assert sample_article.ai_check_status == "completed"
            assert sample_article.ai_check_result is not None
            assert sample_article.ai_check_result["decision"] == "include"
            assert sample_article.last_ai_check is not None

    @pytest.mark.asyncio
    async def test_screen_article_exclude_decision(
        self,
        session: Session,
        sample_article: Article,
        sample_criteria: list[Criterion],
        sample_project: Project,
    ):
        """Test screening with exclude decision."""
        mock_result = ScreeningResult(
            decision="exclude",
            confidence=0.85,
            criteria_evaluations=[
                CriterionEvaluation(
                    criterion_code="I1",
                    criterion_type="inclusion",
                    met=True,
                    confidence=0.9,
                    reasoning="Study is about exercise and mental health.",
                ),
                CriterionEvaluation(
                    criterion_code="I2",
                    criterion_type="inclusion",
                    met=True,
                    confidence=0.85,
                    reasoning="Uses quantitative methods.",
                ),
                CriterionEvaluation(
                    criterion_code="E1",
                    criterion_type="exclusion",
                    met=True,
                    confidence=0.9,
                    reasoning="The study sample includes only children aged 8-11.",
                ),
                CriterionEvaluation(
                    criterion_code="E2",
                    criterion_type="exclusion",
                    met=False,
                    confidence=0.8,
                    reasoning="Appears to be peer-reviewed.",
                ),
            ],
            primary_exclusion_reason="E1",
            summary_reasoning="Excluded because the study focuses on children under 12.",
        )

        mock_run_result = MagicMock()
        mock_run_result.output = mock_result

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_run_result)
        with patch(
            "app.features.research.agent.get_screening_agent",
            return_value=mock_agent,
        ):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
            )

            assert decision.decision == ScreeningDecisionType.exclude
            assert decision.primary_exclusion_reason == "E1"
            assert decision.confidence_score == 0.85

            # Verify article status
            session.refresh(sample_article)
            assert sample_article.ai_check_status == "completed"
            assert sample_article.ai_check_result["decision"] == "exclude"

    @pytest.mark.asyncio
    async def test_screen_article_uncertain_decision(
        self,
        session: Session,
        sample_article: Article,
        sample_criteria: list[Criterion],
        sample_project: Project,
    ):
        """Test screening with uncertain decision."""
        mock_result = ScreeningResult(
            decision="uncertain",
            confidence=0.5,
            criteria_evaluations=[
                CriterionEvaluation(
                    criterion_code="I1",
                    criterion_type="inclusion",
                    met=None,
                    confidence=0.5,
                    reasoning="The abstract does not provide enough detail to determine if exercise effects are studied.",
                ),
                CriterionEvaluation(
                    criterion_code="I2",
                    criterion_type="inclusion",
                    met=None,
                    confidence=0.5,
                    reasoning="Methods are not clearly described in the abstract.",
                ),
                CriterionEvaluation(
                    criterion_code="E1",
                    criterion_type="exclusion",
                    met=None,
                    confidence=0.6,
                    reasoning="Age range is not specified.",
                ),
                CriterionEvaluation(
                    criterion_code="E2",
                    criterion_type="exclusion",
                    met=False,
                    confidence=0.7,
                    reasoning="Appears to be a research article.",
                ),
            ],
            primary_exclusion_reason=None,
            summary_reasoning="Insufficient information in the abstract to make a confident decision. Full text review needed.",
        )

        mock_run_result = MagicMock()
        mock_run_result.output = mock_result

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_run_result)
        with patch(
            "app.features.research.agent.get_screening_agent",
            return_value=mock_agent,
        ):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
            )

            assert decision.decision == ScreeningDecisionType.uncertain
            assert decision.confidence_score == 0.5
            assert decision.primary_exclusion_reason is None

    @pytest.mark.asyncio
    async def test_screen_article_with_full_text(
        self,
        session: Session,
        sample_article: Article,
        sample_criteria: list[Criterion],
        sample_project: Project,
    ):
        """Test screening with full text available uses full_text stage."""
        sample_article.full_text_retrieved = True
        sample_article.current_stage = ScreeningStage.full_text
        sample_article.full_text_content = "Full text content"
        session.add(sample_article)
        session.commit()

        mock_result = ScreeningResult(
            decision="include",
            confidence=0.9,
            criteria_evaluations=[
                CriterionEvaluation(
                    criterion_code="I1",
                    criterion_type="inclusion",
                    met=True,
                    confidence=0.9,
                    reasoning="Confirmed in full text.",
                ),
                CriterionEvaluation(
                    criterion_code="I2",
                    criterion_type="inclusion",
                    met=True,
                    confidence=0.9,
                    reasoning="Methods clearly described.",
                ),
                CriterionEvaluation(
                    criterion_code="E1",
                    criterion_type="exclusion",
                    met=False,
                    confidence=0.95,
                    reasoning="Adults only.",
                ),
                CriterionEvaluation(
                    criterion_code="E2",
                    criterion_type="exclusion",
                    met=False,
                    confidence=0.9,
                    reasoning="Peer-reviewed.",
                ),
            ],
            primary_exclusion_reason=None,
            summary_reasoning="Include based on full text review.",
        )

        mock_run_result = MagicMock()
        mock_run_result.output = mock_result

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_run_result)
        with patch(
            "app.features.research.agent.get_screening_agent",
            return_value=mock_agent,
        ):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
            )

            # Should use full_text stage
            assert decision.stage == ScreeningStage.full_text

    @pytest.mark.asyncio
    async def test_screen_article_handles_agent_error(
        self,
        session: Session,
        sample_article: Article,
        sample_criteria: list[Criterion],
        sample_project: Project,
    ):
        """Test that agent errors are handled gracefully."""
        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(side_effect=Exception("API rate limit exceeded"))
        with patch(
            "app.features.research.agent.get_screening_agent",
            return_value=mock_agent,
        ):
            with pytest.raises(Exception, match="API rate limit exceeded"):
                await screen_article(
                    article=sample_article,
                    criteria=sample_criteria,
                    review_question=sample_project.review_question,
                    session=session,
                )

            # Article should be marked with error status
            session.refresh(sample_article)
            assert sample_article.ai_check_status == "error"
            assert sample_article.ai_check_result is not None
            assert "API rate limit exceeded" in sample_article.ai_check_result["error"]
            assert sample_article.last_ai_check is not None

    @pytest.mark.asyncio
    async def test_screen_article_with_reviewer_id(
        self,
        session: Session,
        sample_article: Article,
        sample_criteria: list[Criterion],
        sample_project: Project,
        a_user,
    ):
        """Test that reviewer_id can be optionally provided."""
        user = a_user()

        mock_result = ScreeningResult(
            decision="include",
            confidence=0.9,
            criteria_evaluations=[
                CriterionEvaluation(
                    criterion_code="I1",
                    criterion_type="inclusion",
                    met=True,
                    confidence=0.9,
                    reasoning="Meets criterion.",
                ),
                CriterionEvaluation(
                    criterion_code="I2",
                    criterion_type="inclusion",
                    met=True,
                    confidence=0.9,
                    reasoning="Meets criterion.",
                ),
                CriterionEvaluation(
                    criterion_code="E1",
                    criterion_type="exclusion",
                    met=False,
                    confidence=0.9,
                    reasoning="Does not trigger.",
                ),
                CriterionEvaluation(
                    criterion_code="E2",
                    criterion_type="exclusion",
                    met=False,
                    confidence=0.9,
                    reasoning="Does not trigger.",
                ),
            ],
            primary_exclusion_reason=None,
            summary_reasoning="Include.",
        )

        mock_run_result = MagicMock()
        mock_run_result.output = mock_result

        mock_agent = MagicMock()
        mock_agent.run = AsyncMock(return_value=mock_run_result)
        with patch(
            "app.features.research.agent.get_screening_agent",
            return_value=mock_agent,
        ):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
                reviewer_id=user.id,
            )

            assert decision.reviewer_id == user.id


def _eval(code: str, ctype: str, met: bool | None = True, **kw) -> dict:
    return {
        "criterion_code": code,
        "criterion_type": ctype,
        "met": met,
        "confidence": kw.get("confidence", 0.9),
        "reasoning": kw.get("reasoning", f"reasoning for {code}"),
    }


def _result_args(codes=("I1", "I2", "E1", "E2"), decision="include", **overrides):
    evals = [_eval(c, "inclusion" if c.startswith("I") else "exclusion") for c in codes]
    args = {
        "decision": decision,
        "confidence": 0.8,
        "criteria_evaluations": evals,
        "primary_exclusion_reason": None,
        "summary_reasoning": "summary",
    }
    args.update(overrides)
    return args


def _function_model(responses: list[dict], seen: list):
    """FunctionModel that replies with the given final_result args in order."""
    calls = {"n": 0}

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        seen.append(messages)
        args = responses[min(calls["n"], len(responses) - 1)]
        calls["n"] += 1
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, json.dumps(args))]
        )

    return FunctionModel(fn)


class TestRealAgentEndToEnd:
    """Exercise the real pydantic-ai Agent (no mocking of agent.run)."""

    @pytest.mark.asyncio
    async def test_function_model_happy_path_records_provenance(
        self, session, sample_article, sample_criteria, sample_project
    ):
        seen: list = []
        model = _function_model([_result_args()], seen)
        with get_screening_agent().override(model=model):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
            )

        assert decision.decision == ScreeningDecisionType.include
        assert set(decision.criteria_evaluations) == {"I1", "I2", "E1", "E2"}
        assert decision.prompt_version == PROMPT_VERSION
        assert decision.model_name == "function:fn:"  # FunctionModel's model_name
        assert decision.stage == ScreeningStage.title_abstract
        # The article text reached the model
        assert sample_article.title in str(seen[0])

    @pytest.mark.asyncio
    async def test_test_model_with_custom_output(
        self, session, sample_article, sample_criteria, sample_project
    ):
        model = TestModel(custom_output_args=_result_args())
        with get_screening_agent().override(model=model):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
            )
        assert decision.decision == ScreeningDecisionType.include
        assert decision.model_name == "test"

    @pytest.mark.asyncio
    async def test_validator_retries_when_criterion_missing(
        self, session, sample_article, sample_criteria, sample_project
    ):
        seen: list = []
        model = _function_model(
            [_result_args(codes=("I1", "I2", "E1")), _result_args()], seen
        )
        with get_screening_agent().override(model=model):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
            )

        assert len(seen) == 2  # one retry
        assert "E2" in str(seen[1][-1])  # retry prompt names the missing code
        assert set(decision.criteria_evaluations) == {"I1", "I2", "E1", "E2"}

    @pytest.mark.asyncio
    async def test_validator_retries_on_extra_and_duplicate_codes(
        self, session, sample_article, sample_criteria, sample_project
    ):
        seen: list = []
        model = _function_model(
            [
                _result_args(codes=("I1", "I2", "E1", "E2", "X9")),
                _result_args(codes=("I1", "I1", "I2", "E1", "E2")),
                _result_args(),
            ],
            seen,
        )
        with get_screening_agent().override(model=model):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
            )
        assert len(seen) == 3
        assert "X9" in str(seen[1][-1])
        assert "I1" in str(seen[2][-1])
        assert decision.id is not None

    @pytest.mark.asyncio
    async def test_validator_ignores_inactive_criteria(
        self, session, sample_article, sample_criteria, sample_project
    ):
        sample_criteria[3].is_active = False  # E2
        session.add(sample_criteria[3])
        session.commit()
        seen: list = []
        model = _function_model([_result_args(codes=("I1", "I2", "E1"))], seen)
        with get_screening_agent().override(model=model):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
            )
        assert len(seen) == 1
        assert set(decision.criteria_evaluations) == {"I1", "I2", "E1"}

    @pytest.mark.asyncio
    async def test_validator_exhausts_retries_marks_article_error(
        self, session, sample_article, sample_criteria, sample_project
    ):
        seen: list = []
        model = _function_model([_result_args(codes=("I1",))], seen)
        with get_screening_agent().override(model=model):
            with pytest.raises(UnexpectedModelBehavior):
                await screen_article(
                    article=sample_article,
                    criteria=sample_criteria,
                    review_question=sample_project.review_question,
                    session=session,
                )
        session.refresh(sample_article)
        assert sample_article.ai_check_status == "error"

    @pytest.mark.asyncio
    async def test_uncertain_not_forced_to_match_criteria(
        self, session, sample_article, sample_criteria, sample_project
    ):
        """Model may say uncertain even when every criterion looks met."""
        model = _function_model([_result_args(decision="uncertain")], [])
        with get_screening_agent().override(model=model):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
            )
        assert decision.decision == ScreeningDecisionType.uncertain

    @pytest.mark.asyncio
    async def test_full_text_reaches_model_and_sets_stage(
        self, session, sample_article, sample_criteria, sample_project
    ):
        sample_article.current_stage = ScreeningStage.full_text
        sample_article.full_text_retrieved = True
        sample_article.full_text_content = "UNIQUE-METHODS-SECTION-TEXT"
        session.add(sample_article)
        session.commit()
        seen: list = []
        with get_screening_agent().override(
            model=_function_model([_result_args()], seen)
        ):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
            )
        assert "UNIQUE-METHODS-SECTION-TEXT" in str(seen[0])
        assert decision.stage == ScreeningStage.full_text

    @pytest.mark.asyncio
    async def test_stage_is_title_abstract_when_no_full_text_available(
        self, session, sample_article, sample_criteria, sample_project
    ):
        """At full_text stage but nothing extracted: model only saw the abstract."""
        sample_article.current_stage = ScreeningStage.full_text
        sample_article.full_text_retrieved = True  # flag alone is not enough
        sample_article.full_text_content = None
        session.add(sample_article)
        session.commit()
        with get_screening_agent().override(
            model=_function_model([_result_args()], [])
        ):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
            )
        assert decision.stage == ScreeningStage.title_abstract

    @pytest.mark.asyncio
    async def test_ai_decision_does_not_change_article_final_status(
        self, session, sample_article, sample_criteria, sample_project
    ):
        sample_article.status = ArticleStatus.screening
        session.add(sample_article)
        session.commit()
        with get_screening_agent().override(
            model=_function_model(
                [_result_args(decision="exclude", primary_exclusion_reason="E1")], []
            )
        ):
            await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
            )
        session.refresh(sample_article)
        assert sample_article.status == ArticleStatus.screening
        assert sample_article.current_stage == ScreeningStage.title_abstract
        assert sample_article.final_decision == FinalDecision.pending


class TestCriteriaSnapshot:
    @pytest.mark.asyncio
    async def test_snapshot_records_active_criteria_versions(
        self, session, sample_article, sample_criteria, sample_project
    ):
        sample_criteria[0].version = 3
        session.add(sample_criteria[0])
        session.commit()
        active = {c.code: c.version for c in sample_criteria if c.is_active}
        model = _function_model([_result_args()], [])
        with get_screening_agent().override(model=model):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
            )
        assert decision.criteria_snapshot == active
        assert decision.criteria_snapshot["I1"] == 3
