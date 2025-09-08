import os

import rispy
from sqlmodel import select

from app.core.celery import get_celery_session, celery
from app.features.research.models import Article


@celery.task(name="tasks.parse_ris_file")
def parse_ris_file(file_path: str, project_id: int) -> dict:
    """
    A Celery task to parse a RIS file and save/update the entries in the database,
    linking them to a specific project.
    It checks for existing articles based on DOI to avoid creating duplicates.
    """
    # The temporary filename is expected to be in format `{uuid}_{original_filename}`
    # We extract the original filename here for provenance.
    try:
        original_filename = "_".join(os.path.basename(file_path).split("_")[1:])
    except IndexError:
        original_filename = os.path.basename(file_path)

    print(f"Starting to parse file: {file_path} (from {original_filename})")
    articles_created = 0
    articles_updated = 0

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            entries = rispy.load(file)

            with get_celery_session() as session:
                for entry in entries:
                    doi = entry.get("doi")

                    # A DOI and title are essential for a meaningful record.
                    if not doi or not (
                        entry.get("title") or entry.get("primary_title")
                    ):
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

                # The session is committed automatically by the context manager.

    except FileNotFoundError:
        return {"status": "Error", "message": "File not found."}
    except Exception as e:
        print(f"An error occurred while parsing {file_path}: {e}")
        if os.path.exists(file_path):
            os.remove(file_path)
        raise e  # Reraise to mark the task as FAILED in Celery.
    finally:
        # Ensure the temporary file is always cleaned up.
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"Cleaned up temporary file: {file_path}")

    print(
        f"Processing complete for {original_filename}. Created: {articles_created}, Updated: {articles_updated}"
    )
    return {
        "status": "Success",
        "articles_created": articles_created,
        "articles_updated": articles_updated,
    }
