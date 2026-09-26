# injection_guard.py
#
# Narrow, deterministic prompt-injection detection for Strud AI.
#
# WHY SEPARATE FROM THE DOMAIN LAYER
# ----------------------------------
# Strud has four independent concerns and they must not be merged:
#
#   injection  -> this module (deterministic, never tolerated)
#   domain     -> semantic_router (natural, permissive)
#   grounding  -> evidence_sufficiency (measured, conservative)
#   safety     -> not implemented here (see the Phase 3 report)
#
# Only genuine attempts to rewrite instructions, hijack Strud's role,
# or fabricate textbook evidence are flagged. Ordinary conversation -
# slang, feelings, sarcasm, emoji, "wait what", "bro I don't get
# meiosis" - must pass through untouched, because the router and the
# generator handle those naturally.
#
# The detector runs BEFORE generation and never calls a model, so it
# cannot be talked out of a decision by the text it is inspecting.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ============================================================
# CATEGORIES
# ============================================================

INSTRUCTION_OVERRIDE = "instruction_override"
PROMPT_EXTRACTION = "prompt_extraction"
ROLE_HIJACK = "role_hijack"
CITATION_FABRICATION = "citation_fabrication"
EVIDENCE_TAMPERING = "evidence_tampering"


# ============================================================
# PATTERNS (deliberately narrow)
# ============================================================

_PATTERNS: list[tuple[str, str]] = [

    # ---- Instruction override ---------------------------------
    (
        INSTRUCTION_OVERRIDE,
        r"\bignore\s+(all\s+|any\s+|your\s+|the\s+)?"
        r"(previous|prior|above|earlier|original|preceding|system)?\s*"
        r"(instruction|instructions|prompt|prompts|rules|rule|"
        r"guidelines|directions|constraints)\b",
    ),
    (
        INSTRUCTION_OVERRIDE,
        r"\b(disregard|forget|overwrite|override|bypass|break)\s+"
        r"(all\s+|your\s+|the\s+)?(instruction|instructions|rules|"
        r"rule|guidelines|safety|filters|restrictions|constraints)\b",
    ),
    (
        INSTRUCTION_OVERRIDE,
        r"\bdo\s+not\s+(follow|obey)\s+(your\s+|the\s+)?"
        r"(instruction|instructions|rules|prompt)\b",
    ),
    (
        INSTRUCTION_OVERRIDE,
        r"\b(developer|dan|jailbreak|god|unrestricted|unfiltered)\s+mode\b",
    ),
    (
        INSTRUCTION_OVERRIDE,
        r"\bwithout\s+(any\s+)?(restrictions|limits|rules|filters)\b",
    ),

    # ---- Prompt / configuration extraction --------------------
    (
        PROMPT_EXTRACTION,
        r"\b(show|give|reveal|print|share|paste|leak|display|output|"
        r"repeat|copy|send|tell)\b[^.!?]{0,40}"
        r"\b(system|hidden|secret|private|developer|original|initial|"
        r"master|internal|real)\s+"
        r"(prompt|prompts|instruction|instructions|message|messages|"
        r"configuration|config)\b",
    ),
    (
        PROMPT_EXTRACTION,
        r"\bwhat\s+(are|were)\s+your\s+(hidden|secret|real|original|"
        r"internal|system)\s+(instruction|instructions|prompt|prompts|"
        r"rules)\b",
    ),

    # ---- Role hijack ------------------------------------------
    (
        ROLE_HIJACK,
        r"\bpretend\s+(to\s+be|you\s+are|that\s+you\s+are)\s+"
        r"(an?\s+)?(ai|assistant|model|chatbot|bot|unrestricted|"
        r"unfiltered|different|another|chatgpt|gpt|qwen|gemini|claude)\b",
    ),
    (
        ROLE_HIJACK,
        r"\bact\s+as\s+(an?\s+)?(unrestricted|unfiltered|jailbroken|"
        r"evil|different|another)\b",
    ),
    (
        ROLE_HIJACK,
        r"\byou\s+are\s+now\s+(an?\s+)?"
        r"(unrestricted|unfiltered|jailbroken|different|new|another)\b",
    ),
    (
        ROLE_HIJACK,
        r"\b(roleplay|role-play)\s+as\s+(an?\s+)?"
        r"(unrestricted|unfiltered|different|another|ai|model)\b",
    ),
    (
        ROLE_HIJACK,
        r"\bfrom\s+now\s+on\s+you\s+(are|will|must)\b",
    ),

    # ---- Citation fabrication ---------------------------------
    (
        CITATION_FABRICATION,
        r"\b(make\s+up|invent|fabricate|create|fake|forge)\b[^.!?]{0,30}"
        r"\b(page|pages|page\s+number|page\s+numbers|citation|citations|"
        r"reference|references|quote|quotes|source|sources|chapter)\b",
    ),
    (
        CITATION_FABRICATION,
        r"\b(use|cite|claim|say\s+it\s+is\s+on)\s+page\s+\d{1,3}\b"
        r"[^.!?]{0,40}\b(even\s+if|whether\s+or\s+not|regardless|"
        r"doesn'?t\s+exist|does\s+not\s+exist|isn'?t\s+there)\b",
    ),
    (
        CITATION_FABRICATION,
        r"\bjust\s+(make\s+up|invent|guess)\b",
    ),

    # ---- Evidence tampering -----------------------------------
    (
        EVIDENCE_TAMPERING,
        r"\bignore\s+(the\s+|your\s+|all\s+)?"
        r"(textbook|book|resource\s+book|evidence|sources?|retrieval|"
        r"page|pages|context)\b",
    ),
    (
        EVIDENCE_TAMPERING,
        r"\b(don'?t|do\s+not)\s+(use|check|consult|read|cite)\s+"
        r"(the\s+|your\s+)?(textbook|book|resource\s+book|evidence|"
        r"sources?|pages?)\b",
    ),
]


