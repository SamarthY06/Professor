# 🎯 Goals: Professor‑Driven AI Learning Agent

## 1. Vision

Build a **Professor‑Driven AI Learning System** that *actively teaches*, *plans*, *tracks*, *motivates*, and *evaluates* students end‑to‑end — instead of passively responding like a chatbot.

The system should feel like a **dedicated professor** who:

* Understands the student’s level and goals
* Plans a personalized learning path
* Teaches step‑by‑step interactively
* Proactively brings the student back if they disengage
* Evaluates understanding through quizzes
* Tracks progress visually
* Adapts plans dynamically with human‑in‑the‑loop control

The **AI drives the learning journey**, not the user.

---

## 2. Core Philosophy

* ❌ Not a chatbot
* ❌ Not one‑shot explanations
* ✅ A persistent professor with memory, intent, and goals
* ✅ Agent‑driven, event‑driven, and stateful
* ✅ Human‑in‑the‑loop at every major decision

---

## 3. High‑Level User Journey (End‑to‑End)

### Step 1: PDF Upload & Configuration

User uploads a PDF (book, notes, research material).

During upload, the UI collects:

* Learning level (e.g., BTech / MTech / Research)
* Chapters to study (full book or selected chapters)
* Deadline / timeline
* Quiz preference:

  * Quiz after every chapter
  * Quiz after N chapters
  * Only final quiz
* Quiz depth & number of questions
* Reminder & inactivity preferences

---

### Step 2: Ingestion & Chunking

* PDF is chunked
* Chapters and subtopics are indexed
* Metadata stored (chapter → topic → chunk mapping)
* No teaching starts yet

---

### Step 3: Professor Initiation (Auto‑Triggered)

Once chunking completes, the **Professor Agent automatically triggers**.

Professor greets the user:

> “Hello! How are you? I’ve analyzed your material. Shall I plan your learning journey?”

This is **not user‑initiated** — the system starts the interaction.

---

### Step 4: Planner Agent (Human‑in‑the‑Loop)

If user agrees:

* Planner Agent is triggered
* Generates a **detailed, chapter‑wise, timeline‑aware plan** based on:

  * User level
  * Selected chapters
  * Deadline
  * Quiz settings

Planner iterates with the user until:

* User reviews
* User requests changes (depth, pacing, ordering)
* User explicitly **accepts** the plan

No teaching starts until plan acceptance.

---

## 4. Teaching Flow (Chapter‑Wise, Step‑by‑Step)

### Chapter Start

Professor says:

* “Let’s begin with Chapter 1.”
* Explains what will be covered *today*
* Confirms excitement & readiness

### Controlled RAG Retrieval

* Only **current chapter’s relevant chunks** are retrieved
* Sent as context to Teaching Agent
* Prevents context explosion

### Teaching Style

* Step‑by‑step explanation
* Interactive questioning
* Continuous understanding checks
* Professor decides pacing

### Doubt Resolution

After chapter completion:

* Professor asks explicitly for doubts
* Clears doubts interactively
* Does not move forward prematurely

### Chapter Summary

* Generates a concise summary
* Stores summary in DB
* Marks chapter as completed

---

## 5. Multi‑Chapter Continuity

When moving to the next chapter:

* Previous chapter summary is retrieved
* Professor recaps:

  > “In Chapter 1, we covered…”
* Then introduces Chapter 2
* New chapter chunks are retrieved

This continues until all selected chapters are completed.

---

## 6. Quiz Agent (Evaluation Layer)

### Quiz Trigger Conditions

Based on user preference:

* After every chapter
* After N chapters
* Only at the end

When trigger condition is met:

* Quiz Agent activates automatically

### Quiz Behavior

* Uses:

  * Chapter summaries
  * Relevant retrieved chunks
* Asks **one question at a time**
* Validates answers (not just asks)
* Provides feedback and corrections

### Quiz Memory Design

* Quiz Agent has **separate context**
* Shares summarized knowledge with Teaching Agent
* Efficient memory usage (no raw chunk overload)

User can:

* Control number of questions
* End quiz when confident

---

## 7. Progress Tracker Agent

Maintains global learning state:

* Chapter completion
* Quiz completion
* Current position

UI Dashboard:

* Chapter 1 ✅ | Quiz 1 ✅
* Chapter 2 ✅ | Quiz 2 ⏳
* Visual indicators (progress bar / timeline / graph)

State is persistent across sessions.

---

## 8. Temporal‑Driven Proactive Learning

### Why Temporal

Temporal is the **orchestration backbone**, not the teacher.

Temporal:

* Detects inactivity
* Triggers agents
* Manages time‑based workflows

### Inactivity Handling

If user disengages (based on configured time):

Temporal triggers:

1. **Motivation Agent**

   * Sends WhatsApp reminder
   * Shows progress snapshot
   * Encouraging, contextual message

2. **Recall / Quiz Agent (optional)**

   * Light recall question to re‑engage

3. **Schedule Adjustment Logic**

   * Professor asks:

     * Continue with compressed plan?
     * Or shift timeline?

All decisions are AI‑driven with human approval.

---

## 9. Motivation Agent

* Activated by Temporal
* Context‑aware encouragement
* Mentions:

  * Completed chapters
  * Remaining workload
* Pulls user back proactively

---

## 10. Dynamic Plan Adjustment

If user:

* Delays learning
* Requests postponement
* Changes availability

Professor:

* Replans remaining chapters
* Asks for confirmation
* Updates timeline intelligently

No hardcoded rules — LLM‑driven reasoning.

---

## 11. Early Termination Handling

If user says:

> “I’ve learned enough.”

System:

* Ends learning session gracefully
* Marks progress as user‑ended
* Stores final state

---

## 12. Agent Architecture Summary

### Core Agents

* Professor / Teaching Agent
* Planner Agent
* Quiz Agent
* Progress Tracker Agent
* Motivation Agent

### Orchestration

* Temporal controls *when* agents act
* Agents control *what* happens

---

## 13. Ultimate Goal

Create a system where:

* Learning is **guided, not reactive**
* AI behaves like a **real professor**
* Students are **pulled into learning**, not pushed to use a tool
* End‑to‑end journey is clear, structured, and adaptive

This document defines the **single source of truth** for building the system.


Notes Feature

1) User can select any professor response
2) Click “Add to Notes”
3) Content is stored in a separate Notes document in local
Linked to: User PDF / Book Chapter Timestamp

Notes:

Are user-curated (no auto-generation)
Persist across sessions
Do NOT pollute teaching / quiz context
Can be optionally used later for revision or recall
Accessible via a Notes panel / document view

