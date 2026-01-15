"""Smart document chunking with semantic coherence."""

import hashlib
import re
from dataclasses import dataclass, field
from typing import List, Optional
from uuid import UUID

import tiktoken

from app.config import settings
from app.logs.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Section:
    """A detected section within a chapter."""
    title: Optional[str]
    text: str
    start_index: int = 0


@dataclass
class Chunk:
    """A text chunk ready for embedding."""
    content: str
    content_hash: str
    token_count: int
    chunk_index: int
    section_title: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    embedding: Optional[List[float]] = None


class SmartChunker:
    """
    Chunks text while preserving semantic coherence.
    Target: 300-500 tokens per chunk with overlap.
    """
    
    def __init__(
        self,
        target_size: int = None,
        min_size: int = None,
        max_size: int = None,
        overlap: int = None,
    ):
        self.target_size = target_size or settings.chunk_size
        self.min_size = min_size or int(self.target_size * 0.5)
        self.max_size = max_size or int(self.target_size * 1.5)
        self.overlap = overlap or settings.chunk_overlap
        
        # Use tiktoken for accurate token counting
        self.tokenizer = tiktoken.encoding_for_model("gpt-4")
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.tokenizer.encode(text))
    
    def chunk_chapter(
        self,
        chapter_text: str,
        chapter_id: UUID,
        book_id: UUID,
        page_offset: int = 0,
    ) -> List[Chunk]:
        """
        Chunk a chapter's text into semantic chunks.
        
        Args:
            chapter_text: The full text of the chapter
            chapter_id: The chapter's UUID
            book_id: The book's UUID
            page_offset: Starting page number for metadata
            
        Returns:
            List of Chunk objects
        """
        # Split into sections first
        sections = self._split_by_sections(chapter_text)
        
        chunks = []
        global_chunk_index = 0
        
        for section in sections:
            section_chunks = self._chunk_section(
                section,
                start_index=global_chunk_index,
            )
            
            for chunk in section_chunks:
                chunk.metadata.update({
                    "chapter_id": str(chapter_id),
                    "book_id": str(book_id),
                    "page_offset": page_offset,
                })
                chunks.append(chunk)
            
            global_chunk_index += len(section_chunks)
        
        logger.info(
            "chapter_chunked",
            chapter_id=str(chapter_id),
            chunk_count=len(chunks),
            avg_tokens=sum(c.token_count for c in chunks) // max(len(chunks), 1),
        )
        
        return chunks
    
    def _split_by_sections(self, text: str) -> List[Section]:
        """Split text by section headers."""
        # Pattern for markdown-style headers or section breaks
        section_pattern = r'^#{1,3}\s+(.+)$|^([A-Z][A-Z\s]+)$'
        
        lines = text.split('\n')
        sections = []
        current_section = Section(title=None, text="", start_index=0)
        
        for i, line in enumerate(lines):
            match = re.match(section_pattern, line, re.MULTILINE)
            
            if match:
                # Save current section if it has content
                if current_section.text.strip():
                    sections.append(current_section)
                
                # Start new section
                title = match.group(1) or match.group(2)
                current_section = Section(
                    title=title.strip() if title else None,
                    text="",
                    start_index=i,
                )
            else:
                current_section.text += line + '\n'
        
        # Don't forget the last section
        if current_section.text.strip():
            sections.append(current_section)
        
        # If no sections found, return entire text as one section
        if not sections:
            sections = [Section(title=None, text=text, start_index=0)]
        
        return sections
    
    def _chunk_section(
        self,
        section: Section,
        start_index: int = 0,
    ) -> List[Chunk]:
        """Chunk a single section."""
        paragraphs = self._split_paragraphs(section.text)
        
        chunks = []
        current_content = []
        current_tokens = 0
        
        for para in paragraphs:
            para_tokens = self.count_tokens(para)
            
            # If single paragraph exceeds max, split it
            if para_tokens > self.max_size:
                # Save current chunk first
                if current_content and current_tokens >= self.min_size:
                    chunks.append(self._create_chunk(
                        content="\n\n".join(current_content),
                        section_title=section.title,
                        chunk_index=start_index + len(chunks),
                    ))
                    current_content = []
                    current_tokens = 0
                
                # Split large paragraph into sentences
                sentence_chunks = self._chunk_large_paragraph(
                    para,
                    section.title,
                    start_index + len(chunks),
                )
                chunks.extend(sentence_chunks)
                start_index += len(sentence_chunks)
                continue
            
            # Check if adding this paragraph exceeds max
            if current_tokens + para_tokens > self.max_size:
                # Save current chunk
                if current_tokens >= self.min_size:
                    chunks.append(self._create_chunk(
                        content="\n\n".join(current_content),
                        section_title=section.title,
                        chunk_index=start_index + len(chunks),
                    ))
                    
                    # Start new chunk with overlap
                    overlap_content = current_content[-1] if current_content else ""
                    overlap_tokens = self.count_tokens(overlap_content)
                    
                    if overlap_tokens <= self.overlap:
                        current_content = [overlap_content, para]
                        current_tokens = overlap_tokens + para_tokens
                    else:
                        current_content = [para]
                        current_tokens = para_tokens
                else:
                    # Current chunk too small, just add paragraph
                    current_content.append(para)
                    current_tokens += para_tokens
            else:
                current_content.append(para)
                current_tokens += para_tokens
        
        # Don't forget the last chunk
        if current_content and current_tokens >= self.min_size // 2:
            chunks.append(self._create_chunk(
                content="\n\n".join(current_content),
                section_title=section.title,
                chunk_index=start_index + len(chunks),
            ))
        
        return chunks
    
    def _chunk_large_paragraph(
        self,
        paragraph: str,
        section_title: Optional[str],
        start_index: int,
    ) -> List[Chunk]:
        """Split a large paragraph by sentences."""
        # Split by sentence boundaries
        sentences = re.split(r'(?<=[.!?])\s+', paragraph)
        
        chunks = []
        current_content = []
        current_tokens = 0
        
        for sentence in sentences:
            sentence_tokens = self.count_tokens(sentence)
            
            if current_tokens + sentence_tokens > self.max_size:
                if current_content:
                    chunks.append(self._create_chunk(
                        content=" ".join(current_content),
                        section_title=section_title,
                        chunk_index=start_index + len(chunks),
                    ))
                current_content = [sentence]
                current_tokens = sentence_tokens
            else:
                current_content.append(sentence)
                current_tokens += sentence_tokens
        
        if current_content:
            chunks.append(self._create_chunk(
                content=" ".join(current_content),
                section_title=section_title,
                chunk_index=start_index + len(chunks),
            ))
        
        return chunks
    
    def _split_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs."""
        # Split on double newlines or multiple newlines
        paragraphs = re.split(r'\n\s*\n', text)
        
        # Clean up and filter empty paragraphs
        return [p.strip() for p in paragraphs if p.strip()]
    
    def _create_chunk(
        self,
        content: str,
        section_title: Optional[str],
        chunk_index: int,
    ) -> Chunk:
        """Create a Chunk object."""
        content = content.strip()
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        token_count = self.count_tokens(content)
        
        return Chunk(
            content=content,
            content_hash=content_hash,
            token_count=token_count,
            chunk_index=chunk_index,
            section_title=section_title,
        )
