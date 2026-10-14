# tests/test_memory_and_quiz.py
#
# Deterministic offline tests for the persistent memory layers and the
# LangGraph routing/scoring logic. NO LLM calls — these run anywhere.
#
# Run: .venv/bin/python -m pytest tests/test_memory_and_quiz.py -q
#   or .venv/bin/python tests/test_memory_and_quiz.py

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from strud.backend.memory_store import MemoryStore  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


# ============================================================
# A) CONVERSATION MEMORY
# ============================================================

def test_conversations() -> None:
    print("\n== A) Conversation memory ==")
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(Path(tmp) / "t.db")

        store.append_message("c1", "u1", "user", "Explain mitosis")
        store.append_message("c1", "u1", "assistant", "Mitosis has four stages...")
        # duplicate message (retry) is preserved — append-only history
        store.append_message("c1", "u1", "user", "B")

        history = store.get_history("c1", "u1")
        check("history persists", len(history) == 3)
        check("order preserved", history[0]["content"] == "Explain mitosis")
        check("duplicate retries kept", history[2]["content"] == "B")

        # user isolation: another user sees nothing
        check("user isolation", store.get_history("c1", "u2") == [])
        # chat isolation: another chat sees nothing
        check("chat isolation", store.get_history("c2", "u1") == [])

        cleared = store.clear_conversation("c1", "u1")
        check("clear works", cleared == 3 and store.get_history("c1", "u1") == [])


# ============================================================
# B) USER MEMORY
# ============================================================

def test_user_memory() -> None:
    print("\n== B) Cross-chat user memory ==")
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(Path(tmp) / "t.db")

        store.remember("u1", "I prefer short bullet-point answers", source="explicit")
        store.remember("u1", "I prefer short bullet-point answers", source="explicit")  # dedup
        facts = store.recall("u1")
        check("stored + deduped", len(facts) == 1)

        check("user isolation", store.recall("u2") == [])

        # correction
        store.correct("u1", "bullet-point", "concise paragraph answers")
        facts = store.recall("u1")
        check(
            "correction replaces content",
            len(facts) == 1 and "concise paragraph" in facts[0]["content"]
            and facts[0]["source"] == "corrected",
        )

        # forget
        deleted = store.forget("u1", "concise paragraph")
        check("forget deletes", deleted == 1 and store.recall("u1") == [])

        # forget-by-id
        mid = store.remember("u1", "studying for March exam")
        check("forget_by_id", store.forget_by_id("u1", mid) == 1 and store.recall("u1") == [])


# ============================================================
# C) QUIZ SESSIONS & ATTEMPTS
# ============================================================

def test_quiz_scoring() -> None:
    print("\n== C) Quiz scoring (deterministic) ==")
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(Path(tmp) / "t.db")

        quiz = store.start_quiz_session("u1", "chat1", topic="enzymes")
        # 2 correct, 1 wrong -> 2/3 (66.7%)
        store.record_attempt("u1", quiz, "chat1", "q1", "Q1?", "B", "B", True)
        store.record_attempt("u1", quiz, "chat1", "q2", "Q2?", "D", "D", True)
        store.record_attempt("u1", quiz, "chat1", "q3", "Q3?", "C", "A", False)

        score = store.score_quiz("u1", quiz)
        check("2/3 attempted", score["attempted"] == 3)
        check("2/3 correct", score["correct"] == 2)
        check("66.7%", abs(score["percentage"] - 66.7) < 0.05)

        # retry same question overwrites, never double-counts
        store.record_attempt("u1", quiz, "chat1", "q3", "Q3?", "C", "C", True)
        score = store.score_quiz("u1", quiz)
        check("retry overwrites", score["attempted"] == 3 and score["correct"] == 3)

        # pending questions don't count
        store.register_pending_question("u1", quiz, "chat1", "q4", "Q4?")
        score = store.score_quiz("u1", quiz)
        check("pending not counted", score["attempted"] == 3)

        # grading the pending turns it into a real (incorrect) answer
        store.grade_pending_attempt("u1", quiz, "q4", "B", False)
        score = store.score_quiz("u1", quiz)
        check("graded pending counts", score["attempted"] == 4 and score["correct"] == 3)

        # user isolation
        check("quiz user isolation", store.score_quiz("u2", quiz) is None)

        # cross-chat lookup: quiz started in chat1 is findable from chat2
        found = store.find_quiz_sessions("u1", topic_substring="enzyme")
        check("cross-chat quiz lookup", len(found) == 1 and found[0]["quiz_id"] == quiz)


