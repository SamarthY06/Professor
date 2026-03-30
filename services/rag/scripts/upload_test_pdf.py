#!/usr/bin/env python3
"""Upload test PDF to the RAG service."""
import asyncio
import os
import sys
import time
from pathlib import Path

import httpx

# Configuration
API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
TEST_PDF_PATH = os.environ.get(
    "TEST_PDF_PATH",
    "/Users/samarthyadannavar/Desktop/Personal/Textbook_RAG/MR_book.pdf"
)


async def upload_document(pdf_path: str) -> dict:
    """Upload a PDF document."""
    print(f"Uploading: {pdf_path}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        with open(pdf_path, "rb") as f:
            files = {"file": (os.path.basename(pdf_path), f, "application/pdf")}
            response = await client.post(
                f"{API_BASE_URL}/documents/upload",
                files=files,
            )

        if response.status_code != 201:
            print(f"Upload failed: {response.status_code}")
            print(response.text)
            return {}

        return response.json()


async def get_progress(document_id: str) -> dict:
    """Get document processing progress."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{API_BASE_URL}/documents/{document_id}/progress"
        )
        return response.json()


async def get_chapters(document_id: str) -> dict:
    """Get document chapters."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{API_BASE_URL}/documents/{document_id}/chapters"
        )
        return response.json()


async def monitor_progress(document_id: str, interval: int = 5) -> None:
    """Monitor document processing progress."""
    print(f"\nMonitoring progress for document: {document_id}")
    print("-" * 60)

    while True:
        progress = await get_progress(document_id)

        status = progress.get("status", "UNKNOWN")
        phase = progress.get("current_phase", "UNKNOWN")
        total = progress.get("total_chapters", 0)
        completed = progress.get("completed_chapters", 0)
        percentage = progress.get("percentage", 0)

        print(
            f"Status: {status} | Phase: {phase} | "
            f"Progress: {completed}/{total} ({percentage}%)"
        )

        if status in ("COMPLETED", "FAILED", "PARTIAL_READY"):
            if progress.get("error_reason"):
                print(f"Error: {progress['error_reason']}")
            break

        await asyncio.sleep(interval)

    print("-" * 60)
    print("Processing complete!")


async def main() -> None:
    """Main function."""
    # Check if PDF exists
    pdf_path = TEST_PDF_PATH
    if not os.path.exists(pdf_path):
        # Try alternate path
        pdf_path = pdf_path.replace("\\", "")
        if not os.path.exists(pdf_path):
            print(f"ERROR: PDF not found at {TEST_PDF_PATH}")
            sys.exit(1)

    print(f"Using PDF: {pdf_path}")
    print(f"API URL: {API_BASE_URL}")
    print()

    # Check API health
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{API_BASE_URL}/health")
            if response.status_code != 200:
                print("ERROR: API is not healthy")
                sys.exit(1)
            print("API is healthy!")
    except Exception as e:
        print(f"ERROR: Cannot connect to API: {e}")
        sys.exit(1)

    # Upload document
    result = await upload_document(pdf_path)
    if not result:
        sys.exit(1)

    document_id = result.get("document_id")
    print(f"\nDocument uploaded successfully!")
    print(f"Document ID: {document_id}")
    print(f"Status: {result.get('status')}")

    # Monitor progress
    await monitor_progress(document_id)

    # Get chapters
    print("\nFetching chapters...")
    chapters = await get_chapters(document_id)

    if chapters.get("chapters"):
        print(f"\nFound {chapters['total_chapters']} chapters:")
        for ch in chapters["chapters"]:
            print(
                f"  {ch['chapter_number']}. {ch['title']} "
                f"(pages {ch['start_page']}-{ch['end_page']}, "
                f"{ch['chunk_count']} chunks)"
            )
    else:
        print("No chapters found")


if __name__ == "__main__":
    asyncio.run(main())
