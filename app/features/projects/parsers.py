"""Parsers for PubMed export file formats."""

import csv
import re
from io import StringIO
from typing import Any


def parse_pubmed_txt(file_path: str) -> list[dict[str, Any]]:
    """Parse a PubMed MEDLINE format (.txt) file.

    The MEDLINE format uses tagged fields (e.g., PMID-, TI  -, AB  -) with
    multi-line values continuing with leading whitespace.

    Args:
        file_path: Path to the MEDLINE format file.

    Returns:
        List of article dictionaries with mapped fields.
    """
    articles = []
    current_record: dict[str, Any] = {}
    current_tag = None
    current_value: list[str] = []

    # Tag pattern: 2-4 uppercase letters, optional whitespace, dash, space
    tag_pattern = re.compile(r"^([A-Z]{2,4})\s*-\s*(.*)$")

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n\r")

            # Check if this is a new tag line
            match = tag_pattern.match(line)
            if match:
                # Save the previous tag's value if any
                if current_tag and current_value:
                    _add_medline_field(current_record, current_tag, current_value)

                current_tag = match.group(1)
                value = match.group(2)
                current_value = [value] if value else []

            elif line.startswith("      ") or line.startswith("\t"):
                # Continuation line - append to current value
                if current_tag:
                    current_value.append(line.strip())

            elif line.strip() == "":
                # Blank line - end of record
                if current_tag and current_value:
                    _add_medline_field(current_record, current_tag, current_value)

                if current_record and current_record.get("PMID"):
                    articles.append(_map_medline_to_article(current_record))

                current_record = {}
                current_tag = None
                current_value = []

        # Handle the last record
        if current_tag and current_value:
            _add_medline_field(current_record, current_tag, current_value)
        if current_record and current_record.get("PMID"):
            articles.append(_map_medline_to_article(current_record))

    return articles


def _add_medline_field(record: dict[str, Any], tag: str, values: list[str]) -> None:
    """Add a MEDLINE field to the record, handling multi-value fields.

    Args:
        record: The current record dictionary.
        tag: The MEDLINE tag (e.g., "PMID", "TI", "AU").
        values: List of value strings for this tag.
    """
    # Join multi-line values with space
    full_value = " ".join(values)

    # Multi-value tags that should be collected as lists
    list_tags = {"AU", "FAU", "MH", "OT", "PT", "AID", "IS"}

    if tag in list_tags:
        if tag not in record:
            record[tag] = []
        record[tag].append(full_value)
    else:
        # Single value tags - first occurrence wins
        if tag not in record:
            record[tag] = full_value


def _map_medline_to_article(record: dict[str, Any]) -> dict[str, Any]:
    """Map MEDLINE fields to Article model fields.

    Args:
        record: Dictionary of MEDLINE tag values.

    Returns:
        Dictionary with Article model field names.
    """
    article: dict[str, Any] = {}

    # PMID
    article["pmid"] = record.get("PMID")

    # Title
    article["title"] = record.get("TI")

    # Abstract
    article["abstract"] = record.get("AB")

    # Authors - prefer full author names (FAU) over abbreviated (AU)
    if "FAU" in record:
        article["authors"] = record["FAU"]
    elif "AU" in record:
        article["authors"] = record["AU"]
    else:
        article["authors"] = []

    # Journal
    article["journal"] = record.get("JT") or record.get("TA")

    # Publication date
    article["publication_date"] = record.get("DP")

    # Extract year from publication date
    dp = record.get("DP", "")
    year_match = re.match(r"(\d{4})", dp)
    if year_match:
        article["year"] = int(year_match.group(1))

    # Volume, Issue, Pages
    article["volume"] = record.get("VI")
    article["issue"] = record.get("IP")
    article["pages"] = record.get("PG")

    # DOI - extract from AID fields
    doi = None
    for aid in record.get("AID", []):
        if "[doi]" in aid:
            doi = aid.replace("[doi]", "").strip()
            break
    article["doi"] = doi

    # ISSN - take first one
    issn_list = record.get("IS", [])
    if issn_list and isinstance(issn_list, list):
        # Take the first non-linking ISSN
        for issn in issn_list:
            if "Linking" not in issn:
                # Extract just the ISSN number
                issn_match = re.match(r"([\d-]+)", issn)
                if issn_match:
                    article["issn"] = issn_match.group(1)
                    break
        if not article.get("issn") and issn_list:
            issn_match = re.match(r"([\d-]+)", issn_list[0])
            if issn_match:
                article["issn"] = issn_match.group(1)
    elif isinstance(issn_list, str):
        issn_match = re.match(r"([\d-]+)", issn_list)
        if issn_match:
            article["issn"] = issn_match.group(1)

    # MeSH terms
    article["mesh_terms"] = record.get("MH", [])

    # Keywords (Other Terms)
    article["keywords"] = record.get("OT", [])

    # PMC ID
    article["pmcid"] = record.get("PMC")

    # Publication type - join multiple types
    pt_list = record.get("PT", [])
    if pt_list:
        article["publication_type"] = "; ".join(pt_list)

    return article


def parse_pubmed_csv(file_path: str) -> list[dict[str, Any]]:
    """Parse a PubMed CSV export file.

    PubMed CSV exports have columns: PMID, Title, Authors, Citation,
    First Author, Journal/Book, Publication Year, Create Date, PMCID, NIHMS ID, DOI

    Note: CSV exports do not include abstracts - these need to be fetched via
    PubMed E-utilities API.

    Args:
        file_path: Path to the CSV file.

    Returns:
        List of article dictionaries with mapped fields.
    """
    articles = []

    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            article = _map_csv_to_article(row)
            if article.get("pmid"):
                articles.append(article)

    return articles


def _map_csv_to_article(row: dict[str, str]) -> dict[str, Any]:
    """Map CSV row to Article model fields.

    Args:
        row: Dictionary of CSV column values.

    Returns:
        Dictionary with Article model field names.
    """
    article: dict[str, Any] = {}

    # PMID
    article["pmid"] = row.get("PMID", "").strip() or None

    # Title
    article["title"] = row.get("Title", "").strip() or None

    # Authors - parse comma-separated list
    authors_str = row.get("Authors", "").strip()
    if authors_str:
        # Authors are typically "LastName Initials, LastName Initials."
        # Split by period followed by comma or end of string
        authors = [a.strip().rstrip(".") for a in authors_str.split(",")]
        # Filter out empty strings
        article["authors"] = [a for a in authors if a]
    else:
        article["authors"] = []

    # Journal
    article["journal"] = row.get("Journal/Book", "").strip() or None

    # Publication Year
    year_str = row.get("Publication Year", "").strip()
    if year_str:
        try:
            article["year"] = int(year_str)
        except ValueError:
            pass

    # DOI
    doi = row.get("DOI", "").strip()
    article["doi"] = doi if doi else None

    # PMCID
    pmcid = row.get("PMCID", "").strip()
    article["pmcid"] = pmcid if pmcid else None

    # Note: CSV doesn't have abstracts - mark as needing fetch
    article["abstract"] = None
    article["needs_abstract_fetch"] = True

    return article


def parse_pubmed_csv_content(content: str) -> list[dict[str, Any]]:
    """Parse PubMed CSV content from a string.

    Args:
        content: CSV content as a string.

    Returns:
        List of article dictionaries with mapped fields.
    """
    articles = []
    reader = csv.DictReader(StringIO(content))
    for row in reader:
        article = _map_csv_to_article(row)
        if article.get("pmid"):
            articles.append(article)
    return articles
