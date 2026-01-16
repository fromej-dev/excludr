"""PubMed E-utilities service for fetching article abstracts."""

import asyncio
import time
import xml.etree.ElementTree as ET
from typing import Optional

import httpx

from app.core.config import get_settings


class PubMedService:
    """Service for interacting with PubMed E-utilities API."""

    EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    MAX_PMIDS_PER_REQUEST = 200  # NCBI guideline
    RATE_LIMIT_WITH_KEY = 10  # requests per second with API key
    RATE_LIMIT_WITHOUT_KEY = 3  # requests per second without API key

    def __init__(
        self,
        email: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        """Initialize the PubMed service.

        Args:
            email: Email address for NCBI (required by their guidelines).
            api_key: Optional NCBI API key for higher rate limits.
        """
        settings = get_settings()
        self.email = email or settings.pubmed_email
        self.api_key = api_key or settings.pubmed_api_key
        self._last_request_time = 0.0

    @property
    def _rate_limit(self) -> float:
        """Return the rate limit delay in seconds."""
        if self.api_key:
            return 1.0 / self.RATE_LIMIT_WITH_KEY
        return 1.0 / self.RATE_LIMIT_WITHOUT_KEY

    async def _rate_limit_wait(self) -> None:
        """Wait to respect rate limits."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._rate_limit:
            await asyncio.sleep(self._rate_limit - elapsed)
        self._last_request_time = time.time()

    def _build_params(self, pmids: list[str]) -> dict:
        """Build request parameters for efetch."""
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "xml",
            "retmode": "xml",
        }
        if self.email:
            params["email"] = self.email
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    def _parse_abstracts_from_xml(self, xml_content: str) -> dict[str, str]:
        """Parse abstracts from PubMed XML response.

        Args:
            xml_content: XML response from efetch.

        Returns:
            Dictionary mapping PMIDs to abstracts.
        """
        abstracts = {}
        try:
            root = ET.fromstring(xml_content)

            for article in root.findall(".//PubmedArticle"):
                # Get PMID
                pmid_elem = article.find(".//PMID")
                if pmid_elem is None or pmid_elem.text is None:
                    continue
                pmid = pmid_elem.text

                # Get abstract - can be in multiple parts (AbstractText elements)
                abstract_parts = []
                for abstract_text in article.findall(".//AbstractText"):
                    # Some abstracts have labeled sections (NlmCategory attribute)
                    label = abstract_text.get("Label")

                    # Get all text including from child elements
                    full_text = "".join(abstract_text.itertext())

                    if label:
                        abstract_parts.append(f"{label}: {full_text}")
                    else:
                        abstract_parts.append(full_text)

                if abstract_parts:
                    abstracts[pmid] = " ".join(abstract_parts)

        except ET.ParseError as e:
            print(f"Error parsing PubMed XML: {e}")

        return abstracts

    async def fetch_abstracts(self, pmids: list[str]) -> dict[str, str]:
        """Fetch abstracts for a list of PMIDs.

        Args:
            pmids: List of PubMed IDs.

        Returns:
            Dictionary mapping PMIDs to abstracts.
        """
        if not pmids:
            return {}

        all_abstracts: dict[str, str] = {}

        # Split into batches
        batches = [
            pmids[i : i + self.MAX_PMIDS_PER_REQUEST]
            for i in range(0, len(pmids), self.MAX_PMIDS_PER_REQUEST)
        ]

        async with httpx.AsyncClient(timeout=30.0) as client:
            for batch in batches:
                await self._rate_limit_wait()

                params = self._build_params(batch)
                try:
                    response = await client.get(self.EFETCH_URL, params=params)
                    response.raise_for_status()

                    abstracts = self._parse_abstracts_from_xml(response.text)
                    all_abstracts.update(abstracts)

                except httpx.HTTPError as e:
                    print(f"Error fetching abstracts from PubMed: {e}")
                    continue

        return all_abstracts

    def fetch_abstracts_sync(self, pmids: list[str]) -> dict[str, str]:
        """Synchronous version of fetch_abstracts for use in Prefect tasks.

        Args:
            pmids: List of PubMed IDs.

        Returns:
            Dictionary mapping PMIDs to abstracts.
        """
        if not pmids:
            return {}

        all_abstracts: dict[str, str] = {}

        # Split into batches
        batches = [
            pmids[i : i + self.MAX_PMIDS_PER_REQUEST]
            for i in range(0, len(pmids), self.MAX_PMIDS_PER_REQUEST)
        ]

        with httpx.Client(timeout=30.0) as client:
            for batch in batches:
                # Simple rate limiting for sync version
                elapsed = time.time() - self._last_request_time
                if elapsed < self._rate_limit:
                    time.sleep(self._rate_limit - elapsed)
                self._last_request_time = time.time()

                params = self._build_params(batch)
                try:
                    response = client.get(self.EFETCH_URL, params=params)
                    response.raise_for_status()

                    abstracts = self._parse_abstracts_from_xml(response.text)
                    all_abstracts.update(abstracts)

                except httpx.HTTPError as e:
                    print(f"Error fetching abstracts from PubMed: {e}")
                    continue

        return all_abstracts
