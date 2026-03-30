#!/usr/bin/env python3
"""Full-book E2E test — plays a student through every day of the plan.

This is a state-driven test: it reads the current day from the backend
and sends contextual student messages until the course completes.

Usage (Docker stack must be running):

    TOKEN=$(docker exec professor-backend python3 -c \\
      "from app.security.jwt import create_access_token; from datetime import timedelta; \\
       print(create_access_token(subject='a3fce926-4d02-4cb4-bebf-7340c8fb8f61', expires_delta=timedelta(hours=3)))")

    E2E_AUTH_TOKEN=$TOKEN python3 -u backend/tests/e2e/test_full_book.py

Environment variables:
    E2E_AUTH_TOKEN  (required)  JWT bearer token
    E2E_BASE_URL    (optional)  default http://localhost:8000
    E2E_BOOK_ID     (optional)  default auto-detected
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = os.getenv("E2E_BASE_URL", "http://localhost:8000")
BOOK_ID = os.getenv("E2E_BOOK_ID", "add5a73b-4d2b-45db-ad4f-922b1324995a")
AUTH_TOKEN = os.getenv("E2E_AUTH_TOKEN", "")

REQUEST_TIMEOUT = 180
MAX_TOTAL_MESSAGES = 300
QUIZ_FALLBACK = "B"
INTER_MSG_DELAY = 2.5       # seconds between messages to respect burst limits
MAX_RETRIES_429 = 4
MAX_STALE_ROUNDS = 5        # give up on a day if quiz can't be triggered after this many extra attempts

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DayReport:
    day_number: int
    teaching_msgs: int = 0
    quiz_answers: int = 0
    quiz_passed: Optional[bool] = None
    total_chars: int = 0
    latency_total_ms: int = 0
    errors: List[str] = field(default_factory=list)


@dataclass
class Report:
    days: Dict[int, DayReport] = field(default_factory=dict)
    total_messages: int = 0
    elapsed_s: float = 0
    final_phase: str = ""
    final_day: int = 0
    completed_days: List[int] = field(default_factory=list)
    completed_chapters: List[int] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

_HDR: Dict[str, str] = {}


def _init():
    global _HDR
    _HDR = {"Authorization": f"Bearer {AUTH_TOKEN}", "Content-Type": "application/json"}


def _chat(msg: str) -> Dict[str, Any]:
    for attempt in range(MAX_RETRIES_429 + 1):
        r = requests.post(
            f"{BASE_URL}/api/chat/v2",
            headers=_HDR,
            json={"message": msg, "book_id": BOOK_ID},
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code == 429:
            wait = 6 * (attempt + 1)
            print(f"      [429] Rate limited, waiting {wait}s (attempt {attempt+1})...")
            time.sleep(wait)
            continue
        r.raise_for_status()
        time.sleep(INTER_MSG_DELAY)
        return r.json()
    r.raise_for_status()
    return {}


def _reset():
    r = requests.post(f"{BASE_URL}/api/learning/state/{BOOK_ID}/reset", headers=_HDR, timeout=30)
    r.raise_for_status()
    time.sleep(4)


def _progress() -> Dict[str, Any]:
    time.sleep(1)  # short delay so the save_chat_state activity can complete
    r = requests.get(f"{BASE_URL}/api/learning/progress/{BOOK_ID}/detailed", headers=_HDR, timeout=15)
    r.raise_for_status()
    return r.json()


def _plan() -> Dict[str, Any]:
    r = requests.get(f"{BASE_URL}/api/planning/{BOOK_ID}/current", headers=_HDR, timeout=15)
    if r.status_code == 404:
        return {}
    r.raise_for_status()
    data = r.json()
    return data.get("plan_data", data)


# ---------------------------------------------------------------------------
# Helpers for per-day topic messages
# ---------------------------------------------------------------------------

def _topics_for_day(plan_data: Dict[str, Any], day_num: int) -> List[str]:
    """Return the list of topic names for a given day in the plan."""
    for d in plan_data.get("days", []):
        if d.get("day") == day_num:
            names = []
            for item in d.get("items", []):
                for t in item.get("topics", []):
                    names.append(t["name"] if isinstance(t, dict) else str(t))
            return names
    return []


def _chapter_titles_for_day(plan_data: Dict[str, Any], day_num: int) -> str:
    for d in plan_data.get("days", []):
        if d.get("day") == day_num:
            return ", ".join(i.get("chapter_title", "") for i in d.get("items", []))
    return ""


# ---------------------------------------------------------------------------
# Main test loop — state-driven
# ---------------------------------------------------------------------------

def run() -> Report:
    report = Report()
    t0 = time.time()

    print("=" * 70)
    print("FULL E2E TEST — Modern Robotics (State-Driven)")
    print("=" * 70)

    _init()

    # ---- Reset ----
    print("[setup] Resetting...")
    _reset()
    prog = _progress()
    assert prog["current_day"] == 1, f"Reset failed: day={prog['current_day']}"
    print(f"[setup] Clean: Day=1")

    plan_data = _plan()
    plan_days = plan_data.get("days", [])
    if not plan_days:
        print("[FATAL] No plan found.")
        sys.exit(1)
    total_days = plan_data.get("total_days", len(plan_days))
    teaching_count = sum(1 for d in plan_days if not d.get("rest"))
    print(f"[setup] Plan: {total_days} days ({teaching_count} teaching)")
    print()

    last_phase = "teaching"
    msg_count = 0

    while msg_count < MAX_TOTAL_MESSAGES:
        prog = _progress()
        cur_day = prog["current_day"]
        completed = prog.get("completed_days", [])

        # Check for course completion
        if last_phase == "completed" or cur_day > total_days:
            print("*** COURSE COMPLETED ***")
            break

        # Ensure we have a DayReport
        if cur_day not in report.days:
            report.days[cur_day] = DayReport(day_number=cur_day)
        dr = report.days[cur_day]

        topics = _topics_for_day(plan_data, cur_day)
        ch_titles = _chapter_titles_for_day(plan_data, cur_day)
        print(f"--- Day {cur_day}: {ch_titles or 'N/A'} | topics={topics} ---")

        # Handle transition phases
        if last_phase in ("chapter_transition", "awaiting_chapter_start"):
            for _ in range(3):
                if last_phase not in ("chapter_transition", "awaiting_chapter_start"):
                    break
                print(f"  [transition] phase={last_phase}")
                try:
                    resp = _chat("Yes, let's continue to the next chapter!")
                    last_phase = resp.get("phase", last_phase)
                    msg_count += 1
                    report.total_messages += 1
                    dr.total_chars += len(resp.get("message", ""))
                    print(f"    -> phase={last_phase}")
                except Exception as e:
                    dr.errors.append(f"transition: {e}")
                    print(f"    [ERR] {e}")
                    break

        if last_phase == "completed":
            print("*** COURSE COMPLETED ***")
            break

        # ---- Teaching phase ----
        # Start with a generic opener
        teach_msgs = [f"Let's begin Day {cur_day}'s lesson. Please teach me the key concepts."]
        # Ask about each topic explicitly
        for t in topics:
            teach_msgs.append(
                f"Please explain {t} from {ch_titles} in detail with formulas and examples."
            )
        # Finish with summary + quiz request
        if topics:
            all_names = ", ".join(topics)
            teach_msgs.append(
                f"I now understand {all_names}. All topics are covered. "
                f"Please start the quiz!"
            )
        else:
            teach_msgs.append("I understand everything. Let's do a quiz!")

        for i, msg in enumerate(teach_msgs):
            if last_phase in ("quiz", "quiz_feedback", "completed"):
                break
            # Re-check progress — another quiz might have advanced the day
            p2 = _progress()
            if p2["current_day"] != cur_day:
                break

            tag = f"teach {i+1}/{len(teach_msgs)}"
            print(f"  [{tag}] \"{msg[:70]}\"")
            try:
                t1 = time.time()
                resp = _chat(msg)
                ms = int((time.time() - t1) * 1000)
                msg_count += 1
                report.total_messages += 1
                dr.teaching_msgs += 1
                txt = resp.get("message", "")
                dr.total_chars += len(txt)
                dr.latency_total_ms += ms
                last_phase = resp.get("phase", last_phase)
                print(f"    -> phase={last_phase}, len={len(txt)}, {ms}ms")
            except Exception as e:
                dr.errors.append(f"teach_{i}: {e}")
                print(f"    [ERR] {e}")

        # ---- If still teaching, send extra quiz-trigger messages ----
        stale = 0
        while last_phase == "teaching" and stale < MAX_STALE_ROUNDS:
            stale += 1
            trigger_msg = (
                f"I've learned all the topics for today: {', '.join(topics)}. "
                f"All scope items are covered. Please give me the quiz now!"
                if topics else "Please start the quiz now!"
            )
            print(f"  [quiz_trigger {stale}/{MAX_STALE_ROUNDS}] Forcing quiz...")
            try:
                resp = _chat(trigger_msg)
                msg_count += 1
                report.total_messages += 1
                last_phase = resp.get("phase", last_phase)
                dr.total_chars += len(resp.get("message", ""))
                print(f"    -> phase={last_phase}")
            except Exception as e:
                dr.errors.append(f"quiz_trigger_{stale}: {e}")
                print(f"    [ERR] {e}")
                break

            # If the teacher keeps teaching, absorb the content and try again
            if last_phase == "teaching":
                try:
                    resp = _chat("OK, got it. Now can we please do the quiz?")
                    msg_count += 1
                    report.total_messages += 1
                    last_phase = resp.get("phase", last_phase)
                    dr.total_chars += len(resp.get("message", ""))
                except Exception as e:
                    dr.errors.append(f"quiz_nudge_{stale}: {e}")
                    break

        # ---- Quiz phase ----
        for q in range(8):
            if last_phase not in ("quiz", "quiz_feedback"):
                break

            if last_phase == "quiz_feedback":
                print(f"  [quiz_feedback] Declining retry, moving on...")
                try:
                    resp = _chat("No thanks, let's move on to the next day.")
                    msg_count += 1
                    report.total_messages += 1
                    last_phase = resp.get("phase", last_phase)
                    dr.quiz_passed = False
                    print(f"    -> phase={last_phase}")
                except Exception as e:
                    dr.errors.append(f"feedback: {e}")
                    print(f"    [ERR] {e}")
                break

            print(f"  [quiz Q{q+1}] Answering '{QUIZ_FALLBACK}'")
            try:
                t1 = time.time()
                resp = _chat(QUIZ_FALLBACK)
                ms = int((time.time() - t1) * 1000)
                msg_count += 1
                report.total_messages += 1
                dr.quiz_answers += 1
                dr.total_chars += len(resp.get("message", ""))
                dr.latency_total_ms += ms
                last_phase = resp.get("phase", last_phase)
                print(f"    -> phase={last_phase}, {ms}ms")
            except Exception as e:
                dr.errors.append(f"quiz_{q}: {e}")
                print(f"    [ERR] {e}")
                break

        # ---- End of day ----
        prog = _progress()
        dr.quiz_passed = cur_day in (prog.get("completed_days") or [])
        new_day = prog["current_day"]

        print(f"  [done] DB day={new_day}, completed={prog.get('completed_days', [])}")
        print()

        # Safety: if day didn't advance after all attempts, force next iteration
        if new_day == cur_day and last_phase == "teaching":
            print(f"  [WARN] Day {cur_day} stuck, sending fallback advance message...")
            try:
                resp = _chat("Let's move on to the next topic please.")
                msg_count += 1
                report.total_messages += 1
                last_phase = resp.get("phase", last_phase)
            except Exception as e:
                dr.errors.append(f"stuck: {e}")
            prog = _progress()
            if prog["current_day"] == cur_day:
                print(f"  [WARN] Still stuck on day {cur_day}. Continuing anyway.")

    # ---- Final state ----
    prog = _progress()
    report.final_phase = last_phase
    report.final_day = prog["current_day"]
    report.completed_days = prog.get("completed_days", [])
    report.completed_chapters = prog.get("completed_chapters", [])
    report.elapsed_s = time.time() - t0
    for dr in report.days.values():
        report.errors.extend(dr.errors)
    return report


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(r: Report):
    print()
    print("=" * 70)
    print("E2E TEST REPORT")
    print("=" * 70)
    print(f"Time:     {r.elapsed_s:.0f}s ({r.elapsed_s/60:.1f}min)")
    print(f"Messages: {r.total_messages}")
    print(f"Phase:    {r.final_phase}")
    print(f"Day:      {r.final_day}")
    print(f"Done:     {sorted(r.completed_days)}")
    print(f"Chapters: {sorted(r.completed_chapters)}")
    print(f"Errors:   {len(r.errors)}")
    print()

    hdr = f"{'Day':>4} {'Teach':>6} {'Quiz':>5} {'Chars':>7} {'Ms':>8} {'Passed':>7} {'Err':>4}"
    print(hdr)
    print("-" * len(hdr))
    for day_num in sorted(r.days.keys()):
        d = r.days[day_num]
        passed = "yes" if d.quiz_passed else ("no" if d.quiz_passed is False else "-")
        print(
            f"{d.day_number:>4} {d.teaching_msgs:>6} "
            f"{d.quiz_answers:>5} {d.total_chars:>7} {d.latency_total_ms:>7}ms "
            f"{passed:>7} {len(d.errors):>4}"
        )
    print()

    warns = []
    for d in r.days.values():
        if d.teaching_msgs > 0 and d.total_chars < 500:
            warns.append(f"Day {d.day_number}: Very short responses ({d.total_chars} chars)")
        if d.errors:
            for e in d.errors:
                warns.append(f"Day {d.day_number}: {e}")
    if warns:
        print("WARNINGS:")
        for w in warns:
            print(f"  - {w}")
        print()

    expected = set(range(1, 12))  # Days 1-11
    done = set(r.completed_days)
    missing = expected - done

    if r.final_phase == "completed" and not missing:
        print("RESULT: PASS")
    elif not missing:
        print(f"RESULT: PARTIAL — all days done but phase='{r.final_phase}'")
    else:
        print(f"RESULT: FAIL — missing days {sorted(missing)}, phase='{r.final_phase}'")

    if r.errors:
        print(f"\nErrors ({len(r.errors)}):")
        for e in r.errors[:20]:
            print(f"  - {e}")


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not AUTH_TOKEN:
        print("ERROR: E2E_AUTH_TOKEN not set. Generate with:")
        print("  docker exec professor-backend python3 -c \\")
        print("    \"from app.security.jwt import create_access_token; from datetime import timedelta; "
              "print(create_access_token(subject='<USER_ID>', expires_delta=timedelta(hours=3)))\"")
        sys.exit(2)
    rpt = run()
    print_report(rpt)
    sys.exit(0 if rpt.final_phase == "completed" else 1)
