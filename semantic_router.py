# semantic_router.py
#
# SemanticRouter — lightweight LLM decision layer for Strud AI.
#
# The router does NOT produce user-facing answers and does NOT act
# as an "out-of-domain rejection gate". It decides:
#   - what the user is trying to do (intent)
#   - whether textbook retrieval would help
#   - whether the active image matters
#   - whether this is ordinary conversation / about Strud itself
#   - whether clarification is genuinely needed
#   - a normalized query (typo/slang correction) for retrieval
#
# The main reasoning model (GPT-OSS) remains responsible for every
# final user-facing response.

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from config import ASSISTANT_NAME, ASSISTANT_DOMAIN

# Deterministic fallback router for when the router LLM call is
# unavailable or returns unusable output.
from question_router import route_question, QuestionRoute


# ============================================================
# ROUTER DECISION
# ============================================================

@dataclass
class RouteDecision:
    intent: str = "other"
    domain: str = "other"
    normalized_query: str = ""
    needs_retrieval: bool = False
    needs_vision: bool = False
    conversation_relevant: bool = True
    needs_clarification: bool = False
    is_about_assistant: bool = False
    confidence: float = 0.5
    reasoning: str = ""

    # Debug metadata (filled by the caller).
    source: str = "llm"           # "llm" | "fallback"
    fallback_route: str = ""

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "domain": self.domain,
            "normalized_query": self.normalized_query,
            "needs_retrieval": self.needs_retrieval,
            "needs_vision": self.needs_vision,
            "conversation_relevant": self.conversation_relevant,
            "needs_clarification": self.needs_clarification,
            "is_about_assistant": self.is_about_assistant,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "source": self.source,
        }


# ============================================================
# ROUTER PROMPT
# ============================================================

ROUTER_SYSTEM_PROMPT = f"""You are the intent router inside {ASSISTANT_NAME},
an AI study assistant for {ASSISTANT_DOMAIN} students.

Your ONLY job is to analyze the user's latest message and return a
small JSON object describing it. You do NOT answer the user.

Analyze:
- what the user is trying to do (intent)
- whether it relates to biology / studying
- whether searching the biology textbook would help answer it
- whether it refers to an image or visual element
- whether it is ordinary conversation (greeting, small talk,
  expressing a feeling, commenting on life)
- whether it is about the assistant itself
- whether the message is genuinely ambiguous enough to need a
  clarifying question

IMPORTANT RULES:

- Retrieval is a TOOL, not a default. Set "needs_retrieval" = true
  ONLY when textbook material would genuinely improve the answer:
  biology questions, study/practice requests, or follow-ups on an
  ongoing biology discussion. Set it = false for general-knowledge
  and non-biology questions (technology, history, people, how
  everyday things work) — those are answered from general knowledge
  without textbook chunks, unless the user explicitly asks what the
  textbook says.
- Reactions and social messages (laughter, "bro", "lol", "huh",
  "what are you yapping about", acknowledgements, reactions to the
  previous answer) always have needs_retrieval = false. These are
  replies to the CONVERSATION, not questions about the world; the
  main model interprets them using the recent history.
- Ordinary greetings and small talk should also have
  needs_retrieval = false.
- Messages about the assistant itself (identity, capabilities,
  who made it) should have is_about_assistant = true and
  needs_retrieval = false; the application handles these.
- Fix obvious spelling mistakes in "normalized_query"
  (e.g. "what is meosis" -> "What is meiosis?") but keep the
  user's meaning. If nothing needs fixing, copy the message.
- "domain" is "biology" if the message relates to biology or
  studying, "conversation" for small talk, "assistant" for
  messages about the assistant, otherwise "other".
- Never refuse, never moralize, never add commentary.

Respond with ONLY this JSON (no markdown fences, no extra text):

{{"intent": "...", "domain": "...", "normalized_query": "...", "needs_retrieval": true/false, "needs_vision": true/false, "conversation_relevant": true/false, "needs_clarification": true/false, "is_about_assistant": true/false, "confidence": 0.0-1.0, "reasoning": "one short sentence"}}

Intent values (use the closest):
- "biology_explanation" — asking a biology question / explanation
- "study_request" — wants to learn, practice, or be quizzed
- "visual_question" — asks about an image/diagram/figure
- "capability_request" — asks what the assistant can do / whether it can do something
- "assistant_meta" — identity/creator/technology questions
- "casual_conversation" — greetings, small talk, feelings, comments
- "social_reaction" — pure reactions to the previous exchange:
  laughter, "lol/lmao", emojis as reaction, "bro", "nice", "okay",
  "thanks", "got me", or expressions of confusion about the
  previous answer ("huh?", "what are you yapping about"). What the
  user is reacting to matters — read the recent history.
- "clarification_needed" — genuinely ambiguous
- "other" — anything else the main model should handle naturally
"""


def _build_router_user_prompt(
    message: str,
    has_image: bool,
    recent_history: Optional[list] = None,
) -> str:
    parts = []

    if recent_history:
        lines = []
        for msg in recent_history[-4:]:
            role = "User" if msg.get("role") == "user" else "Assistant"
            content = (msg.get("content") or "")[:300]
            lines.append(f"{role}: {content}")
        parts.append("Recent conversation:\n" + "\n".join(lines))

    if has_image:
        parts.append(
            "An image is currently loaded in the conversation context."
        )

    parts.append(f"Latest user message:\n{message}")

    return "\n\n".join(parts)


