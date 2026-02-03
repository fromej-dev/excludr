"""AI screening agent using pydantic-ai for systematic review screening."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic_ai import Agent, RunContext
from sqlmodel import Session

from app.core.config import get_settings
from app.features.criteria.models import Criterion, CriterionType
from app.features.research.models import Article, ScreeningStage
from app.features.research.schemas import ScreeningResult
from app.features.screening.models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionType,
)


@dataclass
class ScreeningDeps:
    """Dependencies for the screening agent.

    Attributes:
        review_question: The research question guiding the systematic review
        criteria: List of criteria dictionaries with type, code, description, rationale
    """

    review_question: str
    criteria: list[dict]


# Initialize the screening agent
settings = get_settings()
model_name = f"anthropic:{settings.default_llm_model}"

screening_agent = Agent(
    model_name,
    result_type=ScreeningResult,
    deps_type=ScreeningDeps,
)


@screening_agent.system_prompt
async def build_system_prompt(ctx: RunContext[ScreeningDeps]) -> str:
    """Build a dynamic system prompt with review question and criteria.

    Args:
        ctx: Run context containing dependencies with review question and criteria

    Returns:
        System prompt string for the agent
    """
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


def _build_article_text(article: Article) -> str:
    """Build the article text from title, abstract, and full text if available.

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

    # Read full text if available
    if article.full_text_retrieved and article.full_text_path:
        try:
            full_text_path = Path(article.full_text_path)
            if full_text_path.exists():
                full_text = full_text_path.read_text(encoding="utf-8")
                parts.append(f"\n## Full Text\n\n{full_text}\n")
        except Exception:
            # If we can't read the full text, continue with what we have
            pass

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
    # Build article text
    article_text = _build_article_text(article)

    # Prepare criteria list
    criteria_list = _prepare_criteria_list(criteria)

    # Set up agent dependencies
    deps = ScreeningDeps(review_question=review_question, criteria=criteria_list)

    # Run the agent
    try:
        result = await screening_agent.run(article_text, deps=deps)
        screening_result: ScreeningResult = result.data

        # Determine screening stage based on whether full text was used
        stage = (
            ScreeningStage.full_text
            if article.full_text_retrieved
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
        )

        session.add(screening_decision)

        # Update article's AI check fields
        article.ai_check_status = "completed"
        article.ai_check_result = {
            "decision": screening_result.decision,
            "confidence": screening_result.confidence,
            "criteria_evaluations": criteria_evaluations,
            "summary": screening_result.summary_reasoning,
        }
        article.last_ai_check = datetime.utcnow()

        session.add(article)
        session.commit()
        session.refresh(screening_decision)

        return screening_decision

    except Exception as e:
        # Update article with error status
        article.ai_check_status = "error"
        article.ai_check_result = {"error": str(e)}
        article.last_ai_check = datetime.utcnow()
        session.add(article)
        session.commit()
        raise
