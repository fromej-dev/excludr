"""Relevance ranking of the title/abstract queue (prioritized screening).

Every record of a prioritized project that is still waiting at title/abstract gets
a ``relevance_score`` (higher = more likely relevant). The scores come from a local
model trained on the humans' title/abstract decisions: TF-IDF features of title,
abstract, keywords and MeSH terms, and a class-balanced logistic regression. No LLM
is called.

Labels per article: the settled human outcome if there is one, else the majority of
the reviewers' latest votes. ``uncertain`` votes and conflicts are left out, and so
are AI decisions and records sent past title/abstract (``title_abstract_skipped``).
An article included at title/abstract and excluded later at full text still counts
as relevant. With dual screening, unsettled labels of articles still in screening
are dropped as well, so one reviewer's vote does not steer the other's queue.

Until there is at least one include and one exclude (cold start) records are ranked
by their similarity to the review question and the active inclusion criteria; if
that gives nothing, by a seeded random order.

Retraining runs in the background after human title/abstract decisions (see
``should_retrain`` for the throttle). The per-project registry below keeps at most
one run per project going, plus one queued follow-up. Like ``inflight``, it lives
in process memory under a ``threading.Lock``, which is enough for the current
single-process deployment; with several API workers two processes could rank the
same project at once (last writer wins, two ``RankingRun`` rows).
"""

import asyncio
import logging
import threading
import time
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Any, Optional

import anyio.to_thread
import numpy as np
from fastapi import BackgroundTasks
from scipy.sparse import csr_matrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sqlalchemy import Float, Integer, bindparam, column, update, values
from sqlmodel import Session, select

from app.core.config import get_settings
from app.core.database import engine
from app.features.criteria.models import Criterion, CriterionType
from app.features.projects.models import Project
from app.features.research.models import Article, ArticleStatus
from app.features.websocket.schemas import NotificationLevel
from app.features.websocket.services import NotificationService

from .consensus import (
    INCLUDE,
    UNCERTAIN,
    Vote,
    evaluate_stage,
    latest_vote_per_reviewer,
)
from .models import DecisionSource, RankingRun, ScreeningDecision, ScreeningStage

logger = logging.getLogger(__name__)

MODEL_VERSION = (
    "tfidf-logreg-v1"  # engine version; bump when any parameter below changes
)
METHOD_MODEL, METHOD_SIMILARITY, METHOD_RANDOM = "model", "similarity", "random"
TRIGGER_AUTO, TRIGGER_MANUAL = "auto", "manual"
RETRAIN_EVERY = 5  # new labels between automatic retrains
MIN_DOCS_FOR_MIN_DF = 10  # below this corpus size min_df=1
MAX_FEATURES = 100_000
WRITE_CHUNK = 5_000  # rows per UPDATE statement (2 params/row, below PG's 65535 limit)
IN_CHUNK = 5_000  # ids per IN (...) clause (SQLite variable limit)


# --- Labels ---------------------------------------------------------------


def label_from_votes(
    votes: Sequence[Vote], required_reviewers: int, *, settled_only: bool = False
) -> Optional[bool]:
    """True = relevant, False = not relevant, None = no usable label.

    A settled outcome (agreement or owner resolution) decides. A conflict gives
    None. While pending, the strict majority of the reviewers' latest votes counts
    (in practice dual screening with one vote so far); ``uncertain`` votes and ties
    give None. With ``settled_only`` the pending case gives None.
    """
    state = evaluate_stage(votes, required_reviewers)
    if state.outcome is not None:
        return state.outcome == INCLUDE
    if state.conflict or settled_only:
        return None
    current = latest_vote_per_reviewer(votes)
    if not current or any(v.decision == UNCERTAIN for v in current):
        return None
    includes = sum(1 for v in current if v.decision == INCLUDE)
    excludes = len(current) - includes
    if includes == excludes:
        return None
    return includes > excludes


