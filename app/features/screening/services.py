from collections import defaultdict
from typing import Annotated, Optional

from fastapi import Depends
from sqlmodel import Session, and_, select, func

from .consensus import (
    INCLUDE,
    EXCLUDE,
    StageState,
    Vote,
    binary_metrics,
    cohens_kappa,
    evaluate_stage,
    latest_vote_per_reviewer,
    percent_agreement,
)
from .models import (
    DecisionSource,
    ScreeningDecision,
    ScreeningDecisionCreate,
    ScreeningDecisionType,
    ScreeningStage,
    ScreeningStats,
)
from .schemas import (
    AIAgreementRead,
    AIDecisionSummary,
    AIDisagreementRead,
    AgreementRead,
    ConflictRead,
    HumanAgreementRead,
    ReviewerDecisionRead,
)
from ..projects.models import Project
from ..research.models import Article, ArticleStatus
from ..research.services import ArticleService
from ..users.models import User
from ...core.database import SessionDep

SCREENING_STAGES = (ScreeningStage.title_abstract, ScreeningStage.full_text)

StageKey = tuple[int, ScreeningStage]


class ScreeningError(Exception):
    """Domain error carrying the HTTP status the router should return."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _vote(d: ScreeningDecision) -> Vote:
    return Vote(d.id, d.reviewer_id, d.decision, d.is_resolution)


class ScreeningService:
    """Service class for managing screening decisions."""

    def __init__(self, session: Session):
        self.session = session

    def get_decisions_for_article(
        self,
        article_id: int,
        blind_for_user_id: Optional[int] = None,
        blind_stage: Optional[ScreeningStage] = None,
    ):
        """Get all screening decisions for an article.

        Args:
            article_id: Article to list decisions for.
            blind_for_user_id: When set, other reviewers' (non-resolution) human
                decisions at ``blind_stage`` are hidden from this user.
            blind_stage: The stage still being screened (the article's current one).
        """
        query = select(ScreeningDecision).where(
            ScreeningDecision.article_id == article_id
        )
        if blind_for_user_id is not None and blind_stage is not None:
            query = query.where(
                ~and_(
                    ScreeningDecision.source == DecisionSource.human,
                    ScreeningDecision.is_resolution.is_(False),
                    ScreeningDecision.stage == blind_stage,
                    ScreeningDecision.reviewer_id != blind_for_user_id,
                )
            )
        return query.order_by(
            ScreeningDecision.created_at.desc(), ScreeningDecision.id.desc()
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
        self,
        project_id: int,
        stage: ScreeningStage,
        reviewer_id: Optional[int] = None,
        required_reviewers: int = 1,
    ) -> Article | None:
        """Get the next article this reviewer should screen at the given stage.

        Skips articles the reviewer already decided on (AI decisions and other
        reviewers' decisions are ignored, which keeps screening independent), and,
        in dual-screening mode, articles that already have the required number of
        reviewers (those are settled or waiting for the owner).
        """
        # For title/abstract: get articles with status 'screening'
        # For full_text: get articles with status 'full_text_retrieved'
        if stage == ScreeningStage.title_abstract:
            target_status = ArticleStatus.screening
        else:
            target_status = ArticleStatus.full_text_retrieved

        human = and_(
            ScreeningDecision.stage == stage,
            ScreeningDecision.source == DecisionSource.human,
            ScreeningDecision.is_resolution.is_(False),
        )
        query = select(Article).where(
            Article.project_id == project_id, Article.status == target_status
        )
        if reviewer_id is not None:
            decided_by_me = select(ScreeningDecision.article_id).where(
                human, ScreeningDecision.reviewer_id == reviewer_id
            )
            query = query.where(Article.id.notin_(decided_by_me))
        if required_reviewers >= 2:
            fully_reviewed = (
                select(ScreeningDecision.article_id)
                .where(human)
                .group_by(ScreeningDecision.article_id)
                .having(
                    func.count(func.distinct(ScreeningDecision.reviewer_id))
                    >= required_reviewers
                )
            )
            query = query.where(Article.id.notin_(fully_reviewed))
        return self.session.exec(query.order_by(Article.id)).first()

    # ------------------------------------------------------------------
    # Dual screening: submitting, resolving and evaluating decisions
    # ------------------------------------------------------------------

    def human_decisions(
        self,
        project_id: int,
        stage: Optional[ScreeningStage] = None,
        article_id: Optional[int] = None,
    ) -> list[ScreeningDecision]:
        """Human decisions (reviewers' and resolutions) of a project, oldest first."""
        query = (
            select(ScreeningDecision)
            .join(Article, ScreeningDecision.article_id == Article.id)
            .where(
                Article.project_id == project_id,
                ScreeningDecision.source == DecisionSource.human,
            )
            .order_by(ScreeningDecision.id)
        )
        if stage is not None:
            query = query.where(ScreeningDecision.stage == stage)
        if article_id is not None:
            query = query.where(ScreeningDecision.article_id == article_id)
        return list(self.session.exec(query).all())

    @staticmethod
    def _group(
        decisions: list[ScreeningDecision],
    ) -> dict[StageKey, list[ScreeningDecision]]:
        grouped: dict[StageKey, list[ScreeningDecision]] = defaultdict(list)
        for d in decisions:
            grouped[(d.article_id, d.stage)].append(d)
        return grouped

    def get_stage_state(
        self, project: Project, article_id: int, stage: ScreeningStage
    ) -> StageState:
        """Consensus state of one article at one stage."""
        decisions = self.human_decisions(project.id, stage, article_id)
        return evaluate_stage([_vote(d) for d in decisions], project.required_reviewers)

    def get_final_outcomes(
        self, project: Project, stage: Optional[ScreeningStage] = None
    ) -> dict[StageKey, StageState]:
        """Settled (include/exclude) human outcome per (article, stage)."""
        outcomes: dict[StageKey, StageState] = {}
        grouped = self._group(self.human_decisions(project.id, stage))
        for key, decisions in grouped.items():
            state = evaluate_stage(
                [_vote(d) for d in decisions], project.required_reviewers
            )
            if state.outcome is not None:
                outcomes[key] = state
        return outcomes

    def apply_consensus(self, project: Project, article: Article) -> Article:
        """Advance the article if its current stage has a settled human outcome."""
        stage = article.current_stage
        if stage not in SCREENING_STAGES:
            return article
        state = self.get_stage_state(project, article.id, stage)
        if state.outcome is None:
            return article
        return ArticleService(self.session).update_article_status_from_decision(
            article, stage, state.outcome.value
        )

    def reevaluate_project(self, project: Project) -> int:
        """Re-apply consensus to every article (after ``required_reviewers`` changes).

        Returns the number of articles whose status changed.
        """
        articles = self.session.exec(
            select(Article).where(
                Article.project_id == project.id,
                Article.current_stage.in_(SCREENING_STAGES),
            )
        ).all()
        changed = 0
        for article in articles:
            before = article.status
            if self.apply_consensus(project, article).status != before:
                changed += 1
        return changed

    def submit_human_decision(
        self,
        project: Project,
        article: Article,
        data: ScreeningDecisionCreate,
        reviewer_id: int,
    ) -> tuple[ScreeningDecision, bool]:
        """Record a reviewer's decision and apply consensus.

        Each reviewer has one *effective* decision per article and stage: posting
        again supersedes the earlier one (no 409). The earlier row is kept as
        history; only each reviewer's latest decision counts towards consensus,
        conflicts and agreement statistics.

        Returns:
            ``(decision, replaced)`` where ``replaced`` is True if this superseded an
            earlier decision by the same reviewer.

        Raises:
            ScreeningError: 409 if the article is not currently at ``data.stage``.
        """
        if data.stage not in SCREENING_STAGES or article.current_stage != data.stage:
            raise ScreeningError(
                409, f"Article is not at the '{data.stage.value}' stage"
            )
        replaced = (
            self.session.exec(
                select(ScreeningDecision.id).where(
                    ScreeningDecision.article_id == article.id,
                    ScreeningDecision.stage == data.stage,
                    ScreeningDecision.source == DecisionSource.human,
                    ScreeningDecision.is_resolution.is_(False),
                    ScreeningDecision.reviewer_id == reviewer_id,
                )
            ).first()
            is not None
        )
        decision = self.create_decision(article.id, data, reviewer_id)
        self.apply_consensus(project, article)
        self.session.refresh(decision)
        return decision, replaced

    def resolve_conflict(
        self,
        project: Project,
        article: Article,
        owner_id: int,
        decision: ScreeningDecisionType,
        reason: str,
        primary_exclusion_reason: Optional[str] = None,
    ) -> ScreeningDecision:
        """Store the owner's final decision for a conflicted article and advance it.

        Raises:
            ScreeningError: 409 if the article is not currently in conflict.
        """
        stage = article.current_stage
        if (
            stage not in SCREENING_STAGES
            or not self.get_stage_state(project, article.id, stage).conflict
        ):
            raise ScreeningError(409, "Article is not in conflict")
        resolution = ScreeningDecision(
            article_id=article.id,
            stage=stage,
            decision=decision,
            source=DecisionSource.human,
            reviewer_id=owner_id,
            reasoning=reason,
            primary_exclusion_reason=primary_exclusion_reason,
            is_resolution=True,
        )
        self.session.add(resolution)
        self.session.commit()
        self.session.refresh(resolution)
        self.apply_consensus(project, article)
        self.session.refresh(resolution)
        return resolution

    def list_conflicts(self, project: Project) -> list[ConflictRead]:
        """Articles whose reviewers disagree at the article's current stage."""
        if project.required_reviewers < 2:
            return []
        rows = self.session.exec(
            select(ScreeningDecision, Article.title, User.name)
            .join(Article, ScreeningDecision.article_id == Article.id)
            .outerjoin(User, User.id == ScreeningDecision.reviewer_id)
            .where(
                Article.project_id == project.id,
                ScreeningDecision.source == DecisionSource.human,
                ScreeningDecision.stage == Article.current_stage,
            )
            .order_by(ScreeningDecision.id)
        ).all()
        titles: dict[int, Optional[str]] = {}
        names: dict[int, Optional[str]] = {}
        grouped: dict[StageKey, list[ScreeningDecision]] = defaultdict(list)
        for d, title, name in rows:
            titles[d.id], names[d.id] = title, name
            grouped[(d.article_id, d.stage)].append(d)
        conflicts: list[ConflictRead] = []
        for (article_id, stage), decisions in sorted(grouped.items()):
            state = evaluate_stage(
                [_vote(d) for d in decisions], project.required_reviewers
            )
            if not state.conflict:
                continue
            current = {v.decision_id for v in state.votes}
            conflicts.append(
                ConflictRead(
                    article_id=article_id,
                    title=titles[decisions[0].id],
                    stage=stage,
                    decisions=[
                        ReviewerDecisionRead(
                            decision_id=d.id,
                            reviewer_id=d.reviewer_id,
                            reviewer_name=names[d.id],
                            decision=d.decision,
                            reasoning=d.reasoning,
                            primary_exclusion_reason=d.primary_exclusion_reason,
                            confidence_score=d.confidence_score,
                            created_at=d.created_at,
                        )
                        for d in decisions
                        if d.id in current
                    ],
                )
            )
        return conflicts

    def _latest_ai_by_key(
        self, project_id: int, stage: Optional[ScreeningStage] = None
    ) -> dict[StageKey, ScreeningDecision]:
        """Latest AI decision per (article, stage)."""
        query = (
            select(ScreeningDecision)
            .join(Article, ScreeningDecision.article_id == Article.id)
            .where(
                Article.project_id == project_id,
                ScreeningDecision.source == DecisionSource.ai_agent,
            )
            .order_by(ScreeningDecision.created_at, ScreeningDecision.id)
        )
        if stage is not None:
            query = query.where(ScreeningDecision.stage == stage)
        return {(d.article_id, d.stage): d for d in self.session.exec(query).all()}

    def list_ai_disagreements(
        self, project: Project, stage: Optional[ScreeningStage] = None
    ) -> list[AIDisagreementRead]:
        """Articles where the latest AI include/exclude differs from the human outcome.

        AI ``uncertain`` decisions and articles without a settled human outcome are
        not reported.
        """
        outcomes = self.get_final_outcomes(project, stage)
        ai_by_key = self._latest_ai_by_key(project.id, stage)
        titles = dict(
            self.session.exec(
                select(Article.id, Article.title).where(
                    Article.project_id == project.id
                )
            ).all()
        )
        result: list[AIDisagreementRead] = []
        for key in sorted(outcomes):
            ai = ai_by_key.get(key)
            state = outcomes[key]
            if ai is None or ai.decision not in (INCLUDE, EXCLUDE):
                continue
            if ai.decision == state.outcome:
                continue
            result.append(
                AIDisagreementRead(
                    article_id=key[0],
                    title=titles.get(key[0]),
                    stage=key[1],
                    ai=AIDecisionSummary(
                        decision_id=ai.id,
                        decision=ai.decision,
                        confidence_score=ai.confidence_score,
                        reasoning=ai.reasoning,
                    ),
                    human_decision=state.outcome,
                    human_is_resolution=state.is_resolution,
                )
            )
        return result

    def get_agreement(self, project: Project, stage: ScreeningStage) -> AgreementRead:
        """Inter-reviewer and AI-vs-human agreement statistics for one stage."""
        grouped = self._group(self.human_decisions(project.id, stage))

        human: Optional[HumanAgreementRead] = None
        if project.required_reviewers >= 2:
            pairs: list[tuple[str, str]] = []
            reviewers: set[int] = set()
            for decisions in grouped.values():
                votes = latest_vote_per_reviewer(_vote(d) for d in decisions)
                if len(votes) < 2:
                    continue
                # Rater A is the lower reviewer id of the first two reviewers.
                a, b = sorted(votes[:2], key=lambda v: v.reviewer_id or 0)
                pairs.append((a.decision.value, b.decision.value))
                reviewers.update(v.reviewer_id for v in (a, b) if v.reviewer_id)
            human = HumanAgreementRead(
                reviewers=sorted(reviewers),
                n_articles=len(pairs),
                percent_agreement=percent_agreement(pairs),
                cohens_kappa=cohens_kappa(pairs),
            )

        outcomes = self.get_final_outcomes(project, stage)
        ai_by_key = self._latest_ai_by_key(project.id, stage)
        bin_pairs: list[tuple[bool, bool]] = []
        ai_uncertain = without_ai = 0
        for key, state in outcomes.items():
            ai = ai_by_key.get(key)
            if ai is None:
                without_ai += 1
            elif ai.decision not in (INCLUDE, EXCLUDE):
                ai_uncertain += 1
            else:
                bin_pairs.append((ai.decision == INCLUDE, state.outcome == INCLUDE))
        m = binary_metrics(bin_pairs)
        return AgreementRead(
            stage=stage,
            required_reviewers=project.required_reviewers,
            human_vs_human=human,
            ai_vs_human=AIAgreementRead(
                n_articles=m.n,
                true_positives=m.tp,
                false_positives=m.fp,
                true_negatives=m.tn,
                false_negatives=m.fn,
                accuracy=m.accuracy,
                sensitivity=m.sensitivity,
                specificity=m.specificity,
                cohens_kappa=m.kappa,
                ai_uncertain=ai_uncertain,
                without_ai_decision=without_ai,
            ),
        )

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
