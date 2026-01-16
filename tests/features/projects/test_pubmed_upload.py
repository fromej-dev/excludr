"""Tests for PubMed file upload and parsing."""

from app.features.projects.parsers import parse_pubmed_txt, parse_pubmed_csv


BASE_API = "api/v1/projects"


class TestPubMedTxtParser:
    """Unit tests for the MEDLINE format parser."""

    def test_parse_pubmed_txt_basic(self):
        """Test parsing a basic MEDLINE file."""
        articles = parse_pubmed_txt("./tests/docs/test_pubmed.txt")

        assert len(articles) == 2

        # First article
        article1 = articles[0]
        assert article1["pmid"] == "12345678"
        assert (
            article1["title"]
            == "A test article for unit testing PubMed MEDLINE format parsing."
        )
        assert "test abstract that spans multiple lines" in article1["abstract"]
        assert article1["authors"] == ["Smith, John", "Doe, Jane"]
        assert article1["journal"] == "Test Journal of Medicine"
        assert article1["year"] == 2023
        assert article1["volume"] == "10"
        assert article1["issue"] == "5"
        assert article1["pages"] == "100-110"
        assert article1["doi"] == "10.1234/test.2023.001"
        assert article1["pmcid"] == "PMC9999999"
        assert "Humans" in article1["mesh_terms"]
        assert "Testing" in article1["mesh_terms"]
        assert "unit test" in article1["keywords"]

        # Second article - has fewer fields
        article2 = articles[1]
        assert article2["pmid"] == "87654321"
        assert article2["title"] == "Another test article without some optional fields."
        assert article2["abstract"] == "A shorter abstract for the second test article."
        assert article2["authors"] == ["Johnson, Robert"]
        assert article2["doi"] == "10.5678/another.test"
        assert article2.get("issue") is None

    def test_parse_pubmed_txt_multiline_abstract(self):
        """Test that multi-line abstracts are correctly joined."""
        articles = parse_pubmed_txt("./tests/docs/test_pubmed.txt")
        abstract = articles[0]["abstract"]

        # Should be joined with spaces, not newlines
        assert "\n" not in abstract
        assert "multiple lines" in abstract
        assert "information about the study" in abstract

    def test_parse_pubmed_txt_extracts_doi_correctly(self):
        """Test that DOI is correctly extracted from AID fields."""
        articles = parse_pubmed_txt("./tests/docs/test_pubmed.txt")

        # DOI should not include the [doi] suffix
        assert articles[0]["doi"] == "10.1234/test.2023.001"
        assert "[doi]" not in articles[0]["doi"]


class TestPubMedCsvParser:
    """Unit tests for the PubMed CSV parser."""

    def test_parse_pubmed_csv_basic(self):
        """Test parsing a basic PubMed CSV file."""
        articles = parse_pubmed_csv("./tests/docs/test_pubmed.csv")

        assert len(articles) == 2

        # First article
        article1 = articles[0]
        assert article1["pmid"] == "11111111"
        assert article1["title"] == "Test CSV Article One"
        assert article1["journal"] == "Test Journal"
        assert article1["year"] == 2023
        assert article1["doi"] == "10.1111/test.one"
        assert article1["pmcid"] == "PMC1111111"
        assert article1["abstract"] is None
        assert article1["needs_abstract_fetch"] is True

        # Second article
        article2 = articles[1]
        assert article2["pmid"] == "22222222"
        assert article2["title"] == "Test CSV Article Two"
        assert article2["year"] == 2022
        assert article2["pmcid"] is None  # Empty in CSV

    def test_parse_pubmed_csv_marks_abstract_needed(self):
        """Test that CSV parser marks articles as needing abstract fetch."""
        articles = parse_pubmed_csv("./tests/docs/test_pubmed.csv")

        for article in articles:
            assert article["abstract"] is None
            assert article["needs_abstract_fetch"] is True


