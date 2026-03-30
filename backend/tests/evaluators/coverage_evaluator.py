"""Coverage evaluator for teaching quality.

Evaluates whether teaching messages adequately cover all concepts
from a chapter checklist, with optional RAG overlap scoring.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI

from tests.fixtures.modern_robotics import (
    CHAPTER_2_CHECKLIST,
    CHAPTER_3_CHECKLIST,
    CHAPTER_4_CHECKLIST,
)

# Map chapter number to checklist
CHAPTER_CHECKLISTS: Dict[int, dict] = {
    2: CHAPTER_2_CHECKLIST,
    3: CHAPTER_3_CHECKLIST,
    4: CHAPTER_4_CHECKLIST,
}


@dataclass
class CoverageResult:
    """Result for a single concept's coverage evaluation."""

    concept_name: str
    llm_verified: bool
    formula_covered: bool
    evidence_quote: str
    missing_elements: List[str]
    rag_overlap_score: Optional[float] = None


@dataclass
class CoverageReport:
    """Report summarizing chapter coverage evaluation."""

    chapter: int
    total_concepts: int
    concepts_covered: int
    coverage_percentage: float
    formulas_total: int
    formulas_covered: int
    concept_results: List[CoverageResult]
    passed: bool


async def evaluate_chapter_coverage(
    book_id: str,
    chapter_number: int,
    teaching_messages: List[dict],
    checklist: Optional[dict] = None,
    api_key: Optional[str] = None,
    rag_client: Optional[Any] = None,
) -> CoverageReport:
    """
    Evaluate whether teaching messages adequately cover all concepts in the checklist.

    Args:
        book_id: Book/document identifier.
        chapter_number: Chapter being evaluated.
        teaching_messages: List of messages with 'role' and 'content' (e.g. user/assistant).
        checklist: Chapter checklist with 'concepts' array. Uses default if None.
        api_key: OpenAI API key for gpt-4.1-mini. Required if not in env.
        rag_client: Optional RAGClient for overlap scoring.

    Returns:
        CoverageReport with concept-level results and pass/fail.
    """
    checklist = checklist or CHAPTER_CHECKLISTS.get(
        chapter_number,
        {"concepts": []},
    )
    concepts = checklist.get("concepts", [])

    if not concepts:
        return CoverageReport(
            chapter=chapter_number,
            total_concepts=0,
            concepts_covered=0,
            coverage_percentage=0.0,
            formulas_total=0,
            formulas_covered=0,
            concept_results=[],
            passed=True,
        )

    # Concatenate teaching messages into a single transcript
    transcript_parts: List[str] = []
    for msg in teaching_messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str):
            transcript_parts.append(f"[{role}]: {content}")
        else:
            transcript_parts.append(f"[{role}]: {str(content)}")
    transcript = "\n\n".join(transcript_parts)

    client = AsyncOpenAI(api_key=api_key)

    concept_results: List[CoverageResult] = []
    formulas_total = sum(1 for c in concepts if c.get("formula"))
    formulas_covered = 0

    for concept in concepts:
        name = concept.get("name", "")
        ctype = concept.get("type", "concept")
        formula = concept.get("formula")
        must_mention = concept.get("must_mention", [])

        prompt = f"""You are evaluating whether a teaching transcript adequately covered a specific concept.

TRANSCRIPT:
---
{transcript}
---

CONCEPT: {name}
TYPE: {ctype}
"""
        if formula:
            prompt += f"KEY FORMULA (must be taught or explained): {formula}\n"
        if must_mention:
            prompt += f"SHOULD MENTION (at least some): {must_mention}\n"

        prompt += """
Respond with a JSON object (no markdown) with:
- "covered": true/false - was this concept adequately taught?
- "formula_covered": true/false - was the formula (if any) taught or derived?
- "evidence": a short quote from the transcript proving coverage (or "none")
- "missing": list of missing elements (key terms, formula, etc.)
"""

        response = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=400,
        )
        raw = response.choices[0].message.content.strip()

        # Parse JSON from response (handle markdown code blocks)
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"covered": False, "formula_covered": False, "evidence": "none", "missing": ["Parse error"]}

        llm_verified = data.get("covered", False)
        formula_covered = data.get("formula_covered", False) if formula else True
        evidence_quote = data.get("evidence", "none") or "none"
        missing_elements = data.get("missing", [])
        if not isinstance(missing_elements, list):
            missing_elements = [str(missing_elements)]

        if formula and formula_covered:
            formulas_covered += 1

        # Optional: RAG overlap score if rag_client provided
        rag_overlap_score: Optional[float] = None
        if rag_client and hasattr(rag_client, "search"):
            try:
                search_resp = await rag_client.search(
                    query=f"{name} {formula or ''}",
                    document_id=book_id,
                    limit=3,
                )
                if search_resp.results:
                    rag_overlap_score = sum(r.score for r in search_resp.results[:3]) / 3
            except Exception:
                pass

        concept_results.append(
            CoverageResult(
                concept_name=name,
                llm_verified=llm_verified,
                formula_covered=formula_covered,
                evidence_quote=evidence_quote,
                missing_elements=missing_elements,
                rag_overlap_score=rag_overlap_score,
            )
        )

    concepts_covered = sum(1 for r in concept_results if r.llm_verified)
    coverage_percentage = (concepts_covered / len(concepts)) * 100.0
    passed = concepts_covered == len(concepts) and (
        formulas_total == 0 or formulas_covered == formulas_total
    )

    return CoverageReport(
        chapter=chapter_number,
        total_concepts=len(concepts),
        concepts_covered=concepts_covered,
        coverage_percentage=coverage_percentage,
        formulas_total=formulas_total,
        formulas_covered=formulas_covered,
        concept_results=concept_results,
        passed=passed,
    )
