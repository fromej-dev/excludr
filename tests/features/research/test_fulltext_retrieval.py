"""Tests for the open-access full-text retrieval service (HTTP fully mocked)."""

import os

import httpx
import pytest

from app.core.config import get_settings
from app.features.research import fulltext_retrieval as ft
from app.features.research.models import Article, ArticleStatus
from .fulltext_helpers import PDF_BYTES, jats, pdf_response

pytestmark = pytest.mark.asyncio

UNPAYWALL = "api.unpaywall.org/v2/10.1/abc"
IDCONV = "www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
OA = "www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"
NO_PMCID = httpx.Response(200, json={"records": [{"status": "error"}]})
EPMC = "www.ebi.ac.uk/europepmc/webservices/rest/PMC123/fullTextXML"


def unpaywall_json(best=None, others=()):
    return httpx.Response(
        200,
        json={
            "best_oa_location": {"url_for_pdf": best} if best else None,
            "oa_locations": [{"url_for_pdf": u} for u in others],
        },
    )


def oa_xml(*links: tuple[str, str]):
    inner = "".join(f'<link format="{f}" href="{h}"/>' for f, h in links)
    return httpx.Response(
        200, text=f'<OA><records><record id="PMC123">{inner}</record></records></OA>'
    )


@pytest.fixture
def make_article(session, a_user, a_project):
    project = a_project(a_user())

    def _make(**kw):
        defaults = {"title": "T", "status": ArticleStatus.awaiting_full_text}
        article = Article(project_id=project.id, **{**defaults, **kw})
        session.add(article)
        session.commit()
        session.refresh(article)
        return article

    return _make


async def test_unpaywall_best_location_downloads_and_stores(session, make_article, web):
    article = make_article(doi="10.1/abc")
    web.add(UNPAYWALL, unpaywall_json(best="https://oa.example.org/p.pdf"))
    web.add("oa.example.org/p.pdf", pdf_response())

    result = await ft.retrieve_full_text(session, article)

    assert result.retrieved and result.source == "unpaywall"
    assert [a.status for a in result.attempts] == ["success"]
    session.refresh(article)
    assert article.status == ArticleStatus.full_text_retrieved
    assert article.full_text_retrieved is True
    assert article.full_text_source == "unpaywall"
    assert article.full_text_retrieval_error is None
    assert article.full_text_attempted_at is not None
    stored = article.full_text_path
    assert stored.endswith(".pdf")
    assert os.path.dirname(stored) == get_settings().pdf_storage_path
    assert open(stored, "rb").read() == PDF_BYTES
    # email query param + contact e-mail only; doi in the path
    assert web.requests[0].url.params["email"] == "me@example.org"


async def test_unpaywall_falls_back_to_other_locations(session, make_article, web):
    article = make_article(doi="10.1/abc")
    web.add(
        UNPAYWALL,
        unpaywall_json(
            best="https://bad.example.org/x.pdf",
            others=["https://ok.example.org/y.pdf"],
        ),
    )
    web.add("bad.example.org/x.pdf", httpx.Response(200, text="<html>paywall</html>"))
    web.add("ok.example.org/y.pdf", pdf_response())

    result = await ft.retrieve_full_text(session, article)

    assert result.retrieved
    assert web.hosts_called()[1:] == ["bad.example.org/x.pdf", "ok.example.org/y.pdf"]


async def test_doi_url_prefix_is_stripped(session, make_article, web):
    article = make_article(doi="https://doi.org/10.1/abc")
    web.add(UNPAYWALL, httpx.Response(404))
    await ft.retrieve_full_text(session, article)
    assert web.requests[0].url.path == "/v2/10.1/abc"


async def test_missing_unpaywall_email_is_reported_not_error(
    session, make_article, web, monkeypatch
):
    monkeypatch.setattr(get_settings(), "unpaywall_email", None)
    article = make_article(doi="10.1/abc")
    web.add(IDCONV, NO_PMCID)

    result = await ft.retrieve_full_text(session, article)

    assert not result.retrieved
    unpaywall = result.attempts[0]
    assert (unpaywall.source, unpaywall.status) == ("unpaywall", "not_configured")
    assert web.hosts_called() == [IDCONV]  # Unpaywall was never called
    session.refresh(article)
    assert "not configured" in article.full_text_retrieval_error
    assert article.status == ArticleStatus.awaiting_full_text


async def test_pmc_pdf_link_from_pmcid(session, make_article, web):
    article = make_article(pmcid="PMC123")
    web.add(
        OA,
        oa_xml(
            ("tgz", "ftp://ftp.ncbi.nlm.nih.gov/a.tgz"),
            ("pdf", "https://ftp.ncbi.nlm.nih.gov/pub/pmc/a.pdf"),
        ),
    )
    web.add("ftp.ncbi.nlm.nih.gov/pub/pmc/a.pdf", pdf_response())

    result = await ft.retrieve_full_text(session, article)

    assert result.retrieved and result.source == "pmc"
    assert [a.status for a in result.attempts] == ["not_available", "success"]
    assert article.full_text_source == "pmc"
    assert web.requests[0].url.params["id"] == "PMC123"


