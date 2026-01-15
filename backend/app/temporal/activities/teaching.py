"""Teaching activities for professor-driven instruction."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from temporalio import activity
from openai import AsyncOpenAI

from app.config import settings
from app.logs.logger import get_logger
from app.models.book import Book, BookChapter
from app.models.learning import DocumentChunk, ChapterSummary, LearningState

logger = get_logger(__name__)

# Database setup
_engine = None
_session_factory = None


def get_engine():
    """Get or create database engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def get_session_factory():
    """Get or create session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


async def get_db_session() -> AsyncSession:
    """Get a database session for activities."""
    factory = get_session_factory()
    return factory()


def get_openai_client(api_key: Optional[str] = None) -> AsyncOpenAI:
    """Get OpenAI client."""
    return AsyncOpenAI(api_key=api_key or settings.openai_api_key)


@activity.defn
async def get_chapter_topics(
    book_id: str,
    chapter_number: int,
) -> Dict[str, Any]:
    """
    Get the main topics/sections for a chapter.
    
    Args:
        book_id: The book's ID
        chapter_number: The chapter number
        
    Returns:
        Dict with list of topics
    """
    activity.logger.info(f"Getting topics for chapter {chapter_number} of book {book_id}")
    
    async with await get_db_session() as db:
        try:
            # Get chapter
            result = await db.execute(
                select(BookChapter)
                .where(BookChapter.book_id == UUID(book_id))
                .where(BookChapter.chapter_number == chapter_number)
            )
            chapter = result.scalar_one_or_none()
            
            if not chapter:
                return {"success": False, "topics": [], "error": "Chapter not found"}
            
            # Get unique section titles from chunks
            chunks_result = await db.execute(
                select(DocumentChunk.section_title)
                .where(DocumentChunk.chapter_id == chapter.id)
                .distinct()
            )
            section_titles = [r[0] for r in chunks_result.fetchall() if r[0]]
            
            # If no sections, create topics from key concepts
            if not section_titles and chapter.key_concepts:
                topics = list(chapter.key_concepts.keys())[:10]
            elif not section_titles:
                topics = [f"Section {i+1}" for i in range(5)]
            else:
                topics = section_titles[:10]
            
            return {
                "success": True,
                "topics": topics,
                "chapter_title": chapter.title,
                "chapter_number": chapter_number,
            }
            
        except Exception as e:
            logger.exception("get_chapter_topics_failed", error=str(e))
            return {"success": False, "topics": [], "error": str(e)}


@activity.defn
async def generate_chapter_introduction(
    user_id: str,
    book_id: str,
    chapter_number: int,
) -> Dict[str, Any]:
    """
    Generate an engaging introduction for a chapter.
    
    Args:
        user_id: The student's ID
        book_id: The book's ID
        chapter_number: The chapter number
        
    Returns:
        Dict with introduction text
    """
    activity.logger.info(f"Generating introduction for chapter {chapter_number}")
    
    async with await get_db_session() as db:
        try:
            # Get chapter info
            chapter_result = await db.execute(
                select(BookChapter)
                .where(BookChapter.book_id == UUID(book_id))
                .where(BookChapter.chapter_number == chapter_number)
            )
            chapter = chapter_result.scalar_one_or_none()
            
            if not chapter:
                return {"success": False, "introduction": "Let's begin this chapter."}
            
            # Get book title
            book_result = await db.execute(
                select(Book).where(Book.id == UUID(book_id))
            )
            book = book_result.scalar_one_or_none()
            book_title = book.title if book else "this book"
            
            # Get student's level
            state_result = await db.execute(
                select(LearningState)
                .where(LearningState.user_id == UUID(user_id))
                .where(LearningState.book_id == UUID(book_id))
            )
            state = state_result.scalar_one_or_none()
            level = state.professor_level if state else "intermediate"
            
            # Get first few chunks for context
            chunks_result = await db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.chapter_id == chapter.id)
                .order_by(DocumentChunk.chunk_index)
                .limit(3)
            )
            chunks = chunks_result.scalars().all()
            context = "\n".join([c.content[:500] for c in chunks])
            
            # Generate introduction using LLM
            client = get_openai_client()
            
            prompt = f"""You are Professor, an expert educator introducing a new chapter.

Book: {book_title}
Chapter {chapter_number}: {chapter.title or 'New Chapter'}
Student Level: {level}

Chapter Content Preview:
{context}

Generate an engaging 2-3 paragraph introduction that:
1. Welcomes the student to this chapter
2. Explains what they will learn and why it matters
3. Connects to real-world applications
4. Sets expectations for the journey ahead

