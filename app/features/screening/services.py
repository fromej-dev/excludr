from typing import Annotated, Optional

from fastapi import Depends
from sqlmodel import Session, select, func

from .models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionCreate,
    ScreeningStage,
    ScreeningStats,
)
from ..research.models import Article, ArticleStatus
from ...core.database import SessionDep


class ScreeningService:
    """Service class for managing screening decisions."""

    def __init__(self, session: Session):
        self.session = session

    def get_decisions_for_article(self, article_id: int):
        """Get all screening decisions for an article."""
        return (
            select(ScreeningDecision)
            .where(ScreeningDecision.article_id == article_id)
            .order_by(ScreeningDecision.created_at.desc(), ScreeningDecision.id.desc())
        )

    def get_decision_by_id(self, decision_id: int) -> ScreeningDecision | None:
        """Get a screening decision by ID."""
        return self.session.exec(
            select(ScreeningDecision).where(ScreeningDecision.id == decision_id)
        ).first()

    def get_latest_decision(
        self, article_id: int, stage: ScreeningStage
    ) -> ScreeningDecision | None:
        """Get the latest decision for an article at a given stage."""
        return self.session.exec(
            select(ScreeningDecision)
            .where(
                ScreeningDecision.article_id == article_id,
                ScreeningDecision.stage == stage,
            )
            .order_by(ScreeningDecision.created_at.desc(), ScreeningDecision.id.desc())
        ).first()

    def get_latest_ai_decisions(self, project_id: int) -> list[ScreeningDecision]:
        """Latest AI decision per article in a project.

        "Latest" is by ``created_at`` then ``id`` (ties broken by higher id).
        """
        rank = (
            func.row_number()
            .over(
                partition_by=ScreeningDecision.article_id,
                order_by=(
                    ScreeningDecision.created_at.desc(),
                    ScreeningDecision.id.desc(),
                ),
            )
            .label("rank")
        )
        ranked = (
            select(ScreeningDecision.id.label("decision_id"), rank)
            .join(Article, ScreeningDecision.article_id == Article.id)
            .where(
                Article.project_id == project_id,
                ScreeningDecision.source == DecisionSource.ai_agent,
            )
            .subquery()
        )
        return list(
            self.session.exec(
                select(ScreeningDecision)
                .join(ranked, ScreeningDecision.id == ranked.c.decision_id)
                .where(ranked.c.rank == 1)
                .order_by(ScreeningDecision.article_id)
            ).all()
        )

    def get_stale_ai_article_ids(
        self, project_id: int, current_snapshot: dict[str, int]
    ) -> list[int]:
        """Article ids whose latest AI decision used different criteria.

        Args:
            project_id: Project to inspect.
            current_snapshot: ``{code: version}`` of the project's active criteria.

        A decision with no snapshot (made before versioning) cannot be verified
        and is reported as stale.
        """
        return [
            d.article_id
            for d in self.get_latest_ai_decisions(project_id)
            if d.criteria_snapshot != current_snapshot
        ]

    def create_decision(
        self,
        article_id: int,
        data: ScreeningDecisionCreate,
        reviewer_id: Optional[int] = None,
    ) -> ScreeningDecision:
        """Create a new screening decision."""
        decision = ScreeningDecision(**data.model_dump())
        decision.article_id = article_id
        decision.reviewer_id = reviewer_id

        self.session.add(decision)
        self.session.commit()
        self.session.refresh(decision)
        return decision

    def get_next_article_for_screening(
        self, project_id: int, stage: ScreeningStage
    ) -> Article | None:
        """Get the next article that needs screening at the given stage."""
        # For title/abstract: get articles with status 'screening'
        # For full_text: get articles with status 'full_text_retrieved'
        if stage == ScreeningStage.title_abstract:
            target_status = ArticleStatus.screening
        else:
            target_status = ArticleStatus.full_text_retrieved

        # Find articles that haven't been screened at this stage yet
        screened_article_ids = (
            select(ScreeningDecision.article_id)
            .where(ScreeningDecision.stage == stage)
            .distinct()
        )

        return self.session.exec(
            select(Article)
            .where(
                Article.project_id == project_id,
                Article.status == target_status,
                Article.id.notin_(screened_article_ids),
            )
            .order_by(Article.id)
        ).first()

    def get_screening_stats(self, project_id: int) -> ScreeningStats:
        """Get screening statistics for a project."""
        stats = ScreeningStats()

        # Total articles
        stats.total_articles = self.session.exec(
            select(func.count(Article.id)).where(Article.project_id == project_id)
        ).one()

        # Count by status
        status_counts = self.session.exec(
            select(Article.status, func.count(Article.id))
            .where(Article.project_id == project_id)
            .group_by(Article.status)
        ).all()

        for status, count in status_counts:
            if status == ArticleStatus.included:
                stats.included = count
            elif status == ArticleStatus.excluded:
                stats.excluded = count
            elif status == ArticleStatus.screening:
                stats.awaiting_screening = count
            elif status == ArticleStatus.awaiting_full_text:
                stats.awaiting_full_text = count

        # Count decisions by stage
        stats.screened_title_abstract = self.session.exec(
            select(func.count(func.distinct(ScreeningDecision.article_id)))
            .join(Article, ScreeningDecision.article_id == Article.id)
            .where(
                Article.project_id == project_id,
                ScreeningDecision.stage == ScreeningStage.title_abstract,
            )
        ).one()

        stats.screened_full_text = self.session.exec(
            select(func.count(func.distinct(ScreeningDecision.article_id)))
            .join(Article, ScreeningDecision.article_id == Article.id)
            .where(
                Article.project_id == project_id,
                ScreeningDecision.stage == ScreeningStage.full_text,
            )
        ).one()

        return stats


def get_screening_service(session: SessionDep) -> ScreeningService:
    """Dependency injection function to get ScreeningService instance."""
    return ScreeningService(session=session)


ScreeningServiceDep = Annotated[ScreeningService, Depends(get_screening_service)]
