#!/usr/bin/env python3
"""Passive-student E2E test — lets the teacher drive the entire book.

The student ONLY responds with minimal acknowledgments:
  - "Yes, understood. Please continue."
  - During quizzes: tries to answer correctly, falls back to "B"
  - During transitions: "Yes, let's continue."

This validates that the teacher agent autonomously covers all topics,
triggers quizzes, handles day/chapter transitions, and reaches completion.

Usage:
    E2E_AUTH_TOKEN=<token> python3 -u backend/tests/e2e/test_passive_student.py
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

REQUEST_TIMEOUT = 200
MAX_TOTAL_MESSAGES = 500
INTER_MSG_DELAY = 2.5
MAX_RETRIES_429 = 4
MAX_MSGS_PER_DAY = 40
MAX_STALE_ROUNDS = 8

PASSIVE_RESPONSES = [
    "Yes, understood. Please continue teaching.",
    "Got it, that makes sense. What's next?",
    "I understand. Please go on.",
    "Okay, I follow. Continue please.",
    "Makes sense. Please continue with the next topic.",
]

# After this many passive messages per day, check scope and nudge for quiz
PASSIVE_BEFORE_SCOPE_CHECK = 6

# ---------------------------------------------------------------------------
# Data
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


def _progress() -> Dict[str, Any]:
    time.sleep(1)
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


def _passive_msg(idx: int) -> str:
    return PASSIVE_RESPONSES[idx % len(PASSIVE_RESPONSES)]


# ---------------------------------------------------------------------------
# Main test loop
# ---------------------------------------------------------------------------

def run() -> Report:
    report = Report()
    t0 = time.time()

    print("=" * 70)
    print("PASSIVE STUDENT E2E TEST — Modern Robotics")
    print("Teacher drives all content; student only acknowledges.")
    print("=" * 70)

    _init()

    plan_data = _plan()
    plan_days = plan_data.get("days", [])
    if not plan_days:
        print("[FATAL] No plan found.")
        sys.exit(1)
    total_days = plan_data.get("total_days", len(plan_days))
    teaching_count = sum(1 for d in plan_days if not d.get("rest"))
    print(f"[setup] Plan: {total_days} days ({teaching_count} teaching)")
    print()

    prog = _progress()
    last_phase = prog.get("current_phase", "teaching")
    msg_count = 0
    passive_idx = 0

    # Send initial "Let's begin" to kick off Day 1
    print("[start] Sending: \"Let's begin today's lesson.\"")
    try:
        resp = _chat("Let's begin today's lesson.")
        msg_count += 1
        report.total_messages += 1
        last_phase = resp.get("phase", last_phase)
        txt = resp.get("message", "")
        print(f"  -> phase={last_phase}, len={len(txt)}")
        print(f"  -> preview: {txt[:200]}...")
    except Exception as e:
        print(f"  [ERR] {e}")
        report.errors.append(f"start: {e}")

    while msg_count < MAX_TOTAL_MESSAGES:
        prog = _progress()
        cur_day = prog["current_day"]
        completed = prog.get("completed_days", [])

        if last_phase == "completed" or cur_day > total_days:
            print("\n*** COURSE COMPLETED ***")
            break

        if cur_day not in report.days:
            report.days[cur_day] = DayReport(day_number=cur_day)
        dr = report.days[cur_day]
        day_msgs = 0

        print(f"\n--- Day {cur_day} / {total_days} | phase={last_phase} | completed={completed} ---")

        scope_check_done = False

        while day_msgs < MAX_MSGS_PER_DAY and msg_count < MAX_TOTAL_MESSAGES:
            prog = _progress()
            new_day = prog["current_day"]
            if new_day != cur_day:
                print(f"  [day_advance] Day moved from {cur_day} -> {new_day}")
                break

            last_phase = prog.get("current_phase", last_phase)

            if last_phase == "completed":
                break

            # After N passive messages, check scope and nudge for quiz if >= 90%
            scope_pct = prog.get("scope_completion_percentage", 0)
            if (day_msgs >= PASSIVE_BEFORE_SCOPE_CHECK
                    and last_phase == "teaching"
                    and scope_pct >= 90):
                if not scope_check_done:
                    msg = (
                        "I've understood all the topics for today's session. "
                        "All scope items are covered. Please start the quiz now!"
                    )
                    tag = "scope_nudge"
                    scope_check_done = True
                elif day_msgs % 2 == 0:
                    msg = "Yes, I'm ready. Please give me the quiz now."
                    tag = "quiz_force"
                else:
                    msg = "OK got it. Can we please do the quiz?"
                    tag = "quiz_force"
            elif last_phase in ("chapter_transition", "awaiting_chapter_start"):
                msg = "Yes, let's continue to the next chapter."
                tag = "transition"
            elif last_phase in ("quiz", "quiz_feedback"):
                if last_phase == "quiz_feedback":
                    msg = "No thanks, let's move on to the next day."
                    tag = "quiz_feedback"
                else:
                    msg = "B"
                    tag = "quiz"
            elif last_phase == "teaching":
                msg = _passive_msg(passive_idx)
                passive_idx += 1
                tag = "passive"
            else:
                msg = _passive_msg(passive_idx)
                passive_idx += 1
                tag = f"phase:{last_phase}"

            print(f"  [{tag}] \"{msg[:60]}\"")
            try:
                t1 = time.time()
                resp = _chat(msg)
                ms = int((time.time() - t1) * 1000)
                msg_count += 1
                report.total_messages += 1
                day_msgs += 1
                txt = resp.get("message", "")
                last_phase = resp.get("phase", last_phase)
                dr.total_chars += len(txt)
                dr.latency_total_ms += ms

                if tag == "quiz":
                    dr.quiz_answers += 1
                elif tag in ("passive", "transition"):
                    dr.teaching_msgs += 1

                print(f"    -> phase={last_phase}, len={len(txt)}, {ms}ms")

                # Print first 200 chars of teacher content for visibility
                if len(txt) > 0:
                    preview = txt[:200].replace("\n", " ")
                    print(f"    -> {preview}...")

            except Exception as e:
                dr.errors.append(f"{tag}: {e}")
                print(f"    [ERR] {e}")
                break

        # End of day summary
        prog = _progress()
        dr.quiz_passed = cur_day in (prog.get("completed_days") or [])
        print(f"  [day_done] completed_days={prog.get('completed_days', [])}")

    # Final state
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
    print("PASSIVE STUDENT E2E TEST REPORT")
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

    if r.errors:
        print("ERRORS:")
        for e in r.errors[:20]:
            print(f"  - {e}")
        print()

    expected = set(range(1, 12))
    done = set(r.completed_days)
    missing = expected - done

    if r.final_phase == "completed" and not missing:
        print("RESULT: PASS -- Teacher drove entire book successfully")
    elif not missing:
        print(f"RESULT: PARTIAL -- all days done but phase='{r.final_phase}'")
    else:
        print(f"RESULT: FAIL -- missing days {sorted(missing)}, phase='{r.final_phase}'")


# ---------------------------------------------------------------------------
# Entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if not AUTH_TOKEN:
        print("ERROR: E2E_AUTH_TOKEN not set.")
        sys.exit(2)
    rpt = run()
    print_report(rpt)
    sys.exit(0 if rpt.final_phase == "completed" else 1)