Keep it warm, encouraging, and around 150-200 words."""

            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "You are Professor, a warm and knowledgeable educator."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=400,
                temperature=0.7,
            )
            
            introduction = response.choices[0].message.content
            
            return {
                "success": True,
                "introduction": f"📖 **Chapter {chapter_number}: {chapter.title or 'Beginning'}**\n\n{introduction}",
                "chapter_title": chapter.title,
            }
            
        except Exception as e:
            logger.exception("generate_introduction_failed", error=str(e))
            return {
                "success": False,
                "introduction": f"Welcome to Chapter {chapter_number}! Let's explore this topic together.",
            }


@activity.defn
async def generate_teaching_segment(
    user_id: str,
    book_id: str,
    chapter_number: int,
    topic: str,
    topics_already_taught: List[str],
) -> Dict[str, Any]:
    """
    Generate a teaching segment for a specific topic.
    
    Args:
        user_id: The student's ID
        book_id: The book's ID
        chapter_number: The chapter number
        topic: The topic to teach
        topics_already_taught: List of topics already covered
        
    Returns:
        Dict with teaching content
    """
    activity.logger.info(f"Generating teaching for topic: {topic}")
    
    async with await get_db_session() as db:
        try:
            # Get chapter
            chapter_result = await db.execute(
                select(BookChapter)
                .where(BookChapter.book_id == UUID(book_id))
                .where(BookChapter.chapter_number == chapter_number)
            )
            chapter = chapter_result.scalar_one_or_none()
            
            if not chapter:
                return {"success": False, "content": "Let me explain this concept..."}
            
            # Get relevant chunks for this topic
            chunks_result = await db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.chapter_id == chapter.id)
                .where(DocumentChunk.section_title == topic)
                .order_by(DocumentChunk.chunk_index)
                .limit(5)
            )
            chunks = chunks_result.scalars().all()
            
            if not chunks:
                # Fallback to any chunks from the chapter
                chunks_result = await db.execute(
                    select(DocumentChunk)
                    .where(DocumentChunk.chapter_id == chapter.id)
                    .order_by(DocumentChunk.chunk_index)
                    .limit(5)
                )
                chunks = chunks_result.scalars().all()
            
            context = "\n---\n".join([c.content for c in chunks])
            
            # Get student's level
            state_result = await db.execute(
                select(LearningState)
                .where(LearningState.user_id == UUID(user_id))
                .where(LearningState.book_id == UUID(book_id))
            )
            state = state_result.scalar_one_or_none()
            level = state.professor_level if state else "intermediate"
            
            # Generate teaching content
            client = get_openai_client()
            
            already_taught = ", ".join(topics_already_taught[-3:]) if topics_already_taught else "None yet"
            
            prompt = f"""You are Professor teaching a student about: {topic}

Student Level: {level}
Previously Covered: {already_taught}

Content from the book:
{context}

Generate a clear, engaging teaching segment that:
1. Explains the key concepts from this section
2. Uses examples and analogies appropriate for the student's level
3. Builds on what was previously covered (if relevant)
4. Is around 200-300 words
5. Ends naturally to invite questions or continue learning

Do NOT ask a question at the end - just teach the content."""

            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "You are Professor, an expert educator who explains complex topics clearly."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=500,
                temperature=0.7,
            )
            
            content = response.choices[0].message.content
            
            return {
                "success": True,
                "content": content,
                "topic": topic,
            }
            
        except Exception as e:
            logger.exception("generate_teaching_failed", error=str(e))
            return {
                "success": False,
                "content": f"Let me explain {topic}. This is an important concept that builds on our previous discussions.",
            }


@activity.defn
async def generate_comprehension_question(
    user_id: str,
    book_id: str,
    chapter_number: int,
    topic: str,
) -> Dict[str, Any]:
    """
    Generate a comprehension question about a topic.
    
    Args:
        user_id: The student's ID
        book_id: The book's ID
        chapter_number: The chapter number
        topic: The topic to ask about
        
    Returns:
        Dict with question and expected answer elements
    """
    activity.logger.info(f"Generating comprehension question for: {topic}")
    
    try:
        client = get_openai_client()
        
        prompt = f"""Generate a comprehension question about: {topic}

The question should:
1. Test understanding, not just memorization
2. Be open-ended enough for discussion
3. Be answerable in 1-3 sentences
4. Be appropriate for an intermediate student

