"""Match bulk-uploaded full-text PDFs to a project's articles.

Each PDF is matched on, in order of strength:

1. **Article id** in the filename (``article-12.pdf``, the name Excludr gives a
   downloaded PDF).
2. **Identifiers**: the DOI in the PDF metadata, a DOI/PMID/PMCID in the
   filename (``10.1016_j.x.2021.01.002.pdf``, ``PMID12345678.pdf``), then a DOI or
   labelled PMID/PMCID on the first two pages. A DOI found only in the page text
   may belong to a cited paper, so it is confirmed against the article title.
3. **Title**: the article title on the first pages, in the PDF title metadata or
   in the filename (reference-manager names like ``Smith - 2020 - Title.pdf``),
   confirmed with the first author's surname and the publication year.

Texts are compared as "keys": lower-case ASCII letters and digits only, so line
breaks, hyphenation, punctuation and ligatures do not matter.

A match is proposed only when it is ``high`` or ``medium`` confidence and points
at a single article; weaker or tied results are returned as candidates for the
user to choose from.
"""

import logging
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal, Optional

from .models import Article

logger = logging.getLogger(__name__)

Confidence = Literal["high", "medium", "low"]
_RANK: dict[str, int] = {"high": 3, "medium": 2, "low": 1}

FIRST_PAGES = 2
MAX_PAGE_CHARS = 20_000
MIN_TITLE_KEY = 15  # shorter titles ("Editorial") match far too much
TITLE_PREFIX_KEY = 40  # long titles are also tried by their start (subtitles differ)
MIN_DOI_KEY = 8
MIN_SURNAME_KEY = 3
MAX_CANDIDATES = 5

# Excludr's own download name; browsers may append " (1)"
_ARTICLE_ID_RE = re.compile(r"^article[-_](\d+)(?:\s*\(\d+\))?$", re.I)
_PMCID_RE = re.compile(r"\bPMC[-_ ]?(\d{4,9})\b", re.I)
_PMID_FILENAME_RE = re.compile(r"pmid[-_ :]*(\d{1,9})", re.I)
_PMID_TEXT_RE = re.compile(r"\bPMID\s*:?\s*(\d{1,9})\b")
_DIGITS_RE = re.compile(r"^\d{6,9}$")
_TAG_RE = re.compile(r"<[^>]+>")
_DOI_PREFIX_RE = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:)", re.I)


def text_key(value: Optional[str]) -> str:
    """Lower-case ASCII letters and digits of ``value`` (tags and accents removed)."""
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", _TAG_RE.sub(" ", value))
    value = value.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "", value)


def doi_key(doi: Optional[str]) -> str:
    """Key of a DOI without its ``https://doi.org/`` or ``doi:`` prefix."""
    if not doi:
        return ""
    return text_key(_DOI_PREFIX_RE.sub("", doi.strip()))


def first_author_surname(authors: Optional[list[str]]) -> Optional[str]:
    """Surname of the first author: ``"Smith, John"`` and ``"Smith J"`` give Smith."""
    if not authors:
        return None
    first = (authors[0] or "").strip()
    if not first:
        return None
    if "," in first:
        return first.split(",", 1)[0].strip() or None
    return first.split()[0]


def _normalize_pmcid(value: Optional[str]) -> str:
    digits = re.sub(r"\D", "", value or "")
    return f"PMC{digits}" if digits else ""


def _normalize_pmid(value: Optional[str]) -> str:
    digits = re.sub(r"\D", "", value or "")
    return digits.lstrip("0")


# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------


@dataclass
class PdfFingerprint:
    """What matching looks at in one PDF."""

    filename: str
    metadata_title: str = ""
    metadata_text: str = ""  # subject, keywords and XMP; searched for a DOI
    page_text: str = ""  # first pages

    @property
    def has_text(self) -> bool:
        return bool(self.page_text.strip())


def read_fingerprint(path: str, filename: str) -> PdfFingerprint:
    """Read metadata and the first pages of the PDF at ``path``.

    Raises:
        ValueError: If the file cannot be opened as a PDF.
    """
    import fitz  # PyMuPDF

    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise ValueError("could not be read as a PDF") from exc
    try:
        meta = doc.metadata or {}
        try:
            xmp = doc.get_xml_metadata() or ""
        except Exception:
            xmp = ""
        pages = []
        for index in range(min(FIRST_PAGES, len(doc))):
            try:
                pages.append(doc[index].get_text()[:MAX_PAGE_CHARS])
            except Exception:
                logger.warning("Could not read page %d of %s", index, filename)
        return PdfFingerprint(
            filename=filename,
            metadata_title=meta.get("title") or "",
            metadata_text=" ".join(
                [meta.get("subject") or "", meta.get("keywords") or "", xmp]
            ),
            page_text="\n".join(pages),
        )
    finally:
        doc.close()


