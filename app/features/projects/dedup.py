"""Deterministic duplicate detection for article imports (scoped to one project)."""

import re
from typing import Optional

from sqlmodel import Session, select

from app.features.research.models import Article

_APOSTROPHES = re.compile(r"['’‘`]")
_NON_WORD = re.compile(r"[^\w\s]|_")
_WHITESPACE = re.compile(r"\s+")

TitleYearKey = tuple[str, Optional[int]]


def normalize_title(title: Optional[str]) -> str:
    """Normalize a title for duplicate comparison.

    Lowercases, drops apostrophes, turns other punctuation into spaces and
    collapses whitespace, so "The Cat's Hat: A Study!" and "the cats hat - a study"
    compare equal.
    """
    if not title:
        return ""
    text = _APOSTROPHES.sub("", title.casefold())
    text = _NON_WORD.sub(" ", text)
    return _WHITESPACE.sub(" ", text).strip()


class ProjectArticleIndex:
    """In-memory lookup of a project's existing articles for import dedup.

    Built once per import (one query) and updated as new articles are added, so
    duplicates inside the same file are detected as well.
    """

    def __init__(self, session: Session, project_id: int) -> None:
        self.by_doi: dict[str, Article] = {}
        self.by_pmid: dict[str, Article] = {}
        self.by_title_year: dict[TitleYearKey, Article] = {}
        for article in session.exec(
            select(Article).where(Article.project_id == project_id)
        ).all():
            self.add(article)

    @staticmethod
    def title_year_key(
        title: Optional[str], year: Optional[int]
    ) -> Optional[TitleYearKey]:
        """Return the (normalized title, year) key, or None if there is no title."""
        normalized = normalize_title(title)
        return (normalized, year) if normalized else None

    def add(self, article: Article) -> None:
        """Register an article so later entries can be matched against it."""
        if article.doi:
            self.by_doi.setdefault(article.doi, article)
        if article.pmid:
            self.by_pmid.setdefault(article.pmid, article)
        key = self.title_year_key(article.title, article.year)
        if key:
            self.by_title_year.setdefault(key, article)

    def find(
        self,
        doi: Optional[str],
        pmid: Optional[str],
        title: Optional[str],
        year: Optional[int],
    ) -> tuple[Optional[Article], str]:
        """Find an existing duplicate.

        Matches on DOI, then PMID. Only when the entry has neither identifier
        does it fall back to normalized title + year.

        Returns:
            ``(article, kind)`` where kind is ``"identifier"``, ``"title_year"``
            or ``""`` when nothing matched.
        """
        if doi and doi in self.by_doi:
            return self.by_doi[doi], "identifier"
        if pmid and pmid in self.by_pmid:
            return self.by_pmid[pmid], "identifier"
        if not doi and not pmid:
            key = self.title_year_key(title, year)
            if key and key in self.by_title_year:
                return self.by_title_year[key], "title_year"
        return None, ""
