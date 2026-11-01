"""Order of a reviewer's screening queue.

Used by ``GET /screening/next`` and ``GET /articles?pending_for_me=true``, so both
serve the same order. Three modes:

- ``id``: import order. Full text, completed, and projects without prioritization.
- ``random_start``: prioritized title/abstract while fewer than
  ``Project.ranking_min_random`` outcomes are settled; a seeded random order that is
  stable across requests.
- ``ranked``: prioritized title/abstract, ``relevance_score DESC NULLS LAST``.
  Articles without a score yet (new imports) come last.

Ties always break on ``Article.id``. "Settled" means a distinct article with a human
title/abstract decision that has left title/abstract screening (not skipped, not
closed by the stopping rule), counted project-wide and over all time. That is about
the number of labels the ranking model can train on, whatever the review mode.
Dual-screening reviewers see the same order (the decisions stay blind).

This module imports models only (no scikit-learn, no services).
"""

from dataclasses import dataclass
from enum import Enum

from sqlalchemy import BigInteger, cast, literal
from sqlmodel import Session, func, select

from ..projects.models import Project
from ..research.models import Article, ArticleStatus
from .models import DecisionSource, ScreeningDecision, ScreeningStage

RANDOM_MOD = 2_147_483_647  # 2**31 - 1, prime
_MUL, _SEED_MUL, _SEED_ADD = 48271, 69621, 12345


class QueueMode(str, Enum):
    id = "id"
    random_start = "random_start"
    ranked = "ranked"


@dataclass(frozen=True)
class QueueOrder:
    """ORDER BY expressions (always ending in ``Article.id``) and the mode they implement."""

    mode: QueueMode
    clauses: tuple
    random_start_remaining: int = 0  # settled outcomes to go; 0 unless random_start


def random_key(project_id: int, article_id: int) -> int:
    """Python mirror of :func:`random_key_expr`."""
    a = (article_id * _MUL + project_id * _SEED_MUL + _SEED_ADD) % RANDOM_MOD
    return (a * a) % RANDOM_MOD


def random_key_expr(project_id: int):
    """Portable SQL expression for a per-article pseudo-random key, seeded by the project.

    Integer ``+ * %`` only, so SQLite and PostgreSQL agree. ``a < 2**31`` so ``a * a < 2**62``
    fits a 64-bit integer; the id is cast to BIGINT because PostgreSQL ``integer * integer``
    would overflow for large ids.
    """
    seed = literal(project_id * _SEED_MUL + _SEED_ADD, BigInteger)
    a = (cast(Article.id, BigInteger) * _MUL + seed) % RANDOM_MOD
    return (a * a) % RANDOM_MOD


def ranked_clauses() -> tuple:
    return (Article.relevance_score.desc().nulls_last(), Article.id.asc())


def settled_title_abstract_count(session: Session, project_id: int, limit: int) -> int:
    """Number of settled human title/abstract outcomes, counting at most ``limit``."""
    human_decided = select(ScreeningDecision.id).where(
        ScreeningDecision.article_id == Article.id,
        ScreeningDecision.stage == ScreeningStage.title_abstract,
        ScreeningDecision.source == DecisionSource.human,
    )
    inner = (
        select(Article.id)
        .where(
            Article.project_id == project_id,
            Article.status.notin_((ArticleStatus.imported, ArticleStatus.screening)),
            Article.title_abstract_skipped.is_(False),
            Article.not_screened_stopping_rule.is_(False),
            human_decided.exists(),
        )
        .limit(limit)
        .subquery()
    )
    return session.exec(select(func.count()).select_from(inner)).one()


def queue_order(
    session: Session, project: Project, stage: ScreeningStage
) -> QueueOrder:
    """Queue order for ``project`` at ``stage`` (see the module docstring)."""
    if stage != ScreeningStage.title_abstract or not project.prioritized_screening:
        return QueueOrder(QueueMode.id, (Article.id.asc(),))
    n = project.ranking_min_random or 0
    if n > 0:
        settled = settled_title_abstract_count(session, project.id, n)
        if settled < n:
            return QueueOrder(
                QueueMode.random_start,
                (random_key_expr(project.id).asc(), Article.id.asc()),
                n - settled,
            )
    return QueueOrder(QueueMode.ranked, ranked_clauses())
