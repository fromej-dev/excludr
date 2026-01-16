"""Prefect flows for project-related background tasks."""

import os
from typing import Any

import rispy
from prefect import flow, task
from sqlmodel import select

from app.core.prefect_config import get_prefect_session
from app.features.research.models import Article
from app.features.projects.parsers import parse_pubmed_txt, parse_pubmed_csv
from app.features.research.pubmed_service import PubMedService


@task(name="parse_ris_entries")
def parse_ris_entries(file_path: str, project_id: int, original_filename: str) -> dict:
    """Parse RIS entries and save to database.

    This task handles the actual parsing and database operations.
    """
    articles_created = 0
    articles_updated = 0

    with open(file_path, "r", encoding="utf-8") as file:
        entries = rispy.load(file)

        with get_prefect_session() as session:
            for entry in entries:
                doi = entry.get("doi")

                # A DOI and title are essential for a meaningful record.
                if not doi or not (entry.get("title") or entry.get("primary_title")):
                    print(
                        f"Skipping entry due to missing DOI or title: {entry.get('id', 'N/A')}"
                    )
                    continue

                # Check if an article with this DOI already exists in the database.
                statement = select(Article).where(Article.doi == doi)
                existing_article = session.exec(statement).first()

                # --- Map all available RIS tags to the Article model fields ---

                # Gracefully parse year, handling formats like '2023/05/10'
                year = None
                try:
                    year_str = entry.get("year") or entry.get("publication_year")
                    if year_str:
                        # Take the first part of a date string and convert to int
                        year = int(float(str(year_str).split("/")[0]))
                except (ValueError, TypeError):
                    print(f"Could not parse year for article with DOI {doi}")

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
                    "title": entry.get("title") or entry.get("primary_title"),
                    "authors": entry.get("authors", []),
                    "abstract": entry.get("abstract"),
                    "publication_date": entry.get("date"),
                    "year": year,
                    "journal": entry.get("journal_name")
                    or entry.get("secondary_title"),
                    "volume": entry.get("volume"),
                    "issue": entry.get("issue"),
                    "pages": pages,
                    "publication_type": entry.get("type_of_reference"),
                    "doi": doi,
                    "pmid": entry.get(
                        "accession_number"
                    ),  # This tag is often used for PMID.
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
                else:
                    # Or, create a new article instance.
                    new_article = Article(**article_data)
                    session.add(new_article)
                    articles_created += 1

    return {
        "articles_created": articles_created,
        "articles_updated": articles_updated,
    }


@flow(name="parse_ris_file", log_prints=True)
def parse_ris_file_flow(file_path: str, project_id: int) -> dict:
    """Prefect flow to parse a RIS file and save/update entries in the database.

    Args:
        file_path: Path to the RIS file to parse.
        project_id: ID of the project to associate articles with.

    Returns:
        Dictionary with status, articles_created, and articles_updated counts.
    """
    # Extract original filename from the temp path
    try:
        original_filename = "_".join(os.path.basename(file_path).split("_")[1:])
    except IndexError:
        original_filename = os.path.basename(file_path)

    print(f"Starting to parse file: {file_path} (from {original_filename})")

    try:
        result = parse_ris_entries(file_path, project_id, original_filename)

        print(
            f"Processing complete for {original_filename}. "
            f"Created: {result['articles_created']}, Updated: {result['articles_updated']}"
        )

        return {
            "status": "Success",
            "articles_created": result["articles_created"],
            "articles_updated": result["articles_updated"],
        }

    except FileNotFoundError:
        return {"status": "Error", "message": "File not found."}
    except Exception as e:
        print(f"An error occurred while parsing {file_path}: {e}")
        raise
    finally:
        # Ensure the temporary file is always cleaned up.
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Cleaned up temporary file: {file_path}")


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
    pmids_needing_abstracts: list[str] = []

    # Parse the file based on format
    if file_format == "txt":
        entries = parse_pubmed_txt(file_path)
    else:
        entries = parse_pubmed_csv(file_path)

    with get_prefect_session() as session:
        for entry in entries:
            pmid = entry.get("pmid")
            title = entry.get("title")

            # A PMID and title are essential for a meaningful record
            if not pmid or not title:
                print(f"Skipping entry due to missing PMID or title: {entry}")
                continue

            # Check for existing article by PMID first
            existing_article = None
            statement = select(Article).where(
                Article.pmid == pmid, Article.project_id == project_id
            )
            existing_article = session.exec(statement).first()

            # Fall back to DOI check if PMID not found
            if not existing_article and entry.get("doi"):
                statement = select(Article).where(
                    Article.doi == entry.get("doi"), Article.project_id == project_id
                )
                existing_article = session.exec(statement).first()

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
                new_article = Article(**article_data)
                session.add(new_article)
                articles_created += 1

                # Track if we need to fetch abstract
                if entry.get("needs_abstract_fetch"):
                    pmids_needing_abstracts.append(pmid)

    return {
        "articles_created": articles_created,
        "articles_updated": articles_updated,
        "pmids_needing_abstracts": pmids_needing_abstracts,
    }


