import pytest

from app.core.config import get_settings
from app.features.research import flows, fulltext_retrieval
from .fulltext_helpers import FakeWeb


@pytest.fixture(autouse=True)
def fast_retrieval(monkeypatch, tmp_path):
    """No sleeping, a temp PDF dir and a configured Unpaywall e-mail."""
    settings = get_settings()
    monkeypatch.setattr(settings, "pdf_storage_path", str(tmp_path / "pdfs"))
    monkeypatch.setattr(settings, "unpaywall_email", "me@example.org")
    monkeypatch.setattr(fulltext_retrieval, "RETRY_BACKOFF_SECONDS", 0.0)
    monkeypatch.setattr(fulltext_retrieval, "HOST_INTERVALS", {})
    monkeypatch.setattr(fulltext_retrieval, "DEFAULT_HOST_INTERVAL", 0.0)


@pytest.fixture
def web(monkeypatch) -> FakeWeb:
    """A fake internet; every retrieval client talks only to it."""
    fake = FakeWeb()
    monkeypatch.setattr(fulltext_retrieval, "build_client", fake.client)
    monkeypatch.setattr(flows, "build_client", fake.client)
    return fake
