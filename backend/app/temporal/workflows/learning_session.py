"""Learning Session Workflow - Teacher-driven chapter-by-chapter instruction.

This workflow implements the core philosophy: Professor drives the conversation.
The student responds to what the professor teaches, not the other way around.

Flow:
1. Student starts a learning session (triggers workflow)
2. Professor introduces the chapter
3. Professor teaches concept by concept
4. Professor asks comprehension questions periodically
5. Student responds
6. Professor evaluates and adjusts teaching
7. After chapter completion, generates summary
8. Triggers chapter quiz
9. On quiz pass, unlocks next chapter
10. Repeats until all chapters complete
"""

from datetime import timedelta
from typing import Optional, List
from dataclasses import dataclass

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from app.temporal.activities.teaching import (
        generate_chapter_introduction,
        generate_teaching_segment,
        generate_comprehension_question,
        evaluate_student_response,
        generate_chapter_summary,
        get_chapter_topics,
    )
    from app.temporal.activities.learning import (
        unlock_next_chapter,
        update_motivation_score,
        get_user_learning_state,
    )
    from app.temporal.activities.quiz import generate_chapter_quiz
    from app.temporal.activities.notifications import send_push_notification
    from app.temporal.activities.session import (
        send_professor_message,
        get_pending_student_response,
        save_session_state,
    )


@dataclass
class SessionState:
    """State tracked within the workflow."""
    current_topic_index: int = 0
    topics_taught: List[str] = None
    messages_since_check: int = 0
    comprehension_scores: List[float] = None
    chapter_started: bool = False
    
    def __post_init__(self):
        if self.topics_taught is None:
            self.topics_taught = []
        if self.comprehension_scores is None:
            self.comprehension_scores = []


