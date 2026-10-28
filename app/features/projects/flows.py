"""Prefect flows for project-related background tasks."""

import logging
import os
from typing import Any

import rispy
from prefect import flow, task
from sqlmodel import select

from app.core.prefect_config import get_prefect_session
from app.features.projects.dedup import ProjectArticleIndex, normalize_title
from app.features.projects.models import ImportBatch
from app.features.research.models import Article, ArticleStatus, ScreeningStage
from app.features.projects.parsers import (
    parse_pubmed_csv,
    parse_pubmed_txt,
    ris_pmcid,
    ris_pmid,
)
from app.features.research.pubmed_service import PubMedRecord, PubMedService

logger = logging.getLogger(__name__)


def new_screening_article(article_data: dict[str, Any]) -> Article:
    """Build a newly imported article that is ready for title/abstract screening.

    Imported articles go straight into the screening queue, in the same session
    (and transaction) that creates them. Existing articles matched by dedup are
    updated elsewhere and keep their status.
    """
    return Article(
        **article_data,
        status=ArticleStatus.screening,
        current_stage=ScreeningStage.title_abstract,
    )


def record_import_batch(
    project_id: int,
    filename: str,
    file_format: str,
    result: dict[str, Any],
    user_id: int | None,
) -> None:
    """Persist an :class:`ImportBatch` (and its audit event) for a finished import."""
    from app.features.audit import services as audit

    with get_prefect_session() as session:
        batch = ImportBatch(
            project_id=project_id,
            filename=filename[:500],
            format=file_format,
            records_found=result["records_found"],
            imported=result["articles_created"],
            duplicates=result["duplicates"],
            created_by=user_id,
        )
        session.add(batch)
        session.flush()
        audit.record_event(
            session,
            project_id,
            audit.IMPORT_COMPLETED,
            "import_batch",
            batch.id,
            user_id,
            {
                "filename": batch.filename,
                "format": file_format,
                "records_found": batch.records_found,
                "imported": batch.imported,
                "duplicates": batch.duplicates,
            },
        )