async def test_pmc_ftp_pdf_link_is_rewritten_to_https(session, make_article, web):
    article = make_article(pmcid="PMC123")
    web.add(OA, oa_xml(("pdf", "ftp://ftp.ncbi.nlm.nih.gov/pub/pmc/a.pdf")))
    web.add("ftp.ncbi.nlm.nih.gov/pub/pmc/a.pdf", pdf_response())

    result = await ft.retrieve_full_text(session, article)

    assert result.retrieved
    assert str(web.requests[1].url).startswith("https://ftp.ncbi.nlm.nih.gov/")


async def test_pmid_resolved_to_pmcid_via_idconverter(session, make_article, web):
    article = make_article(pmid="555")
    web.add(
        IDCONV,
        httpx.Response(200, json={"records": [{"pmid": "555", "pmcid": "PMC123"}]}),
    )
    web.add(OA, oa_xml(("pdf", "https://ftp.ncbi.nlm.nih.gov/p.pdf")))
    web.add("ftp.ncbi.nlm.nih.gov/p.pdf", pdf_response())

    result = await ft.retrieve_full_text(session, article)

    assert result.retrieved and result.source == "pmc"
    params = web.requests[0].url.params
    assert params["ids"] == "555" and params["tool"] == "excludr"
    assert params["email"] == "me@example.org"


async def test_tgz_only_falls_back_to_europepmc_text(session, make_article, web):
    article = make_article(pmcid="PMC123")
    web.add(OA, oa_xml(("tgz", "ftp://ftp.ncbi.nlm.nih.gov/a.tgz")))
    paragraphs = ["Alpha " * 40, "Beta " * 40]
    web.add(EPMC, httpx.Response(200, content=jats(paragraphs)))

    result = await ft.retrieve_full_text(session, article)

    assert result.retrieved and result.source == "europepmc"
    session.refresh(article)
    assert article.full_text_source == "europepmc"
    assert article.full_text_path is None
    assert article.full_text_retrieved is True
    assert article.status == ArticleStatus.full_text_retrieved
    assert "Section 0" in article.full_text_content
    assert "Alpha" in article.full_text_content and "Beta" in article.full_text_content
    assert "FIGURE CAPTION" not in article.full_text_content
    assert not os.path.exists(get_settings().pdf_storage_path)  # no PDF stored


async def test_all_sources_fail_records_error_and_keeps_status(
    session, make_article, web
):
    article = make_article(doi="10.1/abc", pmcid="PMC123")
    web.add(UNPAYWALL, httpx.Response(404))
    web.add(OA, httpx.Response(200, text='<OA><error code="idIsNotOpenAccess"/></OA>'))
    web.add(EPMC, httpx.Response(404))

    result = await ft.retrieve_full_text(session, article)

    assert not result.retrieved
    assert [(a.source, a.status) for a in result.attempts] == [
        ("unpaywall", "not_available"),
        ("pmc", "not_available"),
        ("europepmc", "not_available"),
    ]
    session.refresh(article)
    assert article.status == ArticleStatus.awaiting_full_text
    assert article.full_text_retrieved is False
    assert article.full_text_retrieval_error == result.error
    assert article.full_text_attempted_at is not None


async def test_success_clears_previous_error(session, make_article, web):
    article = make_article(doi="10.1/abc", full_text_retrieval_error="old failure")
    web.add(UNPAYWALL, unpaywall_json(best="https://oa.example.org/p.pdf"))
    web.add("oa.example.org/p.pdf", pdf_response())

    await ft.retrieve_full_text(session, article)

    session.refresh(article)
    assert article.full_text_retrieval_error is None


async def test_retries_429_and_5xx_with_backoff_then_succeeds(
    session, make_article, web
):
    article = make_article(doi="10.1/abc")
    web.add(
        UNPAYWALL,
        [
            httpx.Response(429),
            httpx.Response(503),
            unpaywall_json(best="https://oa.example.org/p.pdf"),
        ],
    )
    web.add("oa.example.org/p.pdf", pdf_response())

    result = await ft.retrieve_full_text(session, article)

    assert result.retrieved
    assert web.hosts_called().count(UNPAYWALL) == 3


async def test_gives_up_after_three_attempts(session, make_article, web):
    article = make_article(doi="10.1/abc")
    web.add(UNPAYWALL, httpx.Response(500))

    result = await ft.retrieve_full_text(session, article)

    assert not result.retrieved
    assert web.hosts_called().count(UNPAYWALL) == 3
    assert result.attempts[0].status == "error"
    assert "HTTP 500" in result.attempts[0].detail


