# Professor - AI-Powered Personalized Learning Platform

Professor is a production-grade AI learning system that transforms any PDF textbook into an interactive, professor-led learning experience. It uses multi-agent LLM orchestration with Temporal workflows for durable execution and LangGraph for intelligent conversation management.

## Features

- **PDF Book Learning** -- Upload any textbook, the system detects chapters, chunks and embeds content for retrieval-augmented teaching
- **AI Professor** -- A professor-driven conversation that teaches from the textbook, not generic GPT output. Covers day-by-day scope with smart RAG queries
- **Personalized Planning** -- Conversational planner gathers your deadline, daily study time, and preferences, then generates a day-by-day learning plan
- **Smart Quizzes** -- AI-generated quizzes from textbook content with intelligent answer evaluation and explanations
- **Voice Input** -- Speech-to-text via OpenAI Whisper so students can talk to the professor naturally
- **Progress Tracking** -- Day/chapter progress, scope coverage, summaries of past sessions
- **LaTeX Rendering** -- Mathematical formulas rendered beautifully in the chat via KaTeX
- **BYOK Support** -- Students can use their own OpenAI API key (encrypted at rest with Fernet/AES)

## Architecture

```
                                    ┌─────────────┐
                                    │   Nginx     │ :80
                                    └──────┬──────┘
                          ┌────────────────┼────────────────┐
                          ▼                ▼                ▼
                   ┌──────────┐     ┌──────────┐     ┌──────────┐
                   │ Next.js  │     │ FastAPI  │     │   RAG    │
                   │ Frontend │     │ Backend  │     │ Service  │
                   │  :3000   │     │  :8000   │     │  :8001   │
                   └──────────┘     └────┬─────┘     └────┬─────┘
                                        │                 │
              ┌──────────┬──────────┬───┴───┐        ┌───┴────┐
              ▼          ▼          ▼       ▼        ▼        ▼
        ┌──────────┐ ┌───────┐ ┌────────┐ ┌───┐ ┌────────┐ ┌──────┐
        │PostgreSQL│ │ Redis │ │Temporal│ │LG │ │Temporal│ │Qdrant│
        │+ PGVector│ │       │ │ Server │ │   │ │Workers │ │      │
        └──────────┘ └───────┘ └────────┘ └───┘ └────────┘ └──────┘
```

**13 services** running via Docker Compose:

| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL | 5433 | Main database + Temporal metadata |
| Redis | 6380 | Cache, sessions, rate limiting |
| Qdrant | 6333 | Vector store for RAG embeddings |
| Temporal Server | 7233 | Workflow orchestration engine |
| Temporal UI | 8081 | Workflow monitoring dashboard |
| RAG Service | 8001 | Document ingestion and semantic search |
| RAG Worker | -- | Temporal worker for ingestion workflows |
| Backend API | 8000 | FastAPI application server |
| Professor Worker | -- | Temporal worker for learning workflows |
| Frontend | 3000 | Next.js web application |
| Nginx | 80 | Reverse proxy, rate limiting, security headers |
| Prometheus | 9090 | Metrics collection |
| Grafana | 3001 | Monitoring dashboards |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- An OpenAI API key

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/SamarthY06/Professor.git
   cd Professor
   ```

2. **Create environment files**
   ```bash
   cp backend/.env.example backend/.env
   cp web/.env.example web/.env.local
   ```

3. **Configure required secrets**

   Edit `backend/.env` and set these required values:
   ```bash
   SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
   ENCRYPTION_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
   OPENAI_API_KEY=sk-your-key-here
   ```

   Set compose-level secrets (in a root `.env` file or your shell):
   ```bash
   export POSTGRES_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
   export JWT_SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
   export GRAFANA_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
   ```

4. **Start all services**
   ```bash
   docker compose up -d --build
   ```

5. **Run database migrations**
   ```bash
   docker compose exec backend alembic upgrade head
   docker compose exec rag-service alembic upgrade head
   ```

6. **Access the application**
   - Frontend: http://localhost:3000
   - Backend API docs: http://localhost:8000/docs
   - RAG Service docs: http://localhost:8001/docs
   - Temporal UI: http://localhost:8081
   - Grafana: http://localhost:3001

## Agent System

Professor uses three core LangGraph agents orchestrated by Temporal workflows:

| Agent | Purpose |
|-------|---------|
| **PlannerAgent** | Conversationally gathers learning preferences, generates day-by-day study plans |
| **TeacherAgent** | Drives professor-led teaching using RAG tools to teach from the actual textbook |
| **QuizAgent** | Generates contextual quizzes from textbook content, evaluates answers intelligently |

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy (async), Gunicorn/Uvicorn
- **Frontend**: Next.js 14, TypeScript, Tailwind CSS, Radix UI
- **AI/ML**: OpenAI GPT-4o, Whisper, LangGraph, LangChain
- **Orchestration**: Temporal.io (durable workflow execution)
- **Databases**: PostgreSQL + pgvector, Redis, Qdrant
- **RAG**: PyMuPDF (PDF parsing), OpenAI embeddings, Qdrant (vector search)
- **Observability**: Prometheus, Grafana, structured logging (structlog)
- **Infrastructure**: Docker Compose, Nginx

## Development

```bash
# Backend (local, without Docker)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (local)
cd web
npm install
npm run dev

# Run tests
docker compose exec backend pytest tests/ -v
```

## License

MIT
