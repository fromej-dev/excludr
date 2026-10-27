"""AI screening agent using pydantic-ai for systematic review screening."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session

from app.core.config import get_settings
from app.features.criteria.models import Criterion
from app.features.research.models import Article, ScreeningStage
from app.features.research.schemas import ScreeningResult
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionType,
)


logger = logging.getLogger(__name__)

# Bump whenever the system prompt, article formatting or validation rules change;
# stored on every AI decision for provenance.
PROMPT_VERSION = "2026-10-27.1"


class AIScreeningNotConfiguredError(RuntimeError):
    """Raised when AI screening is requested but no LLM API key is configured."""


def ensure_ai_configured() -> None:
    """Raise AIScreeningNotConfiguredError if no Anthropic API key is set."""
    if not get_settings().anthropic_api_key:
        raise AIScreeningNotConfiguredError("AI screening is not configured")


@dataclass
class ScreeningDeps:
    """Dependencies for the screening agent.

    Attributes:
        review_question: The research question guiding the systematic review
        criteria: List of criteria dictionaries with type, code, description, rationale
    """

    review_question: str
    criteria: list[dict]


# Lazy-initialized screening agent (deferred to avoid requiring API key at import time)
_screening_agent: Optional[Agent] = None


def _build_model() -> "Model | str":
    """Build the LLM model, passing the configured API key explicitly."""
    settings = get_settings()
    if settings.anthropic_api_key:
        return AnthropicModel(
            settings.default_llm_model,
            provider=AnthropicProvider(api_key=settings.anthropic_api_key),
        )
    # No key: defer; callers are expected to call ensure_ai_configured() first.
    return f"anthropic:{settings.default_llm_model}"


def get_screening_agent() -> Agent:
    """Get or create the screening agent (lazy initialization)."""
    global _screening_agent
    if _screening_agent is None:
        agent: Agent = Agent(
            _build_model(),
            output_type=ScreeningResult,
            deps_type=ScreeningDeps,
            retries={"output": 2},
            defer_model_check=True,
        )

        @agent.system_prompt
        async def build_system_prompt(ctx: RunContext[ScreeningDeps]) -> str:
            return _build_system_prompt(ctx)

        @agent.output_validator
        async def validate_output(
            ctx: RunContext[ScreeningDeps], output: ScreeningResult
        ) -> ScreeningResult:
            return _validate_screening_result(ctx.deps.criteria, output)

        _screening_agent = agent

    return _screening_agent


def _validate_screening_result(
    criteria: list[dict], output: ScreeningResult
) -> ScreeningResult:
    """Ensure evaluations cover exactly the active criteria.

    Raises:
        ModelRetry: If codes are missing, unknown, duplicated, or typed wrongly.
            The overall decision is deliberately not constrained: the model may
            answer "uncertain" regardless of the per-criterion outcomes.
    """
    expected = {c["code"]: c["type"] for c in criteria}
    returned = [e.criterion_code for e in output.criteria_evaluations]
    problems: list[str] = []

    missing = sorted(set(expected) - set(returned))
    extra = sorted(set(returned) - set(expected))
    duplicates = sorted({c for c in returned if returned.count(c) > 1})
    if missing:
        problems.append(f"missing evaluations for: {', '.join(missing)}")
    if extra:
        problems.append(f"unknown criterion codes: {', '.join(extra)}")
    if duplicates:
        problems.append(f"duplicate evaluations for: {', '.join(duplicates)}")
    wrong_type = sorted(
        e.criterion_code
        for e in output.criteria_evaluations
        if e.criterion_code in expected
        and e.criterion_type != expected[e.criterion_code]
    )
    if wrong_type:
        problems.append(f"wrong criterion_type for: {', '.join(wrong_type)}")

    if problems:
        raise ModelRetry(
            "criteria_evaluations must contain exactly one evaluation for each of "
            f"the criteria {sorted(expected)}; " + "; ".join(problems) + "."
        )
    return output


def _build_system_prompt(ctx: RunContext[ScreeningDeps]) -> str:
    """Build a dynamic system prompt with review question and criteria."""
    review_question = ctx.deps.review_question
    criteria = ctx.deps.criteria

    # Build criteria descriptions
    inclusion_criteria = [c for c in criteria if c["type"] == "inclusion"]
    exclusion_criteria = [c for c in criteria if c["type"] == "exclusion"]

    criteria_text = "## INCLUSION CRITERIA\n\n"
    for criterion in inclusion_criteria:
        criteria_text += f"**{criterion['code']}**: {criterion['description']}\n"
        if criterion.get("rationale"):
            criteria_text += f"  *Rationale*: {criterion['rationale']}\n"
        criteria_text += "\n"

    criteria_text += "## EXCLUSION CRITERIA\n\n"
    for criterion in exclusion_criteria:
        criteria_text += f"**{criterion['code']}**: {criterion['description']}\n"
        if criterion.get("rationale"):
            criteria_text += f"  *Rationale*: {criterion['rationale']}\n"
        criteria_text += "\n"

    system_prompt = f"""You are an expert systematic review screener assisting researchers in evaluating academic articles.

