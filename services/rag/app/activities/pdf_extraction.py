"""PDF extraction activities using PyMuPDF."""
import base64
import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from temporalio import activity

from app.config.settings import settings
from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ExtractedImage:
    """Extracted image metadata (without raw data to avoid payload size issues)."""

    page_number: int
    image_index: int
    bbox: tuple[float, float, float, float]
    width: int
    height: int


@dataclass
class ExtractedText:
    """Extracted text block."""

    page_number: int
    text: str
    bbox: Optional[tuple[float, float, float, float]] = None


@dataclass
class ChapterContent:
    """Extracted chapter content."""

    chapter_id: str
    text_blocks: list[ExtractedText]
    images: list[ExtractedImage]
    start_page: int
    end_page: int


@activity.defn
async def extract_chapter_pages(
    pdf_path: str,
    start_page: int,
    end_page: int,
    output_dir: str,
) -> str:
    """
    Extract specific pages from PDF and save as a new PDF.

    Args:
        pdf_path: Path to the source PDF
        start_page: Start page (1-indexed)
        end_page: End page (1-indexed, inclusive)
        output_dir: Directory to save extracted PDF

    Returns:
        Path to the extracted PDF
    """
    activity.logger.info(
        f"Extracting pages {start_page}-{end_page} from {pdf_path}"
    )

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Open source PDF
    src_doc = fitz.open(pdf_path)

    try:
        # Create new PDF with selected pages
        dst_doc = fitz.open()

        # Convert to 0-indexed
        start_idx = max(0, start_page - 1)
        end_idx = min(len(src_doc), end_page)

        for page_num in range(start_idx, end_idx):
            dst_doc.insert_pdf(src_doc, from_page=page_num, to_page=page_num)

        # Generate output filename
        output_filename = f"chapter_{start_page}_{end_page}.pdf"
        output_path = os.path.join(output_dir, output_filename)

        # Save extracted PDF
        dst_doc.save(output_path)
        dst_doc.close()

        activity.logger.info(f"Extracted PDF saved to {output_path}")
        return output_path

    finally:
        src_doc.close()


@activity.defn
async def extract_text_and_images(
    pdf_path: str,
    chapter_id: str,
    start_page: int,
    end_page: int,
) -> dict:
    """
    Extract text and image metadata from a PDF chapter.

    Note: Image data is NOT included to avoid Temporal payload size limits.
    Only image metadata (page, position, size) is returned.

    Args:
        pdf_path: Path to the PDF file
        chapter_id: Chapter identifier
        start_page: Start page (1-indexed)
        end_page: End page (1-indexed, inclusive)

    Returns:
        Dictionary with text_blocks and images (metadata only)
    """
    activity.logger.info(
        f"Extracting text and images from {pdf_path}, pages {start_page}-{end_page}"
    )

    doc = fitz.open(pdf_path)
    text_blocks: list[dict] = []
    images: list[dict] = []

    try:
        # Convert to 0-indexed
        start_idx = max(0, start_page - 1)
        end_idx = min(len(doc), end_page)

        for page_num in range(start_idx, end_idx):
            page = doc[page_num]
            actual_page = page_num + 1  # Convert back to 1-indexed

            # Extract text blocks
            blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

            for block in blocks:
                if block["type"] == 0:  # Text block
                    # Combine all spans in the block
                    block_text = ""
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            block_text += span.get("text", "")
                        block_text += "\n"

                    block_text = block_text.strip()
                    if block_text:
                        text_blocks.append({
                            "page_number": actual_page,
                            "text": block_text,
                            "bbox": block.get("bbox"),
                        })

            # Extract image metadata only (no raw data)
            image_list = page.get_images(full=True)

            for img_index, img_info in enumerate(image_list):
                try:
                    xref = img_info[0]

                    # Get image position on page
                    img_rect = page.get_image_rects(xref)
                    bbox = img_rect[0] if img_rect else (0, 0, 0, 0)

                    # Get basic image info without extracting full data
                    images.append({
                        "page_number": actual_page,
                        "image_index": img_index,
                        "bbox": tuple(bbox) if bbox else (0, 0, 0, 0),
                        "width": img_info[2] if len(img_info) > 2 else 0,
                        "height": img_info[3] if len(img_info) > 3 else 0,
                    })
                except Exception as e:
                    activity.logger.warning(
                        f"Failed to get image metadata {img_index} from page {actual_page}: {e}"
                    )

        activity.logger.info(
            f"Extracted {len(text_blocks)} text blocks and {len(images)} images"
        )

        return {
            "chapter_id": chapter_id,
            "text_blocks": text_blocks,
            "images": images,
            "start_page": start_page,
            "end_page": end_page,
        }

    finally:
        doc.close()


def get_pdf_page_count(pdf_path: str) -> int:
    """Get total page count of a PDF."""
    doc = fitz.open(pdf_path)
    try:
        return len(doc)
    finally:
        doc.close()


def extract_pages_text(pdf_path: str, start_page: int, end_page: int) -> str:
    """
    Extract plain text from specific pages.

    Args:
        pdf_path: Path to PDF
        start_page: Start page (1-indexed)
        end_page: End page (1-indexed, inclusive)

    Returns:
        Concatenated text from pages
    """
    doc = fitz.open(pdf_path)
    text_parts = []

    try:
        start_idx = max(0, start_page - 1)
        end_idx = min(len(doc), end_page)

        for page_num in range(start_idx, end_idx):
            page = doc[page_num]
            text_parts.append(f"--- Page {page_num + 1} ---\n")
            text_parts.append(page.get_text())

        return "\n".join(text_parts)

    finally:
        doc.close()
