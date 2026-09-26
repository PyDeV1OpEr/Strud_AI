# answer_intelligence.py
#
# Internal reasoning layer for Strud AI (Phase 3).
#
# This module decides HOW an answer should be shaped, and keeps a small
# amount of conversational state so follow-ups ("explain that again",
# "why?") resolve against what was actually discussed.
#
# It is strictly INTERNAL:
#   - it never writes user-facing prose
#   - it never decides the domain (semantic_router does)
#   - it never decides grounding (evidence_sufficiency does)
#   - it never exposes JSON to the student
#
# Structured plans/validations use Pydantic when it is installed and
# plain dataclasses otherwise, so the offline runtime never gains a
# mandatory dependency for this.

from __future__ import annotations

import re
from dataclasses import asdict, field, fields, is_dataclass
from typing import Any, Optional

from config import (
    MAX_HISTORY_MESSAGES,
    MAX_MEMORY_TURNS,
    FOLLOWUP_MAX_WORDS,
    REPETITION_LOOKBACK_TURNS,
    ASSISTANT_DOMAIN,
)

# ------------------------------------------------------------
# Pydantic-if-available schema base
# ------------------------------------------------------------

try:  # pragma: no cover - depends on the local environment
    from pydantic.dataclasses import dataclass as _schema

    PYDANTIC_AVAILABLE = True
except Exception:  # pragma: no cover
    from dataclasses import dataclass as _schema

    PYDANTIC_AVAILABLE = False


def to_dict(instance) -> dict:
    """Dataclass/pydantic-dataclass -> plain dict (internal use only)."""
    try:
        return asdict(instance)
    except Exception:
        return {}


# ============================================================
# VOCABULARIES
# ============================================================

DEPTH_LEVELS = ("very_short", "short", "normal", "detailed", "deep_dive")

TUTORING_MODES = (
    "none", "explanation", "socratic", "quiz", "correction",
    "revision", "exam",
)

ANSWER_TYPES = (
    "conversation", "direct_fact", "conceptual_explanation",
    "mechanism", "comparison", "visual_explanation",
    "quiz_question", "answer_feedback", "revision_summary",
)


# ============================================================
# INTERNAL SCHEMAS
# ============================================================

@_schema
class AnswerPlan:
    """
    Internal plan for one answer. Never shown to the student.

    intent/mode describe WHAT is needed; depth/tone/structure describe
    HOW it should sound. The router decides the first half, this plan
    decides the second, and generation follows it loosely - it is
    guidance, not a template.
    """

    intent: str = "other"
    mode: str = "conversation"
    tutoring_mode: str = "none"
    depth: str = "normal"
    tone: str = "friendly"
    answer_type: str = "conversation"
    needs_retrieval: bool = False
    evidence_required: bool = False
    evidence_sufficient: bool = False
    evidence_verdict: str = "not_assessed"
    citation_required: bool = False
    grounded: bool = False
    has_visual_evidence: bool = False
    notes: str = ""


@_schema
class AnswerValidation:
    """Internal record of the post-generation quality checks."""

    grounded: bool = False
    evidence_sufficient: bool = False
    citations_valid: bool = True
    answered_question: bool = True
    unsupported_claims: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.citations_valid
            and self.answered_question
            and not self.issues
        )


# ============================================================
# MARKERS
# ============================================================

DEEP_MARKERS = (
    "in detail", "in depth", "deeply", "go deeper", "step by step",
    "step-by-step", "thoroughly", "everything about", "full mechanism",
    "full explanation", "explain fully", "in a lot of detail",
    "deep dive", "comprehensive",
)

CONFUSION_MARKERS = (
    "don't understand", "dont understand", "do not understand",
    "don't get", "dont get", "do not get", "confused", "no idea",
    "i'm lost", "im lost", "lost me", "still don't", "still dont",
    "not clear", "doesn't make sense", "doesnt make sense",
    "help me understand", "makes no sense",
)

QUIZ_MARKERS = (
    "test me", "quiz me", "test my", "test on", "quiz on",
    "ask me questions", "ask me a question",
    "give me a question", "give me questions", "give me another",
    "make me questions", "make questions", "ask questions",
    "practice questions", "past paper questions", "mcq", "mcqs",
    "multiple choice", "harder", "harder one", "easier one",
)

CORRECTION_MARKERS = (
    "is that right", "did i get", "was i right", "is my answer",
    "check my answer", "did i answer", "is it correct",
    "did i do it right",
)

