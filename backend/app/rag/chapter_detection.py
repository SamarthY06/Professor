"""Chapter detection from PDF documents."""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from app.logs.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DetectedChapter:
    """A detected chapter in a document."""
    chapter_number: int
    title: str
    start_page: int
    end_page: Optional[int] = None


class ChapterDetector:
    """
    Detects chapter boundaries in PDF documents.
    Uses multiple signals: headings, page breaks, TOC.
    """
    
    CHAPTER_PATTERNS = [
        # "Chapter 1: Introduction" or "Chapter 1 - Introduction" (with title)
        r'^Chapter\s+(\d+)[\s:.\-]+([A-Za-z].{2,})$',
        r'^CHAPTER\s+(\d+)[\s:.\-]+([A-Za-z].{2,})$',
        # "Chapter 1" alone on a line (title on next line or no title)
        r'^Chapter\s+(\d+)\s*$',
        r'^CHAPTER\s+(\d+)\s*$',
        # "1. Introduction" - title must start with letter and be 3+ chars
        r'^(\d+)\.\s+([A-Z][A-Za-z\s]{3,})$',
        # Other formats
        r'^Part\s+(\d+)[\s:.\-]+([A-Za-z].{2,})$',
        r'^Section\s+(\d+)[\s:.\-]+([A-Za-z].{2,})$',
        r'^Unit\s+(\d+)[\s:.\-]+([A-Za-z].{2,})$',
        r'^Module\s+(\d+)[\s:.\-]+([A-Za-z].{2,})$',
    ]
    
    TOC_PATTERNS = [
        r'table\s+of\s+contents',
        r'contents',
        r'index',
    ]
    
    def __init__(self):
        self.chapter_regexes = [
            re.compile(pattern, re.MULTILINE | re.IGNORECASE)
            for pattern in self.CHAPTER_PATTERNS
        ]
        self.toc_regexes = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.TOC_PATTERNS
        ]
    
    async def detect_chapters(
        self,
        pages: List[Tuple[int, str]],
    ) -> List[DetectedChapter]:
        """
        Detect chapters from document pages.
        
        Args:
            pages: List of (page_number, page_text) tuples
            
        Returns:
            List of detected chapters
        """
        # Try TOC first
        toc_chapters = await self._find_toc_chapters(pages[:15])
        if toc_chapters:
            logger.info("chapters_detected_from_toc", count=len(toc_chapters))
            return toc_chapters
        
        # Fallback to pattern matching
        pattern_chapters = await self._find_pattern_chapters(pages)
        if pattern_chapters:
            logger.info("chapters_detected_from_patterns", count=len(pattern_chapters))
            return pattern_chapters
        
        # If no chapters found, treat entire document as one chapter
        logger.info("no_chapters_detected_using_single")
        return [DetectedChapter(
            chapter_number=1,
            title="Full Document",
            start_page=0,
            end_page=len(pages) - 1,
        )]
    
    async def _find_toc_chapters(
        self,
        pages: List[Tuple[int, str]],
    ) -> Optional[List[DetectedChapter]]:
        """Try to find chapters from Table of Contents."""
        for page_num, page_text in pages:
            # Check if this looks like a TOC page
            is_toc = any(
                pattern.search(page_text)
                for pattern in self.toc_regexes
            )
            
            if not is_toc:
                continue
            
            # Parse TOC entries
            chapters = []
            lines = page_text.split('\n')
            
            for line in lines:
                # Look for patterns like "Chapter 1: Introduction........5"
                toc_match = re.search(
                    r'(?:Chapter|Part|Section|Unit)?\s*(\d+)[.\s:]+([^.]+)\.+\s*(\d+)',
                    line,
                    re.IGNORECASE,
                )
                if toc_match:
                    chapter_num = int(toc_match.group(1))
                    title = toc_match.group(2).strip()
                    start_page = int(toc_match.group(3)) - 1  # 0-indexed
                    
                    chapters.append(DetectedChapter(
                        chapter_number=chapter_num,
                        title=title,
                        start_page=start_page,
                    ))
            
            if chapters:
                # Set end pages
                for i, chapter in enumerate(chapters[:-1]):
                    chapter.end_page = chapters[i + 1].start_page - 1
                
                return chapters
        
        return None
    
    async def _find_pattern_chapters(
        self,
        pages: List[Tuple[int, str]],
    ) -> List[DetectedChapter]:
        """Find chapters using pattern matching."""
        chapters = []
        
        for page_num, page_text in pages:
            # Check first few lines of each page for chapter headers
            first_lines = '\n'.join(page_text.split('\n')[:10])
            
            for pattern in self.chapter_regexes:
                match = pattern.search(first_lines)
                if match:
                    try:
                        chapter_num = int(match.group(1))
                        title = match.group(2).strip() if match.lastindex >= 2 else ""
                        
                        # Ensure title is meaningful (not just numbers or too short)
                        if not title or len(title) < 3 or title.isdigit():
                            title = f"Chapter {chapter_num}"
                        
                        # Avoid duplicates
                        if not any(c.chapter_number == chapter_num for c in chapters):
                            chapters.append(DetectedChapter(
                                chapter_number=chapter_num,
                                title=title,
                                start_page=page_num,
                            ))
                    except (ValueError, IndexError):
                        continue
                    break
        
        if not chapters:
            return []
        
        # Sort by chapter number
        chapters.sort(key=lambda c: c.chapter_number)
        
        # Set end pages
        for i, chapter in enumerate(chapters[:-1]):
            chapter.end_page = chapters[i + 1].start_page - 1
        
        # Set last chapter end page
        if chapters:
            chapters[-1].end_page = len(pages) - 1
        
        return chapters
    
    def estimate_duration(
        self,
        page_count: int,
        words_per_page: int = 300,
        reading_speed_wpm: int = 200,
    ) -> int:
        """
        Estimate reading/study duration in minutes.
        
        Args:
            page_count: Number of pages in the chapter
            words_per_page: Average words per page
            reading_speed_wpm: Reading speed in words per minute
            
        Returns:
            Estimated duration in minutes
        """
        total_words = page_count * words_per_page
        # Add 50% for study time (re-reading, thinking, notes)
        study_time = (total_words / reading_speed_wpm) * 1.5
        return max(5, int(study_time))
