#!/usr/bin/env python3
"""Test script for PDF processing without full workflow."""
import asyncio
import json
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config.settings import settings
from app.config.logging import configure_logging, get_logger
from app.activities.pdf_extraction import (
    get_pdf_page_count,
    extract_pages_text,
)
from app.activities.toc_detection import _parse_json_response, _fill_end_pages
from app.activities.chunking import count_tokens

configure_logging()
logger = get_logger(__name__)


def test_pdf_extraction(pdf_path: str) -> None:
    """Test PDF extraction capabilities."""
    print(f"\n{'='*60}")
    print(f"Testing PDF: {pdf_path}")
    print(f"{'='*60}\n")

    # Check if file exists
    if not os.path.exists(pdf_path):
        print(f"ERROR: File not found: {pdf_path}")
        return

    # Get page count
    total_pages = get_pdf_page_count(pdf_path)
    print(f"Total pages: {total_pages}")

    # Extract first 20 pages
    pages_to_extract = min(20, total_pages)
    print(f"\nExtracting first {pages_to_extract} pages...")

    first_pages_text = extract_pages_text(pdf_path, 1, pages_to_extract)
    print(f"Extracted {len(first_pages_text)} characters")

    # Show sample of extracted text
    print(f"\n--- Sample of extracted text (first 2000 chars) ---")
    print(first_pages_text[:2000])
    print(f"--- End sample ---\n")

    # Try to find TOC patterns
    print("\n--- Looking for TOC patterns ---")
    toc_indicators = [
        "contents",
        "table of contents",
        "chapter",
        "section",
    ]

    for indicator in toc_indicators:
        count = first_pages_text.lower().count(indicator)
        if count > 0:
            print(f"  Found '{indicator}': {count} occurrences")

    # Count tokens
    token_count = count_tokens(first_pages_text)
    print(f"\nToken count for first {pages_to_extract} pages: {token_count}")

    # Test chunking simulation
    print("\n--- Chunking simulation ---")
    chunk_size = 700  # Target chunk size
    estimated_chunks = token_count // chunk_size
    print(f"Estimated chunks (at {chunk_size} tokens each): {estimated_chunks}")

    print("\n" + "="*60)
    print("PDF extraction test complete!")
    print("="*60 + "\n")


def test_toc_parsing() -> None:
    """Test TOC parsing with sample data."""
    print("\n--- Testing TOC parsing ---")

    # Sample TOC response (simulating what LLM might return)
    sample_response = '''
    {
      "has_toc": true,
      "chapters": [
        {
          "title": "Preview",
          "start_page": 1,
          "end_page": null,
          "sections": []
        },
        {
          "title": "Configuration Space",
          "start_page": 11,
          "end_page": null,
          "sections": [
            {"title": "Degrees of Freedom of a Rigid Body", "start_page": 12},
            {"title": "Degrees of Freedom of a Robot", "start_page": 15}
          ]
        },
        {
          "title": "Rigid-Body Motions",
          "start_page": 59,
          "end_page": null,
          "sections": []
        }
      ]
    }
    '''

    parsed = _parse_json_response(sample_response)
    if parsed:
        print("Successfully parsed TOC response")
        print(f"Found {len(parsed.get('chapters', []))} chapters")

        # Fill end pages
        chapters = _fill_end_pages(parsed["chapters"], 600)
        print("\nChapters with filled end pages:")
        for ch in chapters:
            print(f"  - {ch['title']}: pages {ch['start_page']}-{ch['end_page']}")
    else:
        print("Failed to parse TOC response")


def main() -> None:
    """Main test function."""
    # Default test PDF path
    pdf_path = os.environ.get(
        "TEST_PDF_PATH",
        "/Users/samarthyadannavar/Desktop/Personal/Textbook_RAG/MR_book\\.pdf"
    )

    # Also try without backslash
    if not os.path.exists(pdf_path):
        pdf_path = "/Users/samarthyadannavar/Desktop/Personal/Textbook_RAG/MR_book.pdf"

    test_pdf_extraction(pdf_path)
    test_toc_parsing()


if __name__ == "__main__":
    main()
