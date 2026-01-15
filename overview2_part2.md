# Professor - Redesigned System Architecture (Part 2)

## Table of Contents - Part 2

11. [Quiz Logic - Code Architecture](#11-quiz-logic---code-architecture)
12. [Background Summarization - Code Architecture](#12-background-summarization---code-architecture)
13. [Progress Tracking - Code Architecture](#13-progress-tracking---code-architecture)
14. [Motivation and Inactivity - Code Architecture](#14-motivation-and-inactivity---code-architecture)
15. [Session Management - Code Architecture](#15-session-management---code-architecture)
16. [Notes Feature - Code Architecture](#16-notes-feature---code-architecture)
17. [Configuration System - All Settings](#17-configuration-system---all-settings)
18. [Database Models - Complete Schema](#18-database-models---complete-schema)
19. [API Endpoints - Complete Reference](#19-api-endpoints---complete-reference)
20. [Error Handling Strategy](#20-error-handling-strategy)

See **overview2_part1.md** for sections 1-10.

---

## 11. Quiz Logic - Code Architecture

### Files Involved
- `backend/app/agents/quiz.py` - QuizAgent
- `backend/app/models/quiz.py` - Quiz models

### QuizAgent Overview

QuizAgent takes control when user agrees to take a quiz. It runs a loop until all questions are answered, then returns control.

### Quiz Flow

**Entry Point:**
- TeacherAgent asks "Ready for a quiz?"
- User says yes
- TeacherAgent signals [START_QUIZ]
- Phase changes to "quiz"
- QuizAgent takes over

**QuizAgent.start_quiz(state) Logic:**

1. Get chapter content from retrieved_chunks (already in state from teaching)
2. Determine difficulty distribution based on comprehension_score:
   - High (≥0.8): 60% hard, 30% medium, 10% easy
   - Average (0.6-0.8): 30% hard, 50% medium, 20% easy
   - Low (<0.6): 20% hard, 40% medium, 40% easy

3. Determine question type distribution:
   - MCQ: 50%
   - True/False: 25%
   - Short Answer: 25%

4. Build generation prompt:
   - Include chapter content
   - Specify number of questions (from config)
   - Specify difficulty and type distribution
   - Request JSON array response

5. Call OpenAI GPT-4 to generate questions
6. Parse JSON response into quiz_questions array
7. Set quiz_current_index = 0
8. Return first question formatted for display

**Question Structure:**
```
{
  "question": "Question text",
  "type": "mcq" | "true_false" | "short_answer",
  "difficulty": "easy" | "medium" | "hard",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."],  // MCQ only
  "correct_answer": "The answer",
  "explanation": "Why this is correct",
  "topic": "Topic being tested"
}
```

### QuizAgent.process_answer(state, user_answer) Logic

**Step 1: Get Current Question**
- question = quiz_questions[quiz_current_index]

**Step 2: Evaluate Answer**
1. Build evaluation prompt:
   - Include question text
   - Include correct answer
   - Include explanation
   - Include user's answer
   - Instructions: Be fair, partial credit for short answers

2. Call OpenAI GPT-4-mini (faster for evaluation)
3. Parse response: {correct: bool, score: 0-1, feedback: string}

**Step 3: Update State**
1. Append score to quiz_scores array
2. Increment quiz_current_index

**Step 4: Check Completion**
- If quiz_current_index >= questions_per_quiz: Quiz complete
- Else: More questions remaining

**Step 5: Return Result**
- If more questions:
  - Return feedback + next question
  - Stay in quiz phase
- If complete:
  - Calculate final_score = average(quiz_scores)
  - Determine passed = final_score >= 0.7
  - Return completion message with score

### Quiz Completion Handling

**If Passed (≥70%):**
1. Set quiz_passed = True
2. Generate congratulations message
3. Update comprehension_score: blend 30% old + 70% quiz score
4. Update motivation_score with "quiz_passed" event (+0.15)
5. Log QuizAttempt with passed=True
6. Transition to chapter_transition phase

**If Failed (<70%):**
1. Set quiz_passed = False
2. Generate message: "You scored X%. Would you like to retry or move on to the next chapter?"
3. Update motivation_score with "quiz_failed" event (-0.1)
4. Wait for user response

**User Response to Failure:**

If user wants retry ("retry", "try again", "yes"):
1. Clear quiz_questions
2. Reset quiz_current_index = 0
3. Clear quiz_scores
4. Call start_quiz() again (regenerates different questions)
5. Stay in quiz phase

If user wants to proceed ("move on", "next chapter", "no"):
1. Log QuizAttempt with passed=False
2. Generate message: "No problem! Let's continue. You can always review later."
3. Transition to chapter_transition phase

### QuizAgent Orchestrator Prompt

```
You are the Quiz Master for Professor.

You are conducting a quiz on Chapter {current_chapter}: {chapter_title}.

Current Question ({quiz_current_index + 1} of {questions_per_quiz}):
{current_question}

Student's Answer: {user_answer}

Correct Answer: {correct_answer}
Explanation: {explanation}

Evaluate the student's answer:
1. Determine if it's correct (for MCQ/True-False: exact match; for short answer: semantic match)
2. Provide brief, encouraging feedback
3. If incorrect, explain the right answer without being discouraging

Respond with:
- Whether they got it right
- Brief feedback
- The next question (if not complete)

Format your evaluation as:
[EVALUATION: correct/incorrect, score: 0-1]
{Your feedback message}
{Next question if applicable}
```

---

## 12. Background Summarization - Code Architecture

### Files Involved
- `backend/app/services/summarization.py` - Summarization service
- `backend/app/models/learning.py` - ChapterSummary model

### Purpose

After a chapter is completed, an async background job summarizes what was covered. This summary is stored in the database and made available to TeacherAgent when starting the next chapter.

### When Triggered

Chapter transition triggers summarization:
1. User completes quiz (pass or proceed after fail)
2. Phase changes to chapter_transition
3. chapter_transition_node fires background summarization task
4. Task runs async (fire-and-forget)
5. User doesn't wait for it

### Summarization Logic

**summarize_chapter(user_id, book_id, chapter_number, session_id) Logic:**

**Step 1: Gather Teaching History**
1. Query ChatMessages for this session and chapter
2. Filter: chapter_at_time = chapter_number
3. Get all assistant messages (what TeacherAgent taught)
4. Get all user messages (questions asked)

**Step 2: Build Summarization Prompt**
```
You are summarizing a teaching session for Chapter {chapter_number}: {chapter_title}.

Here is the conversation between Professor and the student:
{formatted_conversation}

Create a concise summary that includes:
1. Key topics that were explained
2. Important concepts covered
3. Questions the student asked and key clarifications made
4. Any areas where the student seemed to struggle

This summary will be used by Professor when teaching the next chapter to maintain continuity.

Keep it under 500 words.
```

**Step 3: Generate Summary**
1. Call OpenAI GPT-4-mini (sufficient for summarization)
2. Get summary text

**Step 4: Store Summary**
1. Create or update ChapterSummary record:
   - user_id
   - book_id
   - chapter_number
   - summary_text
   - topics_covered (extracted list)
   - created_at

**Step 5: Log Completion**
- Log that summarization completed
- No user notification needed

### How TeacherAgent Uses Summary

When TeacherAgent starts a new chapter:

1. Retrieval tool queries ChapterSummary for previous chapter
2. If summary exists:
   - Include in context as "Previous Chapter Summary"
   - TeacherAgent can reference: "Building on what we covered last time..."
3. If no summary (first chapter or summarization failed):
   - TeacherAgent starts fresh
   - No error, just no continuity context

### Summary Storage

**chapter_summaries table:**
- id: UUID
- user_id: FK to users
- book_id: FK to books
- chapter_number: Integer
- summary_text: Text
- topics_covered: Array of strings
- created_at: DateTime
- Unique constraint: (user_id, book_id, chapter_number)

---

## 13. Progress Tracking - Code Architecture

### Files Involved
- `backend/app/services/progress.py` - Progress utility functions
- `backend/app/models/learning.py` - LearningState, ProgressSnapshot models

### Design: Utility Functions, Not Agent

Progress tracking is handled by simple Python functions. No LLM calls, no agent overhead.

### Progress Utility Functions

**File: backend/app/services/progress.py**

**update_study_time(learning_state, minutes=2):**
```
learning_state.total_study_time_minutes += minutes
```
Called after each teaching interaction. Default 2 minutes per message exchange.

**update_attention_score(learning_state, correct: bool):**
```
if correct:
    learning_state.attention_score = min(1.0, learning_state.attention_score + 0.1)
else:
    learning_state.attention_score = max(0.0, learning_state.attention_score - 0.15)
```
Called when TeacherAgent asks and evaluates an attention question.

**update_comprehension_score(learning_state, quiz_score: float):**
```
learning_state.comprehension_score = 0.3 * learning_state.comprehension_score + 0.7 * quiz_score
```
Called after quiz completion (only if passed). Weights recent performance more heavily.

**update_motivation_score(learning_state, event: str):**
```
deltas = {
    "chapter_complete": 0.2,
    "quiz_passed": 0.15,
    "quiz_failed": -0.1,
    "active_session": 0.05,
    "missed_session": -0.1,
    "returned_after_break": 0.1
}
delta = deltas.get(event, 0)
learning_state.motivation_score = max(0.0, min(1.0, learning_state.motivation_score + delta))
```
Called at various events throughout the flow.

**mark_chapter_complete(learning_state, chapter_number):**
```
if chapter_number not in learning_state.chapters_completed:
    learning_state.chapters_completed.append(chapter_number)
learning_state.current_chapter = chapter_number + 1
learning_state.topics_covered_this_chapter = []  # Reset for new chapter
```
Called during chapter transition.

**create_progress_snapshot(learning_state):**
```
snapshot = ProgressSnapshot(
    learning_state_id=learning_state.id,
    snapshot_date=date.today(),
    chapter_progress=learning_state.current_chapter,
    comprehension_score=learning_state.comprehension_score,
    attention_score=learning_state.attention_score,
    motivation_score=learning_state.motivation_score,
    study_duration_minutes=learning_state.total_study_time_minutes,
    topics_covered=learning_state.topics_covered_this_chapter.copy()
)
db.add(snapshot)
```
Called at chapter completion for historical tracking.

**get_progress_summary(learning_state):**
```
return {
    "chapters_completed": len(learning_state.chapters_completed),
    "total_chapters": learning_state.total_chapters,
    "completion_percentage": len(learning_state.chapters_completed) / learning_state.total_chapters * 100,
    "total_study_time": format_duration(learning_state.total_study_time_minutes),
    "comprehension_score": learning_state.comprehension_score,
    "attention_score": learning_state.attention_score,
    "motivation_score": learning_state.motivation_score
}
```
Used for dashboard display.

### When Functions Are Called

| Event | Function Called |
|-------|-----------------|
| Each teaching message | update_study_time(state, 2) |
| Attention question answered | update_attention_score(state, correct) |
| Quiz completed (passed) | update_comprehension_score(state, score) |
| Quiz passed | update_motivation_score(state, "quiz_passed") |
| Quiz failed | update_motivation_score(state, "quiz_failed") |
| Chapter completed | mark_chapter_complete(state, chapter) |
| Chapter completed | update_motivation_score(state, "chapter_complete") |
| Chapter completed | create_progress_snapshot(state) |
| Inactivity detected | update_motivation_score(state, "missed_session") |
| User returns after break | update_motivation_score(state, "returned_after_break") |

---

## 14. Motivation and Inactivity - Code Architecture

### Files Involved
- `backend/app/temporal/workflows/inactivity_monitor.py` - Temporal workflow
- `backend/app/services/motivation.py` - Motivation message generation
- `backend/app/services/notifications.py` - Notification sending

### Design: Temporal + LLM Call (Not an Agent)

Motivation is NOT an agent. It's:
1. Temporal workflow detects inactivity
2. Simple LLM call generates motivation message
3. Notification service sends message

### Inactivity Monitor Workflow (Temporal)

**InactivityMonitorWorkflow:**

**Input:**
- user_id
- book_id

**Configuration:**
- inactivity_threshold_hours: 24 (default)
- check_interval_hours: 6 (default)
- max_notifications: 5 (spam prevention)

**Workflow Loop:**
```
notifications_sent = 0

while True:
    # Sleep for check interval
    await workflow.sleep(timedelta(hours=check_interval_hours))
    
    # Check if user is inactive
    inactivity_status = await check_user_inactivity(user_id, book_id)
    
    if inactivity_status.is_inactive:
        if notifications_sent < max_notifications:
            # Generate and send motivation message
            await send_motivation_message(
                user_id, 
                book_id, 
                inactivity_status.days_inactive
            )
            notifications_sent += 1
            
            # Update motivation score
            await update_motivation_score_activity(user_id, book_id, "missed_session")
    else:
        # User is active, reset counter
        notifications_sent = 0
    
    # Check for stop signal
    if workflow.is_cancelled():
        break
```

**Signals:**
- stop_monitoring: Stop the workflow (when book completed or deleted)

### Check User Inactivity Activity

**check_user_inactivity(user_id, book_id) Logic:**

1. Query LearningState for user/book
2. Get last_active_at timestamp
3. Calculate hours_inactive = now - last_active_at
4. Calculate days_inactive = hours_inactive / 24
5. Return:
   - is_inactive: hours_inactive > threshold
   - days_inactive: float
   - last_active_at: datetime

### Motivation Message Generation (LLM Call)

**generate_motivation_message(user_id, book_id, days_inactive) Logic:**

This is a simple LLM call, NOT an agent.

**Step 1: Gather Context**
1. Get user's name and professor_style preference
2. Get book title
3. Get progress summary (chapters completed, etc.)
4. Get days_inactive

**Step 2: Build Prompt**
```
Generate a brief, personalized motivation message for a student.

Student: {user_name}
Book: {book_title}
Days Inactive: {days_inactive}
Progress: {chapters_completed}/{total_chapters} chapters completed
Professor Style: {professor_style}

Style guidelines:
- strict: Brief, goal-focused. "Your goals are waiting."
- balanced: Empathetic but practical. "I understand life gets busy, but..."
- encouraging: Warm and supportive. "I miss our sessions! You've made great progress..."

Keep the message under 100 words. Make it feel personal, not generic.
End with a gentle call to action.
```

**Step 3: Generate Message**
1. Call OpenAI GPT-4-mini
2. Get message text

**Step 4: Return Message**
- Return generated message string

### Send Motivation Message Activity

**send_motivation_message(user_id, book_id, days_inactive) Logic:**

1. Generate message using generate_motivation_message()
2. Get user's notification preferences
3. Get user's WhatsApp number (if configured)

4. Send via preferred channel:
   - If WhatsApp enabled and number configured:
     - Call Twilio API to send WhatsApp message
   - Else if Push enabled:
     - Send push notification (if implemented)
   - Else:
     - Log that no channel available

5. Log notification in notification_log table
6. Return delivery status

### Twilio WhatsApp Integration

**send_whatsapp_message(to_number, message) Logic:**

1. Initialize Twilio client with credentials
2. Send message:
   - from: twilio_whatsapp_number (format: "whatsapp:+1234567890")
   - to: user's number (format: "whatsapp:+{user_number}")
   - body: message
3. Return success/failure

### When Workflow Starts/Stops

**Starts:**
- When book processing completes and LearningState is created
- Workflow ID stored in LearningState.workflow_id

**Stops:**
- When user completes all chapters (phase = "completed")
- When user deletes the book
- When user explicitly pauses long-term

---

## 15. Session Management - Code Architecture

### Files Involved
- `backend/app/api/chat.py` - Chat session endpoints
- `backend/app/langgraph/graph.py` - State management
- `backend/app/models/learning.py` - LearningState model

### Single Source of Truth

**LearningState** is the only state model. No separate ConversationState.

### Session Initialization

**GET /api/chat/init/{book_id} Logic:**

1. Verify book exists and belongs to user
2. Check book.processing_status == "ready"
3. Get or create LearningState:
   - If exists: Load existing state
   - If not exists: Create with defaults (phase="greeting", chapter=1)
4. Get or create ChatSession
5. Load recent messages (last 50)
6. If user returning after break:
   - Update motivation_score with "returned_after_break"
7. Return:
   - session_id
   - phase
   - active_agent
   - current_chapter
   - messages
   - progress_summary

### Chat Message Processing

**POST /api/chat Logic:**

1. Validate request (book_id, message)
2. Get ChatSession
3. Get LearningState
4. Save user message to ChatMessage

5. Determine active agent from phase:
   - greeting, planning → PlannerAgent
   - teaching → TeacherAgent
   - quiz → QuizAgent

6. If TeacherAgent:
   - Call retrieval tool to get context
   - Load previous chapter summary from DB

7. Build ProfessorState from LearningState

8. Call active_agent.process(state, user_message)

9. Agent returns:
   - response: Message text
   - state_updates: Dict of state changes

10. Apply state_updates to LearningState

11. Update last_active_at = now()

12. If phase changed to chapter_transition:
    - Trigger background summarization
    - Call mark_chapter_complete()
    - Call create_progress_snapshot()

13. Save assistant message to ChatMessage

14. Persist LearningState to database

15. Return:
    - message: response text
    - agent_name
    - phase
    - progress_summary

### State Persistence

After every interaction:
1. LearningState updated with all changes
2. Single database transaction
3. Atomic - no partial updates

### Pause and Resume

**Pause:**
- User closes browser or says "I'm done for today"
- State already persisted (always saved after each message)
- No explicit pause action needed
- last_active_at tracks when user was last active

**Resume:**
- User returns to learn page
- GET /api/chat/init loads saved state
- Continues from where they left off
- If returning after break, motivation boost applied

### Concurrent Request Handling

**Optimistic Locking:**
1. LearningState has version field
2. On load: Read current version
3. On save: UPDATE WHERE version = loaded_version, SET version = version + 1
4. If rows affected = 0: Version conflict
5. On conflict: Reload state, reprocess (max 3 retries)

---

## 16. Notes Feature - Code Architecture

### Files Involved
- `backend/app/api/notes.py` - Notes API endpoints
- `backend/app/models/note.py` - UserNote model
- `web/src/components/SelectionToNotes.tsx` - Selection handler

### Notes API Logic

**GET /api/notes - List Notes:**
1. Get user_id from token
2. Apply optional filters: book_id, chapter_id, tag, pinned_only
3. Order by: is_pinned DESC, updated_at DESC
4. Return paginated list

**POST /api/notes - Create Note:**
1. Validate: title (required, max 200), content (required, max 10000)
2. Create UserNote record
3. Link to book/chapter if provided
4. Return created note

**PATCH /api/notes/{id} - Update Note:**
1. Verify ownership
2. Apply partial updates
3. Update updated_at
4. Return updated note

**DELETE /api/notes/{id} - Delete Note:**
1. Verify ownership
2. Delete record

**POST /api/notes/{id}/pin - Toggle Pin:**
1. Verify ownership
2. Toggle is_pinned
3. Return new status

**GET /api/notes/export/{format} - Export Notes:**
1. Get all notes (optional book_id filter)
2. Format as JSON, Markdown, or TXT
3. Return as file download

### Frontend Selection Handler

**SelectionToNotes Component:**
1. Listen for mouseup in chat area
2. On text selection:
   - Get selected text
   - Show floating "Save to Notes" button at selection position
3. On button click:
   - Get context (bookId, chapterNumber)
   - Call POST /api/notes
   - Show success toast
   - Clear selection

---

## 17. Configuration System - All Settings

### Files Involved
- `backend/app/config.py` - Settings class
- `backend/app/models/learning_config.py` - LearningConfig model
- `backend/app/models/user.py` - UserSettings model

### Application Settings (config.py)

**Application:**
- app_name: "Professor"
- environment: "development" | "production"
- debug: True | False

**Database:**
- database_url: PostgreSQL async connection string
- db_pool_size: 10
- db_max_overflow: 20

**Redis:**
- redis_url: Redis connection string

**Security:**
- secret_key: JWT signing key
- encryption_key: Fernet key for API key encryption
- access_token_expire_minutes: 1440 (24 hours)
- refresh_token_expire_days: 7

**Google OAuth:**
- google_client_id
- google_client_secret

**URLs:**
- frontend_url: "http://localhost:3000"
- backend_url: "http://localhost:8000"

**File Storage:**
- pdf_storage_path: "/app/data/pdfs"
- max_file_size_mb: 50

**OpenAI:**
- openai_api_key: Default key
- openai_model: "gpt-4" (for agents)
- openai_model_mini: "gpt-4-mini" (for evaluation, summarization)

**RAG Settings:**
- chunk_size: 400 tokens
- chunk_overlap: 50 tokens
- embedding_model: "text-embedding-ada-002"
- embedding_dimensions: 1536
- retrieval_top_k: 8 chunks
- retrieval_current_chapter_boost: 1.5

**Teaching Settings:**
- max_response_tokens: 600
- default_temperature: 0.7

**Quiz Settings:**
- questions_per_quiz: 5
- quiz_passing_score: 0.7

**Cache TTLs:**
- cache_ttl_embeddings: 604800 (7 days)

**Inactivity Settings:**
- inactivity_threshold_hours: 24
- inactivity_check_interval_hours: 6
- max_inactivity_notifications: 5

**Twilio:**
- twilio_account_sid
- twilio_auth_token
- twilio_whatsapp_number

**Temporal:**
- temporal_host: "localhost:7233"
- temporal_namespace: "default"
- temporal_task_queue: "professor-queue"

### Learning Configuration (LearningConfig model)

Per-book settings:
- learning_level: "beginner" | "intermediate" | "advanced" | "research"
- study_all_chapters: Boolean
- selected_chapters: JSON array
- deadline: Date
- daily_study_minutes: Integer
- quiz_frequency: "after_each_chapter" | "after_n_chapters" | "final_only"
- quiz_after_n_chapters: Integer
- questions_per_quiz: Integer
- plan_accepted: Boolean

### User Settings (UserSettings model)

Global preferences:
- professor_style: "strict" | "balanced" | "encouraging"
- notification_preferences: JSON {whatsapp, push}
- whatsapp_number: String
- timezone: String

---

## 18. Database Models - Complete Schema

### User Domain

**users:**
- id: UUID PK
- email: String, unique
- password_hash: String, nullable
- name: String
- phone: String, nullable
- role: String ("student", "admin")
- is_active: Boolean
- created_at, updated_at: DateTime

**user_auth:**
- id: UUID PK
- user_id: FK to users
- provider: String ("google")
- provider_user_id: String
- created_at: DateTime

**encrypted_api_keys:**
- id: UUID PK
- user_id: FK to users, unique
- encrypted_key: Bytes
- key_hash: String
- is_valid: Boolean
- created_at: DateTime

**user_settings:**
- id: UUID PK
- user_id: FK to users, unique
- professor_style: String
- notification_preferences: JSON
- whatsapp_number: String, nullable
- timezone: String
- created_at: DateTime

### Book Domain

**books:**
- id: UUID PK
- user_id: FK to users
- title: String
- author: String, nullable
- file_path: String
- file_hash: String
- total_pages: Integer
- total_chapters: Integer
- processing_status: String
- processing_progress: Integer
- processing_error: String, nullable
- created_at: DateTime

**book_chapters:**
- id: UUID PK
- book_id: FK to books
- chapter_number: Integer
- title: String
- start_page, end_page: Integer
- estimated_duration_minutes: Integer
- created_at: DateTime
- Unique: (book_id, chapter_number)

### Learning Domain

**learning_configs:**
- id: UUID PK
- user_id: FK to users
- book_id: FK to books, unique
- learning_level: String
- study_all_chapters: Boolean
- selected_chapters: JSON
- deadline: Date, nullable
- daily_study_minutes: Integer
- quiz_frequency: String
- quiz_after_n_chapters: Integer
- questions_per_quiz: Integer
- plan_accepted: Boolean
- created_at, updated_at: DateTime

**learning_plans:**
- id: UUID PK
- config_id: FK to learning_configs
- user_id: FK to users
- book_id: FK to books
- plan_data: JSON
- summary: String
- version: Integer
- status: String
- created_at: DateTime

**learning_states:**
- id: UUID PK
- user_id: FK to users
- book_id: FK to books
- phase: String
- active_agent: String
- current_chapter: Integer
- total_chapters: Integer
- chapters_completed: Array of integers
- chapter_title: String
- topics_covered_this_chapter: Array of strings
- comprehension_score: Float
- attention_score: Float
- motivation_score: Float
- total_study_time_minutes: Integer
- quiz_questions: JSON, nullable
- quiz_current_index: Integer
- quiz_scores: JSON
- plan_data: JSON, nullable
- plan_accepted: Boolean
- last_active_at: DateTime
- workflow_id: String, nullable
- version: Integer (optimistic locking)
- created_at, updated_at: DateTime
- Unique: (user_id, book_id)

**chapter_summaries:**
- id: UUID PK
- user_id: FK to users
- book_id: FK to books
- chapter_number: Integer
- summary_text: Text
- topics_covered: Array of strings
- created_at: DateTime
- Unique: (user_id, book_id, chapter_number)

**progress_snapshots:**
- id: UUID PK
- learning_state_id: FK to learning_states
- snapshot_date: Date
- chapter_progress: Integer
- comprehension_score: Float
- attention_score: Float
- motivation_score: Float
- study_duration_minutes: Integer
- topics_covered: Array of strings
- created_at: DateTime

### RAG Domain

**document_chunks:**
- id: UUID PK
- book_id: FK to books
- chapter_id: FK to book_chapters
- chunk_index: Integer
- content: Text
- content_hash: String
- token_count: Integer
- embedding: Vector(1536)
- created_at: DateTime
- Index: (book_id, chapter_id)
- Index: embedding (ivfflat)

### Chat Domain

**chat_sessions:**
- id: UUID PK
- user_id: FK to users
- book_id: FK to books
- learning_state_id: FK to learning_states
- is_active: Boolean
- message_count: Integer
- created_at: DateTime
- last_message_at: DateTime

**chat_messages:**
- id: UUID PK
- session_id: FK to chat_sessions
- role: String ("user", "assistant")
- content: Text
- agent_name: String, nullable
- chapter_at_time: Integer
- is_quiz_question: Boolean
- created_at: DateTime
- Index: (session_id, created_at)

### Quiz Domain

**quiz_attempts:**
- id: UUID PK
- user_id: FK to users
- learning_state_id: FK to learning_states
- book_id: FK to books
- chapter_number: Integer
- questions: JSON
- answers: JSON
- score: Float
- passed: Boolean
- started_at: DateTime
- completed_at: DateTime, nullable

### Notes Domain

**user_notes:**
- id: UUID PK
- user_id: FK to users
- book_id: FK to books, nullable
- chapter_id: FK to book_chapters, nullable
- title: String
- content: Text
- tags: Array of strings
- is_pinned: Boolean
- created_at, updated_at: DateTime

### Notifications Domain

**notification_log:**
- id: UUID PK
- user_id: FK to users
- channel: String
- message_type: String
- message_content: Text
- sent_at: DateTime
- delivery_status: String

---

## 19. API Endpoints - Complete Reference

### Authentication (/api/auth)
- POST /signup - Register with email/password
- POST /signin - Login with email/password
- POST /google - Google OAuth
- POST /refresh - Refresh access token
- GET /me - Get current user
- POST /logout - Logout

### Users (/api/users)
- GET /profile - Get user profile
- PATCH /profile - Update profile
- GET /settings - Get user settings
- PATCH /settings - Update settings
- GET /api-key/status - Get API key status
- POST /api-key - Save API key
- DELETE /api-key - Delete API key

### Books (/api/books)
- GET / - List user's books
- GET /{id} - Get book details
- GET /{id}/status - Get processing status
- POST /upload - Upload PDF
- POST /upload-with-config - Upload with configuration
- DELETE /{id} - Delete book
- GET /{id}/chapters - Get book chapters
- POST /{id}/config - Save learning config

### Chat (/api/chat)
- POST / - Send message
- GET /init/{book_id} - Initialize session
- GET /sessions - List sessions
- GET /sessions/{id}/messages - Get messages

### Learning (/api/learning)
- GET /state/{book_id} - Get learning state
- GET /progress/{book_id} - Get progress summary

### Notes (/api/notes)
- GET / - List notes
- POST / - Create note
- PATCH /{id} - Update note
- DELETE /{id} - Delete note
- POST /{id}/pin - Toggle pin
- GET /export/{format} - Export notes

### Admin (/api/admin)
- GET /dashboard - Admin stats
- GET /users - List users
- GET /system/health - Health check

---

## 20. Error Handling Strategy

### API Error Responses

Consistent JSON structure:
- status_code: HTTP status
- error: Error type
- message: Human-readable message
- details: Optional additional info

### PDF Processing Errors

**Corrupted PDF:**
- Mark failed with message: "The PDF file appears to be corrupted."

**Password Protected:**
- Mark failed with message: "This PDF is password-protected. Please remove the password."

**Scanned/Image PDF:**
- Mark failed with message: "This PDF contains scanned images without text."

**Rate Limit:**
- Retry with exponential backoff
- If still failing: Save checkpoint, mark failed with "Processing paused due to high demand."

### LLM API Errors

**Rate Limit:** Retry with backoff (3 attempts)
**Context Length:** Truncate context, retry
**Invalid Response:** Retry with stricter prompt
**API Key Invalid:** Fall back to default key

### Database Errors

**Connection Timeout:** Retry once, then 503
**Version Conflict:** Reload and reprocess (3 attempts)
**Constraint Violation:** Return 409 with specific message

### Graceful Degradation

**If Summarization Fails:**
- Log error
- Next chapter proceeds without summary
- No user-facing error

**If Motivation Message Fails:**
- Log error
- Skip notification
- Try again next interval

**If Retrieval Returns Empty:**
- TeacherAgent proceeds with general knowledge
- Logs warning for debugging

---

## Summary

This redesigned architecture is:

**Agent-Driven:**
- 3 agents only: PlannerAgent, TeacherAgent, QuizAgent
- Agents drive conversation, not intent classifiers
- Orchestrator prompts make agents intelligent

**Tool-Based:**
- Retrieval is a tool for TeacherAgent, not an agent
- TeacherAgent calls retrieval tool to get context

**Background Processing:**
- Summarization happens async after chapter completion
- Summary available for next chapter's continuity
- Motivation is an LLM call triggered by Temporal, not an agent

**Simplified State:**
- Single LearningState model
- No redundant ConversationState
- All state persisted after each interaction

**Clean Flow:**
```
Greeting → PlannerAgent → TeacherAgent (with retrieval tool) → QuizAgent → Chapter Transition → Repeat
                              ↑                                    ↓
                              └──────────────────────────────────────┘
```

**Key Files:**
- `backend/app/agents/planner.py` - PlannerAgent
- `backend/app/agents/teacher.py` - TeacherAgent (main agent)
- `backend/app/agents/quiz.py` - QuizAgent
- `backend/app/tools/retrieval.py` - Retrieval tool (not agent)
- `backend/app/services/summarization.py` - Background summarization
- `backend/app/services/motivation.py` - Motivation message generation
- `backend/app/services/progress.py` - Progress utility functions
- `backend/app/temporal/workflows/inactivity_monitor.py` - Inactivity detection

---

*Document Version: 2.0*
*Architecture: Agent-Driven with 3 Agents*
*Last Updated: January 2026*
