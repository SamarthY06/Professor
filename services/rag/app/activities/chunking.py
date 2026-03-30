"""Text chunking activities."""
import re
from dataclasses import dataclass
from typing import Optional

import tiktoken
from temporalio import activity

from app.config.settings import settings
from app.config.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TextChunk:
    """A chunk of text with metadata."""

    content: str
    token_count: int
    start_page: int
    end_page: int
    chunk_index: int
    section_title: Optional[str] = None


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens in text using tiktoken."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences."""
    # Simple sentence splitting - handles common cases
    sentence_endings = re.compile(r'(?<=[.!?])\s+(?=[A-Z])')
    sentences = sentence_endings.split(text)
    return [s.strip() for s in sentences if s.strip()]


@activity.defn
async def chunk_text(
    text_blocks: list[dict],
    chapter_id: str,
    min_chunk_size: Optional[int] = None,
    max_chunk_size: Optional[int] = None,
) -> list[dict]:
    """
    Chunk text blocks into appropriately sized chunks.

    Args:
        text_blocks: List of text blocks with page_number and text
        chapter_id: Chapter identifier
        min_chunk_size: Minimum tokens per chunk
        max_chunk_size: Maximum tokens per chunk

    Returns:
        List of chunk dictionaries
    """
    min_size = min_chunk_size or settings.chunk_size_min
    max_size = max_chunk_size or settings.chunk_size_max

    activity.logger.info(
        f"Chunking text for chapter {chapter_id}, "
        f"target size: {min_size}-{max_size} tokens"
    )

    # Combine text blocks with page tracking
    combined_text = []
    page_ranges = []

    for block in text_blocks:
        combined_text.append(block["text"])
        page_ranges.append(block["page_number"])

    full_text = "\n\n".join(combined_text)

    if not full_text.strip():
        activity.logger.warning(f"No text to chunk for chapter {chapter_id}")
        return []

    # Split into paragraphs first
    paragraphs = re.split(r'\n\s*\n', full_text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]

    chunks = []
    current_chunk = []
    current_tokens = 0
    chunk_index = 0

    # Track page range for current chunk
    current_start_page = page_ranges[0] if page_ranges else 1
    current_end_page = current_start_page

    for para_idx, paragraph in enumerate(paragraphs):
        para_tokens = count_tokens(paragraph)

        # If single paragraph exceeds max, split it
        if para_tokens > max_size:
            # Flush current chunk first
            if current_chunk:
                chunk_text_content = "\n\n".join(current_chunk)
                chunks.append({
                    "content": chunk_text_content,
                    "token_count": current_tokens,
                    "start_page": current_start_page,
                    "end_page": current_end_page,
                    "chunk_index": chunk_index,
                    "chapter_id": chapter_id,
                })
                chunk_index += 1
                current_chunk = []
                current_tokens = 0

            # Split large paragraph by sentences
            sentences = split_into_sentences(paragraph)
            sentence_chunk = []
            sentence_tokens = 0

            for sentence in sentences:
                sent_tokens = count_tokens(sentence)

                if sentence_tokens + sent_tokens > max_size and sentence_chunk:
                    # Save sentence chunk
                    chunk_text_content = " ".join(sentence_chunk)
                    chunks.append({
                        "content": chunk_text_content,
                        "token_count": sentence_tokens,
                        "start_page": current_start_page,
                        "end_page": current_end_page,
                        "chunk_index": chunk_index,
                        "chapter_id": chapter_id,
                    })
                    chunk_index += 1
                    sentence_chunk = [sentence]
                    sentence_tokens = sent_tokens
                else:
                    sentence_chunk.append(sentence)
                    sentence_tokens += sent_tokens

            # Add remaining sentences
            if sentence_chunk:
                chunk_text_content = " ".join(sentence_chunk)
                chunks.append({
                    "content": chunk_text_content,
                    "token_count": sentence_tokens,
                    "start_page": current_start_page,
                    "end_page": current_end_page,
                    "chunk_index": chunk_index,
                    "chapter_id": chapter_id,
                })
                chunk_index += 1

            # Update page tracking
            if para_idx < len(page_ranges):
                current_start_page = page_ranges[para_idx]
                current_end_page = current_start_page

        elif current_tokens + para_tokens > max_size:
            # Current chunk is full, save it
            if current_chunk:
                chunk_text_content = "\n\n".join(current_chunk)
                chunks.append({
                    "content": chunk_text_content,
                    "token_count": current_tokens,
                    "start_page": current_start_page,
                    "end_page": current_end_page,
                    "chunk_index": chunk_index,
                    "chapter_id": chapter_id,
                })
                chunk_index += 1

            # Start new chunk with current paragraph
            current_chunk = [paragraph]
            current_tokens = para_tokens

            # Update page tracking
            if para_idx < len(page_ranges):
                current_start_page = page_ranges[para_idx]
                current_end_page = current_start_page

        else:
            # Add to current chunk
            current_chunk.append(paragraph)
            current_tokens += para_tokens

            # Update end page
            if para_idx < len(page_ranges):
                current_end_page = page_ranges[para_idx]

    # Don't forget the last chunk
    if current_chunk:
        chunk_text_content = "\n\n".join(current_chunk)
        final_tokens = count_tokens(chunk_text_content)
        chunks.append({
            "content": chunk_text_content,
            "token_count": final_tokens,
            "start_page": current_start_page,
            "end_page": current_end_page,
            "chunk_index": chunk_index,
            "chapter_id": chapter_id,
        })

    activity.logger.info(f"Created {len(chunks)} chunks for chapter {chapter_id}")
    return chunks


def merge_image_summaries_with_chunks(
    chunks: list[dict],
    image_summaries: list[dict],
) -> list[dict]:
    """
    Merge image summaries with nearest text chunks.

    Args:
        chunks: List of text chunks
        image_summaries: List of image summaries with page numbers

    Returns:
        Updated chunks with image summaries attached
    """
    if not image_summaries:
        return chunks

    # Create page to chunk mapping
    page_to_chunk: dict[int, int] = {}
    for idx, chunk in enumerate(chunks):
        for page in range(chunk["start_page"], chunk["end_page"] + 1):
            if page not in page_to_chunk:
                page_to_chunk[page] = idx

    # Attach image summaries to chunks
    for img_summary in image_summaries:
        page = img_summary["page_number"]
        chunk_idx = page_to_chunk.get(page)

        if chunk_idx is not None and chunk_idx < len(chunks):
            if "image_summaries" not in chunks[chunk_idx]:
                chunks[chunk_idx]["image_summaries"] = []
            chunks[chunk_idx]["image_summaries"].append({
                "page": page,
                "summary": img_summary["summary"],
            })

    return chunks
