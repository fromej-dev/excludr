from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, select, update

from .models import (
    Article,
    ArticleStatus,
    ScreeningStage,
    FinalDecision,
    FullTextSource,
)
from ...core.database import SessionDep


def skip_title_abstract(article: Article) -> bool:
    """Send an article still waiting for title/abstract screening to full text.

    For records that already passed title/abstract screening elsewhere. The
    article goes to ``awaiting_full_text`` (or ``full_text_retrieved`` when its
    full text is already stored); articles past title/abstract are left alone.
    The article is marked ``title_abstract_skipped`` (counted apart in the
    statistics and PRISMA). The caller adds and commits the article.

    Returns:
        True if the article moved.
    """
    if article.current_stage != ScreeningStage.title_abstract or article.status not in (
        ArticleStatus.imported,
        ArticleStatus.screening,
    ):
        return False
    article.status = (
        ArticleStatus.full_text_retrieved
        if article.full_text_retrieved
        else ArticleStatus.awaiting_full_text
    )
    article.current_stage = ScreeningStage.full_text
    article.title_abstract_skipped = True
    return True


class ArticleService:
    """Service class for managing Article-related operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_articles_for_project(self, project_id: int):
        """Get all articles for a project."""
        return select(Article).where(Article.project_id == project_id)

    def get_article_by_id(self, article_id: int) -> Article | None:
        """Get an article by its ID."""
        return self.session.exec(
            select(Article).where(Article.id == article_id)
        ).first()

    def get_articles_by_status(self, project_id: int, status: ArticleStatus):
        """Get articles with a specific status."""
        return select(Article).where(
            Article.project_id == project_id,
            Article.status == status,
        )

    def get_articles_by_stage(self, project_id: int, stage: ScreeningStage):
        """Get articles at a specific screening stage."""
        return select(Article).where(
            Article.project_id == project_id,
            Article.current_stage == stage,
        )

    def update_article_status(self, article: Article, status: ArticleStatus) -> Article:
        """Update an article's status."""
        article.status = status
        self.session.add(article)
        self.session.commit()
        self.session.refresh(article)
        return article

    def update_article_stage(self, article: Article, stage: ScreeningStage) -> Article:
        """Update an article's current screening stage."""
        article.current_stage = stage
        self.session.add(article)
        self.session.commit()
        self.session.refresh(article)
        return article

    def update_article_status_from_decision(
        self,
        article: Article,
        stage: "ScreeningStage",
        decision: str,
    ) -> Article:
        """Update article status based on a screening decision."""
        from app.features.screening.models import (
            ScreeningStage as SStage,
            ScreeningDecisionType,
        )

        if stage == SStage.title_abstract:
            if decision == ScreeningDecisionType.include.value or decision == "include":
                # Move to full text; skip retrieval if a full text was already uploaded
                article.status = (
                    ArticleStatus.full_text_retrieved
                    if article.full_text_retrieved
                    else ArticleStatus.awaiting_full_text
                )
                article.current_stage = ScreeningStage.full_text
            elif (
                decision == ScreeningDecisionType.exclude.value or decision == "exclude"
            ):
                article.status = ArticleStatus.excluded
                article.final_decision = FinalDecision.excluded
                article.current_stage = ScreeningStage.completed
            # uncertain stays in screening
        elif stage == SStage.full_text:
            if decision == ScreeningDecisionType.include.value or decision == "include":
                article.status = ArticleStatus.included
                article.final_decision = FinalDecision.included
                article.current_stage = ScreeningStage.completed
            elif (
                decision == ScreeningDecisionType.exclude.value or decision == "exclude"
            ):
                article.status = ArticleStatus.excluded
                article.final_decision = FinalDecision.excluded
                article.current_stage = ScreeningStage.completed

        self.session.add(article)
        self.session.commit()
        self.session.refresh(article)
        return article

    def set_full_text_retrieved(
        self,
        article: Article,
        full_text_path: str | None,
        full_text_content: str | None = None,
        source: str = FullTextSource.manual.value,
    ) -> Article:
        """
        Mark an article as having its full text retrieved.

        Only an article waiting for its full text moves to ``full_text_retrieved``;
        for any other article (still at title/abstract, or already decided) the
        full text is stored without changing where it is in the pipeline.

        Args:
            article: The article to update.
            full_text_path: Path to the stored PDF file (None for text-only retrieval).
            full_text_content: Extracted text content from the PDF (optional).
            source: Where the full text came from (``FullTextSource`` value).

        Returns:
            The updated article.
        """
        article.full_text_retrieved = True
        article.full_text_path = full_text_path
        article.full_text_content = full_text_content
        article.full_text_source = source
        article.full_text_retrieval_error = None
        if article.status == ArticleStatus.awaiting_full_text:
            article.status = ArticleStatus.full_text_retrieved
        self.session.add(article)
        self.session.commit()
        self.session.refresh(article)
        return article

    def start_screening(self, project_id: int) -> int:
        """Move all imported articles to title/abstract screening.

        Imports already create articles in ``screening``, so this only releases
        articles left in ``imported`` (e.g. created before that change). It is
        idempotent: a second call finds nothing to move and returns 0.

        Returns:
            Number of articles moved.
        """
        articles = self.session.exec(
            select(Article).where(
                Article.project_id == project_id,
                Article.status == ArticleStatus.imported,
            )
        ).all()

        count = 0
        for article in articles:
            article.status = ArticleStatus.screening
            article.current_stage = ScreeningStage.title_abstract
            self.session.add(article)
            count += 1

        self.session.commit()
        return count

    def delete_article(self, article: Article) -> None:
        """Delete an article (its AI usage rows are kept, without the link)."""
        from app.features.ai_usage.models import AIUsage

        self.session.exec(
            update(AIUsage)
            .where(AIUsage.article_id == article.id)
            .values(article_id=None, decision_id=None)
        )
        self.session.delete(article)
        self.session.commit()


def get_article_service(session: SessionDep) -> ArticleService:
    """Dependency injection function to get ArticleService instance."""
    return ArticleService(session=session)


ArticleServiceDep = Annotated[ArticleService, Depends(get_article_service)]