Return ONLY the question, nothing else."""

        response = await client.chat.completions.create(
            model=settings.openai_model_mini,
            messages=[
                {"role": "system", "content": "You generate thoughtful comprehension questions."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=100,
            temperature=0.7,
        )
        
        question = response.choices[0].message.content.strip()
        
        return {
            "success": True,
            "question": question,
            "topic": topic,
        }
        
    except Exception as e:
        logger.exception("generate_question_failed", error=str(e))
        return {
            "success": False,
            "question": f"Can you explain {topic} in your own words?",
            "topic": topic,
        }


@activity.defn
async def evaluate_student_response(
    user_id: str,
    book_id: str,
    chapter_number: int,
    question: str,
    response: str,
) -> Dict[str, Any]:
    """
    Evaluate a student's response to a comprehension question.
    
    Args:
        user_id: The student's ID
        book_id: The book's ID
        chapter_number: The chapter number
        question: The question that was asked
        response: The student's response
        
    Returns:
        Dict with score and feedback
    """
    activity.logger.info(f"Evaluating student response to: {question[:50]}...")
    
    try:
        client = get_openai_client()
        
        prompt = f"""Evaluate this student response:

Question: {question}
Student's Answer: {response}

Provide:
1. A score from 0.0 to 1.0 (1.0 = excellent understanding)
2. Brief, encouraging feedback (2-3 sentences)
3. If the answer is incomplete, gently guide them toward the correct understanding

Format your response as:
SCORE: [number]
FEEDBACK: [your feedback]"""

        llm_response = await client.chat.completions.create(
            model=settings.openai_model_mini,
            messages=[
                {"role": "system", "content": "You are Professor evaluating student understanding. Be encouraging but honest."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=200,
            temperature=0.5,
        )
        
        result = llm_response.choices[0].message.content
        
        # Parse response
        score = 0.7  # default
        feedback = "Good effort! Let's continue."
        
        for line in result.split("\n"):
            if line.startswith("SCORE:"):
                try:
                    score = float(line.replace("SCORE:", "").strip())
                except ValueError:
                    pass
            elif line.startswith("FEEDBACK:"):
                feedback = line.replace("FEEDBACK:", "").strip()
        
        return {
            "success": True,
            "score": score,
            "feedback": feedback,
            "question": question,
            "response": response,
        }
        
    except Exception as e:
        logger.exception("evaluate_response_failed", error=str(e))
        return {
            "success": False,
            "score": 0.5,
            "feedback": "Thank you for your answer! Let's continue with our lesson.",
        }


@activity.defn
async def generate_chapter_summary(
    user_id: str,
    book_id: str,
    chapter_number: int,
) -> Dict[str, Any]:
    """
    Generate a comprehensive summary of a completed chapter.
    
    Args:
        user_id: The student's ID
        book_id: The book's ID
        chapter_number: The chapter number
        
    Returns:
        Dict with summary text
    """
    activity.logger.info(f"Generating summary for chapter {chapter_number}")
    
    async with await get_db_session() as db:
        try:
            # Get chapter
            chapter_result = await db.execute(
                select(BookChapter)
                .where(BookChapter.book_id == UUID(book_id))
                .where(BookChapter.chapter_number == chapter_number)
            )
            chapter = chapter_result.scalar_one_or_none()
            
            if not chapter:
                return {"success": False, "summary": "Great work completing this chapter!"}
            
            # Get key chunks for summary
            chunks_result = await db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.chapter_id == chapter.id)
                .order_by(DocumentChunk.chunk_index)
                .limit(10)
            )
            chunks = chunks_result.scalars().all()
            context = "\n---\n".join([c.content[:400] for c in chunks])
            
            # Generate summary
            client = get_openai_client()
            
            prompt = f"""Summarize Chapter {chapter_number}: {chapter.title or 'This Chapter'}

Chapter content:
{context}

Generate a summary that:
1. Lists 3-5 key concepts learned
2. Explains how they connect to each other
3. Notes any practical applications
4. Is around 150-200 words

Format with bullet points for key concepts."""

            response = await client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": "You summarize educational content clearly and concisely."},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=400,
                temperature=0.5,
            )
            
            summary = response.choices[0].message.content
            
            # Store summary in database
            chapter_summary = ChapterSummary(
                user_id=UUID(user_id),
                book_id=UUID(book_id),
                chapter_id=chapter.id,
                summary_type="completion",
                summary_text=summary,
                created_at=datetime.utcnow(),
            )
            db.add(chapter_summary)
            await db.commit()
            
            return {
                "success": True,
                "summary": summary,
                "chapter_title": chapter.title,
            }
            
        except Exception as e:
            logger.exception("generate_summary_failed", error=str(e))
            return {
                "success": False,
                "summary": "You've completed this chapter! The key concepts will help you in the upcoming chapters.",
            }