REVISION_MARKERS = (
    "revise", "revision", "recap", "quick recap", "summarise",
    "summarize", "summary", "key points", "important points",
    "help me remember", "before the exam", "night before",
)

EXAM_MARKERS = (
    "exam", "exam question", "a/l", "advanced level", "marking scheme",
    "marked", "marks", "how many marks", "al paper", "past paper",
)

CASUAL_MARKERS = (
    "bro", "bruh", "bruv", "dude", "ngl", "tbh", "lol", "lmao",
    "lowkey", "highkey", "yo", "sup", "gonna", "wanna", "kinda",
    "sorta", "damn", "nah", "yep", "yeah", "haha", "hahaha",
    "\U0001f602", "\U0001f62d", "\U0001f480", "\U0001f44d",
)

FOLLOWUP_MARKERS = (
    "that again", "explain that", "explain it", "why though",
    "why not", "what about", "and that", "same thing", "the second",
    "the second one", "the first one", "that one", "this one",
    "more detail", "more", "again", "repeat", "what does that mean",
    "why is that", "and why", "but why", "so why", "then what",
    "what happens next", "what next", "how so", "really",
)

SHORT_FACT_MARKERS = (
    "what is", "what are", "what's", "whats", "what does", "define",
    "definition of", "meaning of", "stand for", "stands for",
    "full form", "abbreviation", "who is", "how many", "how much",
    "symbol", "formula for", "unit of",
)

QUIZ_ANSWER_MARKERS = (
    "i don't know", "i dont know", "no idea", "idk", "dunno",
    "not sure", "no clue", "i think it's", "i think its",
    "my answer is", "the answer is",
)


def _contains(text: str, markers) -> bool:
    return any(marker in text for marker in markers)


# ============================================================
# TUTORING / DEPTH / TONE
# ============================================================

def infer_tutoring_mode(
    question: str,
    history: Optional[list] = None,
) -> str:
    """Decide whether the student is asking to be tutored."""
    text = (question or "").lower().strip()

    if _contains(text, QUIZ_MARKERS):
        return "quiz"
    if _contains(text, QUIZ_ANSWER_MARKERS):
        return "correction"
    if _contains(text, CORRECTION_MARKERS):
        return "correction"
    if _contains(text, EXAM_MARKERS):
        return "exam"
    if _contains(text, REVISION_MARKERS):
        return "revision"
    if _contains(text, CONFUSION_MARKERS):
        return "explanation"

    # "teach me X" / "help me learn X"
    if re.search(r"\b(teach|help) me\b", text) or "walk me through" in text:
        return "explanation"

    # Socratic continuation: a bare disagreement inside an explanation
    # conversation invites reasoning rather than a lecture.
    if history and _contains(text, ("what about", "why not", "but why")):
        return "socratic"

    return "none"


def estimate_depth(
    question: str,
    intent: str = "",
    tutoring_mode: str = "none",
) -> str:
    """
    Estimate how much explanation this question deserves.

    Deliberately graduated: a quick fact is not a lecture, and a
    confused student asking about a whole process is not a tweet.
    """
    text = (question or "").lower().strip()
    word_count = len(text.split())

    if tutoring_mode == "quiz":
        return "short"

    if tutoring_mode == "exam":
        return "detailed"

    if tutoring_mode in ("revision",):
        return "short"

    if _contains(text, DEEP_MARKERS):
        return "deep_dive"

    if _contains(text, CONFUSION_MARKERS):
        return "detailed"

    if _contains(text, ("explain", "describe", "discuss", "walk me", "teach")):
        return "detailed" if word_count <= 3 else "normal"

    multi_concept = (
        any(marker in text for marker in (" and ", " then ", " vs ", " versus "))
        or _contains(text, ("compare", "difference", "differences"))
    )

    if intent == "social_reaction":
        return "short"

    if _contains(text, SHORT_FACT_MARKERS):
        return "detailed" if multi_concept else "short"

    if word_count <= 3:
        return "short"

    if multi_concept or word_count >= 18:
        return "detailed"

    if intent in ("casual_conversation", "social_reaction"):
        return "short"

    return "normal"


