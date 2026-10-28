"""Automatic open-access full-text retrieval.

Sources are tried in order and the first that yields a usable full text wins:

1. **Unpaywall** (needs a DOI and ``settings.unpaywall_email``): best open-access
   PDF location, then any other location that advertises a PDF.
2. **PubMed Central** (needs a PMCID: the article's own, one seen in Unpaywall's
   locations, or a PMID/DOI resolved through the NCBI ID converter): the PDF in
   the PMC Cloud Service bucket (``pmc-oa-opendata`` on S3), found through the
   article version's metadata JSON. It replaced the PMC OA web service, retired
   in August 2026, and is one of the services PMC allows automated retrieval from.
3. **Europe PMC** full-text XML (same PMCID): plain text of the body sections.
   No PDF is stored in this case; only ``full_text_content`` is set.

Downloads use bounded timeouts, follow redirects, are capped at
``settings.max_upload_mb`` and must start with ``%PDF-``. Requests identify
themselves with a contact e-mail, are rate limited per host and retried with
backoff on 429/5xx (at most :data:`MAX_ATTEMPTS` tries).
"""

import asyncio
import ipaddress
import json
import logging
import os
import re
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote, urlsplit

import httpx
from sqlmodel import Session

from app.core.config import get_settings
from app.core.uploads import remove_file
from .models import Article, ArticleStatus, FullTextSource
from .pdf_extraction import extract_text_from_pdf_safe
from .schemas import FullTextRetrievalResult, SourceAttempt
from .services import ArticleService

logger = logging.getLogger(__name__)

UNPAYWALL_URL = "https://api.unpaywall.org/v2/"
IDCONV_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
PMC_S3_URL = "https://pmc-oa-opendata.s3.amazonaws.com/"
PMC_S3_BUCKET = "pmc-oa-opendata"
EUROPEPMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"

PDF_MAGIC = b"%PDF-"
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.0  # doubled after each failed attempt
MAX_RETRY_AFTER_SECONDS = 30.0
MIN_FULLTEXT_CHARS = 200  # shorter Europe PMC "bodies" are abstracts/stubs
MAX_ERROR_CHARS = 500
_CHUNK = 64 * 1024

# Minimum seconds between requests to the same host.
HOST_INTERVALS: dict[str, float] = {
    "api.unpaywall.org": 0.2,
    "www.ncbi.nlm.nih.gov": 0.35,  # NCBI allows 3 requests/second without a key
    "pmc-oa-opendata.s3.amazonaws.com": 0.1,
    "www.ebi.ac.uk": 0.2,
}
DEFAULT_HOST_INTERVAL = 0.5

_RETRYABLE = frozenset({429, 500, 502, 503, 504})


def eligible_for_retrieval(article: Article) -> bool:
    """Articles that wait for a full text and do not have one yet."""
    return (
        article.status == ArticleStatus.awaiting_full_text
        and not article.full_text_retrieved
    )


class HostRateLimiter:
    """Spaces out requests per host (slot reservation, safe across event loops)."""

    def __init__(self) -> None:
        self._next_slot: dict[str, float] = {}

    async def wait(self, host: str) -> None:
        """Sleep until this host may be called again, reserving the next slot."""
        interval = HOST_INTERVALS.get(host, DEFAULT_HOST_INTERVAL)
        now = time.monotonic()
        slot = max(now, self._next_slot.get(host, 0.0))
        self._next_slot[host] = slot + interval
        if slot > now:
            await asyncio.sleep(slot - now)


rate_limiter = HostRateLimiter()


class SourceError(Exception):
    """A source could not deliver. ``status`` is the attempt status to report."""

    def __init__(self, detail: str, status: str = "error"):
        super().__init__(detail)
        self.detail = detail
        self.status = status


@dataclass
class _Fetched:
    """What a source produced: PDF bytes, or text only."""

    pdf: Optional[bytes] = None
    text: Optional[str] = None


@dataclass
class _Context:
    """Per-article state shared by the sources."""

    article: Article
    client: httpx.AsyncClient
    max_bytes: int
    email: Optional[str]
    unpaywall_email: Optional[str]
    pmcid: Optional[str] = None
    pmcid_resolved: bool = False
    # Why the ID converter could not be asked, if it could not
    pmcid_problem: Optional[str] = None


def build_client() -> httpx.AsyncClient:
    """Create the polite HTTP client used for all retrieval requests."""
    settings = get_settings()
    contact = settings.unpaywall_email or settings.pubmed_email
    agent = f"Excludr/1.0 (mailto:{contact})" if contact else "Excludr/1.0"
    return httpx.AsyncClient(
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
        max_redirects=5,
        headers={"User-Agent": agent},
    )