def collect_labels(session: Session, project: Project) -> dict[int, bool]:
    """Relevance label per article from the humans' title/abstract decisions."""
    rows = session.exec(
        select(
            ScreeningDecision.id,
            ScreeningDecision.article_id,
            ScreeningDecision.reviewer_id,
            ScreeningDecision.decision,
            ScreeningDecision.is_resolution,
            Article.status,
        )
        .join(Article, ScreeningDecision.article_id == Article.id)
        .where(
            Article.project_id == project.id,
            ScreeningDecision.stage == ScreeningStage.title_abstract,
            ScreeningDecision.source == DecisionSource.human,
            Article.title_abstract_skipped.is_(False),
        )
        .order_by(ScreeningDecision.id)
    ).all()
    votes: dict[int, list[Vote]] = {}
    in_screening: dict[int, bool] = {}
    for decision_id, article_id, reviewer_id, decision, resolution, status in rows:
        votes.setdefault(article_id, []).append(
            Vote(decision_id, reviewer_id, decision, resolution)
        )
        in_screening[article_id] = status == ArticleStatus.screening
    dual = project.required_reviewers >= 2
    labels: dict[int, bool] = {}
    for article_id, article_votes in votes.items():
        label = label_from_votes(
            article_votes,
            project.required_reviewers,
            # Blinding: a single reviewer's vote must not shape the other's queue
            settled_only=dual and in_screening[article_id],
        )
        if label is not None:
            labels[article_id] = label
    return labels


# --- Text -----------------------------------------------------------------


def article_text(
    title: Optional[str],
    abstract: Optional[str],
    keywords: Optional[Sequence[str]],
    mesh_terms: Optional[Sequence[str]],
) -> str:
    """Text a record is ranked on (empty when it has none)."""
    parts = [
        title,
        abstract,
        "; ".join(keywords or []),
        "; ".join(mesh_terms or []),
    ]
    return "\n".join(part for part in parts if part)


def query_text(project: Project, criteria: Sequence[Criterion]) -> str:
    """Review question plus active inclusion criteria, for cold-start similarity."""
    included = sorted(
        (c for c in criteria if c.is_active and c.type == CriterionType.inclusion),
        key=lambda c: (c.order, c.id or 0),
    )
    parts = [project.review_question, *(c.description for c in included)]
    return "\n".join(part for part in parts if part and part.strip())


# --- Scoring (pure) ---------------------------------------------------------


