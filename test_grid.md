# Test Grid — Production-Grade Agentic Learning Platform (Web + Backend)

## 0. Purpose & Non‑Negotiable Standards

This test grid defines **what to test, how to test, and why** for a **production‑grade** system (not a demo). Every test must be:

* Deterministic
* Reproducible
* End‑to‑end
* Backed by real data (NO mock data)
* Fixed **systematically**, not patched

### 🔒 Five Strict Rules for Fixing Issues (MANDATORY)

1. **Validate agent responses** — correctness, alignment, grounding, and intent accuracy.
2. **Only systematic fixes** — root‑cause analysis, no hacks or bypasses.
3. **No mock data** — all flows must run on real DB, vector DB, Temporal, Redis.
4. **UX + system flow must be coherent** — web ↔ backend ↔ agents ↔ storage.
5. **Context integrity is sacred** — no partial context, no accidental drops, no hidden resets.

Failure to follow these rules invalidates the test.

---

## 1. System Goals (What We Are Trying to Achieve)

### Core Product Goals

1. A user can **sign in**, **upload a PDF**, wait for processing, and **chat only after RAG is ready**.
2. The system teaches **exactly 5 chapters**, one by one, driven by agents.
3. Progress is tracked **per user, per book, per chapter, per session**.
4. Context is preserved across multiple sessions and resumes correctly.
5. Temporal drives reminders, motivation agents, quizzes, inactivity nudges.
6. All components run locally via Docker (backend, web, Temporal, DBs).
7. Logs provide full traceability for debugging and audits.

---

## 2. Test Environment Preconditions

### Infrastructure

* Docker Compose running:

  * Backend (API + LangGraph + Agents)
  * Web (Node.js frontend)
  * PostgreSQL
  * Redis (cache + session)
  * Vector DB (pgvector / Qdrant / equivalent)
  * Temporal Server + Worker
* Local filesystem storage for PDFs + notes

### Configuration

* OpenAI key provided by user (encrypted at rest)
* WhatsApp sandbox / test number configured
* Temporal inactivity timers set to **1–5 seconds** for testing

---

## 3. End‑to‑End User Journey Test (CRITICAL PATH)

### Test 3.1 — User Onboarding Flow

**Goal:** Ensure a real user can enter the system correctly.

Steps:

1. User lands on web UI.
2. Clicks "Sign in" (Google OAuth stub accepted for now).
3. Backend creates user record.
4. Popup appears: "Add your OpenAI API Key".
5. User enters key → encrypted → stored.
6. User optionally adds phone number for WhatsApp.
7. User is redirected to dashboard.

Validate:

* User table entry created
* Encrypted OpenAI key stored
* user_id propagated to frontend session
* Audit log written

---

## 4. PDF Upload & RAG Pipeline Testing

### Test 4.1 — PDF Upload

**Goal:** Ensure document ingestion is real, observable, and traceable.

Steps:

1. User uploads `Modern_Robotics.pdf`.
2. UI shows upload success.
3. Backend stores file locally.
4. Background job starts (Temporal workflow).

Validate:

* File exists on disk
* book_id created
* Status = `PROCESSING`
* Upload event logged

---

### Test 4.2 — Chunking & Embeddings

**Goal:** Ensure RAG pipeline is fast, scoped, and structured.

Steps:

1. Temporal workflow extracts text.
2. Chapters detected (limit scope to 5).
3. Chunking applied (chapter‑aware).
4. Embeddings generated.
5. Stored in vector DB.

Validate:

* Chunk table populated
* Vector DB count > 0
* Each chunk has:

  * book_id
  * chapter_id
  * chunk_index
* Processing time within expected range (minutes, not hours)

---

### Test 4.3 — Processing Progress UI

**Goal:** User must NOT chat until RAG is ready.

Steps:

1. User sees progress bar (% chapters processed).
2. Chat input is disabled.
3. Once processing = 100%, "Start Chat" button appears.

Validate:

* UI reflects backend status
* No chat API allowed before completion
* Final status = `READY`

---

## 5. Chat & Agentic Flow Testing

### Test 5.1 — Session Creation

**Goal:** Every conversation is stateful and traceable.

Steps:

1. User clicks "Start Chat".
2. New session_id generated.
3. Session mapped to:

   * user_id
   * book_id
   * active_chapter = 1

Validate:

* Session record created
* Redis + DB state synced

---

### Test 5.2 — Chapter‑Scoped RAG Retrieval

**Goal:** Retrieval must be precise and controlled.

Steps:

1. User asks about Chapter 1.
2. Retriever pulls only Chapter 1 chunks.
3. Previous chapters = none.

Validate:

* Retrieval metadata logged
* No leakage from other chapters

---

### Test 5.3 — Chapter Completion & Summarization

**Goal:** Progression must be explicit and persistent.

Steps:

1. Agent completes Chapter 1.
2. Summary generated.
3. Stored in summaries table.
4. Chapter 1 marked DONE.
5. Chapter 2 becomes ACTIVE.

Validate:

* Summary exists
* Progress table updated
* Next retrieval uses:

  * Chapter 2 chunks
  * Chapter 1 summary as context

---

## 6. Multi‑Session Continuity Testing

### Test 6.1 — Resume Conversation

**Goal:** Context survives session boundaries.

Steps:

1. User exits after Chapter 2.
2. User returns later.
3. Starts new session.

Validate:

* System loads:

  * Completed chapters
  * Stored summaries
  * Last active chapter
* Conversation resumes correctly

---

## 7. Temporal‑Driven Agent Tests

### Test 7.1 — Inactivity Motivation Agent

**Goal:** Agents act without user input.

Steps:

1. User stays inactive for 3 seconds.
2. Temporal timer fires.
3. Motivation agent triggers.

Validate:

* Agent has correct context
* Message sent via WhatsApp
* Event logged

---

### Test 7.2 — Quiz Agent Trigger

**Goal:** Reinforcement via quizzes.

Steps:

1. Chapter marked DONE.
2. Temporal triggers quiz agent.
3. Quiz delivered in chat or WhatsApp.

Validate:

* Quiz questions relevant
* Based on chapter summary

---

## 8. Logging & Observability Tests (MANDATORY)

### Test 8.1 — Log Completeness

Verify every log entry contains:

* user_id
* session_id
* book_id (if applicable)
* chapter_id (if applicable)
* agent_name
* state_transition

Sources:

* User messages
* Agent responses
* RAG retrievals
* Temporal events

---

## 9. Notes & Storage Testing

### Test 9.1 — Notes Creation

**Goal:** User knowledge persists.

Steps:

1. User adds a note during Chapter 3.
2. Note stored locally + DB.

Validate:

* Note retrievable later
* Linked to chapter & session

---

## 10. Web ↔ Backend Connectivity Tests

### Test 10.1 — API Integrity

Validate:

* All UI actions map to backend APIs
* No silent failures
* Errors surfaced to user cleanly

---

## 11. Final Acceptance Criteria

The system passes only if:

* Entire 5‑chapter journey completes
* Progress is accurate
* Context is consistent
* No mock data used
* All logs are present
* Temporal agents fire correctly
* Zero unresolved bugs remain

---

## 12. Final Note (NON‑NEGOTIABLE)

This is **not a prototype**.
If any fix violates the five rules, **reject it**.

System integrity > speed > features.