@task(name="parse_ris_entries")
def parse_ris_entries(file_path: str, project_id: int, original_filename: str) -> dict:
    """Parse RIS entries and save to database.

    This task handles the actual parsing and database operations.
    """
    articles_created = 0
    articles_updated = 0
    duplicates = 0
    duplicates_by_title_year = 0
    pmids_needing_abstracts: list[str] = []

    with open(file_path, "r", encoding="utf-8") as file:
        entries = rispy.load(file)
        records_found = len(entries)

        with get_prefect_session() as session:
            index = ProjectArticleIndex(session, project_id)
            for entry in entries:
                doi = entry.get("doi")
                title = entry.get("title") or entry.get("primary_title")

                # A title is essential for a meaningful record.
                if not title:
                    logger.info(
                        f"Skipping entry due to missing title: {entry.get('id', 'N/A')}"
                    )
                    continue

                # --- Map all available RIS tags to the Article model fields ---

                # Gracefully parse year, handling formats like '2023/05/10'
                year = None
                try:
                    year_str = entry.get("year") or entry.get("publication_year")
                    if year_str:
                        # Take the first part of a date string and convert to int
                        year = int(float(str(year_str).split("/")[0]))
                except (ValueError, TypeError):
                    logger.info(f"Could not parse year for article '{title}'")

                # Look for a duplicate within this project only: DOI/PMID first,
                # then normalized title + year when the entry has no identifiers.
                pmid = ris_pmid(entry.get("accession_number"))
                existing_article, match_kind = index.find(doi, pmid, title, year)
                if existing_article is not None:
                    duplicates += 1
                    if match_kind == "title_year":
                        duplicates_by_title_year += 1
                        continue

                # Construct a page range string if start and end pages are available.
                start_page = entry.get("start_page", "")
                end_page = entry.get("end_page", "")
                pages = ""
                if start_page and end_page:
                    pages = f"{start_page}-{end_page}"
                elif start_page:
                    pages = start_page

                # Consolidate all available URLs into a single list.
                urls = entry.get("urls", [])
                if entry.get("url") and entry.get("url") not in urls:
                    urls.append(entry.get("url"))

                # Prepare a dictionary with all the data to be saved.
                article_data = {
                    "project_id": project_id,
                    "title": title,
                    "authors": entry.get("authors", []),
                    # rispy reads AB as abstract and N2 as notes_abstract; EndNote,
                    # Scopus and Ovid exports put the abstract in N2.
                    "abstract": entry.get("abstract") or entry.get("notes_abstract"),
                    "publication_date": entry.get("date"),
                    "year": year,
                    "journal": entry.get("journal_name")
                    or entry.get("secondary_title"),
                    "volume": entry.get("volume"),
                    "issue": entry.get("issue"),
                    "pages": pages,
                    "publication_type": entry.get("type_of_reference"),
                    "doi": doi,
                    "pmid": pmid,
                    "pmcid": ris_pmcid(entry),
                    "issn": entry.get("issn"),
                    "keywords": entry.get("keywords", []),
                    "mesh_terms": entry.get("mesh_terms", []),
                    "article_url": entry.get("url"),  # The primary URL
                    "urls": urls,
                    "source_filename": original_filename,
                }

                if existing_article:
                    # Update the fields of the existing article.
                    for key, value in article_data.items():
                        # Only update if the new value is not None to avoid overwriting data.
                        if value is not None:
                            setattr(existing_article, key, value)
                    session.add(existing_article)
                    articles_updated += 1
                    article = existing_article
                else:
                    # Or, create a new article instance.
                    article = new_screening_article(article_data)
                    session.add(article)
                    index.add(article)
                    articles_created += 1

                if not article.abstract and pmid:
                    pmids_needing_abstracts.append(pmid)

    return {
        "records_found": records_found,
        "articles_created": articles_created,
        "articles_updated": articles_updated,
        "duplicates": duplicates,
        "duplicates_by_title_year": duplicates_by_title_year,
        "pmids_needing_abstracts": pmids_needing_abstracts,
    }


@flow(name="parse_ris_file", log_prints=True)
def parse_ris_file_flow(
    file_path: str,
    project_id: int,
    original_filename: str | None = None,
    user_id: int | None = None,
) -> dict:
    """Prefect flow to parse a RIS file and save/update entries in the database.

    Args:
        file_path: Path to the RIS file to parse.
        project_id: ID of the project to associate articles with.
        original_filename: Client-supplied display name (metadata only, never a path).
        user_id: User who uploaded the file (recorded on the import batch).

    Returns:
        Dictionary with status, articles_created, and articles_updated counts.
    """
    original_filename = original_filename or os.path.basename(file_path)

    logger.info(f"Starting to parse file: {file_path} (from {original_filename})")

    try:
        result = parse_ris_entries(file_path, project_id, original_filename)
        record_import_batch(project_id, original_filename, "ris", result, user_id)

        # Fill in missing abstracts from PubMed; the record must match the article,
        # because an accession number is not always a PMID.
        abstracts_fetched = 0
        if result["pmids_needing_abstracts"]:
            fetch_result = fetch_pubmed_abstracts(
                result["pmids_needing_abstracts"], project_id, verify=True
            )
            abstracts_fetched = fetch_result["abstracts_fetched"]
            logger.info(f"Fetched {abstracts_fetched} abstracts from PubMed")

        logger.info(
            f"Processing complete for {original_filename}. "
            f"Created: {result['articles_created']}, Updated: {result['articles_updated']}, "
            f"Duplicates: {result['duplicates']}"
        )

        return {
            "status": "Success",
            "articles_created": result["articles_created"],
            "articles_updated": result["articles_updated"],
            "duplicates": result["duplicates"],
            "duplicates_by_title_year": result["duplicates_by_title_year"],
            "abstracts_fetched": abstracts_fetched,
        }

    except FileNotFoundError:
        return {"status": "Error", "message": "File not found."}
    except Exception:
        logger.exception("An error occurred while parsing %s", file_path)
        raise
    finally:
        # Ensure the temporary file is always cleaned up.
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up temporary file: {file_path}")


