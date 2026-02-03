"""PDF text extraction utilities using PyMuPDF."""

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class PDFExtractionError(Exception):
    """Custom exception for PDF extraction errors."""

    pass


def extract_text_from_pdf(file_path: str) -> str:
    """
    Extract text content from a PDF file.

    Args:
        file_path: Absolute path to the PDF file.

    Returns:
        Extracted text content as a string. Returns empty string if no text found.

    Raises:
        PDFExtractionError: If the file cannot be read or is not a valid PDF.
        FileNotFoundError: If the file does not exist.

    Example:
        >>> text = extract_text_from_pdf("/path/to/document.pdf")
        >>> print(f"Extracted {len(text)} characters")
    """
    import fitz  # PyMuPDF

    # Validate file existence
    pdf_path = Path(file_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    if not pdf_path.is_file():
        raise PDFExtractionError(f"Path is not a file: {file_path}")

    try:
        # Open the PDF document
        doc = fitz.open(file_path)

        # Extract text from all pages
        text_content = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            if text.strip():  # Only add non-empty pages
                text_content.append(text)

        doc.close()

        # Join all page text with double newlines
        extracted_text = "\n\n".join(text_content)

        if not extracted_text.strip():
            logger.warning(f"No text content extracted from PDF: {file_path}")
            return ""

        logger.info(
            f"Successfully extracted {len(extracted_text)} characters from {len(text_content)} pages"
        )
        return extracted_text

    except fitz.FileDataError as e:
        # This happens when the file is corrupted or not a valid PDF
        logger.error(f"Invalid or corrupted PDF file: {file_path} - {e}")
        raise PDFExtractionError(f"Invalid or corrupted PDF file: {e}") from e
    except Exception as e:
        # Catch any other unexpected errors
        logger.error(f"Unexpected error extracting text from PDF {file_path}: {e}")
        raise PDFExtractionError(f"Failed to extract text from PDF: {e}") from e


def extract_text_from_pdf_safe(file_path: str) -> Optional[str]:
    """
    Safely extract text from a PDF file, returning None on error.

    This is a wrapper around extract_text_from_pdf that catches all exceptions
    and returns None instead of raising. Useful for non-critical extraction
    where you want to continue processing even if extraction fails.

    Args:
        file_path: Absolute path to the PDF file.

    Returns:
        Extracted text content as a string, or None if extraction fails.

    Example:
        >>> text = extract_text_from_pdf_safe("/path/to/document.pdf")
        >>> if text:
        ...     print(f"Success: {len(text)} characters")
        ... else:
        ...     print("Extraction failed")
    """
    try:
        return extract_text_from_pdf(file_path)
    except Exception as e:
        logger.error(f"Failed to extract text from PDF {file_path}: {e}")
        return None