@dataclass
class _Ref:
    """The parts of an article that matching uses."""

    id: int
    title: Optional[str]
    year: Optional[int]
    first_author: Optional[str]
    has_full_text: bool
    title_key: str
    doi_key: str
    surname_key: str


class ArticleIndex:
    """Lookup tables over a project's articles, built once per upload request."""

    def __init__(self, articles: Iterable[Article]):
        self.refs: dict[int, _Ref] = {}
        self.by_doi: dict[str, int] = {}
        self.by_pmid: dict[str, int] = {}
        self.by_pmcid: dict[str, int] = {}
        for article in articles:
            surname = first_author_surname(article.authors)
            ref = _Ref(
                id=article.id,
                title=article.title,
                year=article.year,
                first_author=surname,
                has_full_text=bool(article.full_text_retrieved),
                title_key=text_key(article.title),
                doi_key=doi_key(article.doi),
                surname_key=text_key(surname),
            )
            self.refs[ref.id] = ref
            if len(ref.doi_key) >= MIN_DOI_KEY:
                self.by_doi[ref.doi_key] = ref.id
            if pmid := _normalize_pmid(article.pmid):
                self.by_pmid[pmid] = ref.id
            if pmcid := _normalize_pmcid(article.pmcid):
                self.by_pmcid[pmcid] = ref.id


# --------------------------------------------------------------------------
# Outputs
# --------------------------------------------------------------------------


@dataclass
class Candidate:
    """One article a PDF may belong to, and why."""

    article_id: int
    method: str  # e.g. "doi_metadata", "title_text"
    confidence: Confidence


@dataclass
class MatchOutcome:
    """The proposed article (if any) and the alternatives, strongest first."""

    match: Optional[Candidate] = None
    candidates: list[Candidate] = field(default_factory=list)


# --------------------------------------------------------------------------
# Matching
# --------------------------------------------------------------------------


@dataclass
class _Keys:
    filename: str
    stem: str
    page: str
    metadata: str
    metadata_title: str
    raw_text: str  # pages + filename, for year and labelled ids


def _keys(fp: PdfFingerprint) -> _Keys:
    stem = fp.filename.rsplit(".", 1)[0] if "." in fp.filename else fp.filename
    return _Keys(
        filename=text_key(stem),
        stem=stem,
        page=text_key(fp.page_text),
        metadata=text_key(fp.metadata_text),
        metadata_title=text_key(fp.metadata_title),
        raw_text=f"{fp.page_text}\n{stem}",
    )