@task(name="parse_pubmed_entries")
def parse_pubmed_entries(
    file_path: str, project_id: int, original_filename: str, file_format: str
) -> dict[str, Any]:
    """Parse PubMed entries and save to database.

    This task handles parsing MEDLINE (.txt) or CSV files and database operations.

    Args:
        file_path: Path to the PubMed export file.
        project_id: ID of the project to associate articles with.
        original_filename: Original name of the uploaded file.
        file_format: Either 'txt' or 'csv'.

    Returns:
        Dictionary with created/updated counts and PMIDs needing abstracts.
    """
    articles_created = 0
    articles_updated = 0
    duplicates = 0
    pmids_needing_abstracts: list[str] = []

    # Parse the file based on format
    if file_format == "txt":
        entries = parse_pubmed_txt(file_path)
    else:
        entries = parse_pubmed_csv(file_path)

    with get_prefect_session() as session:
        index = ProjectArticleIndex(session, project_id)
        for entry in entries:
            pmid = entry.get("pmid")
            title = entry.get("title")

            # A PMID and title are essential for a meaningful record
            if not pmid or not title:
                logger.info(
                    f"Skipping entry due to missing PMID or title: {entry.get('pmid', 'N/A')}"
                )
                continue

            # Per-project duplicate lookup: PMID, then DOI (then title + year, which
            # only applies to entries without identifiers).
            existing_article, _ = index.find(
                entry.get("doi"), pmid, title, entry.get("year")
            )
            if existing_article is not None:
                duplicates += 1

            # Prepare article data
            article_data = {
                "project_id": project_id,
                "title": title,
                "authors": entry.get("authors", []),
                "abstract": entry.get("abstract"),
                "publication_date": entry.get("publication_date"),
                "year": entry.get("year"),
                "journal": entry.get("journal"),
                "volume": entry.get("volume"),
                "issue": entry.get("issue"),
                "pages": entry.get("pages"),
                "publication_type": entry.get("publication_type"),
                "doi": entry.get("doi"),
                "pmid": pmid,
                "pmcid": entry.get("pmcid"),
                "issn": entry.get("issn"),
                "keywords": entry.get("keywords", []),
                "mesh_terms": entry.get("mesh_terms", []),
                "source_filename": original_filename,
            }

            if existing_article:
                # Update fields - only update if new value is not None
                for key, value in article_data.items():
                    if value is not None:
                        current_value = getattr(existing_article, key, None)
                        # Don't overwrite existing non-empty values with empty ones
                        if current_value is None or (
                            value and not isinstance(value, (list, dict))
                        ):
                            setattr(existing_article, key, value)
                        elif isinstance(value, list) and value:
                            setattr(existing_article, key, value)
                session.add(existing_article)
                articles_updated += 1

                # Check if we need to fetch abstract for existing article
                if not existing_article.abstract and entry.get("needs_abstract_fetch"):
                    pmids_needing_abstracts.append(pmid)
            else:
                # Create new article
                new_article = new_screening_article(article_data)
                session.add(new_article)
                index.add(new_article)
                articles_created += 1

                # Track if we need to fetch abstract
                if entry.get("needs_abstract_fetch"):
                    pmids_needing_abstracts.append(pmid)

    return {
        "records_found": len(entries),
        "articles_created": articles_created,
        "articles_updated": articles_updated,
        "duplicates": duplicates,
        "pmids_needing_abstracts": pmids_needing_abstracts,
    }


def _same_article(article: Article, record: PubMedRecord) -> bool:
    """True when a PubMed record describes the imported article (DOI, else title)."""
    if article.doi and record.doi:
        return article.doi.strip().lower() == record.doi.lower()
    title = normalize_title(article.title)
    return bool(title) and title == normalize_title(record.title)


