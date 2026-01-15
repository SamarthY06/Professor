"""Security guardrails for input validation."""

import re
from typing import List, Optional, Tuple

from app.logs.logger import get_logger

logger = get_logger(__name__)


class GuardrailsChecker:
    """
    Security guardrails for validating user input.
    Prevents prompt injection, scope leakage, and unauthorized access.
    """
    
    # Patterns that indicate prompt injection attempts
    BLOCKED_PATTERNS = [
        r"ignore\s+previous\s+instructions",
        r"forget\s+everything",
        r"disregard\s+.*instructions",
        r"system\s*:\s*",
        r"you\s+are\s+now",
        r"pretend\s+to\s+be",
        r"act\s+as\s+if",
        r"new\s+instructions:",
        r"override\s+.*mode",
        r"jailbreak",
        r"ignore\s+.*guidelines",
        r"bypass\s+.*restrictions",
    ]
    
    # Patterns for detecting chapter references
    CHAPTER_PATTERNS = [
        r"chapter\s+(\d+)",
        r"ch\.?\s*(\d+)",
        r"section\s+(\d+)",
        r"part\s+(\d+)",
    ]
    
    def __init__(self):
        self.blocked_regexes = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.BLOCKED_PATTERNS
        ]
        self.chapter_regexes = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.CHAPTER_PATTERNS
        ]
    
    def check_prompt_injection(self, text: str) -> Tuple[bool, Optional[str]]:
        """
        Check if text contains prompt injection attempts.
        
        Returns:
            Tuple of (is_safe, detected_pattern)
        """
        for pattern in self.blocked_regexes:
            match = pattern.search(text)
            if match:
                logger.warning(
                    "prompt_injection_detected",
                    pattern=pattern.pattern,
                    matched_text=match.group(),
                )
                return False, pattern.pattern
        
        return True, None
    
    def extract_chapter_references(self, text: str) -> List[int]:
        """
        Extract chapter numbers referenced in the text.
        
        Returns:
            List of chapter numbers found
        """
        chapters = []
        for pattern in self.chapter_regexes:
            matches = pattern.findall(text)
            chapters.extend(int(m) for m in matches)
        
        return list(set(chapters))
    
    def check_future_chapter_access(
        self,
        text: str,
        current_chapter: int,
        total_chapters: int,
    ) -> Tuple[bool, Optional[int]]:
        """
        Check if user is trying to access future chapters.
        
        Returns:
            Tuple of (is_allowed, attempted_chapter)
        """
        referenced_chapters = self.extract_chapter_references(text)
        
        for chapter in referenced_chapters:
            if chapter > current_chapter and chapter <= total_chapters:
                logger.warning(
                    "future_chapter_access_attempt",
                    current_chapter=current_chapter,
                    attempted_chapter=chapter,
                )
                return False, chapter
        
        return True, None
    
    def check_off_topic(
        self,
        text: str,
        allowed_topics: List[str],
        threshold: float = 0.3,
    ) -> Tuple[bool, float]:
        """
        Check if text is related to allowed topics.
        This is a simple keyword-based check; production would use embeddings.
        
        Returns:
            Tuple of (is_on_topic, relevance_score)
        """
        text_lower = text.lower()
        
        # Count topic keywords present
        matches = sum(1 for topic in allowed_topics if topic.lower() in text_lower)
        
        if not allowed_topics:
            return True, 1.0
        
        relevance = matches / len(allowed_topics)
        
        return relevance >= threshold, relevance
    
    def sanitize_input(self, text: str) -> str:
        """
        Sanitize user input by removing potentially harmful content.
        
        Returns:
            Sanitized text
        """
        # Remove any hidden characters
        sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
        
        # Normalize whitespace
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        
        # Limit length
        max_length = 10000
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        
        return sanitized
    
    def validate_input(
        self,
        text: str,
        current_chapter: int = 1,
        total_chapters: int = 1,
        strict_mode: bool = True,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Comprehensive input validation.
        
        Returns:
            Tuple of (is_valid, sanitized_text, error_message)
        """
        # Sanitize first
        sanitized = self.sanitize_input(text)
        
        if not sanitized:
            return False, "", "Empty input"
        
        # Check prompt injection
        is_safe, pattern = self.check_prompt_injection(sanitized)
        if not is_safe:
            return False, sanitized, "Invalid input detected"
        
        # Check future chapter access in strict mode
        if strict_mode:
            is_allowed, attempted = self.check_future_chapter_access(
                sanitized, current_chapter, total_chapters
            )
            if not is_allowed:
                return False, sanitized, f"Let's focus on Chapter {current_chapter} first"
        
        return True, sanitized, None


# Global instance
guardrails = GuardrailsChecker()