def estimate_tone(question: str, intent: str = "") -> str:
    """Mirror the student's register a little, never all the way."""
    text = (question or "").lower()

    if intent in ("casual_conversation", "social_reaction") or _contains(
        text, CASUAL_MARKERS
    ):
        return "casual"

    if _contains(text, CONFUSION_MARKERS):
        return "reassuring"

    if intent == "biology_explanation" or _contains(text, EXAM_MARKERS):
        return "explanatory"

    return "friendly"


# ============================================================
# ANSWER PLAN
# ============================================================

def build_answer_plan(
    question: str,
    decision=None,
    assessment=None,
    has_image: bool = False,
    memory=None,
) -> AnswerPlan:
    """
    Build the internal plan for one answer.

    decision   - RouteDecision from semantic_router (or None)
    assessment - EvidenceAssessment from evidence_sufficiency (or None)
    """

    intent = getattr(decision, "intent", "other") or "other"
    domain = getattr(decision, "domain", "other") or "other"
    needs_retrieval = bool(getattr(decision, "needs_retrieval", False))

    history = list(getattr(memory, "turns", []) or []) if memory else []

    tutoring_mode = infer_tutoring_mode(question, history)
    depth = estimate_depth(question, intent=intent, tutoring_mode=tutoring_mode)
    tone = estimate_tone(question, intent=intent)

    verdict = getattr(assessment, "verdict", "not_assessed") or "not_assessed"
    sufficient = bool(getattr(assessment, "sufficient", False))

    visual = bool(has_image)

    # --------------------------------------------------------
    # Mode + answer type
    # --------------------------------------------------------

    if tutoring_mode == "quiz":
        mode, answer_type = "interactive_testing", "quiz_question"
        depth = "short"
        needs_retrieval = True
        notes = (
            "QUIZ TURN: reply with exactly one question and nothing "
            "else. No lesson, no definitions, no answer."
        )
    elif tutoring_mode == "correction":
        mode, answer_type = "interactive_testing", "answer_feedback"
        needs_retrieval = True
    elif tutoring_mode == "revision":
        mode, answer_type = "revision", "revision_summary"
        needs_retrieval = True
    elif visual:
        mode, answer_type = "visual_explanation", "visual_explanation"
        needs_retrieval = True
    elif domain == "biology" or intent in (
        "biology_explanation", "study_request", "visual_question"
    ):
        mode, answer_type = "teaching", "conceptual_explanation"
    else:
        mode, answer_type = "conversation", "conversation"

    if mode == "teaching":
        text = (question or "").lower()
        if _contains(text, ("compare", "difference", "differences", " versus ", " vs ")):
            answer_type = "comparison"
        elif _contains(text, ("how does", "how do", "how is", "mechanism", "process")):
            answer_type = "mechanism"
        elif _contains(text, SHORT_FACT_MARKERS) and depth in ("very_short", "short"):
            answer_type = "direct_fact"

    if visual:
        answer_type = "visual_explanation"

    # --------------------------------------------------------
    # Evidence requirements
    # --------------------------------------------------------

    evidence_required = (
        mode in ("teaching", "visual_explanation", "interactive_testing")
        or verdict in ("sufficient", "partial")
    )

    # Citations are only ever offered when the textbook actually
    # supports the answer.
    citation_required = bool(
        sufficient
        and mode in ("teaching", "visual_explanation")
        and needs_retrieval
    )

    notes = ""
    if tutoring_mode == "quiz":
        notes = (
            "QUIZ TURN: reply with exactly one question and nothing "
            "else. No lesson, no definitions, no answer."
        )
    elif intent == "social_reaction":
        notes = (
            "SOCIAL TURN: the student is reacting to the previous "
            "exchange, not asking a new question. Reply socially and "
            "briefly. If they seem confused by the previous answer, "
            "acknowledge it and repair naturally — check what was "
            "actually said before assuming they are right or wrong."
        )
    elif verdict == "partial":
        notes = (
            "Textbook material is related but incomplete: explain what "
            "the material does support, and be explicit about what it "
            "does not."
        )
    elif verdict == "insufficient" and evidence_required:
        notes = (
            "No usable textbook evidence: answer from general biology "
            "knowledge and say plainly that the textbook does not cover "
            "it. Never cite the book."
        )

    return AnswerPlan(
        intent=intent,
        mode=mode,
        tutoring_mode=tutoring_mode,
        depth=depth,
        tone=tone,
        answer_type=answer_type,
        needs_retrieval=needs_retrieval,
        evidence_required=evidence_required,
        evidence_sufficient=sufficient,
        evidence_verdict=verdict,
        citation_required=citation_required,
        grounded=sufficient,
        has_visual_evidence=visual,
        notes=notes,
    )