def _check_url(url: str) -> None:
    """Reject non-http(s) URLs and literal loopback/private addresses."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or not host:
        raise SourceError("unsupported download URL")
    if host == "localhost" or host.endswith(".localhost"):
        raise SourceError("refusing to fetch a local address")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if not ip.is_global:
        raise SourceError("refusing to fetch a non-public address")


def _retry_delay(response: Optional[httpx.Response], attempt: int) -> float:
    delay = RETRY_BACKOFF_SECONDS * (2**attempt)
    if response is not None:
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            delay = max(delay, min(float(retry_after), MAX_RETRY_AFTER_SECONDS))
    return delay


async def _fetch(
    ctx: _Context,
    url: str,
    params: Optional[dict[str, str]] = None,
    *,
    accept_404: bool = False,
) -> Optional[bytes]:
    """GET ``url`` with rate limiting, retries and a size cap.

    Returns the body, or None for a 404 when ``accept_404`` is set.

    Raises:
        SourceError: On a final HTTP/transport failure or an oversized body.
    """
    _check_url(url)
    host = urlsplit(url).hostname or ""
    last_problem = "request failed"
    for attempt in range(MAX_ATTEMPTS):
        await rate_limiter.wait(host)
        response: Optional[httpx.Response] = None
        try:
            async with ctx.client.stream("GET", url, params=params) as response:
                if response.status_code in _RETRYABLE:
                    last_problem = f"HTTP {response.status_code}"
                elif response.status_code == 404 and accept_404:
                    return None
                elif response.status_code >= 400:
                    raise SourceError(f"HTTP {response.status_code}")
                else:
                    declared = response.headers.get("Content-Length", "")
                    if declared.isdigit() and int(declared) > ctx.max_bytes:
                        raise SourceError("file too large")
                    body = bytearray()
                    async for chunk in response.aiter_bytes(_CHUNK):
                        body.extend(chunk)
                        if len(body) > ctx.max_bytes:
                            raise SourceError("file too large")
                    return bytes(body)
        except httpx.TransportError as exc:
            last_problem = f"network error ({type(exc).__name__})"
        if attempt < MAX_ATTEMPTS - 1:
            await asyncio.sleep(_retry_delay(response, attempt))
    raise SourceError(f"{last_problem} after {MAX_ATTEMPTS} attempts")


async def _download_pdf(ctx: _Context, url: str) -> bytes:
    """Download ``url`` and make sure it is really a PDF."""
    body = await _fetch(ctx, url)
    if not body or not body.startswith(PDF_MAGIC):
        raise SourceError("response was not a PDF")
    return body


def _clean_doi(doi: str) -> str:
    return re.sub(r"^(https?://(dx\.)?doi\.org/|doi:)", "", doi.strip(), flags=re.I)


def _normalize_pmcid(value: str) -> str:
    value = value.strip().upper()
    return value if value.startswith("PMC") else f"PMC{value}"


# --------------------------------------------------------------------------
# Sources
# --------------------------------------------------------------------------


async def _from_unpaywall(ctx: _Context) -> _Fetched:
    if not ctx.unpaywall_email:
        raise SourceError("not configured (UNPAYWALL_EMAIL unset)", "not_configured")
    if not ctx.article.doi:
        raise SourceError("article has no DOI", "not_available")
    doi = _clean_doi(ctx.article.doi)
    body = await _fetch(
        ctx,
        UNPAYWALL_URL + quote(doi, safe="/"),
        {"email": ctx.unpaywall_email},
        accept_404=True,
    )
    if body is None:
        raise SourceError("DOI not found in Unpaywall", "not_available")
    try:
        data = _json_object(body)
    except ValueError as exc:
        raise SourceError("invalid Unpaywall response") from exc

    locations = [data.get("best_oa_location"), *(data.get("oa_locations") or [])]
    urls: list[str] = []
    for location in locations:
        location = location or {}
        url = location.get("url_for_pdf")
        if url and url not in urls:
            urls.append(url)
        # PMC copies are listed as landing pages; their PMCID helps the next sources
        if not ctx.pmcid:
            ctx.pmcid = _pmcid_from_url(location.get("url_for_landing_page") or "")
    if not urls:
        raise SourceError("no open-access PDF location", "not_available")

    problems: list[str] = []
    for url in urls:
        try:
            return _Fetched(pdf=await _download_pdf(ctx, url))
        except SourceError as exc:
            logger.info("Unpaywall candidate failed (%s): %s", url, exc.detail)
            problems.append(f"{urlsplit(url).hostname}: {exc.detail}")
    raise SourceError(
        f"none of {len(urls)} PDF location(s) could be downloaded"
        f" ({'; '.join(problems)})"
    )


_PMC_URL = re.compile(
    r"(?:ncbi\.nlm\.nih\.gov/pmc/articles|pmc\.ncbi\.nlm\.nih\.gov/articles)"
    r"/(?:PMC)?(\d+)",
    re.IGNORECASE,
)


def _pmcid_from_url(url: str) -> Optional[str]:
    match = _PMC_URL.search(url)
    return f"PMC{match.group(1)}" if match else None


def _json_object(body: bytes) -> dict:
    """Parse a JSON object body."""
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    return data


async def _resolve_pmcid(ctx: _Context) -> Optional[str]:
    """PMCID from the article or Unpaywall, else via the NCBI ID converter.

    The converter is asked for the PMID first, then the DOI; a failed request
    for one does not stop the other. A PMID field holding anything but digits
    (another database's accession number) is not sent: the converter rejects it.
    """
    if ctx.article.pmcid:
        return _normalize_pmcid(ctx.article.pmcid)
    if ctx.pmcid or ctx.pmcid_resolved:
        return ctx.pmcid
    ctx.pmcid_resolved = True
    pmid = (ctx.article.pmid or "").strip()
    identifiers = [pmid] if pmid.isdigit() else []
    if ctx.article.doi:
        identifiers.append(_clean_doi(ctx.article.doi))
    problems: list[str] = []
    for identifier in identifiers:
        params = {"ids": identifier, "format": "json", "tool": "excludr"}
        if ctx.email:
            params["email"] = ctx.email
        try:
            body = await _fetch(ctx, IDCONV_URL, params)
            records = _json_object(body or b"{}").get("records") or []
        except SourceError as exc:
            problems.append(exc.detail)
            continue
        except ValueError:
            problems.append("invalid ID converter response")
            continue
        for record in records:
            if record.get("pmcid"):
                ctx.pmcid = _normalize_pmcid(str(record["pmcid"]))
                return ctx.pmcid
    if problems:
        ctx.pmcid_problem = f"ID converter: {'; '.join(problems)}"
    return None


def _no_pmcid(ctx: _Context) -> SourceError:
    if ctx.pmcid_problem:
        return SourceError(f"no PMCID available ({ctx.pmcid_problem})")
    return SourceError("no PMCID available", "not_available")


def _s3_versions(listing: bytes, pmcid: str) -> list[str]:
    """Version prefixes (``PMC123.2``) in an S3 listing, highest number first."""
    try:
        root = ET.fromstring(listing)
    except ET.ParseError as exc:
        raise SourceError("invalid PMC dataset listing") from exc
    pattern = re.compile(rf"^{re.escape(pmcid)}\.(\d+)/$")
    versions: list[tuple[int, str]] = []
    for element in root.iter():
        if _local(element.tag) == "Prefix" and element.text:
            if match := pattern.match(element.text):
                versions.append((int(match.group(1)), element.text.rstrip("/")))
    return [name for _, name in sorted(versions, reverse=True)]


def _s3_https(url: str) -> str:
    """``s3://pmc-oa-opendata/KEY?md5=...`` as a public HTTPS URL."""
    parts = urlsplit(url)
    if parts.scheme != "s3" or parts.netloc != PMC_S3_BUCKET or not parts.path:
        raise SourceError("unexpected PDF location in PMC metadata")
    return PMC_S3_URL + parts.path.lstrip("/")


async def _from_pmc(ctx: _Context) -> _Fetched:
    pmcid = await _resolve_pmcid(ctx)
    if not pmcid:
        raise _no_pmcid(ctx)
    listing = await _fetch(
        ctx,
        PMC_S3_URL,
        {"list-type": "2", "prefix": f"{pmcid}.", "delimiter": "/"},
    )
    versions = _s3_versions(listing or b"", pmcid)
    if not versions:
        raise SourceError("not in the PMC open-access dataset", "not_available")
    # PDFs exist only where the licence allows; any version's PDF will do
    for version in versions:
        body = await _fetch(
            ctx, f"{PMC_S3_URL}{version}/{version}.json", accept_404=True
        )
        try:
            pdf_url = _json_object(body or b"{}").get("pdf_url")
        except ValueError:
            continue
        if pdf_url:
            return _Fetched(pdf=await _download_pdf(ctx, _s3_https(str(pdf_url))))
    raise SourceError("PMC has no PDF for this article", "not_available")


_TEXT_TAGS = {"title", "p"}
_SKIPPED_TAGS = {"table-wrap", "fig", "supplementary-material", "disp-formula"}


def _local(tag: object) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def jats_body_text(xml: bytes) -> str:
    """Plain text of the ``<body>`` section titles and paragraphs of a JATS document."""
    root = ET.fromstring(xml)
    body = next((el for el in root.iter() if _local(el.tag) == "body"), None)
    if body is None:
        return ""
    blocks: list[str] = []

    def walk(element: ET.Element) -> None:
        for child in element:
            name = _local(child.tag)
            if name in _SKIPPED_TAGS:
                continue
            if name in _TEXT_TAGS:
                text = re.sub(r"\s+", " ", "".join(child.itertext())).strip()
                if text:
                    blocks.append(text)
            else:
                walk(child)

    walk(body)
    return "\n\n".join(blocks)


async def _from_europepmc(ctx: _Context) -> _Fetched:
    pmcid = await _resolve_pmcid(ctx)
    if not pmcid:
        raise _no_pmcid(ctx)
    body = await _fetch(ctx, EUROPEPMC_URL.format(pmcid=pmcid), accept_404=True)
    if body is None:
        raise SourceError("no full text in Europe PMC", "not_available")
    try:
        text = jats_body_text(body)
    except ET.ParseError as exc:
        raise SourceError("invalid Europe PMC response") from exc
    if len(text) < MIN_FULLTEXT_CHARS:
        raise SourceError("Europe PMC text too short", "not_available")
    return _Fetched(text=text)


_SOURCES: list[tuple[FullTextSource, Callable[[_Context], Awaitable[_Fetched]]]] = [
    (FullTextSource.unpaywall, _from_unpaywall),
    (FullTextSource.pmc, _from_pmc),
    (FullTextSource.europepmc, _from_europepmc),
]


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def _store_pdf(content: bytes) -> str:
    """Write ``content`` to ``<pdf_storage_path>/<uuid>.pdf`` and return the path."""
    directory = get_settings().pdf_storage_path
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{uuid.uuid4()}.pdf")
    with open(path, "wb") as handle:
        handle.write(content)
    return path


def _summarise(attempts: list[SourceAttempt]) -> str:
    detail = "; ".join(f"{a.source}: {a.detail or a.status}" for a in attempts)
    return f"Full text not retrieved ({detail})"[:MAX_ERROR_CHARS]


def record_failure(session: Session, article: Article, error: str) -> None:
    """Persist a retrieval failure; the article keeps its pipeline status."""
    article.full_text_retrieval_error = error[:MAX_ERROR_CHARS]
    article.full_text_attempted_at = datetime.now(timezone.utc)
    session.add(article)
    session.commit()


async def retrieve_full_text(
    session: Session,
    article: Article,
    client: Optional[httpx.AsyncClient] = None,
) -> FullTextRetrievalResult:
    """Try each open-access source for ``article`` and store the first full text.

    On success the article is updated through
    :meth:`ArticleService.set_full_text_retrieved`. On failure the error and the
    attempt time are recorded and the article status is left untouched, so it
    stays in ``awaiting_full_text``. Individual source failures never raise.

    Args:
        session: Database session owning ``article``.
        article: Article to retrieve.
        client: HTTP client to use (a new one is created and closed otherwise).
    """
    settings = get_settings()
    owns_client = client is None
    http = client or build_client()
    ctx = _Context(
        article=article,
        client=http,
        max_bytes=settings.max_upload_mb * 1024 * 1024,
        email=settings.unpaywall_email or settings.pubmed_email,
        unpaywall_email=settings.unpaywall_email,
    )
    attempts: list[SourceAttempt] = []
    fetched: Optional[_Fetched] = None
    used: Optional[FullTextSource] = None
    try:
        for source, fetch in _SOURCES:
            try:
                fetched = await fetch(ctx)
            except SourceError as exc:
                attempts.append(
                    SourceAttempt(
                        source=source.value, status=exc.status, detail=exc.detail
                    )
                )
                continue
            except Exception:
                logger.exception("Unexpected error in %s retrieval", source.value)
                attempts.append(
                    SourceAttempt(
                        source=source.value, status="error", detail="unexpected error"
                    )
                )
                continue
            attempts.append(SourceAttempt(source=source.value, status="success"))
            used = source
            break
    finally:
        if owns_client:
            await http.aclose()

    article.full_text_attempted_at = datetime.now(timezone.utc)
    if fetched is None or used is None:
        error = _summarise(attempts)
        record_failure(session, article, error)
        return FullTextRetrievalResult(
            article_id=article.id, retrieved=False, error=error, attempts=attempts
        )

    path: Optional[str] = None
    try:
        text = fetched.text
        if fetched.pdf is not None:
            path = _store_pdf(fetched.pdf)
            text = await asyncio.to_thread(extract_text_from_pdf_safe, path)
        ArticleService(session).set_full_text_retrieved(
            article, path, text, source=used.value
        )
    except Exception:
        logger.exception("Failed to store retrieved full text for %s", article.id)
        if path:
            remove_file(path)
        session.rollback()
        error = "Full text was found but could not be stored"
        record_failure(session, article, error)
        return FullTextRetrievalResult(
            article_id=article.id, retrieved=False, error=error, attempts=attempts
        )
    return FullTextRetrievalResult(
        article_id=article.id, retrieved=True, source=used.value, attempts=attempts
    )