class TestPubMedUploadEndpoint:
    """Integration tests for PubMed upload endpoint."""

    def test_upload_pubmed_txt_file(self, auth_as, a_project, session, monkeypatch):
        """Test uploading a MEDLINE format file."""

        # Mock the Prefect session
        class MockContextManager:
            def __init__(self, test_session):
                self.test_session = test_session

            def __enter__(self):
                return self.test_session

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

        monkeypatch.setattr(
            "app.features.projects.flows.get_prefect_session",
            lambda: MockContextManager(session),
        )

        client, user = auth_as()
        project = a_project(user)

        with open("./tests/docs/test_pubmed.txt", "rb") as f:
            file_bytes = f.read()

        res = client.post(
            f"{BASE_API}/{project.id}/upload/pubmed",
            files={"file": ("test_pubmed.txt", file_bytes)},
        )

        assert res.status_code == 200
        result = res.json()
        assert result["message"] == "File processing complete."
        assert result["result"]["status"] == "Success"
        assert result["result"]["articles_created"] == 2

    def test_upload_pubmed_csv_file(self, auth_as, a_project, session, monkeypatch):
        """Test uploading a PubMed CSV file."""

        # Mock the Prefect session
        class MockContextManager:
            def __init__(self, test_session):
                self.test_session = test_session

            def __enter__(self):
                return self.test_session

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

        monkeypatch.setattr(
            "app.features.projects.flows.get_prefect_session",
            lambda: MockContextManager(session),
        )

        # Mock the PubMed service to avoid real API calls
        def mock_fetch_abstracts_sync(self, pmids):
            return {pmid: f"Mock abstract for {pmid}" for pmid in pmids}

        monkeypatch.setattr(
            "app.features.research.pubmed_service.PubMedService.fetch_abstracts_sync",
            mock_fetch_abstracts_sync,
        )

        client, user = auth_as()
        project = a_project(user)

        with open("./tests/docs/test_pubmed.csv", "rb") as f:
            file_bytes = f.read()

        res = client.post(
            f"{BASE_API}/{project.id}/upload/pubmed",
            files={"file": ("test_pubmed.csv", file_bytes)},
        )

        assert res.status_code == 200
        result = res.json()
        assert result["message"] == "File processing complete."
        assert result["result"]["status"] == "Success"
        assert result["result"]["articles_created"] == 2
        assert result["result"]["abstracts_fetched"] == 2

    def test_upload_pubmed_unauthorized(self, client, a_project, a_user):
        """Test that unauthenticated users cannot upload files."""
        user = a_user()
        project = a_project(user)

        with open("./tests/docs/test_pubmed.txt", "rb") as f:
            file_bytes = f.read()

        res = client.post(
            f"{BASE_API}/{project.id}/upload/pubmed",
            files={"file": ("test_pubmed.txt", file_bytes)},
        )
        assert res.status_code == 401

    def test_upload_pubmed_wrong_owner(self, auth_as, a_project, a_user):
        """Test that users cannot upload to projects they don't own."""
        client, user = auth_as()
        other_user = a_user()
        project = a_project(other_user)

        with open("./tests/docs/test_pubmed.txt", "rb") as f:
            file_bytes = f.read()

        res = client.post(
            f"{BASE_API}/{project.id}/upload/pubmed",
            files={"file": ("test_pubmed.txt", file_bytes)},
        )
        assert res.status_code == 403

    def test_upload_invalid_file_type(self, auth_as, a_project):
        """Test that only .txt and .csv files can be uploaded."""
        client, user = auth_as()
        project = a_project(user)

        res = client.post(
            f"{BASE_API}/{project.id}/upload/pubmed",
            files={"file": ("test.ris", b"invalid content")},
        )

        assert res.status_code == 400
        assert "Invalid file type" in res.json()["detail"]

    def test_upload_pubmed_deduplication(
        self, auth_as, a_project, session, monkeypatch
    ):
        """Test that duplicate articles by PMID are updated, not duplicated."""

        # Mock the Prefect session
        class MockContextManager:
            def __init__(self, test_session):
                self.test_session = test_session

            def __enter__(self):
                return self.test_session

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

        monkeypatch.setattr(
            "app.features.projects.flows.get_prefect_session",
            lambda: MockContextManager(session),
        )

        client, user = auth_as()
        project = a_project(user)

        with open("./tests/docs/test_pubmed.txt", "rb") as f:
            file_bytes = f.read()

        # First upload
        res1 = client.post(
            f"{BASE_API}/{project.id}/upload/pubmed",
            files={"file": ("test_pubmed.txt", file_bytes)},
        )
        assert res1.status_code == 200
        assert res1.json()["result"]["articles_created"] == 2
        assert res1.json()["result"]["articles_updated"] == 0

        # Second upload of same file - should update, not create
        res2 = client.post(
            f"{BASE_API}/{project.id}/upload/pubmed",
            files={"file": ("test_pubmed.txt", file_bytes)},
        )
        assert res2.status_code == 200
        assert res2.json()["result"]["articles_created"] == 0
        assert res2.json()["result"]["articles_updated"] == 2