def validation_from_report(report, assessment=None, grounded: bool = False) -> AnswerValidation:
    """Adapt a VerificationReport into the internal AnswerValidation."""
    issues = list(getattr(report, "issues", []) or [])

    unsupported: list[str] = []
    for issue in issues:
        lowered = issue.lower()
        if "cite" in lowered or "citation" in lowered:
            unsupported.append(issue)

    return AnswerValidation(
        grounded=bool(grounded),
        evidence_sufficient=bool(getattr(assessment, "sufficient", False)),
        citations_valid=bool(
            getattr(report, "no_unsupported_citations", True)
        ),
        answered_question=bool(getattr(report, "relevance", True))
        and bool(getattr(report, "answered_question", True)),
        unsupported_claims=unsupported,
        issues=issues,
    )


# ============================================================
# CONVERSATION MEMORY (bounded)
# ============================================================

class ConversationMemory:
    """
    Small, bounded short-term memory.

    The engine already keeps the last N messages for the prompt. This
    adds the two things a follow-up needs and a transcript does not
    give you cheaply:
      - what the previous question was about, and
      - which pages were retrieved for it.
    """

    def __init__(self, max_turns: int = MAX_MEMORY_TURNS) -> None:
        self.max_turns = max_turns
        self.turns: list[dict] = []
        self.last_question: str = ""
        self.last_query: str = ""
        self.last_pages: list[int] = []
        self.last_topics: list[str] = []
        self.recent_answers: list[str] = []

    # ------------------------------------------------------

    def record_turn(self, role: str, content: str) -> None:
        content = (content or "").strip()
        if not content:
            return

        self.turns.append({"role": role, "content": content})
        self.turns = self.turns[-(self.max_turns * 2):]

        if role == "user":
            self.last_question = content
        elif role == "assistant":
            self.recent_answers.append(content)
            self.recent_answers = self.recent_answers[-REPETITION_LOOKBACK_TURNS:]

    def record_evidence(self, query: str, pages, topics=None) -> None:
        self.last_query = (query or "").strip()
        self.last_pages = sorted({int(p) for p in (pages or [])})
        if topics:
            self.last_topics = list(topics)[:6]

    def clear(self) -> None:
        self.turns.clear()
        self.recent_answers.clear()
        self.last_question = ""
        self.last_query = ""
        self.last_pages = []
        self.last_topics = []

    # ------------------------------------------------------

    def is_followup(self, question: str) -> bool:
        """Is this message referring to something already discussed?"""
        text = (question or "").lower().strip()
        if not text or not self.last_question:
            return False

        words = text.split()

        if _contains(text, FOLLOWUP_MARKERS):
            return True

        # Explicit continuation intents, however phrased.
        if re.search(
            r"\b(why|what|how|and|so|but|more|again|repeat|also)\b",
            text,
        ) and len(words) <= FOLLOWUP_MAX_WORDS:
            return True

        # Very short messages with no subject of their own.
        if len(words) <= 2 and not re.search(
            r"\b(cell|dna|rna|enzyme|protein|gene|photosynthesis|respiration|"
            r"mitosis|meiosis|blood|heart|kidney|hormone|neuron|plant|"
            r"animal|population|ecosystem)\b",
            text,
        ):
            return True

        return len(words) <= FOLLOWUP_MAX_WORDS and text.endswith(
            ("again", "it", "that", "this", "one", "then")
        )

    def contextual_query(self, question: str) -> str:
        """
        Retrieval query for a follow-up: the previous topic plus the
        new message, so "why are there two divisions?" finds meiosis
        instead of random pages.
        """
        if not self.is_followup(question) or not self.last_question:
            return question

        parts = [self.last_question]
        if self.last_query and self.last_query.lower() != self.last_question.lower():
            parts.append(self.last_query)
        parts.append(question)

        return " ".join(part for part in parts if part).strip()

    def context_note(self) -> str:
        """
        Short internal note about the active discussion, for the prompt.
        Bounded on purpose - never the whole transcript.
        """
        if not self.last_question:
            return ""

        pages = ""
        if self.last_pages:
            pages = f" (textbook pages {', '.join(str(p) for p in self.last_pages[:5])})"

        return (
            f"Most recent topic: {self.last_question.strip()[:160]}{pages}"
        )


