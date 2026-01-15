# Professor - AI-Powered Personalized Learning Assistant

Professor is a production-grade AI learning system that provides personalized teaching, quizzes, and progress tracking using multi-agent LLM orchestration.

## Features

- 📚 **PDF Book Learning**: Upload PDFs and learn chapter by chapter
- 🎯 **Goal-Based Learning**: Set learning goals and follow AI-generated curricula
- 🤖 **Multi-Agent System**: 10 specialized AI agents for different learning tasks
- 📝 **Smart Quizzes**: Chapter-end quizzes and attention check questions
- 📊 **Progress Tracking**: Detailed analytics and progress reports
- 🔒 **Strict Mode**: Prevents skipping ahead in chapters
- 💾 **Stateful**: Progress persists across sessions

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Next.js   │────▶│   FastAPI   │────▶│  LangGraph  │
│   Frontend  │     │   Backend   │     │   Agents    │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │PostgreSQL│    │  Redis   │    │ Temporal │
    │+ PGVector│    │          │    │          │
    └──────────┘    └──────────┘    └──────────┘
```

## Quick Start

### Prerequisites

- Docker & Docker Compose
- OpenAI API key (users can provide their own or use a default)

### Setup

1. **Clone and navigate to the project**
   ```bash
   cd Professor
   ```

2. **Create environment files**
   ```bash
   # Backend
   cp backend/env.template backend/.env
   
   # Frontend
   cp web/env.template web/.env.local
   ```

3. **Configure environment variables**
   
   Edit `backend/.env` and set:
   - `JWT_SECRET_KEY`: Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`
   - `ENCRYPTION_KEY`: Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`
   - `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`: From Google Cloud Console
   - `OPENAI_API_KEY` (optional): Default API key for users who don't provide their own
   
   Edit `web/.env.local` and set:
   - `NEXT_PUBLIC_GOOGLE_CLIENT_ID`: Same as backend

4. **Start the application**
   ```bash
   docker-compose up -d
   ```

5. **Run database migrations**
   ```bash
   docker-compose exec backend alembic upgrade head
   ```

6. **Access the application**
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - Temporal UI: http://localhost:8080

## API Key Management

Professor supports two modes for OpenAI API key usage:

### User-Provided Keys (Recommended)
Users can add their own OpenAI API key in Settings:
- Keys are encrypted using AES-256 before storage
- Keys are never exposed in API responses
- Masked display (sk-abc1****xyz7) for user verification

### Default Backend Key
If no user key is provided, the system falls back to the backend's `OPENAI_API_KEY` environment variable.

## Agent System

Professor uses 10 specialized LangGraph agents:

| Agent | Purpose |
|-------|---------|
| **PlannerAgent** | Creates personalized learning plans |
| **ValidatorAgent** | Guards against policy violations |
| **RetrievalAgent** | Fetches relevant context from RAG |
| **TeachingAgent** | Delivers personalized instruction |
| **QuizAgent** | Generates quiz questions |
| **AssessmentAgent** | Evaluates answers |
| **ProgressAgent** | Updates learning metrics |
| **MotivationAgent** | Provides encouragement |
| **ReschedulerAgent** | Adjusts learning schedules |
| **ReminderAgent** | Generates reminder messages |

## Development

### Backend

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run locally (without Docker)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run tests
pytest tests/ -v
```

### Frontend

```bash
cd web

# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build
```

### Running Tests

```bash
# Backend unit tests
docker-compose exec backend pytest tests/unit -v

# Backend integration tests
docker-compose exec backend pytest tests/integration -v

# E2E tests
docker-compose exec backend pytest tests/e2e -v
```

## Configuration

### Backend Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `REDIS_URL` | Redis connection string | Yes |
| `JWT_SECRET_KEY` | JWT signing key | Yes |
| `ENCRYPTION_KEY` | API key encryption key | Yes |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID | Yes |
| `GOOGLE_CLIENT_SECRET` | Google OAuth secret | Yes |
| `OPENAI_API_KEY` | Default OpenAI API key | No |
| `OPENAI_MODEL` | LLM model (default: gpt-4o) | No |

See `backend/env.template` for the complete list.

### Frontend Environment Variables

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Backend API URL |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | Google OAuth client ID |

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy, LangGraph, Temporal
- **Frontend**: Next.js 14, TypeScript, Tailwind CSS
- **Database**: PostgreSQL with PGVector extension
- **Cache**: Redis
- **Orchestration**: Temporal.io
- **AI**: OpenAI GPT-4o, text-embedding-ada-002

## License

MIT