@workflow.defn
class LearningSessionWorkflow:
    """
    Main workflow for teacher-driven learning sessions.
    
    The professor leads the student through each chapter:
    1. Introduces the chapter
    2. Teaches topics sequentially
    3. Checks understanding periodically
    4. Generates summary and quiz at chapter end
    5. Moves to next chapter on quiz pass
    """
    
    def __init__(self):
        self._student_response: Optional[str] = None
        self._has_response = False
        self._session_ended = False
        self._quiz_completed = False
        self._quiz_passed = False
        self._pause_requested = False
        
    @workflow.run
    async def run(
        self,
        user_id: str,
        book_id: str,
        session_id: str,
        start_chapter: int = 1,
        target_chapters: int = 5,
    ) -> dict:
        """
        Execute the learning session workflow.
        
        Args:
            user_id: The student's user ID
            book_id: The book being studied
            session_id: Unique session identifier
            start_chapter: Chapter to start from (for resuming)
            target_chapters: Number of chapters to cover (default 5)
            
        Returns:
            Dict with session results
        """
        workflow.logger.info(
            f"Starting learning session for user {user_id}, "
            f"book {book_id}, starting chapter {start_chapter}"
        )
        
        retry_policy = RetryPolicy(
            maximum_attempts=3,
            initial_interval=timedelta(seconds=5),
            maximum_interval=timedelta(minutes=1),
        )
        
        current_chapter = start_chapter
        chapters_completed = []
        
        # Main chapter loop
        while current_chapter <= start_chapter + target_chapters - 1:
            if self._session_ended:
                break
                
            # Handle pause requests
            if self._pause_requested:
                await self._save_state(
                    user_id, book_id, session_id, current_chapter, retry_policy
                )
                return {
                    "status": "paused",
                    "user_id": user_id,
                    "book_id": book_id,
                    "current_chapter": current_chapter,
                    "chapters_completed": chapters_completed,
                }
            
            # Teach the chapter
            chapter_result = await self._teach_chapter(
                user_id=user_id,
                book_id=book_id,
                session_id=session_id,
                chapter_number=current_chapter,
                retry_policy=retry_policy,
            )
            
            if chapter_result.get("status") == "completed":
                chapters_completed.append(current_chapter)
                
                # Generate chapter summary
                summary = await workflow.execute_activity(
                    generate_chapter_summary,
                    args=[user_id, book_id, current_chapter],
                    start_to_close_timeout=timedelta(minutes=5),
                    retry_policy=retry_policy,
                )
                
                # Send summary to student
                await workflow.execute_activity(
                    send_professor_message,
                    args=[
                        session_id,
                        f"📚 **Chapter {current_chapter} Complete!**\n\n{summary.get('summary', 'Great work on this chapter!')}\n\nNow let's test your understanding with a short quiz.",
                        "summary",
                    ],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=retry_policy,
                )
                
                # Generate and run quiz
                quiz_result = await self._run_chapter_quiz(
                    user_id=user_id,
                    book_id=book_id,
                    session_id=session_id,
                    chapter_number=current_chapter,
                    retry_policy=retry_policy,
                )
                
                if quiz_result.get("passed"):
                    # Unlock next chapter
                    await workflow.execute_activity(
                        unlock_next_chapter,
                        args=[user_id, book_id, str(current_chapter)],
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=retry_policy,
                    )
                    
                    current_chapter += 1
                    
                    # Congratulate and transition
                    if current_chapter <= start_chapter + target_chapters - 1:
                        await workflow.execute_activity(
                            send_professor_message,
                            args=[
                                session_id,
                                f"🎉 Excellent! You've mastered Chapter {current_chapter - 1}!\n\nLet's move on to Chapter {current_chapter}.",
                                "transition",
                            ],
                            start_to_close_timeout=timedelta(minutes=2),
                            retry_policy=retry_policy,
                        )
                else:
                    # Failed quiz - review and retry
                    await workflow.execute_activity(
                        send_professor_message,
                        args=[
                            session_id,
                            f"Let's review some concepts from Chapter {current_chapter} before moving on. I'll help you strengthen your understanding.",
                            "review",
                        ],
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=retry_policy,
                    )
                    # Stay on same chapter for review
            
            elif chapter_result.get("status") == "paused":
                return chapter_result
        
        # All chapters complete!
        await workflow.execute_activity(
            send_professor_message,
            args=[
                session_id,
                f"🎓 **Congratulations!** You've completed all {len(chapters_completed)} chapters!\n\nYou've demonstrated excellent understanding of the material. Keep up the great work!",
                "completion",
            ],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )
        
        return {
            "status": "completed",
            "user_id": user_id,
            "book_id": book_id,
            "chapters_completed": chapters_completed,
            "total_chapters": len(chapters_completed),
        }
    
    async def _teach_chapter(
        self,
        user_id: str,
        book_id: str,
        session_id: str,
        chapter_number: int,
        retry_policy: RetryPolicy,
    ) -> dict:
        """Teach a single chapter, topic by topic."""
        
        workflow.logger.info(f"Teaching chapter {chapter_number}")
        
        # Get chapter topics
        topics_result = await workflow.execute_activity(
            get_chapter_topics,
            args=[book_id, chapter_number],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )
        topics = topics_result.get("topics", [])
        
        if not topics:
            # No explicit topics - use general teaching approach
            topics = [f"Chapter {chapter_number} content"]
        
        # Send chapter introduction
        intro = await workflow.execute_activity(
            generate_chapter_introduction,
            args=[user_id, book_id, chapter_number],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )
        
        await workflow.execute_activity(
            send_professor_message,
            args=[session_id, intro.get("introduction", "Let's begin this chapter."), "introduction"],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )
        
        # Wait for student acknowledgment or timeout
        await self._wait_for_response_or_continue(
            session_id=session_id,
            timeout_seconds=30,  # Short timeout for ack
            retry_policy=retry_policy,
        )
        
        # Teach each topic
        state = SessionState()
        
        for topic_index, topic in enumerate(topics):
            if self._session_ended or self._pause_requested:
                return {"status": "paused", "chapter": chapter_number, "topic_index": topic_index}
            
            # Generate teaching content for this topic
            teaching = await workflow.execute_activity(
                generate_teaching_segment,
                args=[user_id, book_id, chapter_number, topic, state.topics_taught],
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=retry_policy,
            )
            
            # Send teaching content
            await workflow.execute_activity(
                send_professor_message,
                args=[session_id, teaching.get("content", ""), "teaching"],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            
            state.messages_since_check += 1
            state.topics_taught.append(topic)
            
            # Check comprehension every 2-3 topics
            if state.messages_since_check >= 2:
                comprehension = await self._check_comprehension(
                    user_id=user_id,
                    book_id=book_id,
                    session_id=session_id,
                    chapter_number=chapter_number,
                    topic=topic,
                    retry_policy=retry_policy,
                )
                state.comprehension_scores.append(comprehension.get("score", 0.5))
                state.messages_since_check = 0
                
                # Adjust teaching based on comprehension
                if comprehension.get("score", 0.5) < 0.6:
                    # Re-explain the concept
                    await workflow.execute_activity(
                        send_professor_message,
                        args=[
                            session_id,
                            f"Let me explain {topic} in a different way to make it clearer...",
                            "reteach",
                        ],
                        start_to_close_timeout=timedelta(minutes=2),
                        retry_policy=retry_policy,
                    )
        
        return {
            "status": "completed",
            "chapter": chapter_number,
            "topics_covered": state.topics_taught,
            "avg_comprehension": sum(state.comprehension_scores) / len(state.comprehension_scores) if state.comprehension_scores else 1.0,
        }
    
    async def _check_comprehension(
        self,
        user_id: str,
        book_id: str,
        session_id: str,
        chapter_number: int,
        topic: str,
        retry_policy: RetryPolicy,
    ) -> dict:
        """Ask a comprehension question and evaluate the response."""
        
        # Generate question
        question = await workflow.execute_activity(
            generate_comprehension_question,
            args=[user_id, book_id, chapter_number, topic],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=retry_policy,
        )
        
        # Send question to student
        await workflow.execute_activity(
            send_professor_message,
            args=[
                session_id,
                f"🤔 **Quick check:** {question.get('question', 'Can you explain what you just learned?')}",
                "question",
            ],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )
        
        # Wait for student response
        response = await self._wait_for_response(
            session_id=session_id,
            timeout_seconds=300,  # 5 minutes to answer
            retry_policy=retry_policy,
        )
        
        if not response:
            # No response - send gentle nudge
            await workflow.execute_activity(
                send_professor_message,
                args=[
                    session_id,
                    "Take your time! Would you like me to give you a hint?",
                    "nudge",
                ],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            
            # Wait again
            response = await self._wait_for_response(
                session_id=session_id,
                timeout_seconds=180,
                retry_policy=retry_policy,
            )
        
        if not response:
            return {"score": 0.5, "feedback": "No response received"}
        
        # Evaluate response
        evaluation = await workflow.execute_activity(
            evaluate_student_response,
            args=[user_id, book_id, chapter_number, question.get("question", ""), response],
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=retry_policy,
        )
        
        # Send feedback
        await workflow.execute_activity(
            send_professor_message,
            args=[session_id, evaluation.get("feedback", "Thank you for your answer!"), "feedback"],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )
        
        return evaluation
    
    async def _run_chapter_quiz(
        self,
        user_id: str,
        book_id: str,
        session_id: str,
        chapter_number: int,
        retry_policy: RetryPolicy,
    ) -> dict:
        """Run the end-of-chapter quiz."""
        
        # Generate quiz
        quiz = await workflow.execute_activity(
            generate_chapter_quiz,
            args=[book_id, str(chapter_number), user_id],
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=retry_policy,
        )
        
        quiz_questions = quiz.get("questions", [])
        if not quiz_questions:
            return {"passed": True, "score": 1.0}  # Skip if no quiz
        
        correct_count = 0
        total_questions = len(quiz_questions)
        
        for i, q in enumerate(quiz_questions, 1):
            # Send question
            await workflow.execute_activity(
                send_professor_message,
                args=[
                    session_id,
                    f"📝 **Quiz Question {i}/{total_questions}:**\n\n{q.get('question', '')}",
                    "quiz_question",
                ],
                start_to_close_timeout=timedelta(minutes=2),
                retry_policy=retry_policy,
            )
            
            # Wait for answer
            response = await self._wait_for_response(
                session_id=session_id,
                timeout_seconds=180,
                retry_policy=retry_policy,
            )
            
            if response:
                # Check answer (simplified - real implementation would use AI)
                correct_answer = q.get("correct_answer", "")
                is_correct = response.lower().strip() in correct_answer.lower()
                if is_correct:
                    correct_count += 1
        
        score = correct_count / total_questions if total_questions > 0 else 0
        passed = score >= 0.7  # 70% passing threshold
        
        return {
            "passed": passed,
            "score": score,
            "correct": correct_count,
            "total": total_questions,
        }
    
    async def _wait_for_response(
        self,
        session_id: str,
        timeout_seconds: int,
        retry_policy: RetryPolicy,
    ) -> Optional[str]:
        """Wait for a student response."""
        
        self._has_response = False
        self._student_response = None
        
        try:
            await workflow.wait_condition(
                lambda: self._has_response or self._session_ended,
                timeout=timedelta(seconds=timeout_seconds),
            )
            
            if self._has_response:
                response = self._student_response
                self._has_response = False
                self._student_response = None
                return response
            
            return None
            
        except Exception:
            # Timeout
            return None
    
    async def _wait_for_response_or_continue(
        self,
        session_id: str,
        timeout_seconds: int,
        retry_policy: RetryPolicy,
    ) -> Optional[str]:
        """Wait briefly for response, but continue if none."""
        return await self._wait_for_response(session_id, timeout_seconds, retry_policy)
    
    async def _save_state(
        self,
        user_id: str,
        book_id: str,
        session_id: str,
        current_chapter: int,
        retry_policy: RetryPolicy,
    ):
        """Save current session state for later resume."""
        await workflow.execute_activity(
            save_session_state,
            args=[user_id, book_id, session_id, current_chapter],
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry_policy,
        )
    
    # Signals for external events
    @workflow.signal
    def student_response(self, response: str):
        """Receive a response from the student."""
        self._student_response = response
        self._has_response = True
    
    @workflow.signal
    def pause_session(self):
        """Pause the learning session."""
        self._pause_requested = True
    
    @workflow.signal
    def end_session(self):
        """End the learning session."""
        self._session_ended = True
    
    @workflow.signal
    def quiz_completed(self, passed: bool):
        """Signal that quiz has been completed externally."""
        self._quiz_completed = True
        self._quiz_passed = passed