# RESEARCH QUESTION
{review_question}

# YOUR TASK
Evaluate the provided article against ALL of the following criteria. For each criterion, determine:
1. Whether the article MEETS (inclusion criteria) or TRIGGERS (exclusion criteria) the criterion
2. Your confidence in that judgment (0.0 to 1.0)
3. The reasoning behind your judgment

{criteria_text}

# EVALUATION GUIDELINES

## For INCLUSION criteria:
- Determine if the article MEETS the criterion
- met=True means the article satisfies this inclusion criterion
- met=False means the article does not satisfy this inclusion criterion
- met=None if you cannot determine from the available text

## For EXCLUSION criteria:
- Determine if the article TRIGGERS the exclusion
- met=True means the article triggers this exclusion (should be excluded for this reason)
- met=False means the article does not trigger this exclusion
- met=None if you cannot determine from the available text

## Overall Decision Logic:
- **Include**: Article meets ALL inclusion criteria AND does NOT trigger ANY exclusion criteria
- **Exclude**: Article fails ANY inclusion criterion OR triggers ANY exclusion criterion
- **Uncertain**: You cannot make a confident determination (insufficient information, unclear text, ambiguous findings)

## Confidence Scores:
- Use confidence scores that genuinely reflect your certainty
- Lower confidence when:
  - The text is ambiguous or unclear
  - Key information is missing
  - The criterion requires details not provided in the text
- Higher confidence when:
  - The text clearly addresses the criterion
  - Evidence is explicit and unambiguous

## Be Conservative:
- When uncertain, mark as "uncertain" rather than guessing
- It's better to flag articles for human review than to make incorrect decisions
- Provide clear reasoning that helps human reviewers understand your assessment

## Primary Exclusion Reason:
- If you recommend exclusion, identify the MOST IMPORTANT exclusion reason
- This should be the criterion code (e.g., "E1") or a brief description if multiple criteria apply

