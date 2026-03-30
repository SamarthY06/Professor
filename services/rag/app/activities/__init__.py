"""Temporal activities."""
from app.activities.toc_detection import detect_toc, extract_first_pages
from app.activities.pdf_extraction import extract_chapter_pages, extract_text_and_images
from app.activities.image_summarization import summarize_image, summarize_images_batch
from app.activities.chunking import chunk_text, merge_image_summaries_with_chunks
from app.activities.embedding import generate_embeddings, generate_query_embedding
from app.activities.storage_activities import (
    persist_toc_and_chapters,
    update_chapter_processing_status,
    persist_chunks_and_vectors,
    update_document_completion,
    increment_document_progress,
    set_document_pages,
)

__all__ = [
    "detect_toc",
    "extract_first_pages",
    "extract_chapter_pages",
    "extract_text_and_images",
    "summarize_image",
    "summarize_images_batch",
    "chunk_text",
    "merge_image_summaries_with_chunks",
    "generate_embeddings",
    "generate_query_embedding",
    "persist_toc_and_chapters",
    "update_chapter_processing_status",
    "persist_chunks_and_vectors",
    "update_document_completion",
    "increment_document_progress",
    "set_document_pages",
]