def random_score(project_id: int, article_id: int) -> float:
    """Stable pseudo-random number in [0, 1) for a record (also seeds Phase 3's start)."""
    digest = sha256(f"{project_id}:{article_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def make_vectorizer(n_docs: int, *, strict: bool = True) -> TfidfVectorizer:
    """TF-IDF vectorizer; ``strict=False`` is the fallback for tiny or odd corpora."""
    return TfidfVectorizer(
        ngram_range=(1, 2),
        sublinear_tf=True,
        min_df=2 if strict and n_docs >= MIN_DOCS_FOR_MIN_DF else 1,
        # A fractional max_df would prune every shared term of a 2-document corpus
        max_df=1.0,
        stop_words="english" if strict else None,
        strip_accents="unicode",
        lowercase=True,
        max_features=MAX_FEATURES,
        dtype=np.float32,
    )


def _fit_matrix(docs: list[str]) -> Optional[tuple[TfidfVectorizer, csr_matrix]]:
    """Fit TF-IDF on the documents; None when there is no usable vocabulary."""
    for strict in (True, False):
        vectorizer = make_vectorizer(len(docs), strict=strict)
        try:
            return vectorizer, vectorizer.fit_transform(docs)
        except ValueError:  # empty vocabulary / everything pruned
            continue
    return None


# Fitting TF-IDF dominates a run and does not depend on the labels, so the matrix of
# the latest corpora is kept. The key is a hash of the ids and texts, which does not
# change when the ranking itself rewrites scores. In-process, like the registry below.
MATRIX_CACHE_SIZE = 4
_matrix_cache: "OrderedDict[int, tuple[str, csr_matrix]]" = OrderedDict()
_matrix_lock = threading.Lock()


def _fingerprint(ids: Sequence[int], docs: Sequence[str]) -> str:
    digest = sha256()
    for article_id, doc in zip(ids, docs, strict=True):
        digest.update(f"{article_id}\0{len(doc)}\0".encode())
        digest.update(doc.encode())
    return digest.hexdigest()


def _cached_matrix(
    project_id: int, ids: Sequence[int], docs: list[str]
) -> Optional[csr_matrix]:
    """TF-IDF matrix of the corpus, refit only when the ids or texts changed."""
    key = _fingerprint(ids, docs)
    with _matrix_lock:
        hit = _matrix_cache.get(project_id)
        if hit is not None and hit[0] == key:
            _matrix_cache.move_to_end(project_id)
            return hit[1]
    fitted = _fit_matrix(docs)
    if fitted is None:
        return None
    with _matrix_lock:
        _matrix_cache[project_id] = (key, fitted[1])
        _matrix_cache.move_to_end(project_id)
        while len(_matrix_cache) > MATRIX_CACHE_SIZE:
            _matrix_cache.popitem(last=False)
    return fitted[1]


@dataclass(frozen=True)
class Scores:
    """Scores for the pending records and how they were produced (METHOD_*)."""

    method: str
    by_article: dict[int, float]


def compute_scores(
    project_id: int,
    texts: dict[int, str],
    pending_ids: list[int],
    labels: dict[int, bool],
    query: str,
) -> Scores:
    """Score the pending records.

    The vectorizer is fit on the project's own corpus (labelled and pending
    together). With at least one include and one exclude a logistic regression
    scores by probability of relevance; otherwise by cosine similarity to ``query``;
    failing that by seeded random order. Scores are only comparable within one run.
    """
    if not pending_ids:
        return Scores(METHOD_RANDOM, {})
    ids = sorted(set(pending_ids) | set(labels))
    docs = [texts.get(i, "") for i in ids]
    row = {article_id: n for n, article_id in enumerate(ids)}
    pending_rows = [row[i] for i in pending_ids]

    if True in labels.values() and False in labels.values():
        matrix = _cached_matrix(project_id, ids, docs)
        if matrix is not None:
            label_ids = sorted(labels)
            model = LogisticRegression(
                class_weight="balanced",
                C=1.0,
                solver="liblinear",
                max_iter=1000,
                random_state=0,
            )
            model.fit(
                matrix[[row[i] for i in label_ids]], [labels[i] for i in label_ids]
            )
            proba = model.predict_proba(matrix[pending_rows])[:, 1]
            return Scores(
                METHOD_MODEL,
                {i: float(p) for i, p in zip(pending_ids, proba, strict=True)},
            )

    if query.strip() and pending_ids:
        fitted = _fit_matrix([*docs, query])
        if fitted is not None:
            _, matrix = fitted
            q = matrix[len(docs)]
            if q.nnz:
                sims = (matrix[pending_rows] @ q.T).toarray().ravel()
                if sims.size and sims.max() > 0:
                    return Scores(
                        METHOD_SIMILARITY,
                        {i: float(s) for i, s in zip(pending_ids, sims, strict=True)},
                    )

    return Scores(METHOD_RANDOM, {i: random_score(project_id, i) for i in pending_ids})


# --- Retrain rule (pure) ----------------------------------------------------


def should_retrain(
    includes: int, excludes: int, last: Optional[RankingRun], has_unscored: bool
) -> bool:
    """Whether an automatic run is due.

    Runs the first time, whenever a pending record has no score, once the model
    becomes possible, right after a new include, and every ``RETRAIN_EVERY`` new
    labels. Cold-start scores do not depend on labels, so they are not recomputed (unless
    the last run was a model run whose labels are gone).
    Counts are compared with the last run; a flipped include plus a new include
    leaves them equal, which the next 5-label step or a manual rerank corrects.
    """
    if last is None or has_unscored:
        return True
    if includes < 1 or excludes < 1:
        # Cold-start scores do not depend on labels, but a model run's scores do: once
        # the labels collapse to one class, go back to the cold-start order once.
        return last.method == METHOD_MODEL
    if last.method != METHOD_MODEL:
        return True
    if includes > last.labelled_includes:
        return True
    labelled = includes + excludes
    return labelled - (last.labelled_includes + last.labelled_excludes) >= RETRAIN_EVERY


# --- Writing scores ---------------------------------------------------------


def _pg_update_stmt(project_id: int, chunk: Sequence[tuple[int, float]]) -> Any:
    """PostgreSQL ``UPDATE ... FROM (VALUES ...)`` for one chunk of scores."""
    v = values(column("aid", Integer), column("score", Float), name="v").data(
        list(chunk)
    )
    return (
        update(Article)
        .where(Article.id == v.c.aid, Article.project_id == project_id)
        .values(relevance_score=v.c.score, updated_at=Article.updated_at)
        .execution_options(synchronize_session=False)
    )


def write_scores(session: Session, project_id: int, scores: dict[int, float]) -> None:
    """Bulk-write ``relevance_score`` (no commit; ``updated_at`` is left alone)."""
    items = sorted(scores.items())
    postgres = session.get_bind().dialect.name == "postgresql"
    table = Article.__table__
    for start in range(0, len(items), WRITE_CHUNK):
        chunk = items[start : start + WRITE_CHUNK]
        if postgres:
            session.exec(_pg_update_stmt(project_id, chunk))
        else:
            stmt = (
                update(table)
                .where(
                    table.c.id == bindparam("b_id"),
                    table.c.project_id == project_id,
                )
                .values(
                    relevance_score=bindparam("b_score"), updated_at=table.c.updated_at
                )
            )
            session.connection().execute(
                stmt, [{"b_id": i, "b_score": s} for i, s in chunk]
            )


# --- Orchestration ----------------------------------------------------------


def _pending_filter(project_id: int) -> tuple[Any, ...]:
    return (
        Article.project_id == project_id,
        Article.status == ArticleStatus.screening,
        Article.current_stage == ScreeningStage.title_abstract,
    )


def last_run(session: Session, project_id: int) -> Optional[RankingRun]:
    """The project's most recent ranking run."""
    return session.exec(
        select(RankingRun)
        .where(RankingRun.project_id == project_id)
        .order_by(RankingRun.created_at.desc(), RankingRun.id.desc())
    ).first()


def rerank_project(
    session: Session,
    project_id: int,
    *,
    trigger: str = TRIGGER_AUTO,
    user_id: Optional[int] = None,
    force: bool = False,
) -> Optional[RankingRun]:
    """Score the project's pending title/abstract records and record a run.

    Returns None when prioritization is off, nothing is pending, or (without
    ``force``) the retrain rule says a run is not due yet. Scores of records that
    already left title/abstract are kept as they were.
    """
    project = session.get(Project, project_id)
    if project is None or not project.prioritized_screening:
        return None
    pending = session.exec(
        select(Article.id, Article.relevance_score)
        .where(*_pending_filter(project_id))
        .order_by(Article.id)
    ).all()
    if not pending:
        return None
    pending_ids = [article_id for article_id, _ in pending]

    labels = collect_labels(session, project)
    includes = sum(labels.values())
    excludes = len(labels) - includes
    has_unscored = any(score is None for _, score in pending)
    if not force and not should_retrain(
        includes, excludes, last_run(session, project_id), has_unscored
    ):
        return None

    t0 = time.perf_counter()
    texts: dict[int, str] = {}
    wanted = sorted(set(pending_ids) | set(labels))
    for start in range(0, len(wanted), IN_CHUNK):
        for row in session.exec(
            select(
                Article.id,
                Article.title,
                Article.abstract,
                Article.keywords,
                Article.mesh_terms,
            ).where(Article.id.in_(wanted[start : start + IN_CHUNK]))
        ):
            texts[row[0]] = article_text(*row[1:])
    criteria = session.exec(
        select(Criterion)
        .where(
            Criterion.project_id == project_id,
            Criterion.is_active.is_(True),
            Criterion.type == CriterionType.inclusion,
        )
        .order_by(Criterion.order, Criterion.id)
    ).all()
    scores = compute_scores(
        project_id, texts, pending_ids, labels, query_text(project, criteria)
    )
    write_scores(session, project_id, scores.by_article)
    run = RankingRun(
        project_id=project_id,
        model_version=MODEL_VERSION,
        method=scores.method,
        trigger=trigger,
        triggered_by=user_id,
        labelled_includes=includes,
        labelled_excludes=excludes,
        scored=len(scores.by_article),
        duration_ms=int((time.perf_counter() - t0) * 1000),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


# --- Background execution and locking --------------------------------------


@dataclass(frozen=True)
class RerankRequest:
    """What a queued rerank was asked for."""

    trigger: str = TRIGGER_AUTO
    user_id: Optional[int] = None
    force: bool = False

    def merge(self, other: "RerankRequest") -> "RerankRequest":
        """Combine two requests: a manual one wins, force sticks."""
        base = other if self.trigger != TRIGGER_MANUAL else self
        return replace(base, force=self.force or other.force)


_train_slot = threading.BoundedSemaphore(1)  # one ranking at a time, process-wide
# Tests set this so the task is awaited instead of detached.
run_inline = False
_tasks: set[asyncio.Task] = set()
_lock = threading.Lock()
_running: set[int] = set()
_follow_up: dict[int, RerankRequest] = {}


def claim(project_id: int, request: RerankRequest) -> bool:
    """Start a run (True) or queue the request behind the running one (False)."""
    with _lock:
        if project_id not in _running:
            _running.add(project_id)
            return True
        existing = _follow_up.get(project_id)
        _follow_up[project_id] = existing.merge(request) if existing else request
        return False


def next_request(project_id: int) -> Optional[RerankRequest]:
    """Pop the queued follow-up, or release the project when there is none."""
    with _lock:
        request = _follow_up.pop(project_id, None)
        if request is None:
            _running.discard(project_id)
        return request


def is_running(project_id: int) -> bool:
    with _lock:
        return project_id in _running


def clear() -> None:
    """Drop all state (tests)."""
    with _lock:
        _running.clear()
        _follow_up.clear()
    with _matrix_lock:
        _matrix_cache.clear()


def _run_once(project_id: int, request: RerankRequest) -> Optional[RankingRun]:
    """One rerank in its own session (runs in a worker thread).

    Never uses the request's session, and at most one project trains at a time
    in this process.
    """
    with _train_slot, Session(engine) as session:
        run = rerank_project(
            session,
            project_id,
            trigger=request.trigger,
            user_id=request.user_id,
            force=request.force,
        )
        if run is not None:
            session.expunge(run)  # the summary is read after the session closes
        return run


async def _notify(
    project_id: int,
    message: str,
    data: dict[str, Any],
    level: NotificationLevel = NotificationLevel.INFO,
) -> None:
    """Tell the project room; never let a websocket problem break the task."""
    try:
        await NotificationService.notify_room(
            room_name=f"project_{project_id}",
            message=message,
            level=level,
            data=data,
        )
    except Exception:
        logger.exception("Failed to send ranking notification")


async def _drive(project_id: int, request: Optional[RerankRequest]) -> None:
    """Run the claimed request and its queued follow-ups, then release the project."""
    try:
        while request is not None:
            try:
                run = await anyio.to_thread.run_sync(_run_once, project_id, request)
            except Exception:
                logger.exception("Relevance ranking failed for project %s", project_id)
                await _notify(
                    project_id,
                    "Screening queue ranking failed",
                    {"type": "ranking_failed", "project_id": project_id},
                    NotificationLevel.WARNING,
                )
                run = None
            if run is not None:
                await _notify(
                    project_id,
                    "Screening queue re-ranked",
                    {
                        "type": "ranking_updated",
                        "project_id": project_id,
                        "run_id": run.id,
                        "method": run.method,
                        "trigger": run.trigger,
                        "scored": run.scored,
                        "labelled_includes": run.labelled_includes,
                        "labelled_excludes": run.labelled_excludes,
                        "auto": request.trigger == TRIGGER_AUTO,
                    },
                )
            request = next_request(project_id)
    except BaseException:
        # Release on cancellation too
        with _lock:
            _running.discard(project_id)
            _follow_up.pop(project_id, None)
        raise


async def rerank_in_background(
    project_id: int,
    trigger: str = TRIGGER_AUTO,
    user_id: Optional[int] = None,
    force: bool = False,
) -> None:
    """Hand a rerank off and return at once; coalesces overlapping requests.

    The work runs in a detached task on a worker thread with its own session, so
    the request that scheduled it can finish (and release its database
    connection) without waiting for the training.
    """
    request = RerankRequest(trigger, user_id, force)
    if not claim(project_id, request):
        return  # queued as the follow-up of the running task
    if run_inline:
        await _drive(project_id, request)
        return
    task = asyncio.get_running_loop().create_task(_drive(project_id, request))
    _tasks.add(task)  # keep a reference until it is done
    task.add_done_callback(_tasks.discard)


def schedule_rerank(
    background_tasks: BackgroundTasks,
    project: Project,
    *,
    trigger: str = TRIGGER_AUTO,
    user_id: Optional[int] = None,
    force: bool = False,
) -> bool:
    """Queue a rerank after the response; False when it does not apply.

    Does nothing unless the project is prioritized, and automatic triggers also
    need ``ranking_auto_retrain``. The throttle is checked in the background task,
    so the request itself does no ranking work.
    """
    if not project.prioritized_screening:
        return False
    if trigger == TRIGGER_AUTO and not get_settings().ranking_auto_retrain:
        return False
    background_tasks.add_task(rerank_in_background, project.id, trigger, user_id, force)
    return True