async def test_transport_error_is_reported_not_raised(session, make_article, web):
    article = make_article(doi="10.1/abc")

    def boom(request):
        raise httpx.ConnectTimeout("slow", request=request)

    web.add(UNPAYWALL, boom)

    result = await ft.retrieve_full_text(session, article)

    assert not result.retrieved
    assert "network error" in result.attempts[0].detail
    assert web.hosts_called().count(UNPAYWALL) == 3


async def test_non_retryable_4xx_is_not_retried(session, make_article, web):
    article = make_article(doi="10.1/abc")
    web.add(UNPAYWALL, httpx.Response(403))
    await ft.retrieve_full_text(session, article)
    assert web.hosts_called().count(UNPAYWALL) == 1


async def test_oversized_download_rejected_and_not_stored(
    session, make_article, web, monkeypatch
):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    article = make_article(doi="10.1/abc")
    web.add(UNPAYWALL, unpaywall_json(best="https://oa.example.org/big.pdf"))
    big = b"%PDF-" + b"0" * (1024 * 1024 + 10)
    web.add("oa.example.org/big.pdf", httpx.Response(200, content=big))

    result = await ft.retrieve_full_text(session, article)

    assert not result.retrieved
    assert not os.path.exists(get_settings().pdf_storage_path)


async def test_declared_content_length_over_limit_rejected(
    session, make_article, web, monkeypatch
):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    article = make_article(doi="10.1/abc")
    web.add(UNPAYWALL, unpaywall_json(best="https://oa.example.org/big.pdf"))
    web.add(
        "oa.example.org/big.pdf",
        httpx.Response(200, content=PDF_BYTES, headers={"content-length": str(10**9)}),
    )
    # httpx MockTransport recomputes nothing: header stays as declared
    result = await ft.retrieve_full_text(session, article)
    assert not result.retrieved


async def test_redirects_are_followed(session, make_article, web):
    article = make_article(doi="10.1/abc")
    web.add(UNPAYWALL, unpaywall_json(best="https://oa.example.org/start.pdf"))
    web.add(
        "oa.example.org/start.pdf",
        httpx.Response(302, headers={"location": "https://cdn.example.org/real.pdf"}),
    )
    web.add("cdn.example.org/real.pdf", pdf_response())

    assert (await ft.retrieve_full_text(session, article)).retrieved


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.org/x.pdf",
        "http://localhost/x.pdf",
        "http://127.0.0.1/x.pdf",
        "http://10.0.0.5/x.pdf",
        "http://169.254.169.254/latest",
    ],
)
async def test_unsafe_candidate_urls_are_never_requested(
    session, make_article, web, url
):
    article = make_article(doi="10.1/abc")
    web.add(UNPAYWALL, unpaywall_json(best=url)).add(IDCONV, NO_PMCID)

    result = await ft.retrieve_full_text(session, article)

    assert not result.retrieved
    assert web.hosts_called() == [UNPAYWALL, IDCONV]


async def test_article_without_identifiers_reports_why(session, make_article, web):
    article = make_article()
    result = await ft.retrieve_full_text(session, article)
    assert not result.retrieved
    assert {a.status for a in result.attempts} <= {"not_available", "not_configured"}
    assert web.requests == []


async def test_pdf_text_is_extracted(session, make_article, web):
    import fitz

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Hello retrieved world")
    pdf = doc.tobytes()
    article = make_article(doi="10.1/abc")
    web.add(UNPAYWALL, unpaywall_json(best="https://oa.example.org/p.pdf"))
    web.add("oa.example.org/p.pdf", httpx.Response(200, content=pdf))

    await ft.retrieve_full_text(session, article)

    session.refresh(article)
    assert "Hello retrieved world" in article.full_text_content


async def test_user_agent_contains_contact_email(monkeypatch):
    client = ft.build_client()
    try:
        assert "me@example.org" in client.headers["User-Agent"]
        assert client.follow_redirects is True
    finally:
        await client.aclose()


async def test_rate_limiter_spaces_requests_per_host(monkeypatch):
    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(ft.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(ft, "HOST_INTERVALS", {"a.example": 10.0})
    limiter = ft.HostRateLimiter()
    await limiter.wait("a.example")
    await limiter.wait("a.example")
    await limiter.wait("b.example")
    assert len(sleeps) == 1 and 9.0 < sleeps[0] <= 10.0


def test_jats_body_text_skips_figures_and_handles_namespaces():
    xml = b'<a:article xmlns:a="urn:x"><a:body><a:p>One <a:i>two</a:i></a:p></a:body></a:article>'
    assert ft.jats_body_text(xml) == "One two"
    assert ft.jats_body_text(b"<article><front/></article>") == ""


def test_error_summary_names_each_source():
    attempts = [ft.SourceAttempt(source="unpaywall", status="error", detail="HTTP 500")]
    assert "unpaywall: HTTP 500" in ft._summarise(attempts)
