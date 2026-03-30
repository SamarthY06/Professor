"""Table of Contents detection activities."""
import json
import re
from typing import Optional

from openai import OpenAI
from temporalio import activity

from app.config.settings import settings
from app.config.logging import get_logger
from app.activities.pdf_extraction import extract_pages_text, get_pdf_page_count
from app.activities.cost_tracking import record_cost_sync

logger = get_logger(__name__)

TOC_DETECTION_PROMPT = """You are analyzing the first pages of a textbook or technical document to extract the Table of Contents.

Your task:
1. Identify if there is a Table of Contents in the provided text
2. Extract chapter information with page numbers
3. Return structured JSON

Rules:
- Only include actual chapters, not preface, foreword, index, or appendices unless they are substantial
- Page numbers must be integers
- If you cannot find a clear TOC, attempt to identify chapter headings from the text
- Sections within chapters are optional but helpful

Return ONLY valid JSON in this exact format:
{
  "has_toc": true/false,
  "chapters": [
    {
      "title": "Chapter title",
      "start_page": number,
      "end_page": number or null,
      "sections": [
        {"title": "Section title", "start_page": number}
      ]
    }
  ]
}

If no TOC is found, return:
{
  "has_toc": false,
  "chapters": []
}

Document text to analyze:
"""

HEURISTIC_CHAPTER_PROMPT = """You are analyzing a document that does not have a clear Table of Contents.

Your task:
1. Identify chapter or major section boundaries from the text
2. Look for patterns like "Chapter 1", "CHAPTER ONE", "1. Introduction", etc.
3. Estimate page ranges based on content

Return ONLY valid JSON in this exact format:
{
  "chapters": [
    {
      "title": "Chapter title",
      "start_page": number,
      "end_page": number or null,
      "sections": []
    }
  ]
}

Document text to analyze:
"""


@activity.defn
async def extract_first_pages(pdf_path: str, num_pages: int) -> str:
    """
    Extract text from the first N pages of a PDF.

    Args:
        pdf_path: Path to the PDF file
        num_pages: Number of pages to extract

    Returns:
        Extracted text
    """
    activity.logger.info(f"Extracting first {num_pages} pages from {pdf_path}")

    total_pages = get_pdf_page_count(pdf_path)
    pages_to_extract = min(num_pages, total_pages)

    text = extract_pages_text(pdf_path, 1, pages_to_extract)

    activity.logger.info(f"Extracted {len(text)} characters from {pages_to_extract} pages")
    return text


@activity.defn
async def detect_toc(
    pdf_path: str,
    first_pages_text: str,
    total_pages: int,
    document_id: Optional[str] = None,
) -> dict:
    """
    Detect and parse Table of Contents using LLM.

    Args:
        pdf_path: Path to the PDF file
        first_pages_text: Text from first pages
        total_pages: Total pages in document
        document_id: Optional document ID for cost tracking

    Returns:
        Parsed TOC data with chapters
    """
    activity.logger.info("Detecting TOC using LLM")

    client = OpenAI(api_key=settings.openai_api_key)

    # First attempt: Look for explicit TOC
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": "You are a document analysis expert. Extract table of contents information accurately.",
            },
            {
                "role": "user",
                "content": TOC_DETECTION_PROMPT + first_pages_text[:15000],
            },
        ],
        temperature=0.1,
        max_tokens=4000,
    )

    # Track cost for first TOC detection call
    if response.usage:
        try:
            await record_cost_sync(
                cost_type="TOC_DETECTION",
                model=settings.openai_model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                document_id=document_id,
                description="TOC detection - primary attempt",
            )
        except Exception as e:
            activity.logger.warning(f"Failed to record cost: {e}")

    response_text = response.choices[0].message.content or ""

    # Parse JSON from response
    toc_data = _parse_json_response(response_text)

    if toc_data and toc_data.get("has_toc") and toc_data.get("chapters"):
        activity.logger.info(f"Found TOC with {len(toc_data['chapters'])} chapters")
        # Fill in missing end pages
        toc_data["chapters"] = _fill_end_pages(toc_data["chapters"], total_pages)
        return toc_data

    # Fallback: Heuristic chapter detection
    activity.logger.info("No clear TOC found, using heuristic detection")

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": "You are a document analysis expert. Identify chapter boundaries from document text.",
            },
            {
                "role": "user",
                "content": HEURISTIC_CHAPTER_PROMPT + first_pages_text[:15000],
            },
        ],
        temperature=0.1,
        max_tokens=4000,
    )

    # Track cost for heuristic detection call
    if response.usage:
        try:
            await record_cost_sync(
                cost_type="TOC_DETECTION",
                model=settings.openai_model,
                input_tokens=response.usage.prompt_tokens,
                output_tokens=response.usage.completion_tokens,
                document_id=document_id,
                description="TOC detection - heuristic fallback",
            )
        except Exception as e:
            activity.logger.warning(f"Failed to record cost: {e}")

    response_text = response.choices[0].message.content or ""
    toc_data = _parse_json_response(response_text)

    if toc_data and toc_data.get("chapters"):
        activity.logger.info(
            f"Heuristic detection found {len(toc_data['chapters'])} chapters"
        )
        toc_data["chapters"] = _fill_end_pages(toc_data["chapters"], total_pages)
        toc_data["has_toc"] = False
        return toc_data

    # Last resort: Create single chapter for entire document
    activity.logger.warning("Could not detect chapters, creating single chapter")
    return {
        "has_toc": False,
        "chapters": [
            {
                "title": "Full Document",
                "start_page": 1,
                "end_page": total_pages,
                "sections": [],
            }
        ],
    }


def _parse_json_response(response_text: str) -> Optional[dict]:
    """Parse JSON from LLM response."""
    # Try to extract JSON from response
    try:
        # Look for JSON block
        json_match = re.search(r"\{[\s\S]*\}", response_text)
        if json_match:
            return json.loads(json_match.group())
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse JSON response: {e}")

    return None


def _fill_end_pages(chapters: list[dict], total_pages: int) -> list[dict]:
    """Fill in missing end pages for chapters."""
    for i, chapter in enumerate(chapters):
        if chapter.get("end_page") is None:
            if i + 1 < len(chapters):
                # End page is one before next chapter starts
                chapter["end_page"] = chapters[i + 1]["start_page"] - 1
            else:
                # Last chapter ends at document end
                chapter["end_page"] = total_pages

        # Ensure end_page is not before start_page
        if chapter["end_page"] < chapter["start_page"]:
            chapter["end_page"] = chapter["start_page"]

    return chapters
