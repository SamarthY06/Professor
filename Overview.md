# Professor - Complete System Architecture and Code Overview

## Table of Contents

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
11. [Quiz Logic - Code Architecture](#11-quiz-logic---code-architecture)
12. [Doubt Resolution - Code Architecture](#12-doubt-resolution---code-architecture)
13. [Motivation Agent - Code Architecture](#13-motivation-agent---code-architecture)
14. [Temporal Workflows - Code Architecture](#14-temporal-workflows---code-architecture)
15. [Progress Tracking - Code Architecture](#15-progress-tracking---code-architecture)
16. [Notes Feature - Code Architecture](#16-notes-feature---code-architecture)
17. [Session Management and Ending - Code Architecture](#17-session-management-and-ending---code-architecture)
18. [Configuration System - All Settings](#18-configuration-system---all-settings)
19. [Database Models - Complete Schema](#19-database-models---complete-schema)
20. [API Endpoints - Complete Reference](#20-api-endpoints---complete-reference)

---

## 1. Project Goal and Vision

### Core Philosophy

Professor is a **Professor-Driven AI Learning System** that actively teaches, plans, tracks, motivates, and evaluates students end-to-end. Unlike traditional chatbots that passively respond to queries, Professor drives the learning journey.

**Key Differentiators:**
- **NOT a chatbot** - Professor initiates and guides conversations
- **NOT one-shot explanations** - Persistent memory and stateful learning
- **IS a dedicated professor** with memory, intent, and goals
- **IS agent-driven, event-driven, and stateful**
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

2. **Learning Configuration**
   - Set professor level (beginner, intermediate, advanced, research)
   - Set target completion deadline
   - Configure daily study time (30-120 minutes)
   - Choose quiz frequency (after each chapter, every N chapters, final only)
   - Select specific chapters to study
   - Configure number of questions per quiz

3. **Personalized Learning Plans**
   - AI-generated day-by-day study schedules
   - Milestone tracking
   - Plan iteration with user feedback
   - Dynamic plan adaptation based on performance

4. **Interactive Teaching**
   - Chapter-by-chapter, topic-by-topic instruction
   - RAG-powered context-aware responses
   - Attention questions to check engagement
   - Cross-chapter reference detection
   - Professor style adaptation (strict, balanced, encouraging)

5. **Assessment and Quizzes**
   - MCQ, True/False, and Short Answer questions
   - Adaptive difficulty based on performance
   - LLM-based answer evaluation
   - Detailed feedback and explanations
   - Pass/fail with retry mechanism

6. **Progress Tracking**
   - Chapter completion tracking
   - Comprehension score (0-100%)
   - Attention score (0-100%)
   - Motivation score (0-100%)
   - Total study time tracking
   - Quiz pass rates

7. **Notes Feature**
   - Create notes from any content
   - Save selections from chat messages
   - Tag notes for organization
   - Pin important notes
   - Export notes (JSON, Markdown, TXT)
   - Link notes to books/chapters

8. **Motivation and Engagement**
   - Inactivity detection via Temporal workflows
   - Personalized encouragement messages
   - WhatsApp notification integration
   - Push notification support
   - Progress snapshots and celebrations

9. **User Settings**
   - Professor style preference
   - Notification preferences (email, WhatsApp, push)
   - WhatsApp number configuration
   - Study schedule settings
   - Timezone configuration

10. **API Key Management**
    - Store personal OpenAI API key
    - Encrypted storage with Fernet
    - Key validation against OpenAI
    - Masked display (sk-abc****xyz7)
    - Fallback to default key

11. **Admin Features**
    - Dashboard with user statistics
    - User management
    - System health monitoring
    - Feature flags

---

## 3. User Journey - Complete Flow

### Step 1: Landing Page
User arrives at the landing page showing:
- Hero section with "Meet Professor" tagline
- "Agentic OS" badge indicating multi-agent system
- Four-step flow diagram (Upload → Plan → Learn → Master)
- Agent swarm section (Teaching, Quiz, Motivation agents)
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
- Stats cards (Books uploaded, Goals created, Processing count)
- Tab navigation (My Books / Learning Goals)
- Book cards showing processing status and progress
- Quick actions (Add New, Settings, Notes)

### Step 4: PDF Upload with Configuration
User uploads a PDF and configures:
- Target completion date (date picker)
- Daily study time (30/45/60/90/120 minutes)
- Professor level (beginner/intermediate/advanced)
- Quiz frequency (after_each_chapter/after_n_chapters/final_only)
- Chapter selection (multi-select checkbox list)

### Step 5: PDF Processing (Background)
System processes the PDF:
- Text extraction (pdfplumber)
- Chapter detection (TOC or regex patterns)
- Semantic chunking (400 tokens target)
- Embedding generation (OpenAI text-embedding-ada-002)
- Database storage (PostgreSQL + pgvector)
- Progress updates via polling (every 3 seconds)

### Step 6: Professor Auto-Greeting
When processing completes:
- System automatically creates conversation state
- Generates personalized greeting based on book and config
- Saves greeting as first chat message
- Sets phase to "greeting"
- User sees greeting when entering learn page

### Step 7: Learning Plan Generation
When user accepts greeting prompt:
- PlannerAgent analyzes book structure
- Creates day-by-day learning plan
- Shows plan summary with:
  - Total duration
  - Daily schedule
  - Milestones
  - Chapter breakdown

### Step 8: Plan Review and Iteration
User can:
- Accept the plan and start learning
- Request modifications (more/fewer days, different focus)
- PlannerAgent regenerates based on feedback
- Loop continues until explicit acceptance

### Step 9: Teaching Session
Professor teaches chapter-by-chapter:
- RetrievalAgent fetches relevant content
- TeachingAgent generates explanations
- ProgressAgent tracks metrics
- Attention questions appear periodically
- User can ask questions at any time

### Step 10: Chapter Completion and Doubt Resolution
When chapter content is covered:
- Professor asks if user has doubts
- User can ask unlimited questions
- Each doubt answered using RAG context
- Continues until user confirms no more doubts

### Step 11: Chapter Quiz
After doubts cleared:
- QuizAgent generates questions
- One question at a time
- Immediate feedback per question
- Final score calculation
- Pass (70%+) or retry

### Step 12: Chapter Transition
If quiz passed:
- Chapter summary generated
- Progress updated
- Next chapter unlocked
- Motivation boost message
- Transition to next chapter or completion

### Step 13: Course Completion
When all chapters done:
- Congratulations message
- Final summary
- Options: Review, Final assessment
- Progress statistics

---

## 4. Technology Stack and Libraries

### Backend (Python/FastAPI)

**Web Framework:**
- `fastapi` - Async web framework with automatic OpenAPI docs
- `uvicorn` - ASGI server for FastAPI
- `pydantic` - Data validation using Python type hints
- `pydantic-settings` - Settings management from env vars

**Database:**
- `sqlalchemy` - SQL toolkit and ORM
- `asyncpg` - Async PostgreSQL driver
- `alembic` - Database migration tool
- `pgvector` - PostgreSQL vector similarity extension

**Caching:**
- `redis` - In-memory data store
- `aioredis` - Async Redis client

**AI/ML:**
- `openai` - OpenAI API client (GPT-4, embeddings)
- `langgraph` - Multi-agent orchestration framework
- `tiktoken` - OpenAI tokenizer for accurate token counting

**PDF Processing:**
- `pdfplumber` - PDF text extraction

**Authentication:**
- `python-jose` - JWT token handling
- `bcrypt` - Password hashing
- `cryptography` - API key encryption (Fernet)

**Background Jobs:**
- `temporalio` - Workflow orchestration engine

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

### Infrastructure

**Containerization:**
- `docker` - Container runtime
- `docker-compose` - Multi-container orchestration

**Databases:**
- PostgreSQL 15 with pgvector extension
- Redis for caching and sessions

**Workflow Engine:**
- Temporal for long-running workflows

---

## 5. UI/UX Design and Frontend Architecture

### Design Philosophy

The UI follows a modern, clean design with:
- Blue as primary color (`#2563eb` / `blue-600`)
- Gray scale for text and backgrounds
- Rounded corners (`rounded-lg`, `rounded-xl`)
- Subtle shadows and borders
- Gradient accents (Professor avatar: blue to purple)

### Page Structure

**Landing Page (`web/src/app/page.tsx`):**
- Hero section with gradient background
- Step cards showing user journey
- Agent cards explaining the swarm
- Feature highlights strip
- Call-to-action buttons

**Dashboard (`web/src/app/dashboard/page.tsx`):**
- Sticky header with logo and navigation
- Welcome section with personalized greeting
- Stats cards in 3-column grid
- Tab navigation for Books/Goals
- Book cards with processing status
- Dropdown menu for actions (delete, reprocess)

**Learn Page (`web/src/app/learn/[id]/page.tsx`):**
- Collapsible sidebar with book info
- Chapter list with completion indicators
- Learning metrics display
- Main chat area with message bubbles
- Typing indicator during loading
- Input area with send button
- Selection-to-notes floating button

**Configure Page (`web/src/app/learn/[id]/configure/page.tsx`):**
- Form sections for each configuration
- Button groups for single-select options
- Checkbox list for chapter selection
- Summary preview of settings
- Save and cancel actions

### Component Architecture

**MessageBubble:**
- Differentiates user (right, blue) vs assistant (left, white)
- Markdown rendering for formatted text
- Agent name badge
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
│   │   ├── configure/page.tsx # Configuration
│   │   └── plan/page.tsx     # Plan view
│   ├── notes/page.tsx        # Notes management
│   ├── settings/page.tsx     # User settings
│   ├── quiz/[id]/page.tsx    # Quiz interface
│   └── admin/page.tsx        # Admin dashboard
├── components/
│   ├── Providers.tsx         # Context providers
│   └── SelectionToNotes.tsx  # Text selection handler
├── contexts/
│   └── AuthContext.tsx       # Authentication context
└── lib/
    ├── api.ts                # API client
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

**Signup Flow (`/api/auth/signup`):**
1. Receives email, password, name, optional phone
2. Validates password length (minimum 8 characters) using Pydantic validator
3. Checks if email already exists in `users` table using SQLAlchemy select
4. Hashes password using `bcrypt.hashpw()` with auto-generated salt
5. Creates User record with email, hashed password, name, phone
6. Creates UserSettings record with default values
7. Generates JWT access token (24 hours) and refresh token (7 days)
8. Returns tokens to frontend

**Signin Flow (`/api/auth/signin`):**
1. Receives email and password
2. Queries User by email using SQLAlchemy
3. Returns 401 if user not found
4. Verifies password using `bcrypt.checkpw()` against stored hash
5. Returns 401 if password doesn't match
6. Checks `is_active` flag, returns 403 if deactivated
7. Generates new JWT tokens
8. Returns tokens to frontend

### Google OAuth Logic

**OAuth Flow (`/api/auth/google`):**
1. Receives authorization code and redirect URI from frontend
2. Exchanges code for Google access token using `httpx.AsyncClient`
3. Posts to `oauth2.googleapis.com/token` with client credentials
4. Fetches user info from `googleapis.com/oauth2/v2/userinfo`
5. Extracts Google user ID, email, and name
6. Queries `user_auth` table for existing Google link
7. If found: User exists, get user_id
8. If not found by Google ID:
   - Check if user exists by email
   - If exists: Link Google account to existing user
   - If not exists: Create new User and UserAuth records
9. Creates default UserSettings for new users
10. Generates JWT tokens
11. Returns tokens to frontend

### JWT Token Logic

**Access Token Creation (`create_access_token`):**
1. Calculates expiration time (default: 24 hours from now)
2. Builds payload with: subject (user_id), expiration, type ("access"), issued_at
3. Encodes using `jose.jwt.encode()` with HS256 algorithm
4. Signs with `settings.secret_key`
5. Returns encoded JWT string

**Refresh Token Creation (`create_refresh_token`):**
1. Same as access token but with 7-day expiration
2. Sets type to "refresh"
3. Used to obtain new access tokens without re-login

**Token Verification (`verify_access_token`):**
1. Decodes JWT using `jose.jwt.decode()` with secret key
2. Validates algorithm is HS256
3. Checks token type equals "access"
4. Returns payload if valid, None if invalid or expired
5. Catches JWTError for invalid tokens

### Authentication Middleware

**Dependency (`get_current_user_id`):**
1. Extracts token from Authorization header
2. Expects format: "Bearer {token}"
3. Calls `verify_access_token()` to validate
4. Raises 401 HTTPException if invalid
5. Returns user_id UUID from token payload

### Database Models

**User Model:**
- `id`: UUID primary key
- `email`: Unique, indexed string
- `password_hash`: Optional bcrypt hash
- `name`: Required string
- `phone`: Optional string
- `role`: "student", "admin", or "superadmin"
- `is_active`: Boolean for account status
- Relationships: auth_providers, sessions, settings, api_key

**UserAuth Model:**
- Links User to OAuth providers
- `provider`: "google", "github", etc.
- `provider_user_id`: ID from OAuth provider
- Enables multiple auth methods per user

**UserSession Model:**
- Tracks active sessions
- `token_hash`: For session invalidation
- `device_info`: JSON with browser/device details
- `expires_at`: Session expiration
- Enables logout from all devices

---

## 7. PDF Upload - Code Architecture

### Files Involved
- `backend/app/api/books.py` - Upload endpoints
- `backend/app/rag/ingestion.py` - Processing pipeline
- `backend/app/models/book.py` - Book, BookChapter models
- `backend/app/models/learning_config.py` - LearningConfig model

### Upload Endpoint Logic

**File Upload (`/api/books/upload`):**
1. Receives multipart form data with file, title, author
2. Validates file extension is ".pdf"
3. Validates file size against `max_file_size_mb` setting
4. Generates unique filename: `{timestamp}_{hash}_{originalname}`
5. Saves file to `pdf_storage_path` directory
6. Creates Book record with status "pending"
7. Spawns background task for processing
8. Returns immediately (non-blocking)

**Upload with Config (`/api/books/upload-with-config`):**
1. Same as upload plus:
2. Creates LearningConfig record with user preferences
3. Stores: learning_level, total_days, daily_minutes, quiz_frequency
4. Links config to book via book_id

### Processing Pipeline Logic

**PDFIngestionService.process_book():**

**Phase 1: Text Extraction (5-20%)**
1. Updates progress to 10%
2. Calls `_extract_text_async()` which runs in thread pool
3. Opens PDF using `pdfplumber.open()`
4. Iterates through pages, extracting text
5. Returns list of (page_number, text) tuples
6. Updates book.total_pages

**Phase 2: Chapter Detection (20-30%)**
1. Updates progress to 25%
2. Calls `ChapterDetector.detect_chapters()`
3. First tries TOC-based detection (searches first 15 pages)
4. Looks for "Table of Contents" patterns
5. Parses chapter entries with page numbers
6. If no TOC, uses regex pattern matching on each page
7. Patterns: "Chapter N", "CHAPTER N", "Part N", "Section N", etc.
8. Extracts chapter number and title from matches
9. Sets start_page and end_page for each chapter
10. If no chapters found, creates single chapter from entire document
11. Updates book.total_chapters

**Phase 3: Chunking (30-50%)**
1. Updates progress to 35%
2. Creates BookChapter records in database
3. Estimates reading duration (page_count * 300 words / 200 wpm * 1.5)
4. Runs `SmartChunker.chunk_chapter()` in parallel using thread pool
5. For each chapter:
   - Extracts chapter text from pages
   - Splits by sections (markdown headers, all-caps)
   - Splits sections into paragraphs
   - Accumulates paragraphs until target size (400 tokens)
   - Handles overlap (50 tokens) for context continuity
   - Creates Chunk objects with content, hash, token count
6. Updates progress to 50%

**Phase 4: Embedding (50-85%)**
1. Updates progress to 55%
2. Collects all chunks from all chapters
3. Calls `EmbeddingService.embed_chunks()`
4. Checks cache for existing embeddings by content_hash
5. Creates batches of 500 chunks
6. Processes 3 batches in parallel
7. For each batch:
   - Calls OpenAI embeddings API with batch of texts
   - Assigns embeddings to chunk objects
   - Caches embeddings asynchronously
8. Updates progress to 85%

**Phase 5: Database Storage (85-95%)**
1. Updates progress to 90%
2. Creates DocumentChunk records for each chunk
3. Stores: content, embedding vector, metadata
4. Bulk insert using SQLAlchemy

**Phase 6: Professor Greeting (95-100%)**
1. Updates book status to "ready_for_planning"
2. Creates LearningState for user/book
3. Creates ConversationState with phase "greeting"
4. Creates ChatSession
5. Generates greeting message
6. Saves greeting as ChatMessage
7. Updates progress to 100%

### Greeting Generation Logic

**trigger_professor_greeting():**
1. Gets or creates LearningState record
2. Gets LearningConfig for personalization
3. Selects level_note based on learning_level:
   - beginner: "I'll explain concepts clearly with plenty of examples."
   - intermediate: "I'll balance depth with clarity."
   - advanced: "I'll dive deep into technical details."
   - research: "I'll focus on advanced analysis."
4. Builds greeting template with book title and chapter count
5. Creates ChatMessage with role="assistant"
6. Sets agent_name="Professor"
7. Commits to database

---

## 8. RAG System - Code Architecture

### Files Involved
- `backend/app/rag/chunking.py` - SmartChunker class
- `backend/app/rag/embeddings.py` - EmbeddingService class
- `backend/app/rag/retrieval.py` - Retrieval functions
- `backend/app/rag/chapter_detection.py` - ChapterDetector class
- `backend/app/agents/retrieval.py` - RetrievalAgent

### Chunking Logic

**SmartChunker Configuration:**
- `target_size`: 400 tokens (from settings.chunk_size)
- `min_size`: 200 tokens (50% of target)
- `max_size`: 600 tokens (150% of target)
- `overlap`: 50 tokens (from settings.chunk_overlap)
- Uses `tiktoken` for accurate token counting

**Section Detection (`_split_by_sections`):**
1. Regex pattern: `^#{1,3}\s+(.+)$|^([A-Z][A-Z\s]+)$`
2. Matches markdown headers (##, ###) and all-caps headings
3. Splits text into Section objects with title and content
4. Preserves section titles for metadata

**Paragraph Chunking (`_chunk_section`):**
1. Splits section by double newlines (paragraphs)
2. Iterates through paragraphs:
3. Counts tokens for each paragraph
4. If paragraph > max_size: splits by sentences
5. Accumulates paragraphs into current chunk
6. When adding would exceed max_size:
   - Saves current chunk if >= min_size
   - Starts new chunk with overlap from previous
7. Creates Chunk objects with:
   - content: Joined paragraphs
   - content_hash: SHA256 for deduplication
   - token_count: Accurate count
   - section_title: From parent section
   - metadata: chapter_id, book_id, page_offset

**Large Paragraph Handling (`_chunk_large_paragraph`):**
1. Splits by sentence boundaries: `(?<=[.!?])\s+`
2. Accumulates sentences into chunks
3. Ensures chunk boundaries respect sentence endings

### Embedding Logic

**EmbeddingService Configuration:**
- `model`: "text-embedding-ada-002" (from settings)
- `dimensions`: 1536
- `batch_size`: 500 texts per API call
- `max_parallel_batches`: 3 simultaneous requests

**Caching Strategy:**
1. Before embedding, checks cache for each chunk's content_hash
2. Cache key format: `emb:{content_hash}`
3. Cache TTL: 7 days
4. Skips cached chunks in embedding batches

**Batch Processing (`embed_chunks`):**
1. Separates cached vs uncached chunks
2. Creates batches of 500 uncached chunks
3. Processes batches in groups of 3 in parallel
4. For each batch:
   - Extracts text content from chunks
   - Calls `client.embeddings.create()` with batch
   - Assigns returned embeddings to chunk objects
   - Fire-and-forget cache writes

**API Call (`_embed_batch`):**
1. Creates OpenAI client with connection pooling
2. Sends batch to embeddings endpoint
3. Response contains list of embedding objects
4. Maps embeddings back to chunks by index
5. Handles errors with logging

### Retrieval Logic

**RetrievalAgent.process():**
1. Extracts query, book_id, chapter from state
2. Generates query embedding using same model
3. Creates database session
4. Calls `_retrieve_chunks()` for vector search

**Vector Search (`_retrieve_chunks`):**
1. Formats embedding as PostgreSQL array literal
2. SQL query with pgvector:
   ```sql
   SELECT content, similarity
   FROM document_chunks dc
   JOIN book_chapters bc ON dc.chapter_id = bc.id
   WHERE dc.book_id = :book_id
     AND bc.chapter_number = :chapter_number
   ORDER BY dc.embedding <=> CAST(:embedding AS vector)
   LIMIT :limit
   ```
3. `<=>` is cosine distance operator
4. Returns top-k chunks (default: 8)
5. Includes similarity score: `1 - distance`

**Cross-Reference Detection (`_detect_cross_references`):**
1. Only runs if current_chapter > 1
2. Gets topic graph from cache or builds from DB
3. Extracts topics from query using LLM
4. Matches topics against graph
5. Returns references to previous chapters

---

## 9. Agentic Architecture - LangGraph Code Logic

### Files Involved
- `backend/app/langgraph/graph.py` - Main workflow
- `backend/app/langgraph/state.py` - ProfessorState definition
- `backend/app/agents/*.py` - Individual agents

### State Definition

**ProfessorState (TypedDict):**
```
Identity: user_id, session_id, book_id, book_title
Phase: greeting | planning | plan_review | plan_iteration | teaching | doubt_resolution | quiz | chapter_transition | completed
User Input: user_message
Professor Output: professor_response, response_type
Chapter: current_chapter, total_chapters, chapters_completed, chapter_title
Teaching: current_topic_index, topics_in_chapter, topics_covered, doubts_pending, chapter_complete
Session: session_message_count, is_attention_check, current_question
Quiz: quiz_questions, quiz_current_index, quiz_score, quiz_scores, quiz_passed
Plan: plan_accepted, plan_data, awaiting_plan_confirmation
RAG: retrieved_chunks, chapter_summary
Config: learning_level, daily_study_minutes, quiz_frequency, questions_per_quiz
Metrics: comprehension_score, attention_score, motivation_score
Internal: api_key, error_message, agent_name
```

### Graph Nodes

**greeting_node:**
1. Gets book_title and total_chapters from state
2. Selects level_note based on learning_level
3. Builds greeting message template
4. Returns: professor_response, response_type="greeting", phase="greeting"

**planning_node:**
1. Gets chapters from database
2. Gets learning config (daily_minutes, target_days)
3. Creates PlannerAgent with api_key
4. Builds agent_state with all context
5. Calls `planner.process(agent_state)`
6. Gets learning_plan from result
7. Formats plan summary using `_format_plan_summary()`
8. Returns: plan_data, professor_response, phase="plan_review"

**plan_iteration_node:**
1. Gets current plan and user modification request
2. Creates PlannerAgent
3. Passes user_message as additional_instructions
4. Agent adapts plan based on feedback
5. Returns updated plan with new summary

**teaching_node:**
1. **Step 1: RetrievalAgent**
   - Creates RetrievalAgent with api_key
   - Builds retrieval_state with query and context
   - Calls `retrieval_agent.process()`
   - Gets retrieved_chunks and cross_references

2. **Step 2: TeachingAgent**
   - Gets book and chapter info from database
   - Creates TeachingAgent with api_key
   - Builds teaching_state with all context
   - Calls `teaching_agent.process()`
   - Gets response, chapter_complete, trigger_attention

3. **Step 3: ProgressAgent**
   - Creates ProgressAgent
   - Builds progress_state with current metrics
   - Calls `progress_agent.process()`
   - Gets updated scores and topics_covered

4. **Step 4: Motivation Check**
   - Checks if motivation_score < 0.5
   - If low: Creates MotivationAgent
   - Generates encouragement message
   - Prepends to teaching response

5. **Step 5: Phase Transition**
   - If chapter_complete: phase = "doubt_resolution"
   - If trigger_attention: generate attention question
   - Else: stay in "teaching"

**doubt_resolution_node:**
1. Gets user message and context
2. Calls `detect_intent()` to classify response
3. If intent is "no_doubt" or "accept":
   - Checks if quiz should trigger
   - Transitions to "quiz" or "chapter_transition"
4. If intent is "question" or "doubt":
   - Uses RetrievalAgent + TeachingAgent to answer
   - Stays in "doubt_resolution"

**quiz_node:**
1. **First Entry (no questions):**
   - Creates QuizAgent
   - Generates all questions upfront
   - Stores in quiz_questions
   - Returns first question

2. **Subsequent Entries:**
   - Gets previous answer from user_message
   - Calls `evaluate_answer()` for scoring
   - Updates quiz_scores
   - If not complete: show next question
   - If complete: calculate final score, transition

**chapter_transition_node:**
1. Adds current chapter to completed_chapters
2. Calls `generate_summary()` for chapter summary
3. Updates ProgressAgent metrics
4. If current >= total: phase = "completed"
5. Else: increments current_chapter, resets state

### Graph Edges

**Conditional Edges:**
- planning → teaching (if plan_accepted) OR plan_iteration
- plan_iteration → teaching (if accepted) OR planning
- teaching → doubt_resolution (if chapter_complete) OR teaching (loop)
- doubt_resolution → quiz (if ready) OR doubt_resolution (loop)
- quiz → chapter_transition (if complete) OR quiz (loop)
- chapter_transition → teaching (next chapter) OR END (completed)

### Message Processing Flow

**process_message():**
1. Gets current phase from state
2. Calls `detect_intent()` to understand user message
3. Routes to appropriate node based on phase
4. Executes node function
5. Returns response with updated state

**Intent Detection (`detect_intent`):**
1. Uses GPT-4 Mini for fast classification
2. Prompt includes context and possible intents
3. Returns: accept, reject, question, doubt, no_doubt, continue, pause, unclear
4. JSON response with intent and confidence

---

## 10. Teaching Logic - Code Architecture

### Files Involved
- `backend/app/agents/teaching.py` - TeachingAgent
- `backend/app/services/teaching_service.py` - Utilities

### TeachingAgent.process() Logic

**Context Building:**
1. Gets cross_references from state
2. Formats retrieved_chunks for prompt
3. Joins topics_covered as comma-separated string
4. Gets all context values with safe defaults

**Prompt Construction:**
1. Builds comprehensive prompt with sections:
   - Book/Course info (title, chapter)
   - Student level and style
   - Summarized past context
   - Retrieved chunks (numbered)
   - Cross-references (if any)
   - Topics covered this session
   - User's question

**Response Generation:**
1. Calls `generate_with_retry()` with 3 attempts
2. Uses SYSTEM_PROMPT defining professor personality
3. Sets max_tokens and temperature from settings
4. Has fallback response for failures

**Attention Question Logic:**
1. Checks session_message_count against intervals
2. min_interval: 5 messages (from settings)
3. max_interval: 12 messages
4. probability: 0.3 (30% chance)
5. If within window: random chance to trigger
6. If past max: forced trigger

**Chapter Completion Detection:**
1. Checks topic coverage ratio (80%+)
2. Checks if topics_covered >= retrieved_chunks
3. Looks for completion signals in response:
   - "we've covered all"
   - "that concludes"
   - "those are the key concepts"
4. Returns chapter_complete boolean

### Teaching Style Adaptation

**professor_level:**
- beginner: Simple explanations, analogies, encouragement
- intermediate: Balanced depth, technical terms explained
- advanced: Technical, deeper insights, expects knowledge

**professor_style:**
- strict: Goal-focused, brief responses
- balanced: Empathy with advice
- encouraging: Warm, positive reinforcement

---

## 11. Quiz Logic - Code Architecture

### Files Involved
- `backend/app/agents/quiz.py` - QuizAgent
- `backend/app/services/quiz_service.py` - Quiz utilities
- `backend/app/models/quiz.py` - Quiz models

### QuizAgent.process() Logic

**Mode Detection:**
1. Gets mode from state ("quiz" or "attention_check")
2. Routes to appropriate generation method

**Chapter Quiz Generation:**
1. Gets questions_remaining from state
2. Determines difficulty based on quiz_score:
   - High (80%+): 60% hard, 30% medium, 10% easy
   - Average (60-80%): 30% hard, 50% medium, 20% easy
   - Low (<60%): 20% hard, 40% medium, 40% easy
3. Selects question_type:
   - MCQ: 50% probability
   - True/False: 25%
   - Short Answer: 25%
4. Builds prompt with chapter concepts and weak areas
5. Requests JSON response with question structure
6. Parses and formats for display

**Question Structure:**
```
{
  "question": "The question text",
  "type": "mcq|true_false|short_answer",
  "difficulty": "easy|medium|hard",
  "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
  "correct_answer": "The answer",
  "explanation": "Why this is correct",
  "topic": "Topic being tested",
  "hints": ["hint1", "hint2"]
}
```

**Attention Question Generation:**
1. Gets recent teaching content from state
2. Gets current topic being discussed
3. Builds short prompt for comprehension check
4. Returns simpler JSON structure
5. Should be answerable in <30 seconds

### Answer Evaluation Logic

**evaluate_answer():**
1. Uses GPT-4 Mini for evaluation
2. Prompt includes:
   - Question text
   - Expected answer
   - Explanation
   - Student's answer
3. Instructions: Be fair, partial credit allowed
4. Returns JSON: {correct, score (0-1), feedback}
5. Handles errors with default response

### Quiz Configuration

**should_trigger_quiz():**
1. Gets LearningConfig from database
2. Checks quiz_frequency setting:
   - "after_each_chapter": Always true
   - "after_n_chapters": Check if count % n == 0
   - "final_only": Only if current >= total
3. Returns boolean

---

## 12. Doubt Resolution - Code Architecture

### Files Involved
- `backend/app/langgraph/graph.py` - doubt_resolution_node
- `backend/app/services/intent_service.py` - Intent detection

### Doubt Resolution Logic

**Entry Conditions:**
1. Chapter teaching is complete
2. Professor asks: "Do you have any questions?"
3. User responds

**Intent Classification:**
1. User message sent to `detect_intent()`
2. Context: "Professor asked if user has any doubts"
3. Possible intents: no_doubt, accept, continue (proceed) vs question, doubt (has questions)

**No Doubts Path:**
1. Checks `should_trigger_quiz()`
2. If quiz configured: transitions to "quiz" phase
3. If no quiz: transitions to "chapter_transition"
4. Simple template response

**Has Doubts Path:**
1. Creates RetrievalAgent
2. Retrieves context for the doubt question
3. Creates TeachingAgent
4. Generates answer using RAG context
5. Appends: "Do you have any other questions?"
6. Stays in "doubt_resolution" phase
7. Sets doubts_pending = True

**Loop Until Clear:**
1. User can ask unlimited questions
2. Each answered with RAG-backed response
3. Only proceeds when user confirms no more doubts

---

## 13. Motivation Agent - Code Architecture

### Files Involved
- `backend/app/agents/motivation.py` - MotivationAgent
- `backend/app/temporal/activities/learning.py` - Motivation activities

### MotivationAgent.process() Logic

**Trigger Conditions:**
1. motivation_score < 0.5
2. ProgressAgent sets motivation_check flag
3. Called from teaching_node after progress update

**Context Gathering:**
1. Gets all relevant state values:
   - user_name, motivation_score
   - completed_chapters, total_chapters
   - study_time, missed_sessions
   - quiz_score, professor_style

**Reason Determination:**
1. Checks for multiple missed sessions (3+)
2. Checks for low quiz scores (<50%)
3. Checks for low attention score (<50%)
4. Checks for comprehension challenges (<50%)
5. Defaults to "General motivation dip"

**Progress Formatting:**
1. Lists chapters completed
2. Shows topics covered today
3. Shows total study time
4. Notes recent quiz successes

**Message Generation:**
1. Builds prompt with all context
2. Uses higher temperature (0.8) for natural tone
3. Requests message that:
   - Acknowledges feelings
   - Highlights progress
   - Provides suggestions
   - Ends with encouragement
4. Adapts to professor_style

**Fallback Messages:**
- strict: Focus on goals, brief
- balanced: Acknowledge + practical advice
- encouraging: Warm, emoji-enabled, supportive

**Post-Intervention:**
1. Boosts motivation_score by 0.1
2. Sets motivation_intervention = True
3. Message prepended to teaching response

---

## 14. Temporal Workflows - Code Architecture

### Files Involved
- `backend/app/temporal/workflows/inactivity_monitor.py` - InactivityMonitorWorkflow
- `backend/app/temporal/workflows/learning_session.py` - LearningSessionWorkflow
- `backend/app/temporal/activities/learning.py` - Activities
- `backend/app/temporal/client.py` - Temporal client
- `backend/app/temporal/worker.py` - Worker process

### InactivityMonitorWorkflow Logic

**Configuration:**
- user_id, book_id: Identifiers
- inactivity_threshold_hours: Default 24
- check_interval_hours: Default 6
- max_messages: 5 (spam prevention)

**Main Loop:**
1. Sleep for check_interval
2. Execute check_user_inactivity activity
3. Activity queries ConversationState for last_interaction_at
4. Calculates hours since last interaction
5. Returns is_inactive and days_inactive

**If Inactive:**
1. Execute send_motivation_message activity
2. Message varies by days_inactive:
   - 1 day: "Ready to pick up where we left off?"
   - 2-3 days: "Your progress is waiting!"
   - 4-7 days: "Consistency is key!"
   - 7+ days: "Whenever you're ready..."
3. Tries WhatsApp first, falls back to push
4. Increment messages_sent counter
5. If days_inactive > 2: decrease motivation_score

**If Active:**
1. Reset messages_sent counter
2. Continue monitoring

**Signals:**
- user_active: Stop monitoring
- stop_monitoring: External stop

### LearningSessionWorkflow Logic

**Purpose:** Manages complete learning session lifecycle

**Main Flow:**
1. Start with user_id, book_id, session_id, start_chapter
2. Loop through chapters:
   - Teach chapter via activities
   - Run comprehension checks
   - Generate summary
   - Run quiz
   - Unlock next chapter or retry

**Teaching a Chapter:**
1. Get chapter topics
2. Send introduction
3. For each topic:
   - Generate teaching segment
   - Send to student
   - Check comprehension every 2-3 topics
   - Reteach if score < 0.6

**Comprehension Check:**
1. Generate question about current topic
2. Send to student
3. Wait for response (5 min timeout)
4. Evaluate response
5. Send feedback
6. Return score

**Quiz Flow:**
1. Generate quiz questions
2. For each question:
   - Send question
   - Wait for answer (3 min timeout)
   - Check correctness
3. Calculate final score
4. Return passed boolean

**Signals:**
- student_response: Receive answers
- pause_session: Save state, return
- end_session: Stop workflow
- quiz_completed: External completion

### Activities

**check_user_inactivity:**
1. Query ConversationState
2. Get last_interaction_at
3. Calculate hours since
4. Compare to threshold
5. Return status dict

**send_motivation_message:**
1. Build message based on days_inactive
2. Try WhatsApp via Twilio
3. Fallback to push notification
4. Return delivery status

**unlock_next_chapter:**
1. Get LearningState
2. Check if more chapters exist
3. Update current_chapter
4. Add to completed_chapters
5. Create ProgressSnapshot
6. Commit to database

**update_motivation_score:**
1. Get current LearningState
2. Apply delta (bounded 0-1)
3. Update database
4. Log change

---

## 15. Progress Tracking - Code Architecture

### Files Involved
- `backend/app/agents/progress.py` - ProgressAgent
- `backend/app/models/learning.py` - LearningState, ProgressSnapshot

### ProgressAgent.process() Logic

**Metric Updates:**
1. Increments session_message_count
2. Extracts topic from agent_response
3. Adds to topics_covered_this_session if new
4. Adds 2 minutes to total_study_time

**Attention Score Calculation:**
1. Gets current attention_score (default 1.0)
2. If attention_correct exists:
   - True: +0.1 (bounded at 1.0)
   - False: -0.15 (bounded at 0.0)
3. Returns updated score

**Comprehension Score Calculation:**
1. Gets current comprehension_score (default 1.0)
2. If quiz_score exists:
   - Blend: 30% current + 70% quiz
3. If attention_correct exists:
   - Adjust by +/- 0.05
4. Returns updated score

**Motivation Score Calculation:**
1. Gets current motivation_score (default 1.0)
2. Decreases:
   - Missed sessions: -0.1 each
   - Low quiz (<50%): -0.1
3. Increases:
   - Active session (>5 messages): +0.05
   - Topics covered (>3): +0.05
   - Chapter complete: +0.2
4. Returns bounded 0-1

**Chapter Completion Tracking:**
1. Checks chapter_complete flag
2. If true and not in completed_chapters:
   - Adds to list
   - Logs completion

### Database Persistence

**LearningState Model:**
- current_chapter, current_section
- completed_chapters (array), completed_sections (JSON)
- summarized_past_context, pending_topics
- motivation_score, attention_score, comprehension_score
- missed_sessions, total_study_time_minutes
- quiz_mode, pending_quiz_questions

**ProgressSnapshot Model:**
- learning_state_id: FK to LearningState
- snapshot_date: Date of snapshot
- chapter_progress: Current chapter number
- quiz_scores: JSON of quiz results
- topics_covered: Array of strings

---

## 16. Notes Feature - Code Architecture

### Files Involved
- `backend/app/api/notes.py` - Notes API endpoints
- `backend/app/models/note.py` - UserNote, Reminder models
- `web/src/components/SelectionToNotes.tsx` - Selection handler
- `web/src/lib/notes-store.ts` - Local notes storage

### Notes API Logic

**List Notes (`GET /api/notes`):**
1. Gets user_id from token
2. Builds query conditions:
   - book_id filter (optional)
   - goal_id filter (optional)
   - chapter_id filter (optional)
   - tag filter (optional)
   - pinned_only filter
3. Orders by: is_pinned DESC, updated_at DESC
4. Returns note list

**Create Note (`POST /api/notes`):**
1. Receives: title, content, book_id, goal_id, chapter_id, source_message_id, tags
2. Creates UserNote record
3. Associates with book/chapter if provided
4. Links to source message if from chat
5. Returns created note

**Update Note (`PATCH /api/notes/{id}`):**
1. Verifies note belongs to user
2. Applies partial updates
3. Updates updated_at timestamp
4. Returns updated note

**Toggle Pin (`POST /api/notes/{id}/pin`):**
1. Finds note by id
2. Toggles is_pinned boolean
3. Returns new pin status

**Export Notes (`GET /api/notes/export/{format}`):**
1. Gets all notes for user (optional book filter)
2. Formats based on format parameter:
   - json: Full JSON array
   - markdown: Formatted markdown document
   - txt: Plain text with headers
3. Returns as file download

### Frontend Notes Logic

**SelectionToNotes Component:**
1. Monitors for text selection in chat
2. On selection: shows floating "Save to Notes" button
3. Position calculated from selection coordinates
4. Click triggers note creation with context

**Note Creation from Selection:**
1. Gets selected text
2. Gets context: bookId, bookTitle, chapterNumber, chapterTitle
3. Creates note via API
4. Shows success toast
5. Clears selection

**Notes Store (Local):**
1. Uses localStorage for offline support
2. Syncs with API on load
3. Provides CRUD operations
4. Handles optimistic updates

---

## 17. Session Management and Ending - Code Architecture

### Files Involved
- `backend/app/api/chat.py` - Chat session endpoints
- `backend/app/langgraph/graph.py` - chapter_transition_node

### Session Initialization

**Init Session (`GET /api/chat/init/{book_id}`):**
1. Verifies book exists and belongs to user
2. Checks processing_status is complete
3. Finds existing session or creates new
4. Gets ConversationState for phase
5. Checks for professor greeting
6. Returns: session_id, phase, current_chapter, messages, has_greeting

### Chat Message Processing

**Send Message (`POST /api/chat`):**
1. Gets or creates session
2. Saves user message to ChatMessage
3. Gets LearningState for context
4. Gets ConversationState for phase
5. Gets user's API key
6. Builds current_state dict
7. Calls `process_message()` from LangGraph
8. Updates ConversationState from response
9. Persists quiz state if in quiz
10. Saves assistant message
11. Updates session message_count
12. Returns response

### Chapter Transition Logic

**chapter_transition_node:**
1. Marks chapter complete:
   - Adds to completed_chapters list
2. Generates summary:
   - Calls teaching_service.generate_summary()
   - Uses LLM with chapter context
3. Updates progress:
   - ProgressAgent.process()
   - Creates ProgressSnapshot
4. Checks completion:
   - If current >= total: phase = "completed"
   - Sends congratulations message
5. Prepares next chapter:
   - Increments current_chapter
   - Resets: current_topic_index, session_message_count
   - Clears: topics_covered, quiz state
   - Gets next chapter title from DB
6. Sends transition message with summary

### Handling Early Exit

**User Says "I'm done":**
1. Intent detection catches "pause" intent
2. State saved to database
3. Session marked appropriately
4. Can resume later from saved state

**Workflow Pause Signal:**
1. pause_session signal received
2. Calls save_session_state activity
3. Returns with status "paused"
4. Workflow can be continued later

### Course Completion

**When All Chapters Done:**
1. phase set to "completed"
2. Congratulations message generated
3. Options offered: review, final assessment
4. LearningState updated
5. Final ProgressSnapshot created

---

## 18. Configuration System - All Settings

### Files Involved
- `backend/app/config.py` - Settings class
- `backend/app/models/learning_config.py` - LearningConfig model
- `backend/app/models/user.py` - UserSettings model

### Application Settings (config.py)

**Application:**
- app_name: "Professor MVP"
- environment: "development" | "production"
- debug: True | False

**Database:**
- database_url: PostgreSQL connection string (async)
- database_url_sync: PostgreSQL (sync for migrations)

**Redis:**
- redis_url: Redis connection string
- redis_host, redis_port: Separate components

**Temporal:**
- temporal_host: Temporal server address
- temporal_namespace: "default"
- temporal_task_queue: "professor-queue"

**Security:**
- secret_key: JWT signing key
- encryption_key: Fernet encryption key
- algorithm: "HS256"
- access_token_expire_minutes: 1440 (24 hours)
- refresh_token_expire_days: 7

**Google OAuth:**
- google_client_id, google_client_secret

**URLs:**
- frontend_url: "http://localhost:3000"
- backend_url: "http://localhost:8000"

**File Storage:**
- pdf_storage_path: "/app/data/pdfs"
- max_file_size_mb: 50

**OpenAI:**
- openai_api_key: Default key
- openai_model: "gpt-4.1"
- openai_model_mini: "gpt-4.1-mini"

**RAG Settings:**
- chunk_size: 400 tokens
- chunk_overlap: 50 tokens
- embedding_model: "text-embedding-ada-002"
- embedding_dimensions: 1536
- retrieval_top_k: 8 chunks

**Teaching Settings:**
- max_context_tokens: 8000
- max_response_tokens: 600
- default_temperature: 0.7

**Quiz Settings:**
- questions_per_quiz: 5
- quiz_passing_score: 0.7
- attention_question_min_interval: 5
- attention_question_max_interval: 12
- attention_question_probability: 0.3

**Cache TTLs:**
- cache_ttl_user_state: 3600 (1 hour)
- cache_ttl_chapter_chunks: 3600
- cache_ttl_chapter_summary: 86400 (24 hours)
- cache_ttl_conversation: 1800 (30 minutes)
- cache_ttl_embeddings: 604800 (7 days)

**WhatsApp/Twilio:**
- twilio_account_sid, twilio_auth_token
- twilio_whatsapp_number

### Learning Configuration (LearningConfig model)

**Learning Level:**
- learning_level: "beginner" | "intermediate" | "advanced" | "research"

**Chapter Selection:**
- study_all_chapters: Boolean
- selected_chapters: JSON array of chapter numbers

**Timeline:**
- deadline: Date
- preferred_study_days: Array ["monday", "wednesday", etc.]
- daily_study_minutes: Integer (default 60)

**Quiz Preferences:**
- quiz_frequency: "after_each_chapter" | "after_n_chapters" | "final_only"
- quiz_after_n_chapters: Integer (if frequency is after_n)
- questions_per_quiz: Integer (default 5)
- quiz_difficulty: "easy" | "medium" | "hard" | "match_level"

**Reminders:**
- enable_reminders: Boolean
- reminder_channel: "push" | "email" | "whatsapp" | "all"
- inactivity_threshold_hours: Integer (default 24)

**Plan Status:**
- plan_generated: Boolean
- plan_accepted: Boolean
- plan_accepted_at: DateTime

### User Settings (UserSettings model)

- professor_style: "strict" | "balanced" | "encouraging"
- notification_preferences: JSON {email, whatsapp, push}
- whatsapp_number: String with country code
- study_schedule: JSON
- timezone: String (default "UTC")

---

## 19. Database Models - Complete Schema

### User Domain

**users:**
- id (UUID PK), email (unique), password_hash, name, phone
- role, is_active, created_at, updated_at

**user_auth:**
- id (UUID PK), user_id (FK), provider, provider_user_id
- access_token_hash, refresh_token_hash, created_at

**encrypted_api_keys:**
- id (UUID PK), user_id (FK unique)
- encrypted_key (bytes), key_iv (bytes), key_hash
- is_valid, last_validated_at, created_at

**user_sessions:**
- id (UUID PK), user_id (FK), token_hash
- device_info (JSON), ip_address, expires_at
- created_at, last_active_at

**user_settings:**
- id (UUID PK), user_id (FK unique)
- professor_style, notification_preferences (JSON)
- whatsapp_number, study_schedule (JSON), timezone
- created_at

### Book Domain

**books:**
- id (UUID PK), user_id (FK), title, author, file_path, file_hash
- total_pages, total_chapters
- processing_status, processing_progress, processing_step, processing_error
- book_metadata (JSON)
- professor_greeted, professor_greeting_at
- created_at

**book_chapters:**
- id (UUID PK), book_id (FK), chapter_number, title
- start_page, end_page, summary, key_concepts (JSON)
- prerequisite_chapters (array), estimated_duration_minutes
- created_at

**goals:**
- id (UUID PK), user_id (FK), title, description
- duration_days, difficulty_level, status
- ai_generated_curriculum (JSON), created_at

**goal_chapters:**
- id (UUID PK), goal_id (FK), week_number, title
- topics (JSON), learning_objectives (array)
- summary, created_at

### Learning Domain

**learning_configs:**
- id (UUID PK), user_id (FK), book_id (FK unique)
- learning_level, study_all_chapters, selected_chapters (JSON)
- deadline, preferred_study_days (array), daily_study_minutes
- quiz_frequency, quiz_after_n_chapters, questions_per_quiz, quiz_difficulty
- enable_reminders, reminder_channel, inactivity_threshold_hours
- plan_generated, plan_accepted, plan_accepted_at
- created_at, updated_at

**learning_plans:**
- id (UUID PK), config_id (FK), user_id (FK), book_id (FK)
- plan_data (JSON), summary, version
- status, user_feedback
- created_at, accepted_at

**conversation_states:**
- id (UUID PK), user_id (FK), book_id (FK)
- phase, current_chapter, current_topic_index
- chapters_taught (array), chapters_quizzed (array)
- doubts_cleared, quiz_state (JSON)
- last_professor_action, workflow_id
- last_interaction_at, created_at

**learning_states:**
- id (UUID PK), user_id (FK), book_id (FK), goal_id (FK)
- current_chapter, current_section
- completed_chapters (array), completed_sections (JSON)
- summarized_past_context, last_topic_discussed, pending_topics (array)
- learning_plan (JSON), strict_mode, professor_level
- motivation_score, attention_score, comprehension_score
- missed_sessions, total_study_time_minutes
- last_session_summary, last_active_at
- quiz_mode, pending_quiz_questions (JSON)
- created_at, updated_at

**progress_snapshots:**
- id (UUID PK), learning_state_id (FK)
- snapshot_date, chapter_progress
- quiz_scores (JSON), study_duration_minutes, topics_covered (array)
- created_at

### RAG Domain

**document_chunks:**
- id (UUID PK), book_id (FK), chapter_id (FK)
- section_title, chunk_index, content, content_hash
- token_count, embedding (vector 1536), chunk_metadata (JSON)
- created_at

**chapter_summaries:**
- id (UUID PK), user_id (FK), book_id (FK), chapter_id (FK)
- summary_type, summary_text, key_concepts (JSON), token_count
- created_at

**topic_relationships:**
- id (UUID PK), book_id (FK)
- source_chapter_id (FK), target_chapter_id (FK)
- topic, relationship_type, strength
- created_at

### Chat Domain

**chat_sessions:**
- id (UUID PK), user_id (FK), learning_state_id (FK)
- book_id (FK), goal_id (FK), chapter_context
- session_type, is_active, message_count
- created_at, last_message_at

**chat_messages:**
- id (UUID PK), session_id (FK)
- role, content, agent_name
- chapter_at_time, is_quiz_question, quiz_answer_correct
- latency_ms, created_at

### Quiz Domain

**quizzes:**
- id (UUID PK), book_id (FK), chapter_id (FK)
- quiz_type, title, total_questions, passing_score, time_limit_minutes
- created_at

**quiz_questions:**
- id (UUID PK), quiz_id (FK), book_id (FK), chapter_id (FK)
- question_text, question_type, options (JSON)
- correct_answer, explanation, difficulty, topic
- source_chunk_id (FK), created_at

**quiz_attempts:**
- id (UUID PK), user_id (FK), quiz_id (FK), learning_state_id (FK)
- started_at, completed_at, score, passed, time_taken_seconds
- answers (JSON), feedback (JSON)

**question_responses:**
- id (UUID PK), attempt_id (FK), question_id (FK)
- user_answer, is_correct, time_taken_seconds, created_at

**attention_questions:**
- id (UUID PK), user_id (FK), session_id (FK), chapter_id (FK)
- question_text, expected_answer, user_answer
- is_correct, asked_at, answered_at
- topic_being_taught, triggered_by

### Notes Domain

**user_notes:**
- id (UUID PK), user_id (FK)
- book_id (FK), goal_id (FK), chapter_id (FK)
- title, content, source_message_id (FK)
- tags (array), is_pinned
- created_at, updated_at

**reminders:**
- id (UUID PK), user_id (FK), learning_state_id (FK)
- reminder_type, channel
- message_template, message_data (JSON)
- scheduled_at, sent_at, status, dedup_key
- created_at

---

## 20. API Endpoints - Complete Reference

### Authentication (`/api/auth`)
- `POST /signup` - Register with email/password
- `POST /signin` - Login with email/password
- `POST /google` - Google OAuth
- `POST /refresh` - Refresh access token
- `GET /me` - Get current user
- `POST /logout` - Logout (invalidate sessions)
- `POST /dev-login` - Development login (dev only)

### Users (`/api/users`)
- `GET /profile` - Get user profile
- `PATCH /profile` - Update profile
- `GET /settings` - Get user settings
- `PATCH /settings` - Update settings
- `GET /api-key/status` - Get API key status
- `POST /api-key` - Save API key
- `DELETE /api-key` - Delete API key
- `POST /api-key/validate` - Validate stored key

### Books (`/api/books`)
- `GET /` - List user's books
- `GET /{id}` - Get book details
- `GET /{id}/status` - Get processing status
- `POST /upload` - Upload PDF
- `POST /upload-with-config` - Upload with configuration
- `DELETE /{id}` - Delete book
- `GET /{id}/chapters` - Get book chapters
- `POST /{id}/config` - Save learning config
- `POST /{id}/reprocess` - Retry processing

### Goals (`/api/goals`)
- `GET /` - List goals
- `POST /` - Create goal

### Chat (`/api/chat`)
- `POST /` - Send message
- `GET /sessions` - List sessions
- `GET /sessions/{id}` - Get session with messages
- `DELETE /sessions/{id}` - Delete session
- `GET /init/{book_id}` - Initialize/get session
- `POST /regenerate-greeting/{book_id}` - Regenerate greeting

### Learning (`/api/learning`)
- `GET /state/{book_id}` - Get learning state
- `GET /progress/{book_id}` - Get progress
- `GET /progress/{book_id}/detailed` - Get detailed progress
- `POST /state/{book_id}/reset` - Reset learning state

### Quiz (`/api/quiz`)
- `POST /start/{quiz_id}` - Start quiz
- `POST /answer` - Submit answer

### Planning (`/api/planning`)
- `POST /generate` - Generate plan
- `GET /{book_id}/current` - Get current plan
- `POST /review` - Review/accept plan

### Notes (`/api/notes`)
- `GET /` - List notes
- `GET /{id}` - Get note
- `POST /` - Create note
- `PATCH /{id}` - Update note
- `DELETE /{id}` - Delete note
- `POST /{id}/pin` - Toggle pin
- `GET /export/{format}` - Export notes

### Admin (`/api/admin`)
- `GET /dashboard` - Get admin dashboard
- `GET /users` - List users
- `GET /users/{id}` - Get user detail
- `PATCH /users/{id}/status` - Toggle user status
- `GET /system/health` - System health check
- `GET /feature-flags` - List feature flags
- `PATCH /feature-flags/{name}` - Update feature flag

---

## Summary

Professor is a comprehensive AI-powered learning system built with:

- **Backend**: FastAPI with async SQLAlchemy, LangGraph for agent orchestration, Temporal for workflows
- **Frontend**: Next.js with React, Tailwind CSS for styling
- **AI**: OpenAI GPT-4 for teaching/quizzes, text-embedding-ada-002 for RAG
- **Storage**: PostgreSQL with pgvector for vectors, Redis for caching
- **Security**: JWT authentication, Fernet encryption for API keys

The system implements a multi-agent architecture where specialized agents (Planner, Teaching, Quiz, Progress, Motivation, Retrieval) work together to provide a professor-like learning experience. Every user interaction flows through the LangGraph state machine, ensuring consistent behavior and proper state management.

Key architectural decisions:
1. **State-driven**: All behavior determined by current state and phase
2. **Agent-based**: Specialized agents for each responsibility
3. **RAG-powered**: Context-aware responses from user's material
4. **Workflow-enabled**: Long-running processes via Temporal
5. **Event-driven**: Automatic triggers for inactivity, completion, etc.