def _drop_contained(hits: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Drop hits whose key is part of another hit's key (``10.1/ab`` vs ``10.1/abc``)."""
    return [
        (aid, key)
        for aid, key in hits
        if not any(key != other and key in other for _, other in hits)
    ]


def _doi_hits(index: ArticleIndex, haystack: str) -> list[int]:
    """Articles whose DOI occurs in ``haystack``, in order of first occurrence."""
    if not haystack:
        return []
    hits = [(aid, key) for key, aid in index.by_doi.items() if key in haystack]
    hits = _drop_contained(hits)
    hits.sort(key=lambda hit: haystack.find(hit[1]))
    return [aid for aid, _ in hits]


def _title_confirmed(ref: _Ref, keys: _Keys) -> bool:
    """Whether the article's title (or its start) is on the first pages."""
    if len(ref.title_key) < MIN_TITLE_KEY:
        return False
    return ref.title_key[:TITLE_PREFIX_KEY] in keys.page


def _identifier_candidates(index: ArticleIndex, keys: _Keys) -> list[Candidate]:
    found: list[Candidate] = []

    if m := _ARTICLE_ID_RE.match(keys.stem.strip()):
        if int(m.group(1)) in index.refs:
            found.append(Candidate(int(m.group(1)), "article_id_filename", "high"))

    for aid in _doi_hits(index, keys.metadata)[:1]:
        found.append(Candidate(aid, "doi_metadata", "high"))
    for aid in _doi_hits(index, keys.filename)[:1]:
        found.append(Candidate(aid, "doi_filename", "high"))

    for m in _PMCID_RE.finditer(keys.stem):
        if aid := index.by_pmcid.get(f"PMC{m.group(1)}"):
            found.append(Candidate(aid, "pmcid_filename", "high"))
    pmids = [m.group(1) for m in _PMID_FILENAME_RE.finditer(keys.stem)]
    if _DIGITS_RE.match(keys.stem.strip()):
        pmids.append(keys.stem.strip())
    for pmid in pmids:
        if aid := index.by_pmid.get(_normalize_pmid(pmid)):
            found.append(Candidate(aid, "pmid_filename", "high"))

    # Ids in the page text may be a cited paper's: confirm with the title.
    text_hits = [(aid, "doi_text") for aid in _doi_hits(index, keys.page)]
    for m in _PMCID_RE.finditer(keys.raw_text):
        if aid := index.by_pmcid.get(f"PMC{m.group(1)}"):
            text_hits.append((aid, "pmcid_text"))
    for m in _PMID_TEXT_RE.finditer(keys.raw_text):
        if aid := index.by_pmid.get(_normalize_pmid(m.group(1))):
            text_hits.append((aid, "pmid_text"))
    for position, (aid, method) in enumerate(text_hits):
        ref = index.refs[aid]
        if _title_confirmed(ref, keys):
            confidence: Confidence = "high"
        else:
            confidence = "medium" if position == 0 else "low"
        found.append(Candidate(aid, method, confidence))
    return found


def _title_candidates(index: ArticleIndex, keys: _Keys) -> list[Candidate]:
    hits: list[tuple[int, str, str, bool]] = []  # id, title key, where, full title
    for ref in index.refs.values():
        title = ref.title_key
        if len(title) < MIN_TITLE_KEY:
            continue
        meta = keys.metadata_title
        if len(meta) >= MIN_TITLE_KEY and (title in meta or meta in title):
            hits.append((ref.id, title, "metadata", True))
        elif title in keys.page:
            hits.append((ref.id, title, "text", True))
        elif title in keys.filename:
            hits.append((ref.id, title, "filename", True))
        elif len(title) > TITLE_PREFIX_KEY:
            prefix = title[:TITLE_PREFIX_KEY]
            if prefix in keys.page:
                hits.append((ref.id, title, "text", False))
            elif prefix in keys.filename:
                hits.append((ref.id, title, "filename", False))

    # "Parenting stress" inside "Parenting stress in fathers ..." is not a match
    longer = _drop_contained([(aid, key) for aid, key, _, _ in hits])
    keep = {aid for aid, _ in longer}

    found = []
    for aid, _, where, full in hits:
        if aid not in keep:
            continue
        ref = index.refs[aid]
        haystack = keys.page + keys.filename
        author = len(ref.surname_key) >= MIN_SURNAME_KEY and ref.surname_key in haystack
        year = ref.year is not None and str(ref.year) in keys.raw_text
        if full:
            confidence: Confidence = "high" if author or year else "medium"
        else:
            confidence = "medium" if author and year else "low"
        found.append(Candidate(aid, f"title_{where}", confidence))
    return found


def match_pdf(fp: PdfFingerprint, index: ArticleIndex) -> MatchOutcome:
    """Propose the article ``fp`` belongs to.

    The strongest candidate per article is kept. The best one becomes the match
    when it is at least ``medium`` and no other article reaches the same level;
    identifier matches beat title matches of the same confidence.
    """
    keys = _keys(fp)
    best: dict[int, Candidate] = {}
    for candidate in _identifier_candidates(index, keys) + _title_candidates(
        index, keys
    ):
        current = best.get(candidate.article_id)
        if current is None or _RANK[candidate.confidence] > _RANK[current.confidence]:
            best[candidate.article_id] = candidate

    ranked = sorted(
        best.values(),
        key=lambda c: (
            -_RANK[c.confidence],
            not c.method.startswith(("article_id", "doi", "pmid", "pmcid")),
        ),
    )
    outcome = MatchOutcome(candidates=ranked[:MAX_CANDIDATES])
    if not ranked or _RANK[ranked[0].confidence] < _RANK["medium"]:
        return outcome

    top = ranked[0]
    rivals = [c for c in ranked[1:] if c.confidence == top.confidence]
    top_is_id = not top.method.startswith("title")
    if rivals and not (top_is_id and all(c.method.startswith("title") for c in rivals)):
        return outcome
    outcome.match = top
    return outcome