# ============================================================
# REPETITION DETECTION (§36)
# ============================================================

REPETITIVE_PHRASES = (
    "i'm here to help",
    "i am here to help",
    "feel free to ask",
    "feel free to",
    "let me know if you'd like",
    "let me know if you would like",
    "let me know if you need",
    "i'm designed for",
    "i am designed for",
    "in g.c.e. advanced level biology",
    "i only answer",
    "i can only answer",
    "here's a detailed explanation",
    "here is a detailed explanation",
    "i'm ready to help",
    "i am ready to help",
    "that's a great question",
    "as an ai language model",
    "how can i help you today",
)


def find_repeated_phrases(answer: str, previous_answers: list[str]) -> list[str]:
    """
    Phrases Strud has already used in recent turns.

    Also collapses close variants: "let me know if you'd like" and
    "let me know if you need" are the same habit, so matching one
    variant against previous turns catches the other too.
    """
    text = (answer or "").lower()
    blobs = " \n ".join((prev or "").lower() for prev in previous_answers or [])

    repeated: list[str] = []

    for phrase in REPETITIVE_PHRASES:
        if phrase not in text:
            continue

        # Exact same phrase previously used?
        if phrase in blobs:
            repeated.append(phrase)
            continue

        # A close variant of the same phrase previously used?
        if " " in phrase:
            head = phrase.rsplit(" ", 1)[0]
            if len(head) >= 12 and head in blobs:
                repeated.append(phrase)

    return repeated


def find_filler_phrases(answer: str) -> list[str]:
    """Scripted-feeling phrases present in this answer at all."""
    text = (answer or "").lower()
    return [phrase for phrase in REPETITIVE_PHRASES if phrase in text]


# ============================================================
# PROMPT-LEVEL GUIDANCE (used by the prompt builder)
# ============================================================

DEPTH_GUIDANCE = {
    "very_short": (
        "A sentence or two, no headings, no bullet lists, no closing "
        "invitation. Answer and stop."
    ),
    "short": (
        "A short, direct answer - a few sentences at most. No headings, "
        "no summary section, no closing filler."
    ),
    "normal": (
        "A clear, moderately sized answer. Structure it only if the "
        "content needs it."
    ),
    "detailed": (
        "A full explanation that teaches the reasoning: what happens, "
        "why, in what order, and how the parts connect. Use a list or "
        "short headed sections only where they genuinely help."
    ),
    "deep_dive": (
        "A thorough, teaching-grade explanation of the whole process: "
        "mechanisms, cause and effect, key terminology, and the "
        "relationships between stages. Length is justified here."
    ),
}

TONE_GUIDANCE = {
    "casual": (
        "Match the student's informal register lightly - natural and "
        "relaxed, at most one bit of casual grammar or a single emoji. "
        "Never turn the answer into slang."
    ),
    "reassuring": (
        "The student is confused or stuck. Be warm and matter-of-fact, "
        "not pitying. Rebuild the idea from something simpler."
    ),
    "explanatory": "Clear, precise, exam-appropriate English.",
    "friendly": "Natural, helpful, human - not stiff.",
}

TUTORING_GUIDANCE = {
    "none": "",
    "explanation": (
        "The student wants to understand, not to be quizzed. Teach the "
        "concept from the ground up and check the specific thing they "
        "are stuck on."
    ),
    "socratic": (
        "Guide the student toward the answer with one focused question "
        "at a time, giving just enough information to make the next "
        "step reachable."
    ),
    "quiz": (
        "Act as an interactive tutor: ask the student ONE question and "
        "STOP. Your entire reply must contain the question, optionally "
        "with a one-line lead-in. Do NOT teach the topic first, do NOT "
        "explain any concepts, and do NOT reveal the answer or ask the "
        "next question. Wait for the student's answer before doing "
        "anything else."
    ),
    "correction": (
        "The student has attempted an answer (or said they don't know). "
        "Say what is right, what is missing or wrong and why, give the "
        "correct reasoning, then optionally offer one follow-up "
        "question. Do not repeat the whole lesson."
    ),
    "revision": (
        "Give a tight, high-value recap of the key points and the "
        "connections between them. Cut anything that does not help "
        "recall."
    ),
    "exam": (
        "Use G.C.E. A/L exam conventions: precise terminology, "
        "mark-scoring-style points, and the wording an examiner expects."
    ),
}