# OUTPUT REQUIREMENTS
Your response must be a structured evaluation with:
1. A decision (include/exclude/uncertain)
2. An overall confidence score
3. Evaluation for EACH criterion with met/confidence/reasoning
4. Primary exclusion reason (if excluded)
5. Summary reasoning explaining your overall decision
"""
    return system_prompt


def _full_text_for_model(article: Article) -> Optional[str]:
    """Return the extracted full text the model should see, or None.

    Full text is only used when the article is past title/abstract screening and
    extracted text (``full_text_content``) exists. ``full_text_path`` points at a
    PDF and is never read here.
    """
    if article.current_stage == ScreeningStage.title_abstract:
        return None
    content = (article.full_text_content or "").strip()
    return content or None


def _build_article_text(article: Article) -> str:
    """Build the article text from title, abstract, and full text if available.

    Full text is truncated to ``screening_max_fulltext_chars`` characters with an
    explicit marker so the model knows it is incomplete.

    Args:
        article: Article instance to extract text from

    Returns:
        Formatted article text for screening
    """
    parts = []

    if article.title:
        parts.append(f"# {article.title}\n")

    if article.authors:
        authors_str = ", ".join(article.authors)
        parts.append(f"**Authors**: {authors_str}\n")

    if article.year:
        parts.append(f"**Year**: {article.year}\n")

    if article.abstract:
        parts.append(f"\n## Abstract\n\n{article.abstract}\n")

    full_text = _full_text_for_model(article)
    if full_text:
        limit = get_settings().screening_max_fulltext_chars
        total = len(full_text)
        if total > limit:
            full_text = (
                full_text[:limit]
                + f"\n\n[... FULL TEXT TRUNCATED: showing the first {limit} of "
                f"{total} characters; the rest was omitted ...]"
            )
        parts.append(f"\n## Full Text\n\n{full_text}\n")

    return "\n".join(parts)


def _prepare_criteria_list(criteria: list[Criterion]) -> list[dict]:
    """Convert Criterion models to dictionaries for agent dependencies.

    Args:
        criteria: List of Criterion model instances

    Returns:
        List of criterion dictionaries
    """
    return [
        {
            "type": c.type.value,
            "code": c.code,
            "description": c.description,
            "rationale": c.rationale,
        }
        for c in criteria
        if c.is_active
    ]


def _model_name_from_result(result: object) -> str:
    """Name of the model that produced the result (falls back to settings)."""
    name = getattr(getattr(result, "response", None), "model_name", None)
    if isinstance(name, str) and name:
        return name
    return get_settings().default_llm_model


async def screen_article(
    article: Article,
    criteria: list[Criterion],
    review_question: str,
    session: Session,
    reviewer_id: Optional[int] = None,
) -> ScreeningDecision:
    """Screen an article using the AI agent against project criteria.

    This function:
    1. Builds article text from title, abstract, and full text (if available)
    2. Runs the AI screening agent with the review question and criteria
    3. Creates a ScreeningDecision record with the agent's evaluation
    4. Updates the article's AI check status fields
    5. Returns the screening decision

    Args:
        article: Article to screen
        criteria: List of active criteria to evaluate against
        review_question: The project's research question
        session: Database session for persistence
        reviewer_id: Optional reviewer ID (None for AI agent)

    Returns:
        ScreeningDecision: The created screening decision record

    Raises:
        Exception: If the agent fails to evaluate the article
    """
    # Build article text and note whether the model actually gets the full text
    article_text = _build_article_text(article)
    full_text_provided = _full_text_for_model(article) is not None

    # Prepare criteria list
    criteria_list = _prepare_criteria_list(criteria)

    # Set up agent dependencies
    deps = ScreeningDeps(review_question=review_question, criteria=criteria_list)

    # Run the agent
    try:
        agent = get_screening_agent()
        result = await agent.run(article_text, deps=deps)
        screening_result: ScreeningResult = result.output

        # The recorded stage reflects what the model actually saw.
        stage = (
            ScreeningStage.full_text
            if full_text_provided
            else ScreeningStage.title_abstract
        )

        # Map decision string to enum
        decision_map = {
            "include": ScreeningDecisionType.include,
            "exclude": ScreeningDecisionType.exclude,
            "uncertain": ScreeningDecisionType.uncertain,
        }
        decision = decision_map[screening_result.decision]

        # Build criteria evaluations JSON
        criteria_evaluations = {
            eval.criterion_code: {
                "criterion_type": eval.criterion_type,
                "met": eval.met,
                "confidence": eval.confidence,
                "reasoning": eval.reasoning,
            }
            for eval in screening_result.criteria_evaluations
        }

        # Create screening decision
        screening_decision = ScreeningDecision(
            article_id=article.id,
            reviewer_id=reviewer_id,  # None for AI agent
            stage=stage,
            decision=decision,
            source=DecisionSource.ai_agent,
            confidence_score=screening_result.confidence,
            reasoning=screening_result.summary_reasoning,
            primary_exclusion_reason=screening_result.primary_exclusion_reason,
            criteria_evaluations=criteria_evaluations,
            model_name=_model_name_from_result(result),
            prompt_version=PROMPT_VERSION,
            criteria_snapshot={c.code: c.version for c in criteria if c.is_active},
        )

        session.add(screening_decision)

        # Update article's AI check fields. AI decisions are advisory: article
        # status / current_stage / final_decision are changed by humans only.
        article.ai_check_status = "completed"
        article.ai_check_result = {
            "decision": screening_result.decision,
            "confidence": screening_result.confidence,
            "criteria_evaluations": criteria_evaluations,
            "summary": screening_result.summary_reasoning,
        }
        article.last_ai_check = datetime.now(timezone.utc)

        session.add(article)
        session.commit()
        session.refresh(screening_decision)

        return screening_decision

    except Exception as e:
        if isinstance(e, SQLAlchemyError):
            session.rollback()  # session unusable until rolled back
        logger.warning("AI screening failed for article %s: %s", article.id, e)
        # Update article with error status
        article.ai_check_status = "error"
        article.ai_check_result = {"error": str(e)}
        article.last_ai_check = datetime.now(timezone.utc)
        session.add(article)
        session.commit()
        raise
