"""Table of Contents schemas."""
from typing import Optional

from pydantic import BaseModel


class TOCSection(BaseModel):
    """Section within a chapter."""

    title: str
    start_page: int


class TOCChapter(BaseModel):
    """Chapter in the table of contents."""

    title: str
    start_page: int
    end_page: Optional[int] = None
    sections: list[TOCSection] = []


class TOCResponse(BaseModel):
    """Parsed table of contents."""

    chapters: list[TOCChapter]
