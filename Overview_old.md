# Professor - Complete System Overview

## Table of Contents

1. [Project Goal](#1-project-goal)
2. [What Professor Can Do](#2-what-professor-can-do)
3. [User Journey](#3-user-journey)
4. [Login and Authentication](#4-login-and-authentication)
5. [PDF Upload Architecture](#5-pdf-upload-architecture)
6. [RAG (Retrieval-Augmented Generation) System](#6-rag-retrieval-augmented-generation-system)
7. [Agentic Architecture (LangGraph)](#7-agentic-architecture-langgraph)
8. [Teaching Logic](#8-teaching-logic)
9. [Quiz Logic](#9-quiz-logic)
10. [Doubt Resolution](#10-doubt-resolution)
11. [Motivation Agent](#11-motivation-agent)
12. [Temporal Inactivity Detection](#12-temporal-inactivity-detection)
13. [Progress Tracking](#13-progress-tracking)
14. [Session Ending and Chapter Completion](#14-session-ending-and-chapter-completion)

---

## 1. Project Goal

**Professor** is a **Professor-Driven AI Learning System** that actively teaches, plans, tracks, motivates, and evaluates students end-to-end. Unlike traditional chatbots that passively respond to queries, Professor drives the learning journey.

### Core Philosophy

- **NOT a chatbot** - Professor initiates and guides conversations
- **NOT one-shot explanations** - Persistent memory and stateful learning
- **IS a dedicated professor** with memory, intent, and goals
- **IS agent-driven, event-driven, and stateful**
- **IS human-in-the-loop** at every major decision

### What Makes Professor Different

The system feels like a dedicated professor who:
- Understands the student's level and goals
- Plans a personalized learning path
- Teaches step-by-step interactively
- Proactively brings the student back if they disengage
- Evaluates understanding through quizzes
- Tracks progress visually
- Adapts plans dynamically

---

## 2. What Professor Can Do

### Learning Plan Creation
- Analyzes uploaded PDF structure (chapters, sections)
- Creates personalized day-by-day learning plans
- Adapts plans based on user performance and pace
- Considers deadlines, study time preferences, and learning level

### Interactive Teaching
- Teaches chapter-by-chapter, topic-by-topic
- Uses RAG to retrieve relevant content from uploaded material
- Checks comprehension through attention questions
- Adjusts teaching style based on user's level (beginner/intermediate/advanced)

### Assessment & Quizzes
- Generates MCQ, True/False, and short-answer questions
- Adapts difficulty based on performance
- Provides immediate feedback with explanations
- Tracks weak areas for review

### Progress Tracking
- Tracks chapters completed, topics covered
- Monitors comprehension, attention, and motivation scores
- Records study time and quiz performance
- Provides visual progress snapshots

### Motivation & Engagement
- Detects user inactivity through Temporal workflows
- Sends personalized encouragement messages
- Adjusts teaching approach based on motivation level
- Sends reminders via WhatsApp or push notifications

---

## 3. User Journey

### Step 1: User Registration/Login
User lands on the application and either:
- Signs up with email/password
- Signs in with existing credentials
- Uses Google OAuth for authentication

### Step 2: API Key Setup
- User navigates to settings
- Enters their OpenAI API key (required for processing)
- Key is encrypted and stored securely

### Step 3: PDF Upload & Configuration
User uploads a PDF and configures:
- Learning level (beginner, intermediate, advanced, research)
- Target deadline for completion
- Daily study time preference
- Quiz frequency (after every chapter, every N chapters, or final only)
- Number of questions per quiz

### Step 4: PDF Processing (Automatic)
- System processes PDF through RAG pipeline
- Extracts text from all pages
- Detects chapter boundaries
- Chunks content semantically
- Generates embeddings
- Stores in vector database

### Step 5: Professor Greeting (Auto-Triggered)
Once processing completes:
- Professor automatically initiates conversation
- Greets the user
- Offers to create a personalized learning plan
- This is NOT user-initiated - the system starts the interaction

### Step 6: Plan Creation & Review
- User accepts the plan prompt
- PlannerAgent creates detailed learning plan
- User reviews and can request modifications
- User explicitly accepts the plan
- No teaching starts until plan acceptance

### Step 7: Teaching Sessions
- Professor teaches chapter-by-chapter
- Uses retrieved context from RAG
- Periodically asks attention questions
- Checks comprehension through quick quizzes
- Tracks topics covered in session

### Step 8: Chapter Completion & Quiz
- Professor detects when chapter content is covered
- Asks if user has any doubts
- Resolves doubts using RAG context
- Generates end-of-chapter quiz
- Evaluates answers with feedback

### Step 9: Chapter Transition
- If quiz passed (70%+), unlocks next chapter
- If quiz failed, schedules review session
- Updates progress tracking
- Celebrates milestones

### Step 10: Course Completion
- Congratulates user on completing all chapters
- Provides final summary
- Offers review or final assessment option

---

## 4. Login and Authentication

### Files Used
- `backend/app/api/auth.py` - Authentication API routes
- `backend/app/security/jwt.py` - JWT token management
- `backend/app/models/user.py` - User database models
- `backend/app/dependencies.py` - Authentication dependencies

### Authentication Methods

**Email/Password Authentication:**
- User submits email and password for signup/signin
- Password is hashed using bcrypt before storage
- System validates credentials against stored hash

**Google OAuth:**
- User initiates Google OAuth flow
- Frontend receives authorization code
- Backend exchanges code for Google access token
- Fetches user info from Google
- Creates/links user account
- If user exists by Google ID, logs them in
- If user exists by email but not Google ID, links accounts
- If new user, creates account with Google info

### JWT Token System

**Access Token Creation:**
- Contains user ID as subject
- Expires in 30 minutes (configurable)
- Includes token type ("access") and issue time
- Signed with secret key using HS256 algorithm

**Refresh Token Creation:**
- Contains user ID as subject
- Expires in 7 days (configurable)
- Includes token type ("refresh") and issue time
- Used to obtain new access tokens without re-login

**Token Verification:**
- Decodes JWT using secret key
- Validates token type (access vs refresh)
- Checks expiration
- Returns payload if valid, None if invalid

### Session Management
- User sessions tracked in database
- Logout invalidates all sessions for user
- Each API request validates access token
- Token extracted from Authorization header

---

## 5. PDF Upload Architecture

### Files Used
- `backend/app/api/books.py` - Book upload and management API
- `backend/app/rag/ingestion.py` - PDF ingestion pipeline
- `backend/app/models/book.py` - Book database models

### Upload Flow

**File Reception:**
- Frontend sends multipart form data with PDF file
- Backend validates file type (must be PDF)
- Generates unique filename using timestamp and hash
- Saves file to storage directory

**Book Record Creation:**
- Creates Book record in database
- Sets status to "pending"
- Stores file path, user ID, title
- Creates associated LearningConfig with user preferences

**Background Processing Trigger:**
- Immediately returns response to user (non-blocking)
- Spawns background task for processing
- Frontend can poll for processing status

### Processing Pipeline

**Phase 1: Text Extraction (5-20%)**
- Uses pdfplumber library for text extraction
- Extracts text from each page asynchronously
- Runs in thread pool to avoid blocking
- Returns list of (page_number, text) tuples

**Phase 2: Chapter Detection (20-30%)**
- Searches first 15 pages for Table of Contents
- If TOC found, parses chapter entries with page numbers
- If no TOC, uses regex pattern matching on page content
- Patterns include: "Chapter N", "Part N", "Section N", etc.
- Sets chapter boundaries (start page, end page)
- If no chapters detected, treats entire document as one chapter

**Phase 3: Chunking (30-50%)**
- Processes all chapters in parallel using thread pool
- Creates BookChapter records in database
- Estimates reading duration based on page count
- Semantic chunking preserves logical boundaries

**Phase 4: Embedding Generation (50-85%)**
- Collects all chunks from all chapters
- Batch embeds using OpenAI API (500 chunks per batch)
- Parallel batch processing (3 batches simultaneously)
- Caches embeddings using content hash

**Phase 5: Database Storage (85-95%)**
- Bulk inserts all DocumentChunk records
- Associates chunks with chapters and books
- Stores embedding vectors in pgvector

**Phase 6: Professor Greeting (95-100%)**
- Updates book status to "ready_for_planning"
- Creates ConversationState with phase "greeting"
- Creates ChatSession for the book
- Saves initial greeting message from Professor

---

## 6. RAG (Retrieval-Augmented Generation) System

### Files Used
- `backend/app/rag/chunking.py` - Smart document chunking
- `backend/app/rag/embeddings.py` - Embedding generation
- `backend/app/rag/retrieval.py` - Vector similarity search
- `backend/app/rag/chapter_detection.py` - Chapter boundary detection
- `backend/app/agents/retrieval.py` - RetrievalAgent for context fetching

### Chunking Logic

**SmartChunker Configuration:**
- Target chunk size: ~400 tokens (configurable)
- Minimum chunk size: 50% of target
- Maximum chunk size: 150% of target
- Overlap: ~50 tokens for context continuity

**Section Detection:**
- Splits text by markdown-style headers (##, ###)
- Detects all-caps section headers
- Preserves section titles in chunk metadata

**Paragraph-Based Chunking:**
- Splits sections into paragraphs (double newlines)
- Accumulates paragraphs until target size reached
- When adding paragraph would exceed max, saves current chunk
- Carries overlap from previous chunk for continuity
- Large paragraphs split by sentences if needed

**Chunk Object Creation:**
- Content: The actual text
- Content Hash: SHA256 for deduplication and caching
- Token Count: Accurate count using tiktoken
- Section Title: Preserved for context
- Metadata: chapter_id, book_id, page_offset

### Embedding Generation

**EmbeddingService Architecture:**
- Uses OpenAI's embedding model (text-embedding-3-small)
- Batch size: 500 texts per API call
- Parallel batches: 3 simultaneous API calls
- Connection pooling with retry logic

**Caching Strategy:**
- Checks cache before generating new embeddings
- Cache key: "emb:{content_hash}"
- Cache TTL: 7 days
- Fire-and-forget cache writes (non-blocking)

### Retrieval Logic

**Query Processing:**
- Receives user query and context (book_id, chapter)
- Generates query embedding using same model
- Falls back to default query if empty

**Vector Similarity Search:**
- Uses PostgreSQL with pgvector extension
- SQL query with cosine distance operator (<=>)
- Strictly scoped to current chapter
- Returns top K chunks (default: 8) ordered by similarity

**Cross-Reference Detection (Optional):**
- Detects if query references previous chapter topics
- Builds topic graph from database
- Extracts topics from query using LLM
- Matches against graph to find relevant prior content

### Handling Large Documents

**Parallel Processing:**
- Text extraction runs in thread pool (4 workers)
- Chapter chunking runs in parallel per chapter
- Embedding generation batched and parallelized
- Database operations use async/await

**Memory Efficiency:**
- Streams large PDFs page-by-page
- Processes chapters independently
- Flushes to database incrementally
- Uses generators where possible

---

## 7. Agentic Architecture (LangGraph)

### Files Used
- `backend/app/langgraph/graph.py` - Main workflow graph
- `backend/app/langgraph/state.py` - State definitions
- `backend/app/agents/planner.py` - PlannerAgent
- `backend/app/agents/teaching.py` - TeachingAgent
- `backend/app/agents/quiz.py` - QuizAgent
- `backend/app/agents/retrieval.py` - RetrievalAgent
- `backend/app/agents/progress.py` - ProgressAgent
- `backend/app/agents/motivation.py` - MotivationAgent
- `backend/app/agents/base.py` - Base agent class

### State Graph Phases

The system uses a state machine with these phases:
- `greeting` - Initial professor greeting
- `planning` - Learning plan generation
- `plan_review` - User reviewing plan
- `plan_iteration` - User modifying plan
- `teaching` - Active teaching session
- `doubt_resolution` - Answering user doubts
- `quiz` - End-of-chapter quiz
- `chapter_transition` - Moving to next chapter
- `completed` - Course completed

### Agent Descriptions

**PlannerAgent**
- Creates personalized learning plans
- Analyzes book structure and chapter dependencies
- Creates timeline based on user's study schedule
- Adapts plan when user misses sessions or excels
- Estimates completion dates
- Uses LLM to generate day-by-day study schedule

**RetrievalAgent**
- Retrieves relevant context from vector store
- Embeds user queries
- Performs chapter-scoped vector search
- Detects cross-chapter references
- Formats retrieved context for teaching

**TeachingAgent**
- Delivers personalized instruction using retrieved context
- Builds comprehensive context from multiple sources
- Generates clear, educational responses
- Determines when to trigger attention questions
- Tracks topic coverage and chapter progress
- Adapts to professor_level (beginner/intermediate/advanced)

**QuizAgent**
- Generates quiz questions for chapter-end assessments
- Creates MCQ, true/false, and short answer questions
- Adapts difficulty based on performance
- Focuses on weak areas identified by attention questions
- Creates attention check questions during teaching

**ProgressAgent**
- Updates learning state after each interaction
- Tracks current chapter/section progress
- Tracks topics covered in session
- Calculates engagement metrics (attention, comprehension, motivation)
- Determines if motivation intervention needed

**MotivationAgent**
- Provides personalized encouragement when motivation is low
- Generates encouraging messages
- Highlights progress made
- Adjusts tone based on professor_style
- Suggests breaks or schedule adjustments

### Graph Flow

```
greeting → planning → plan_review → [teaching_loop] → quiz → chapter_transition
                         ↓                                          ↓
                 plan_iteration                                 [next chapter]
                         ↓                                          ↓
                     planning                              back to teaching_loop
```

**Teaching Loop (Internal):**
```
User Message → RetrievalAgent → TeachingAgent → ProgressAgent
                                     ↓
                          Check chapter_complete?
                                     ↓
              No: Continue teaching with possible attention question
              Yes: Move to doubt_resolution → quiz → chapter_transition
```

### Message Processing Flow

1. **Intent Detection**: Uses LLM to detect user intent (accept, reject, question, doubt, etc.)
2. **Phase Routing**: Routes to appropriate node based on current phase
3. **Agent Execution**: Executes relevant agents in sequence
4. **State Update**: Updates conversation state with results
5. **Response Return**: Returns professor response to user

### How Agents Communicate

**State-Based Communication:**
- All agents receive and return dictionaries
- Each agent reads from state what it needs
- Each agent writes to state what it produces
- State is merged after each agent execution

**Pipeline Pattern:**
- In teaching_node: RetrievalAgent → TeachingAgent → ProgressAgent
- Each agent's output becomes next agent's input context
- Final merged result returned as node output

**Conditional Routing:**
- Graph edges use lambda functions to check state
- Example: `lambda s: "quiz" if s.get("chapter_complete") else "teaching"`
- Enables dynamic flow based on agent decisions

---

## 8. Teaching Logic

### Files Used
- `backend/app/agents/teaching.py` - TeachingAgent
- `backend/app/langgraph/graph.py` - teaching_node function
- `backend/app/services/teaching_service.py` - Teaching utilities

### Teaching Pipeline

**Step 1: Context Retrieval**
- RetrievalAgent receives user query
- Embeds query and searches chapter chunks
- Returns top 8 most relevant chunks
- Optionally detects cross-chapter references

**Step 2: Response Generation**
- TeachingAgent receives:
  - Retrieved chunks
  - Cross-references (if any)
  - Topics already covered this session
  - User's query
  - Book/chapter context
  - Professor level and style preferences

**Step 3: Prompt Construction**
- Builds comprehensive teaching prompt with:
  - Book title and current chapter
  - Summarized past context (memory)
  - Retrieved chunk content
  - Cross-reference section (if applicable)
  - Topics covered in session
  - User's question

**Step 4: LLM Generation**
- Sends prompt to OpenAI
- System prompt defines professor personality
- Temperature and token limits configured
- Includes fallback response on failure

### Professor Personality

The teaching agent adapts based on:

**professor_level:**
- `beginner`: More basic explanations, simpler analogies, more encouragement
- `intermediate`: Balanced depth, some technical terms with explanations
- `advanced`: More technical, deeper insights, expects prior knowledge

**professor_style:**
- `strict`: Focus on goals and discipline, brief responses
- `balanced`: Mix empathy with practical advice
- `encouraging`: Very warm, lots of positive reinforcement

### Attention Questions

**Trigger Logic:**
- Minimum interval: 3 messages before first attention question
- Maximum interval: 7 messages (forced question)
- Probability-based: 30% chance within interval window

**Question Generation:**
- QuizAgent generates quick comprehension check
- Based on recent teaching content
- Should be answerable in 1-2 sentences
- Takes less than 30 seconds to answer

### Chapter Completion Detection

TeachingAgent determines chapter_complete based on:

1. **Topic Coverage Ratio**: If 80%+ of pending topics covered
2. **Chunk Processing**: If topics covered >= chunks retrieved
3. **Completion Signals**: Natural language signals in response like:
   - "we've covered all"
   - "that concludes"
   - "those are the key concepts"

### Teaching Loop Behavior

**If chapter NOT complete:**
- Response returned to user
- Phase stays "teaching"
- May include attention question

**If chapter IS complete:**
- Phase changes to "doubt_resolution"
- Professor asks if user has questions
- Waits for user confirmation before quiz

---

## 9. Quiz Logic

### Files Used
- `backend/app/agents/quiz.py` - QuizAgent
- `backend/app/langgraph/graph.py` - quiz_node function
- `backend/app/services/quiz_service.py` - Quiz utilities

### Quiz Generation

**Question Types:**
- MCQ (50% probability): 4 options, one correct
- True/False (25% probability): Binary choice
- Short Answer (25% probability): Free-form response

**Difficulty Adaptation:**
- High performance (80%+): 60% hard, 30% medium, 10% easy
- Average performance (60-80%): 30% hard, 50% medium, 20% easy
- Low performance (<60%): 20% hard, 40% medium, 40% easy

**Question Components:**
- Question text
- Type (mcq, true_false, short_answer)
- Difficulty level
- Options (for MCQ)
- Correct answer
- Explanation
- Topic being tested
- Optional hints

### Quiz Flow

**First Entry (No Questions Yet):**
1. QuizAgent generates all questions for the quiz
2. Number of questions based on settings (default: 3)
3. First question displayed to user
4. Quiz state stored (questions, current_index, scores)

**Subsequent Messages (Answering):**
1. Evaluate previous answer
2. Calculate score (0-1)
3. Provide feedback (correct/incorrect + explanation)
4. Check if quiz complete
5. If not complete, show next question
6. If complete, show results and transition

### Answer Evaluation

**MCQ/True-False:**
- Simple string matching (case-insensitive)
- Score: 1.0 for correct, 0.0 for incorrect

**Short Answer:**
- Uses LLM to evaluate response
- Compares against expected answer/concepts
- Provides partial credit (0.0-1.0)
- Generates constructive feedback

### Quiz Completion

**Passing (70%+ score):**
- Congratulations message
- Score display
- Unlocks next chapter
- Phase transitions to chapter_transition

**Failing (<70% score):**
- Encouragement message
- Score display
- Review session scheduled
- Weak areas identified for reteaching

---

## 10. Doubt Resolution

### Files Used
- `backend/app/langgraph/graph.py` - doubt_resolution_node function
- `backend/app/services/intent_service.py` - Intent detection

### Doubt Resolution Flow

**Entry Point:**
- Triggered when chapter is complete
- Professor asks: "Do you have any questions before we move forward?"

**Intent Detection:**
- User message analyzed by LLM
- Determines if user has doubts or is ready to proceed
- Intents: "no_doubt", "accept", "continue" = no doubts
- Intents: "question", "doubt" = has questions

**If No Doubts:**
- Check if quiz should trigger
- If quiz scheduled: transition to quiz phase
- If no quiz: transition to chapter_transition

**If Has Doubts:**
1. RetrievalAgent fetches relevant context
2. TeachingAgent generates answer using RAG context
3. Response sent with answer
4. Professor asks again if more questions
5. Loop continues until user has no more doubts

### Multiple Doubt Handling

- Phase stays "doubt_resolution" while doubts_pending is True
- Each question fully answered before asking for more
- User can ask unlimited questions about the chapter
- Only proceeds to quiz when user confirms no more doubts

---

## 11. Motivation Agent

### Files Used
- `backend/app/agents/motivation.py` - MotivationAgent
- `backend/app/langgraph/graph.py` - Motivation check in teaching_node

### Motivation Tracking

**Score Calculation (0.0 to 1.0):**

Factors that DECREASE motivation:
- Missed sessions: -0.1 per missed session
- Low quiz scores (<50%): -0.1
- No recent activity

Factors that INCREASE motivation:
- Active session (>5 messages): +0.05
- Multiple topics covered (>3): +0.05
- Chapter completion: +0.2

### Intervention Trigger

**When activated:**
- motivation_score drops below 0.5
- ProgressAgent sets motivation_check flag

**Integration in Teaching:**
1. ProgressAgent calculates motivation score
2. If score < 0.5, MotivationAgent is called
3. Generates personalized encouragement message
4. Message prepended to teaching response
5. motivation_score boosted by 0.1 after intervention

### Message Generation

**Information Used:**
- Student name
- Current motivation score
- Chapters completed vs total
- Study time so far
- Missed sessions count
- Last quiz score
- Professor style preference

**Message Components:**
1. Acknowledgment of feelings/situation
2. Highlights specific progress made
3. 1-2 actionable suggestions
4. Genuine encouragement ending

**Style Adaptation:**
- `strict`: Brief, goal-focused
- `balanced`: Mix of empathy and advice
- `encouraging`: Warm, lots of positive reinforcement

---

## 12. Temporal Inactivity Detection

### Files Used
- `backend/app/temporal/workflows/inactivity_monitor.py` - InactivityMonitorWorkflow
- `backend/app/temporal/activities/learning.py` - check_user_inactivity, send_motivation_message
- `backend/app/temporal/workflows/learning_session.py` - LearningSessionWorkflow
- `backend/app/temporal/client.py` - Temporal client
- `backend/app/temporal/worker.py` - Temporal worker

### Inactivity Monitor Workflow

**Workflow Configuration:**
- user_id: The user being monitored
- book_id: The book being studied
- inactivity_threshold_hours: Hours before triggering (default: 24)
- check_interval_hours: How often to check (default: 6)

**Workflow Logic:**
```
1. Start workflow with user_id and book_id
2. Sleep for check_interval (6 hours)
3. Execute check_user_inactivity activity
4. If user is inactive beyond threshold:
   a. Execute send_motivation_message activity
   b. Optionally update motivation score
   c. Increment message counter
5. If user is active:
   a. Reset message counter
6. Repeat until max_messages (5) sent or stop signal
```

**Signal Handling:**
- `user_active`: Received when user becomes active, stops monitoring
- `stop_monitoring`: External signal to stop workflow

### Check User Inactivity Activity

**Logic:**
1. Get ConversationState from database
2. Retrieve last_interaction_at timestamp
3. Calculate hours since last interaction
4. Compare against threshold
5. Return inactivity status and days inactive

**Return Data:**
- is_inactive: boolean
- hours_since_last_interaction: float
- days_inactive: integer
- last_interaction: ISO timestamp
- current_phase: conversation phase
- current_chapter: integer

### Send Motivation Message Activity

**Message Crafting Based on Inactivity Duration:**
- 1 day: "Ready to pick up where we left off?"
- 2-3 days: "Your progress is waiting!"
- 4-7 days: "Consistency is key!"
- 7+ days: "Whenever you're ready, I'll be here."

**Delivery Channels:**
1. Try WhatsApp first (via Twilio integration)
2. Fallback to push notification
3. Log result for tracking

### Learning Session Workflow

**Purpose:**
- Manages entire learning session lifecycle
- Handles chapter-by-chapter progression
- Coordinates between teaching, quizzes, transitions

**Flow:**
```
1. Start session for user/book/chapter
2. Get chapter topics
3. Send chapter introduction
4. For each topic:
   a. Generate teaching segment
   b. Send to student
   c. Check comprehension every 2-3 topics
   d. Adjust if score < 0.6
5. When all topics covered:
   a. Generate chapter summary
   b. Run chapter quiz
   c. If passed, unlock next chapter
   d. If failed, schedule review
6. Transition to next chapter or complete
```

**Signal Handling:**
- `student_response`: Receives student answers
- `pause_session`: Pauses and saves state
- `end_session`: Ends session early
- `quiz_completed`: External quiz completion signal

---

## 13. Progress Tracking

### Files Used
- `backend/app/agents/progress.py` - ProgressAgent
- `backend/app/models/learning.py` - LearningState, ProgressSnapshot models
- `backend/app/temporal/activities/learning.py` - Progress activities

### State Tracked

**Per Session:**
- session_message_count: Messages in current session
- topics_covered_this_session: List of topics covered
- total_study_time_minutes: Estimated from interactions (2 min each)

**Per Book:**
- current_chapter: Currently active chapter
- completed_chapters: List of completed chapter numbers
- quiz_scores: Scores from chapter quizzes
- weak_areas: Topics identified as needing review

**Learning Metrics:**
- attention_score: Based on attention question performance
- comprehension_score: Based on quiz and attention performance
- motivation_score: Based on engagement patterns

### Score Calculations

**Attention Score (0.0-1.0):**
- Correct attention answer: +0.1
- Incorrect attention answer: -0.15
- Bounded between 0.0 and 1.0

**Comprehension Score (0.0-1.0):**
- Blended: 30% current + 70% quiz score
- Attention questions: +/- 0.05
- Bounded between 0.0 and 1.0

**Motivation Score (0.0-1.0):**
- Missed sessions: -0.1 each
- Low quiz score: -0.1
- Active session (>5 messages): +0.05
- Topics covered (>3): +0.05
- Chapter completion: +0.2
- Bounded between 0.0 and 1.0

### Progress Persistence

**ProgressSnapshot Creation:**
- Created at chapter transitions
- Records:
  - snapshot_date
  - chapter_progress
  - quiz_scores
  - topics_covered

**LearningState Updates:**
- Updated after each session
- Tracks:
  - Current position
  - Cumulative metrics
  - Last active timestamp

### Database Operations

- Uses async SQLAlchemy for non-blocking DB ops
- Progress persistence handled by API endpoints (not in LangGraph)
- Avoids async context issues in agent execution

---

## 14. Session Ending and Chapter Completion

### Files Used
- `backend/app/langgraph/graph.py` - chapter_transition_node function
- `backend/app/services/teaching_service.py` - generate_summary
- `backend/app/temporal/activities/learning.py` - unlock_next_chapter

### Chapter Completion Flow

**Detection:**
- TeachingAgent sets chapter_complete flag
- Based on topic coverage or natural completion signals

**Doubt Resolution:**
- Professor confirms no remaining doubts
- Uses intent detection to understand user response
- Loops until user confirms ready to proceed

**Quiz (if configured):**
- QuizAgent generates chapter quiz
- Evaluates all answers
- Calculates final score

### Chapter Transition Process

**Step 1: Mark Chapter Complete**
- Add current chapter to completed_chapters list
- Log completion event

**Step 2: Generate Summary**
- Uses LLM to create chapter summary
- Based on topics covered and key concepts
- Stored in chapter_summary field

**Step 3: Update Progress**
- ProgressAgent updates metrics
- Creates progress snapshot
- Updates database records

**Step 4: Check Course Status**
- If current >= total chapters: Course completed
- Otherwise: Prepare next chapter

**Step 5: Unlock Next Chapter**
- Increment current_chapter
- Clear section state
- Reset pending_topics
- Update database

**Step 6: Send Transition Message**
- Show chapter summary
- If more chapters: Offer to continue
- If complete: Celebrate completion

### Handling Early Exit

**User Says "I'm done":**
1. Intent detection identifies "pause" intent
2. Current state saved to database
3. Session marked as paused
4. Progress preserved for later resume

**User Closes Browser:**
- Conversation state already persisted after each message
- Can resume from last known state
- Session recoverable from database

**Pause Signal in Temporal:**
- `pause_session` signal stops workflow
- State saved via activity
- Returns paused status with resume info

### Course Completion

**When All Chapters Done:**
- Congratulations message displayed
- Total chapters counted
- Options offered:
  - Review any topic
  - Take final assessment
  - View progress summary

**Database Updates:**
- LearningState marked complete
- Final ProgressSnapshot created
- Session deactivated

---

## Appendix: Key Configuration

### Environment Variables

```
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host/db

# Redis
REDIS_URL=redis://localhost:6379

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini

# JWT
SECRET_KEY=your-secret-key
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Google OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# Temporal
TEMPORAL_HOST=localhost:7233
```

### Key Settings (config.py)

```
# RAG Settings
chunk_size=400
chunk_overlap=50
retrieval_top_k=8
embedding_model="text-embedding-3-small"

# Teaching Settings
max_response_tokens=800
default_temperature=0.7
attention_question_min_interval=3
attention_question_max_interval=7
attention_question_probability=0.3

# Quiz Settings
questions_per_quiz=5
passing_score=0.7
```

---

## Summary

Professor is a comprehensive AI-powered learning system that transforms traditional passive chatbot interactions into an active, professor-driven educational experience. The system combines:

- **RAG Architecture**: For context-aware teaching from uploaded materials
- **Multi-Agent System**: Specialized agents for planning, teaching, quizzing, and motivation
- **State Machine**: LangGraph-based workflow for managing learning journey phases
- **Temporal Workflows**: For background processing and inactivity monitoring
- **Progress Tracking**: Comprehensive metrics for learning analytics
- **Adaptive Learning**: Dynamic adjustment based on student performance

The architecture ensures that the AI drives the learning experience while keeping the human in the loop for all major decisions.