@task(name="fetch_pubmed_abstracts")
def fetch_pubmed_abstracts(pmids: list[str], project_id: int) -> dict[str, Any]:
    """Fetch abstracts from PubMed for articles missing them.

    Args:
        pmids: List of PMIDs to fetch abstracts for.
        project_id: Project ID for updating articles.

    Returns:
        Dictionary with count of abstracts fetched.
    """
    if not pmids:
        return {"abstracts_fetched": 0}

    # Fetch abstracts from PubMed
    pubmed_service = PubMedService()
    abstracts = pubmed_service.fetch_abstracts_sync(pmids)

    # Update articles with fetched abstracts
    abstracts_updated = 0
    with get_prefect_session() as session:
        for pmid, abstract in abstracts.items():
            statement = select(Article).where(
                Article.pmid == pmid, Article.project_id == project_id
            )
            article = session.exec(statement).first()
            if article and not article.abstract:
                article.abstract = abstract
                session.add(article)
                abstracts_updated += 1

    return {"abstracts_fetched": abstracts_updated}


@flow(name="parse_pubmed_file", log_prints=True)
def parse_pubmed_file_flow(file_path: str, project_id: int) -> dict[str, Any]:
    """Prefect flow to parse a PubMed export file and save entries to the database.

    Supports both MEDLINE (.txt) and CSV formats. For CSV files, abstracts will
    be automatically fetched from PubMed E-utilities API.

    Args:
        file_path: Path to the PubMed export file.
        project_id: ID of the project to associate articles with.

    Returns:
        Dictionary with status and article counts.
    """
    # Extract original filename and determine format
    try:
        original_filename = "_".join(os.path.basename(file_path).split("_")[1:])
    except IndexError:
        original_filename = os.path.basename(file_path)

    # Determine file format from extension
    file_ext = os.path.splitext(file_path)[1].lower()
    if file_ext == ".txt":
        file_format = "txt"
    elif file_ext == ".csv":
        file_format = "csv"
    else:
        return {"status": "Error", "message": f"Unsupported file format: {file_ext}"}

    print(f"Starting to parse PubMed {file_format.upper()} file: {file_path}")
    print(f"Original filename: {original_filename}")

    try:
        # Parse entries and save to database
        result = parse_pubmed_entries(
            file_path, project_id, original_filename, file_format
        )

        print(
            f"Initial processing complete. "
            f"Created: {result['articles_created']}, Updated: {result['articles_updated']}"
        )

        # Fetch abstracts for CSV imports that need them
        abstracts_fetched = 0
        if result["pmids_needing_abstracts"]:
            print(
                f"Fetching abstracts for {len(result['pmids_needing_abstracts'])} articles..."
            )
            fetch_result = fetch_pubmed_abstracts(
                result["pmids_needing_abstracts"], project_id
            )
            abstracts_fetched = fetch_result["abstracts_fetched"]
            print(f"Fetched {abstracts_fetched} abstracts from PubMed")

        return {
            "status": "Success",
            "articles_created": result["articles_created"],
            "articles_updated": result["articles_updated"],
            "abstracts_fetched": abstracts_fetched,
        }

    except FileNotFoundError:
        return {"status": "Error", "message": "File not found."}
    except Exception as e:
        print(f"An error occurred while parsing {file_path}: {e}")
        raise
    finally:
        # Ensure the temporary file is always cleaned up
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Cleaned up temporary file: {file_path}")