# ============================================================
# JSON EXTRACTION
# ============================================================

def _extract_json(text: str) -> Optional[dict]:
    """Extracts the first JSON object from the model output."""
    if not text:
        return None

    text = text.strip()

    # Strip markdown fences if present.
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Fall back: find the first {...} block.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            return None

    return None


def _as_bool(value, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return default


# ============================================================
# SEMANTIC ROUTER
# ============================================================

class SemanticRouter:
    """
    Lightweight semantic decision layer.

    One small LLM call per user message decides which capabilities
    the pipeline should use. It never writes the final answer.
    """

    def __init__(self, llm_client=None, model: Optional[str] = None):
        self.llm_client = llm_client
        self.model = model

        # Simple heuristic cache: identical messages in the same
        # image state reuse the previous decision (per-instance).
        self._cache: dict[tuple, RouteDecision] = {}

    # --------------------------------------------------------
    # MAIN ENTRY
    # --------------------------------------------------------

    def decide(
        self,
        message: str,
        has_image: bool = False,
        recent_history: Optional[list] = None,
    ) -> RouteDecision:
        message = (message or "").strip()

        if not message:
            return RouteDecision(
                intent="casual_conversation",
                domain="conversation",
                confidence=0.5,
                reasoning="Empty message.",
                source="fallback",
            )

        cache_key = (message.lower(), has_image)
        cached = self._cache.get(cache_key)
        if cached is not None:
            decision = RouteDecision(**{
                **cached.to_dict(),
                "source": "cache",
            })
            decision.source = "cache"
            return decision

        decision = self._decide_with_llm(
            message=message,
            has_image=has_image,
            recent_history=recent_history,
        )

        if decision is None:
            decision = self._fallback_decision(message, has_image)

        self._cache[cache_key] = decision
        return decision

    # --------------------------------------------------------
    # LLM DECISION
    # --------------------------------------------------------

    def _decide_with_llm(
        self,
        message: str,
        has_image: bool,
        recent_history: Optional[list],
    ) -> Optional[RouteDecision]:
        if self.llm_client is None:
            return None

        try:
            raw = self.llm_client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": _build_router_user_prompt(
                            message=message,
                            has_image=has_image,
                            recent_history=recent_history,
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=300,
            )
        except Exception:
            return None

        data = _extract_json(raw)
        if data is None:
            return None

        normalized = str(data.get("normalized_query") or message).strip()

        intent = str(data.get("intent") or "other")
        domain = str(data.get("domain") or "other")
        needs_retrieval = _as_bool(data.get("needs_retrieval"))

        # Guardrail: the intents that MEAN "textbook material would
        # help" always warrant retrieval. The LLM's boolean can be
        # wrong in isolation (e.g. a misspelled biology question
        # classified correctly but flagged needs_retrieval=false).
        if not needs_retrieval and (
            intent in (
                "biology_explanation",
                "study_request",
                "visual_question",
            )
            or domain == "biology"
        ):
            needs_retrieval = True

        return RouteDecision(
            intent=intent,
            domain=domain,
            normalized_query=normalized,
            needs_retrieval=needs_retrieval,
            needs_vision=_as_bool(data.get("needs_vision")),
            conversation_relevant=_as_bool(
                data.get("conversation_relevant"), True
            ),
            needs_clarification=_as_bool(data.get("needs_clarification")),
            is_about_assistant=_as_bool(data.get("is_about_assistant")),
            confidence=_clamp_float(data.get("confidence"), 0.5),
            reasoning=str(data.get("reasoning") or "")[:200],
            source="llm",
        )

    # --------------------------------------------------------
    # DETERMINISTIC FALLBACK
    #
    # Used only when the router LLM is unreachable. NOTE: the
    # fallback NEVER rejects — it just picks a permissive route.
    # A "general" route still goes to the main LLM, which
    # decides the natural response.
    # --------------------------------------------------------

    def _fallback_decision(self, message: str, has_image: bool) -> RouteDecision:
        result = route_question(message, has_image=has_image)

        if result.route in (QuestionRoute.BIOLOGY,):
            needs_retrieval = True
            intent = "biology_explanation"
            domain = "biology"
        elif result.route == QuestionRoute.CONVERSATIONAL:
            needs_retrieval = False
            intent = "casual_conversation"
            domain = "conversation"
        elif result.route == QuestionRoute.META:
            needs_retrieval = False
            intent = "assistant_meta"
            domain = "assistant"
        else:
            # GENERAL / UNKNOWN: let the main LLM handle naturally.
            needs_retrieval = False
            intent = "other"
            domain = "other"

        return RouteDecision(
            intent=intent,
            domain=domain,
            normalized_query=message,
            needs_retrieval=needs_retrieval,
            needs_vision=False,
            conversation_relevant=True,
            is_about_assistant=(result.route == QuestionRoute.META),
            confidence=result.confidence,
            reasoning=f"Fallback routing: {result.reason}",
            source="fallback",
            fallback_route=result.route.value,
        )


def _clamp_float(value, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


# ============================================================
# MODULE-LEVEL SINGLETON
# ============================================================

_router: Optional[SemanticRouter] = None


def get_semantic_router(llm_client=None, model: Optional[str] = None) -> SemanticRouter:
    global _router
    if _router is None:
        _router = SemanticRouter(llm_client=llm_client, model=model)
    elif llm_client is not None and _router.llm_client is None:
        _router.llm_client = llm_client
        _router.model = model
    return _router
