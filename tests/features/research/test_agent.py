"""Tests for the AI screening agent."""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlmodel import Session

from app.features.criteria.models import Criterion, CriterionType
from app.features.projects.models import Project
from app.features.research.agent import (
    _build_article_text,
    _prepare_criteria_list,
    screen_article,
)
from app.features.research.models import Article
from app.features.research.schemas import CriterionEvaluation, ScreeningResult
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionType,
    ScreeningStage,
)
from app.features.users.models import User


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
        self, session: Session, sample_article: Article, tmp_path: Path
    ):
        """Test building article text when full text is available."""
        # Create a temporary full text file
        full_text_path = tmp_path / "article.txt"
        full_text_content = "This is the full text content of the article."
        full_text_path.write_text(full_text_content)

        # Update article with full text path
        sample_article.full_text_retrieved = True
        sample_article.full_text_path = str(full_text_path)
        session.add(sample_article)
        session.commit()

        text = _build_article_text(sample_article)

        assert sample_article.title in text
        assert sample_article.abstract in text
        assert full_text_content in text

    def test_handles_missing_full_text_gracefully(
        self, session: Session, sample_article: Article
    ):
        """Test that missing full text doesn't break text building."""
        sample_article.full_text_retrieved = True
        sample_article.full_text_path = "/nonexistent/path.txt"
        session.add(sample_article)
        session.commit()

        # Should not raise exception
        text = _build_article_text(sample_article)
        assert sample_article.title in text
        assert sample_article.abstract in text


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
        assert i1["description"] == "Study investigates the effects of exercise on mental health"
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
        mock_run_result.data = mock_result

        with patch(
            "app.features.research.agent.screening_agent.run",
            new_callable=AsyncMock,
            return_value=mock_run_result,
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
        mock_run_result.data = mock_result

        with patch(
            "app.features.research.agent.screening_agent.run",
            new_callable=AsyncMock,
            return_value=mock_run_result,
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
        mock_run_result.data = mock_result

        with patch(
            "app.features.research.agent.screening_agent.run",
            new_callable=AsyncMock,
            return_value=mock_run_result,
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
        tmp_path: Path,
    ):
        """Test screening with full text available uses full_text stage."""
        # Set up full text
        full_text_path = tmp_path / "article.txt"
        full_text_path.write_text("Full text content")
        sample_article.full_text_retrieved = True
        sample_article.full_text_path = str(full_text_path)
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
        mock_run_result.data = mock_result

        with patch(
            "app.features.research.agent.screening_agent.run",
            new_callable=AsyncMock,
            return_value=mock_run_result,
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
        with patch(
            "app.features.research.agent.screening_agent.run",
            new_callable=AsyncMock,
            side_effect=Exception("API rate limit exceeded"),
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
        mock_run_result.data = mock_result

        with patch(
            "app.features.research.agent.screening_agent.run",
            new_callable=AsyncMock,
            return_value=mock_run_result,
        ):
            decision = await screen_article(
                article=sample_article,
                criteria=sample_criteria,
                review_question=sample_project.review_question,
                session=session,
                reviewer_id=user.id,
            )

            assert decision.reviewer_id == user.id