@task(name="fetch_pubmed_abstracts")
def fetch_pubmed_abstracts(
    pmids: list[str], project_id: int, verify: bool = False
) -> dict[str, Any]:
    """Fetch abstracts from PubMed for articles missing them.

    Args:
        pmids: List of PMIDs to fetch abstracts for.
        project_id: Project ID for updating articles.
        verify: Only use a record whose DOI (or, without one, title) matches the
            article; for PMIDs that may be another database's accession number.

    Returns:
        Dictionary with count of abstracts fetched.
    """
    if not pmids:
        return {"abstracts_fetched": 0}

    # Fetch abstracts from PubMed
    pubmed_service = PubMedService()
    if verify:
        records = pubmed_service.fetch_records_sync(pmids)
    else:
        records = {
            pmid: PubMedRecord(pmid=pmid, abstract=abstract)
            for pmid, abstract in pubmed_service.fetch_abstracts_sync(pmids).items()
        }

    # Update articles with fetched abstracts
    abstracts_updated = 0
    with get_prefect_session() as session:
        for pmid, record in records.items():
            if not record.abstract:
                continue
            statement = select(Article).where(
                Article.pmid == pmid, Article.project_id == project_id
            )
            article = session.exec(statement).first()
            if article is None or article.abstract:
                continue
            if verify and not _same_article(article, record):
                logger.info(f"PubMed record {pmid} does not match the article; skipped")
                continue
            article.abstract = record.abstract
            session.add(article)
            abstracts_updated += 1

    return {"abstracts_fetched": abstracts_updated}


@flow(name="parse_pubmed_file", log_prints=True)
def parse_pubmed_file_flow(
    file_path: str,
    project_id: int,
    original_filename: str | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Prefect flow to parse a PubMed export file and save entries to the database.

    Supports both MEDLINE (.txt) and CSV formats. For CSV files, abstracts will
    be automatically fetched from PubMed E-utilities API.

    Args:
        file_path: Path to the PubMed export file.
        project_id: ID of the project to associate articles with.
        original_filename: Client-supplied display name (metadata only, never a path).
        user_id: User who uploaded the file (recorded on the import batch).

    Returns:
        Dictionary with status and article counts.
    """
    original_filename = original_filename or os.path.basename(file_path)

    # Determine file format from extension
    file_ext = os.path.splitext(file_path)[1].lower()
    if file_ext == ".txt":
        file_format = "txt"
    elif file_ext == ".csv":
        file_format = "csv"
    else:
        if os.path.exists(file_path):
            os.remove(file_path)
        return {"status": "Error", "message": f"Unsupported file format: {file_ext}"}

    logger.info(f"Starting to parse PubMed {file_format.upper()} file: {file_path}")
    logger.info(f"Original filename: {original_filename}")

    try:
        # Parse entries and save to database
        result = parse_pubmed_entries(
            file_path, project_id, original_filename, file_format
        )
        record_import_batch(
            project_id, original_filename, f"pubmed_{file_format}", result, user_id
        )

        logger.info(
            f"Initial processing complete. "
            f"Created: {result['articles_created']}, Updated: {result['articles_updated']}, "
            f"Duplicates: {result['duplicates']}"
        )

        # Fetch abstracts for CSV imports that need them
        abstracts_fetched = 0
        if result["pmids_needing_abstracts"]:
            logger.info(
                f"Fetching abstracts for {len(result['pmids_needing_abstracts'])} articles..."
            )
            fetch_result = fetch_pubmed_abstracts(
                result["pmids_needing_abstracts"], project_id
            )
            abstracts_fetched = fetch_result["abstracts_fetched"]
            logger.info(f"Fetched {abstracts_fetched} abstracts from PubMed")

        return {
            "status": "Success",
            "articles_created": result["articles_created"],
            "articles_updated": result["articles_updated"],
            "duplicates": result["duplicates"],
            "abstracts_fetched": abstracts_fetched,
        }

    except FileNotFoundError:
        return {"status": "Error", "message": "File not found."}
    except Exception:
        logger.exception("An error occurred while parsing %s", file_path)
        raise
    finally:
        # Ensure the temporary file is always cleaned up
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Cleaned up temporary file: {file_path}")