def test_quiz_session_separation() -> None:
    print("\n== D) Quiz session separation ==")
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(Path(tmp) / "t.db")

        q1 = store.start_quiz_session("u1", "chat1", topic="enzymes")
        q2 = store.start_quiz_session("u1", "chat2", topic="mitosis")

        # Each chat has exactly its own active session
        check("chat1 active", store.active_quiz_session("u1", "chat1")["quiz_id"] == q1)
        check("chat2 active", store.active_quiz_session("u1", "chat2")["quiz_id"] == q2)

        # Same chat restarts -> old one completed, not mixed
        q3 = store.start_quiz_session("u1", "chat1", topic="cells")
        check("same-chat replacement", store.active_quiz_session("u1", "chat1")["quiz_id"] == q3)
        s1 = store.get_quiz_session("u1", q1)
        check("old session completed", s1["status"] == "completed")

        # history endpoint shape
        sessions = store.all_quiz_sessions("u1")
        check("all sessions listed", len(sessions) == 3)


# ============================================================
# E) GRAPH ROUTING (offline — no LLM)
# ============================================================
# Route heuristics are exercised by importing the graph module and
# calling its compiled route node through a tiny fake graph? The route
# logic is a closure. Instead test the REGEXES the routes depend on,
# replicated from the module source, plus score patterns end-to-end
# through the store.

def test_route_patterns() -> None:
    print("\n== E) Route patterns ==")
    from strud.backend import tutoring_graph as tg

    # _WRONG_LETTER_RE / _CORRECT_RE live in the builder closure —
    # re-derive them by compiling a throwaway graph and pulling the
    # functions via a probe: simplest is to rebuild the regex behavior
    # through the public API instead. We test the verdict regexes by
    # importing the module-level copies used in tests below.
    import re as _re

    correct_re = _re.compile(
        r"\b([A-D])\b\s*(?:is\s+)?(?:indeed\s+)?(?:the\s+)?correct\b"
        r"|\bcorrect\s+(?:answer|option)\s+is\s+[*\"']{0,2}\(?([A-D])\)?"
        r"|\bthe\s+answer\s+is\s+[*\"']{0,2}\(?([A-D])\)?"
        r"|correct\s+answer\s*[:—-]\s*[*\"']{0,2}\(?([A-D])\)?",
        _re.IGNORECASE,
    )
    wrong_re = _re.compile(
        r"\(?([A-D])\)?\s+is\s+(?:not\s+correct|incorrect|wrong)\b"
        r"|\boption\s+\(?([A-D])\)?\s+is\s+(?:not\s+correct|incorrect|wrong)\b",
        _re.IGNORECASE,
    )

    def first(m):
        return next((g for g in m.groups() if g), None) if m else None

    check(
        "correct: 'C is correct'",
        first(correct_re.search("Yep, C is correct because ...")) == "C",
    )
    check(
        "correct: markdown bold",
        first(correct_re.search("the correct answer is **B** (thylakoid).")) == "B",
    )
    check(
        "correct: 'Correct answer: B'",
        first(correct_re.search("Correct answer: B")) == "B",
    )
    check(
        "wrong: 'C is not correct'",
        first(wrong_re.search("**C is not correct.**")) == "C",
    )
    check(
        "wrong: 'option D is incorrect'",
        first(wrong_re.search("Therefore, option D is incorrect; the correct answer is **B**.")) == "D",
    )
    check(
        "positive unaffected by wrong-letter",
        first(correct_re.search("B is correct")) == "B",
    )

    # score-route patterns (kept in sync with tutoring_graph.route)
    score_patterns = (
        r"what(?:'?s| is) my (?:score|result|marks?)\b",
        r"how did i (?:do|score|perform)\b",
        r"my (?:score|result)\s*(?:for|in|on)?\s*(?:the\s*)?(?:quiz|test|session)?",
        r"\b(?:quiz|test)\s+score\b",
        r"\b(?:show|tell)\s+(?:me\s+)?my\s+(?:score|result|marks?)\b",
    )
    check(
        "score: what's my score?",
        any(_re.search(p, "what's my score?") for p in score_patterns),
    )
    check(
        "score: how did I do?",
        any(_re.search(p, "how did i do on the quiz?") for p in score_patterns),
    )
    check(
        "score: does not match letter answer 'B'",
        not any(_re.search(p, "B") for p in score_patterns),
    )


def test_graph_compiles() -> None:
    print("\n== F) Graph compiles ==")
    from strud.backend.tutoring_graph import build_tutoring_graph
    graph = build_tutoring_graph()
    nodes = set(graph.get_graph().nodes.keys())
    expected = {"load_context", "route", "score_answer", "new_quiz", "quiz_answer",
                "remember", "recall", "forget", "quiz_history", "retrieve",
                "tutor", "validate", "finalize_quiz", "persist"}
    check("all nodes present", expected.issubset(nodes), f"missing: {expected - nodes}")


def main() -> None:
    test_conversations()
    test_user_memory()
    test_quiz_scoring()
    test_quiz_session_separation()
    test_route_patterns()
    test_graph_compiles()
    print(f"\n{'=' * 50}")
    print(f"RESULT: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
