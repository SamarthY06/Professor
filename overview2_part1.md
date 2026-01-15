# Professor - Redesigned System Architecture (Part 1)

## Table of Contents - Part 1

1. [Project Goal and Vision](#1-project-goal-and-vision)
2. [What Professor Can Do - Complete Feature List](#2-what-professor-can-do---complete-feature-list)
3. [User Journey - Complete Flow](#3-user-journey---complete-flow)
4. [Technology Stack and Libraries](#4-technology-stack-and-libraries)
5. [UI/UX Design and Frontend Architecture](#5-uiux-design-and-frontend-architecture)
6. [Login and Authentication - Code Architecture](#6-login-and-authentication---code-architecture)
7. [PDF Upload - Code Architecture](#7-pdf-upload---code-architecture)
8. [RAG System - Code Architecture](#8-rag-system---code-architecture)
9. [Agentic Architecture - LangGraph Code Logic](#9-agentic-architecture---langgraph-code-logic)
10. [Teaching Logic - Code Architecture](#10-teaching-logic---code-architecture)

See **overview2_part2.md** for sections 11-20.

---

## 1. Project Goal and Vision

### Core Philosophy

Professor is a **Professor-Driven AI Learning System** that actively teaches, plans, tracks, motivates, and evaluates students end-to-end. Unlike traditional chatbots that passively respond to queries, Professor drives the learning journey.

**Key Differentiators:**
- **NOT a chatbot** - Professor initiates and guides conversations
- **NOT one-shot explanations** - Persistent memory and stateful learning
- **IS a dedicated professor** with memory, intent, and goals
- **IS agent-driven** - Agents drive the conversation, not intent classification
- **IS human-in-the-loop** at every major decision

### The AI Drives the Learning Journey

The system feels like a dedicated professor who:
- Understands the student's level and goals
- Plans a personalized learning path
- Teaches step-by-step interactively
- Proactively brings the student back if they disengage
- Evaluates understanding through quizzes
- Tracks progress visually
- Adapts plans dynamically

### Architecture Principles (Redesigned)

1. **Agent-Driven, Not Intent-Driven** - Agents drive conversation flow, not intent classifiers
2. **Minimal Agents** - Only 3 agents: PlannerAgent, TeacherAgent, QuizAgent
3. **Tools, Not Agents** - Retrieval is a tool for TeacherAgent, not a separate agent
4. **Orchestrator Prompts** - Complex logic handled by well-crafted prompts, not code branching
5. **Background Processing** - Summarization happens async, results available for next session
6. **Single Source of Truth** - LearningState is the only state model

### Files That Define This Vision
- `Goals.md` - Complete product specification
- `backend/app/langgraph/graph.py` - Main orchestration logic
- `backend/app/langgraph/state.py` - State machine definition

---

## 2. What Professor Can Do - Complete Feature List

### Core Learning Features

1. **PDF Upload and Processing**
   - Upload any PDF textbook or learning material
   - Automatic chapter detection (TOC-based or pattern-matching)
   - Semantic text chunking preserving context
   - Embedding generation for vector search
   - Progress tracking during processing (0-100%)
   - Error handling for corrupted, password-protected, and image-only PDFs

2. **Learning Configuration**
   - Set professor level (beginner, intermediate, advanced, research)
   - Set target completion deadline
   - Configure daily study time (30-120 minutes)
   - Choose quiz frequency (after each chapter, every N chapters, final only)
   - Select specific chapters to study
   - Configure number of questions per quiz

3. **Personalized Learning Plans**
   - AI-generated day-by-day study schedules via PlannerAgent
   - Milestone tracking
   - Plan iteration with user feedback
   - User says "I need more time" or "cover X first" → PlannerAgent regenerates

4. **Interactive Teaching**
   - TeacherAgent drives the entire teaching conversation
   - Retrieval tool fetches relevant context (current chapter + cross-chapter)
   - Previous chapter summary available for continuity
   - Handles doubts inline (no separate doubt phase)
   - Professor style adaptation (strict, balanced, encouraging)
   - Attention questions embedded naturally in teaching flow

5. **Assessment and Quizzes**
   - QuizAgent activated when user agrees to quiz
   - MCQ, True/False, and Short Answer questions
   - Adaptive difficulty based on performance
   - LLM-based answer evaluation
   - Quiz loop continues until all questions answered
   - Pass/fail with option to retry or proceed

6. **Progress Tracking**
   - Chapter completion tracking
   - Comprehension score (0-100%)
   - Attention score (0-100%)
   - Motivation score (0-100%)
   - Total study time tracking
   - Quiz pass rates
   - All tracked via utility functions, not agents

7. **Notes Feature**
   - Create notes from any content
   - Save selections from chat messages
   - Tag notes for organization
   - Pin important notes
   - Export notes (JSON, Markdown, TXT)
   - Link notes to books/chapters

8. **Motivation and Engagement**
   - Inactivity detection via Temporal
   - When inactive: LLM call generates motivation message
   - Message sent via WhatsApp/Push notification
   - Not an agent, just an async LLM call

9. **Background Summarization**
   - After chapter completion, async LLM call summarizes what was covered
   - Summary saved to database
   - Next chapter: TeacherAgent has access to this summary for continuity

10. **User Settings**
    - Professor style preference
    - Notification preferences (email, WhatsApp, push)
    - WhatsApp number configuration
    - Study schedule settings
    - Timezone configuration

11. **API Key Management**
    - Store personal OpenAI API key
    - Encrypted storage with Fernet
    - Key validation against OpenAI
    - Masked display (sk-abc****xyz7)
    - Fallback to default key

---

## 3. User Journey - Complete Flow

### Step 1: Landing Page
User arrives at the landing page showing:
- Hero section with "Meet Professor" tagline
- "Agentic OS" badge indicating multi-agent system
- Four-step flow diagram (Upload → Plan → Learn → Master)
- Agent overview (Planner, Teacher, Quiz agents)
- Feature highlights (Any Material, Progress Tracking, Always Available)

### Step 2: Authentication
User can authenticate via:
- **Email/Password Signup**: Name, email, password (8+ chars), optional phone
- **Email/Password Signin**: Email and password
- **Google OAuth**: One-click Google authentication
- **Dev Login** (development only): Quick login for testing

### Step 3: Dashboard
After login, user sees:
- Welcome message with their name
- Stats cards (Books uploaded, Processing count)
- Book cards showing processing status and progress
- Quick actions (Add New, Settings, Notes)

### Step 4: PDF Upload with Configuration
User uploads a PDF and configures:
- Target completion date (date picker)
- Daily study time (30/45/60/90/120 minutes)
- Professor level (beginner/intermediate/advanced)
- Quiz frequency (after_each_chapter/after_n_chapters/final_only)
- Chapter selection (multi-select checkbox list)

### Step 5: PDF Processing (Background via Temporal)
System processes the PDF with checkpointing:

**Phase 1: Text Extraction (0-20%)**
- Opens PDF using pdfplumber
- Extracts text from each page
- Error handling for corrupted/password-protected/scanned PDFs
- Saves checkpoint after extraction

**Phase 2: Chapter Detection (20-30%)**
- Tries TOC-based detection first
- Falls back to regex pattern matching
- If no chapters found → creates single chapter from entire document

**Phase 3: Chunking (30-50%)**
- Creates BookChapter records
- Runs semantic chunking (400 tokens target, 50 token overlap)
- Simple sliding window, split on sentence boundaries

**Phase 4: Embedding (50-85%)**
- Checks cache for existing embeddings
- Batches chunks (500 per batch, 3 parallel)
- Calls OpenAI embeddings API with retry on rate limit
- Caches new embeddings (7 day TTL)

**Phase 5: Database Storage (85-95%)**
- Bulk inserts DocumentChunk records
- Creates indexes for vector search

**Phase 6: Professor Greeting (95-100%)**
- Creates LearningState record
- Generates personalized greeting
- Saves greeting as first ChatMessage
- Sets phase to "greeting"
- Updates status to "ready"

### Step 6: Professor Auto-Greeting
When user enters learn page:
- System loads existing greeting from database
- Displays greeting with book info and chapter count
- Greeting adapts to learning_level setting
- Asks user if ready to see the learning plan

### Step 7: Learning Plan Generation (PlannerAgent)
When user accepts greeting:
- **PlannerAgent** takes over
- Analyzes book structure and chapter count
- Gets learning config (daily_minutes, deadline, selected_chapters)
- Creates day-by-day learning plan
- Shows plan summary to user
- Asks: "Does this plan work for you?"

### Step 8: Plan Review and Iteration
User responds to plan:

**If user accepts:**
- Plan marked as accepted
- Control transfers to TeacherAgent
- Start with Chapter 1

**If user wants changes:**
- User's feedback passed to PlannerAgent
- PlannerAgent regenerates plan incorporating feedback
- Loop continues until user accepts

### Step 9: Teaching Session (TeacherAgent Drives)

**TeacherAgent takes full control of the teaching conversation.**

For each interaction:
1. TeacherAgent's retrieval tool fetches relevant chunks:
   - Primary: Current chapter content
   - Secondary: Cross-chapter references (boosted lower)
   - Context: Previous chapter summary (if available)
2. TeacherAgent generates teaching response
3. TeacherAgent naturally handles:
   - Explaining concepts
   - Answering questions/doubts (no separate phase)
   - Asking attention questions when appropriate
   - Detecting when chapter content is sufficiently covered
4. When chapter is covered, TeacherAgent asks: "Ready for a quiz on this chapter?"

**Key Point:** The orchestrator prompt makes TeacherAgent smart enough to:
- Know when to explain vs answer a doubt
- Know when to ask an attention question
- Know when chapter content is complete
- Transition naturally without explicit intent classification

### Step 10: Quiz Decision
TeacherAgent asks if user is ready for quiz:

**If user says yes:**
- Control transfers to QuizAgent
- Quiz loop begins

**If user says no/not yet:**
- TeacherAgent continues teaching or reviewing
- Asks again later when appropriate

### Step 11: Chapter Quiz (QuizAgent Loop)

**QuizAgent takes control for the quiz.**

**Quiz Initialization:**
- QuizAgent generates all questions upfront
- Number based on questions_per_quiz setting
- Mix of MCQ, True/False, Short Answer
- Difficulty based on comprehension_score
- First question presented

**Quiz Loop (continues until complete):**
1. User submits answer
2. QuizAgent evaluates answer
3. Provides feedback (correct/incorrect, explanation)
4. If more questions → next question
5. If complete → calculate final score

**Quiz Completion:**
- If passed (≥70%): Congratulations, move to chapter transition
- If failed (<70%): "Would you like to retry or move on?"
  - Retry: Reset quiz, regenerate questions
  - Move on: Log failure, proceed to next chapter

### Step 12: Chapter Transition and Background Summarization

**Immediate Actions:**
1. Add chapter to completed_chapters
2. Update progress metrics
3. Create ProgressSnapshot

**Background Async Job (Fire-and-Forget):**
1. LLM call to summarize what TeacherAgent covered in this chapter
2. Summary includes: key topics, user's questions, areas of difficulty
3. Summary saved to chapter_summaries table
4. This summary will be available when TeacherAgent starts next chapter

**Next Chapter:**
- If more chapters: TeacherAgent starts next chapter with:
  - New chapter's retrieved context
  - Previous chapter's summary for continuity
- If no more chapters: Course completion

### Step 13: Course Completion
When all chapters done:
- Congratulations message
- Final statistics (chapters, time, scores)
- Options: Review any chapter, Final assessment
- Phase set to "completed"

### Step 14: Inactivity and Motivation (Temporal + LLM Call)

**Temporal monitors inactivity:**
1. Checks last_active_at every 6 hours
2. If inactive > 24 hours:
   - Makes LLM call to generate personalized motivation message
   - Message based on: days inactive, progress so far, user's style preference
   - Sends via WhatsApp/Push notification
3. Updates motivation_score
4. Not an agent, just an async LLM call triggered by Temporal

---

## 4. Technology Stack and Libraries

### Backend (Python/FastAPI)

**Web Framework:**
- `fastapi` - Async web framework with automatic OpenAPI docs
- `uvicorn` - ASGI server for FastAPI
- `pydantic` - Data validation using Python type hints
- `pydantic-settings` - Settings management from env vars

**Database:**
- `sqlalchemy` - SQL toolkit and ORM (async mode)
- `asyncpg` - Async PostgreSQL driver
- `alembic` - Database migration tool
- `pgvector` - PostgreSQL vector similarity extension

**Caching:**
- `redis` - In-memory data store
- `aioredis` - Async Redis client

**AI/ML:**
- `openai` - OpenAI API client (GPT-4, embeddings)
- `langgraph` - Agent orchestration framework
- `tiktoken` - OpenAI tokenizer for accurate token counting

**PDF Processing:**
- `pdfplumber` - PDF text extraction

**Authentication:**
- `python-jose` - JWT token handling
- `bcrypt` - Password hashing
- `cryptography` - API key encryption (Fernet)

**Background Jobs:**
- `temporalio` - Workflow orchestration (PDF processing, inactivity monitoring)

**Logging:**
- `structlog` - Structured logging with JSON output

**HTTP Client:**
- `httpx` - Async HTTP client for external APIs

### Frontend (Next.js/React)

**Framework:**
- `next` - React framework with SSR/SSG
- `react` - UI component library
- `typescript` - Type safety

**Styling:**
- `tailwindcss` - Utility-first CSS framework
- `postcss` - CSS processing

**UI Components:**
- `lucide-react` - Icon library
- `react-markdown` - Markdown rendering in chat

**State Management:**
- React Context for auth state
- Local state for UI components
- LocalStorage for token persistence

**API Communication:**
- Fetch API with custom wrapper
- Token-based authentication
- Polling for processing status (every 3 seconds)

### Infrastructure

**Containerization:**
- `docker` - Container runtime
- `docker-compose` - Multi-container orchestration

**Databases:**
- PostgreSQL 15 with pgvector extension
- Redis for caching and sessions

**Background Processing:**
- Temporal for PDF processing and inactivity monitoring

---

## 5. UI/UX Design and Frontend Architecture

### Design Philosophy

The UI follows a modern, clean design with:
- Blue as primary color (#2563eb / blue-600)
- Gray scale for text and backgrounds
- Rounded corners (rounded-lg, rounded-xl)
- Subtle shadows and borders
- Gradient accents (Professor avatar: blue to purple)

### Page Structure

**Landing Page (web/src/app/page.tsx):**
- Hero section with gradient background
- Step cards showing user journey
- Agent cards explaining the three agents
- Feature highlights strip
- Call-to-action buttons

**Dashboard (web/src/app/dashboard/page.tsx):**
- Sticky header with logo and navigation
- Welcome section with personalized greeting
- Stats cards in 3-column grid
- Book cards with processing status
- Dropdown menu for actions (delete, reprocess)

**Learn Page (web/src/app/learn/[id]/page.tsx):**
- Collapsible sidebar with book info
- Chapter list with completion indicators
- Learning metrics display
- Main chat area with message bubbles
- Typing indicator during loading
- Input area with send button
- Selection-to-notes floating button

**Configure Page (web/src/app/learn/[id]/configure/page.tsx):**
- Form sections for each configuration
- Button groups for single-select options
- Checkbox list for chapter selection
- Summary preview of settings
- Save and cancel actions

### Component Architecture

**MessageBubble:**
- Differentiates user (right, blue) vs assistant (left, white)
- Markdown rendering for formatted text
- Agent name badge (Professor, Planner, Quiz Master)
- Save-to-notes hover button
- Quiz question styling (yellow background)

**ChapterItem:**
- Circle with chapter number or checkmark
- Current chapter highlight (blue)
- Completed chapter indicator (green)
- Locked chapter with lock icon

**TypingIndicator:**
- Three bouncing dots
- Professor avatar
- Smooth animation

### Responsive Design
- Mobile-first approach
- Sidebar collapses on mobile
- Grid layouts adjust column count
- Touch-friendly button sizes

### Frontend Files Structure

```
web/src/
├── app/
│   ├── page.tsx              # Landing page
│   ├── layout.tsx            # Root layout with providers
│   ├── globals.css           # Global styles (Tailwind)
│   ├── login/page.tsx        # Login page
│   ├── signin/page.tsx       # Sign in page
│   ├── signup/page.tsx       # Sign up page
│   ├── dashboard/page.tsx    # Main dashboard
│   ├── learn/[id]/
│   │   ├── page.tsx          # Learning interface
│   │   └── configure/page.tsx # Configuration
│   ├── notes/page.tsx        # Notes management
│   ├── settings/page.tsx     # User settings
│   └── admin/page.tsx        # Admin dashboard
├── components/
│   ├── Providers.tsx         # Context providers
│   └── SelectionToNotes.tsx  # Text selection handler
├── contexts/
│   └── AuthContext.tsx       # Authentication context
└── lib/
    ├── api.ts                # API client with polling
    └── notes-store.ts        # Notes local storage
```

---

## 6. Login and Authentication - Code Architecture

### Files Involved
- `backend/app/api/auth.py` - Authentication endpoints
- `backend/app/security/jwt.py` - JWT token creation/verification
- `backend/app/models/user.py` - User, UserAuth, UserSession models
- `backend/app/dependencies.py` - Authentication middleware
- `web/src/contexts/AuthContext.tsx` - Frontend auth state

### Password Authentication Logic

**Signup Flow (/api/auth/signup):**
1. Receives email, password, name, optional phone
2. Validates password length (minimum 8 characters)
3. Checks if email already exists
4. Hashes password using bcrypt
5. Creates User record
6. Creates UserSettings record with defaults
7. Generates JWT access token (24 hours) and refresh token (7 days)
8. Returns tokens to frontend

**Signin Flow (/api/auth/signin):**
1. Receives email and password
2. Queries User by email
3. Returns 401 if user not found
4. Verifies password using bcrypt
5. Returns 401 if password doesn't match
6. Checks is_active flag
7. Generates new JWT tokens
8. Returns tokens to frontend

### Google OAuth Logic

**OAuth Flow (/api/auth/google):**
1. Receives authorization code from frontend
2. Exchanges code for Google access token
3. Fetches user info from Google
4. Checks if user exists by Google ID or email
5. Creates new user if not exists
6. Links Google account if user exists by email
7. Creates default UserSettings for new users
8. Generates JWT tokens
9. Returns tokens to frontend

### JWT Token Logic

**Access Token Creation:**
1. Builds payload with: user_id, expiration (24h), type ("access")
2. Encodes using HS256 algorithm
3. Signs with secret_key

**Token Verification:**
1. Decodes JWT
2. Validates algorithm and type
3. Returns user_id if valid

### Authentication Middleware

**Dependency (get_current_user_id):**
1. Extracts token from Authorization header
2. Verifies token
3. Returns user_id or raises 401

---

## 7. PDF Upload - Code Architecture

### Files Involved
- `backend/app/api/books.py` - Upload endpoints
- `backend/app/rag/ingestion.py` - Processing pipeline
- `backend/app/models/book.py` - Book, BookChapter models
- `backend/app/temporal/workflows/pdf_processing.py` - Temporal workflow

### Upload Endpoint Logic

**File Upload (/api/books/upload):**
1. Receives multipart form data with file, title, author
2. Validates file extension is ".pdf"
3. Validates file size (max 50MB)
4. Generates unique filename
5. Saves file to storage
6. Creates Book record with status "pending"
7. Starts Temporal workflow for processing
8. Returns immediately with book_id

**Upload with Config (/api/books/upload-with-config):**
1. Same as upload plus creates LearningConfig record

### Processing Pipeline (Temporal Workflow)

**PDFProcessingWorkflow with checkpointing:**

**Phase 1: Text Extraction (0-20%)**
- Opens PDF using pdfplumber
- Error handling:
  - Corrupted PDF → mark failed with message
  - Password protected → mark failed with message
  - No text (scanned) → mark failed with message
- Extracts text from each page
- Saves checkpoint

**Phase 2: Chapter Detection (20-30%)**
- Tries TOC-based detection (first 15 pages)
- Falls back to regex patterns
- If no chapters → single chapter from entire document
- Saves checkpoint

**Phase 3: Chunking (30-50%)**
- Creates BookChapter records
- Semantic chunking: 400 tokens, 50 overlap
- Split on sentence boundaries
- Saves checkpoint

**Phase 4: Embedding (50-85%)**
- Checks Redis cache by content_hash
- Batches uncached chunks (500 per batch)
- Calls OpenAI embeddings API
- Retry with exponential backoff on rate limit
- Caches new embeddings (7 day TTL)
- Saves checkpoint

**Phase 5: Database Storage (85-95%)**
- Bulk inserts DocumentChunk records

**Phase 6: Professor Greeting (95-100%)**
- Creates LearningState (phase="greeting", chapter=1)
- Generates personalized greeting based on learning_level
- Saves greeting as ChatMessage
- Updates book status to "ready"

### Frontend Polling

- Checks GET /api/books/{id}/status every 3 seconds
- Shows progress bar and current step
- Stops polling when status is "ready" or "failed"

---

## 8. RAG System - Code Architecture

### Files Involved
- `backend/app/rag/chunking.py` - SimpleChunker class
- `backend/app/rag/embeddings.py` - EmbeddingService class
- `backend/app/rag/retrieval.py` - Retrieval tool functions
- `backend/app/rag/chapter_detection.py` - ChapterDetector class

### Chunking Logic

**SimpleChunker:**
- Target size: 400 tokens
- Overlap: 50 tokens
- Uses tiktoken for token counting

**Algorithm:**
1. Split text by sentence boundaries
2. Accumulate sentences until target size
3. When exceeding target, save chunk with overlap
4. Generate content_hash (SHA256) for each chunk

### Embedding Logic

**EmbeddingService:**
- Model: text-embedding-ada-002
- Dimensions: 1536
- Batch size: 500
- Parallel batches: 3

**Caching:**
- Cache key: emb:{content_hash}
- TTL: 7 days
- Check cache before embedding
- Cache new embeddings async

### Retrieval Tool (For TeacherAgent)

**This is a TOOL, not an agent.** TeacherAgent calls this tool to get context.

**retrieve_context(query, book_id, current_chapter) Logic:**

1. Generate query embedding

2. **Primary Query (Current Chapter - High Priority):**
   - Filter: book_id AND chapter_number = current_chapter
   - Get top 6 chunks by cosine similarity
   - Apply boost factor of 1.5 to scores

3. **Secondary Query (Other Chapters - Lower Priority):**
   - Filter: book_id AND chapter_number != current_chapter
   - Get top 3 chunks by cosine similarity
   - No boost (for cross-references)

4. **Merge Results:**
   - Combine both result sets
   - Sort by boosted similarity
   - Take top 8 chunks total
   - Include chapter info for each chunk

5. **Add Chapter Summary (If Available):**
   - Query chapter_summaries for previous chapters
   - Include most recent summary in context

6. **Return Context Object:**
   - retrieved_chunks: Array of chunk content with metadata
   - previous_summary: String or null
   - cross_chapter_refs: Chapters referenced from other chapters

**Vector Search SQL:**
```
SELECT 
  dc.content,
  bc.chapter_number,
  bc.title,
  1 - (dc.embedding <=> :query_embedding) as similarity
FROM document_chunks dc
JOIN book_chapters bc ON dc.chapter_id = bc.id
WHERE dc.book_id = :book_id
  AND bc.chapter_number [filter condition]
ORDER BY dc.embedding <=> :query_embedding
LIMIT :limit
```

---

## 9. Agentic Architecture - LangGraph Code Logic

### Files Involved
- `backend/app/langgraph/graph.py` - Main workflow
- `backend/app/langgraph/state.py` - ProfessorState definition
- `backend/app/agents/planner.py` - PlannerAgent
- `backend/app/agents/teacher.py` - TeacherAgent
- `backend/app/agents/quiz.py` - QuizAgent
- `backend/app/tools/retrieval.py` - Retrieval tool for TeacherAgent

### Three Agents Only

**1. PlannerAgent**
- Responsibility: Generate and iterate learning plans
- Input: Book structure, learning config, user feedback
- Output: Day-by-day learning plan
- Active during: Plan generation and iteration phase

**2. TeacherAgent**
- Responsibility: Drive the entire teaching conversation
- Has Tool: Retrieval tool (fetches RAG context)
- Input: User message, retrieved context, previous summary
- Output: Teaching response
- Handles: Explaining, answering doubts, attention questions, chapter completion detection
- Active during: All teaching interactions

**3. QuizAgent**
- Responsibility: Generate quiz questions, evaluate answers
- Input: Chapter content, user answers
- Output: Questions, evaluations, final score
- Active during: Quiz phase only (when user agrees to quiz)

### What's NOT an Agent

**Retrieval** - It's a tool that TeacherAgent uses, not a separate agent

**Motivation** - It's an async LLM call triggered by Temporal, not an agent

**Progress Tracking** - It's utility functions, not an agent

**Summarization** - It's a background async LLM call, not an agent

### State Definition

**ProfessorState (TypedDict):**

**Identity:**
- user_id: UUID
- session_id: UUID
- book_id: UUID
- book_title: str

**Phase:**
- phase: "greeting" | "planning" | "teaching" | "quiz" | "chapter_transition" | "completed" | "paused"
- active_agent: "planner" | "teacher" | "quiz"

**User Input:**
- user_message: str

**Output:**
- professor_response: str
- agent_name: str

**Chapter State:**
- current_chapter: int
- total_chapters: int
- chapters_completed: list[int]
- chapter_title: str

**Teaching State:**
- topics_covered_this_chapter: list[str]
- previous_chapter_summary: str (from DB)
- retrieved_context: list[dict] (from retrieval tool)

**Quiz State:**
- quiz_questions: list[dict]
- quiz_current_index: int
- quiz_scores: list[float]
- quiz_passed: bool | None

**Plan State:**
- plan_accepted: bool
- plan_data: dict

**Config:**
- learning_level: str
- daily_study_minutes: int
- quiz_frequency: str
- questions_per_quiz: int
- professor_style: str

**Metrics:**
- comprehension_score: float
- attention_score: float
- motivation_score: float
- total_study_time_minutes: int

### Graph Structure

**Nodes:**
1. greeting_node - Display greeting, wait for acceptance
2. planner_node - PlannerAgent generates/iterates plan
3. teacher_node - TeacherAgent teaches (main node)
4. quiz_node - QuizAgent runs quiz
5. chapter_transition_node - Complete chapter, trigger summarization
6. completion_node - Course completed

**Flow (Agent-Driven, Not Intent-Driven):**

```
greeting_node
    ↓ (user accepts)
planner_node ←──────────────┐
    ↓ (plan generated)      │
    ↓ (user wants changes)──┘
    ↓ (user accepts plan)
teacher_node ←──────────────┐
    ↓ (teaching continues)──┘
    ↓ (chapter complete, user says yes to quiz)
quiz_node ←─────────────────┐
    ↓ (quiz continues)──────┘
    ↓ (quiz complete)
chapter_transition_node
    ↓ (more chapters) → teacher_node
    ↓ (no more chapters)
completion_node
```

### How Agents Drive (Not Intent Classification)

**Traditional Intent-Driven (What We're NOT Doing):**
1. User sends message
2. Classify intent (question? doubt? accept? reject?)
3. Route based on intent
4. Call appropriate handler

**Agent-Driven (What We ARE Doing):**
1. User sends message
2. Pass to active agent (TeacherAgent during teaching)
3. Agent's orchestrator prompt handles everything:
   - If user asks question → agent answers it
   - If user seems confused → agent re-explains
   - If chapter content covered → agent asks about quiz
   - If user says ready for quiz → agent signals phase change
4. Agent returns response AND any state changes needed

**The orchestrator prompt makes the agent intelligent enough to handle all cases without explicit intent classification.**

### Message Processing Flow

**process_message(state, user_message):**
1. Load LearningState from database
2. Determine active_agent from phase:
   - greeting/planning → PlannerAgent
   - teaching → TeacherAgent
   - quiz → QuizAgent
3. If TeacherAgent:
   - Call retrieval tool to get context
   - Include previous_chapter_summary from DB
4. Pass state + user_message to active agent
5. Agent returns:
   - response: The message to show user
   - state_updates: Any state changes (phase, scores, etc.)
6. Apply state_updates
7. Persist to LearningState
8. Update last_active_at
9. Save ChatMessage
10. Return response

---

## 10. Teaching Logic - Code Architecture

### Files Involved
- `backend/app/agents/teacher.py` - TeacherAgent
- `backend/app/tools/retrieval.py` - Retrieval tool
- `backend/app/services/progress.py` - Progress utility functions

### TeacherAgent Overview

TeacherAgent is the main agent that drives the teaching conversation. It has access to a retrieval tool and handles everything during the teaching phase.

### TeacherAgent.process() Logic

**Input:**
- user_message: Current user input
- state: Full ProfessorState

**Step 1: Call Retrieval Tool**
1. TeacherAgent calls retrieve_context tool with:
   - query: user_message (or "teach chapter X" if starting new chapter)
   - book_id: from state
   - current_chapter: from state
2. Tool returns:
   - retrieved_chunks: Relevant content from current + other chapters
   - previous_summary: Summary of last chapter (if exists)

**Step 2: Build Orchestrator Prompt**

The orchestrator prompt is the key to agent-driven behavior. It instructs TeacherAgent how to handle all scenarios.

**System Prompt Structure:**
```
You are Professor, teaching {book_title} to a {learning_level} student.
Your style is {professor_style}.

Current Chapter: {current_chapter} - {chapter_title}
Topics Covered So Far: {topics_covered_this_chapter}

Previous Chapter Summary:
{previous_summary or "This is the first chapter."}

Retrieved Context:
{formatted_chunks}

Your responsibilities:
1. TEACH the material from the retrieved context
2. ANSWER any questions the student asks (don't say "let's move to doubts")
3. Naturally CHECK understanding by asking questions occasionally
4. DETECT when you've covered the main topics of this chapter
5. When chapter content is sufficiently covered, ASK if student is ready for a quiz

Important:
- Handle doubts inline, don't create separate phases
- If student asks about something from a previous chapter, use the cross-chapter context
- Reference the previous chapter summary for continuity
- Track what topics you've explained

When you've covered the chapter and student seems ready, end your response with:
[CHAPTER_COMPLETE: ready_for_quiz]

If student agrees to quiz, end your response with:
[START_QUIZ]
```

**Step 3: Generate Response**
1. Call OpenAI GPT-4 with orchestrator prompt + user message
2. Temperature: 0.7
3. Max tokens: 600

**Step 4: Parse Response for Signals**
1. Check for [CHAPTER_COMPLETE: ready_for_quiz] → TeacherAgent will ask about quiz
2. Check for [START_QUIZ] → Transition to quiz phase
3. Extract topics mentioned → Add to topics_covered_this_chapter

**Step 5: Update Progress**
1. Call update_study_time(state, 2) - Add 2 minutes
2. If attention question was asked and answered:
   - Call update_attention_score(state, correct)

**Step 6: Return Result**
- response: Generated text (with signals stripped)
- state_updates: {topics_covered, phase change if any}

### Retrieval Tool

**retrieve_context(query, book_id, current_chapter):**

This is a tool function, not an agent. TeacherAgent calls it.

1. Generate embedding for query
2. Query current chapter chunks (top 6, boosted)
3. Query other chapter chunks (top 3, for cross-reference)
4. Merge and sort by similarity
5. Load previous chapter summary from DB
6. Return context object

### How TeacherAgent Handles Different Scenarios

**User asks a question:**
- Orchestrator prompt says "ANSWER any questions"
- TeacherAgent naturally answers using retrieved context
- No intent classification needed

**User seems confused:**
- TeacherAgent detects confusion from message
- Re-explains using different approach
- Orchestrator prompt guides this behavior

**User asks about previous chapter:**
- Cross-chapter chunks are in retrieved context
- Previous summary is available
- TeacherAgent references them naturally

**Chapter content is covered:**
- TeacherAgent tracks topics_covered
- When sufficient, adds [CHAPTER_COMPLETE] signal
- Asks user if ready for quiz

**User agrees to quiz:**
- TeacherAgent adds [START_QUIZ] signal
- Phase transitions to quiz
- QuizAgent takes over

### Attention Questions (Embedded in Teaching)

TeacherAgent naturally asks comprehension questions as part of teaching. The orchestrator prompt includes:

```
Occasionally check understanding by asking a quick question about what you just explained.
Don't make it formal - just naturally ask "Does that make sense?" or 
"Quick check - what would happen if...?"
```

When user answers:
- TeacherAgent evaluates inline
- Updates attention_score via utility function
- Continues teaching

### Progress Utility Functions

**update_study_time(state, minutes):**
- state.total_study_time_minutes += minutes

**update_attention_score(state, correct):**
- If correct: += 0.1 (max 1.0)
- If incorrect: -= 0.15 (min 0.0)

**add_topic_covered(state, topic):**
- Append to topics_covered_this_chapter
- If list > 20, summarize old topics

---

*Continued in overview2_part2.md*