_COMPILED = [
    (category, re.compile(pattern, re.IGNORECASE))
    for category, pattern in _PATTERNS
]


# ============================================================
# RESULT
# ============================================================

@dataclass
class InjectionVerdict:
    detected: bool = False
    category: str = ""
    matched: str = ""
    message: str = ""
    categories: list[str] = field(default_factory=list)


# ============================================================
# RESPONSES
# ============================================================
#
# Deterministic and short. These are the only scripted strings in the
# upgrade, and they exist because a security boundary must not be
# negotiable by the text it is inspecting. They deliberately avoid the
# "I'm here to help / feel free to ask" register.

_RESPONSES = {
    INSTRUCTION_OVERRIDE: (
        "I'll keep answering the way I'm built - I can't switch my "
        "instructions off. If there's a Biology question underneath "
        "that, ask it plainly and I'll take it seriously."
    ),
    PROMPT_EXTRACTION: (
        "I can tell you what I'm for and how I work at a high level, "
        "but not my internal instructions. Ask me a Biology question "
        "and you'll get the real thing."
    ),
    ROLE_HIJACK: (
        "I'll stay myself, thanks. Happy to go deep on any A/L Biology "
        "topic instead - where do you want to start?"
    ),
    CITATION_FABRICATION: (
        "I won't invent pages or sources - every reference I give has "
        "to come from a page I actually read. Ask the question and "
        "I'll tell you what the book does and doesn't support."
    ),
    EVIDENCE_TAMPERING: (
        "I won't skip the textbook when it's relevant - that's the "
        "whole point of me. Ask your question and I'll tell you "
        "straight if the book doesn't cover it."
    ),
}


# ============================================================
# DETECTION
# ============================================================

def detect_injection(question: str) -> Optional[InjectionVerdict]:
    """
    Returns an InjectionVerdict when the message is a genuine
    injection attempt, otherwise None.

    Deterministic: identical input always yields an identical verdict,
    and ordinary conversation is never flagged.
    """
    text = (question or "").strip()

    if not text:
        return None

    hits: list[tuple[str, str]] = []

    for category, pattern in _COMPILED:
        match = pattern.search(text)
        if match:
            hits.append((category, match.group(0)))

    if not hits:
        return None

    primary = hits[0][0]

    return InjectionVerdict(
        detected=True,
        category=primary,
        matched=hits[0][1][:120],
        message=_RESPONSES.get(primary, _RESPONSES[INSTRUCTION_OVERRIDE]),
        categories=sorted({category for category, _ in hits}),
    )
