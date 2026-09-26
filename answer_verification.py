# answer_verification.py
#
# VerificationService — silent, bounded answer verification.
#
# Before the final answer is shown, it is checked against the
# retrieved evidence and the question. If verification fails,
# the answer is revised internally (at most max_revision_attempts
# times). The student never sees the verification process.

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from config import (
    VERIFICATION_ENABLED,
    VERIFICATION_MAX_REVISIONS,
    ASSISTANT_NAME,
)

from answer_intelligence import find_repeated_phrases, find_filler_phrases


# ============================================================
# CHECK RESULTS
# ============================================================

@dataclass
class VerificationReport:
    relevance: bool = True
    evidence_support: bool = True
    answered_question: bool = True
    no_unsupported_citations: bool = True
    no_text_only_claims: bool = True
    appropriate_level: bool = True
    no_repetition: bool = True
    issues: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.relevance
            and self.evidence_support
            and self.answered_question
            and self.no_unsupported_citations
            and self.no_text_only_claims
            and self.appropriate_level
            and self.no_repetition
        )


# ============================================================
# PAGE CITATION EXTRACTION
# ============================================================

PAGE_CITATION_PATTERN = re.compile(
    r"\bpage\s+(\d{1,3})\b",
    re.IGNORECASE,
)


def extract_cited_pages(answer: str) -> set[int]:
    """All page numbers the answer cites."""
    return {int(m) for m in PAGE_CITATION_PATTERN.findall(answer or "")}


# ============================================================
# VERIFICATION SERVICE
# ============================================================

class VerificationService:
    """
    Deterministic, fast answer checks plus an optional
    LLM-based revision pass.

    Deterministic checks (always run, no model call):
      1. Non-empty, relevant-length answer
      2. Citations only reference actually-retrieved pages
      3. No "text-only model" claims while visual evidence exists
      4. Question words reflected in the answer (relevance)

    LLM revision (bounded):
      If a deterministic check fails, one revision prompt is sent
      to the reasoning model with the specific problems.
    """

    def __init__(self, llm_client=None, model: str | None = None):
        self.llm_client = llm_client
        self.model = model
        self.max_revisions = VERIFICATION_MAX_REVISIONS
        self.enabled = VERIFICATION_ENABLED

    # --------------------------------------------------------
    # DETERMINISTIC CHECKS
    # --------------------------------------------------------

    def verify(
        self,
        question: str,
        answer: str,
        retrieved_pages: Optional[set[int]] = None,
        has_visual_evidence: bool = False,
        previous_answers: Optional[list[str]] = None,
        answer_plan=None,
    ) -> VerificationReport:
        report = VerificationReport()

        answer = (answer or "").strip()

        # 1. Non-empty answer
        if not answer:
            report.relevance = False
            report.issues.append("Empty answer.")
            return report

        # 0. Turn-format check: when the plan classifies this as a
        #    SOCIAL turn (reaction to the conversation, not a world
        #    question), a biology lecture is a plan violation. This
        #    is checkable deterministically: the answer must stay
        #    short and must not read like teaching material.
        if self._is_social_turn(question, answer_plan):
            social_problems = []
            if len(answer) > 400:
                social_problems.append(
                    f"Answer is {len(answer)} characters; a social "
                    f"reaction must stay short."
                )
            lecture_markers = (
                "in the context of", "key terms", "key concepts",
                "in biology,", "refers to", "means that",
                "is defined as", "let me explain", "for example:",
                "in simple terms,",
            )
            lowered = answer.lower()
            if any(m in lowered for m in lecture_markers):
                social_problems.append(
                    "Answer analyzes or teaches instead of reacting "
                    "socially."
                )
            if social_problems:
                report.appropriate_level = False
                report.issues.extend(
                    ["SOCIAL TURN violation: " + p for p in social_problems]
                )

        # 2. Relevance: answer should be reasonably substantial
        #    and share content words with the question.
        #
        # EXCEPT when this is a quiz turn: a tutor asking one question
        # back shares no content words with "test me on genetics", and
        # that is exactly right. Flagging it would trigger a revision
        # that turns the quiz question into a mini-lecture.
        # Social turns are likewise exempt: a short reaction like
        # "Glad it hit the mark!" correctly shares no content words
        # with "HAHAHAHAHA" - punishing that would push the revision
        # loop into turning the reaction into a biology lecture.
        in_quiz_turn = self._is_quiz_turn(question)
        in_social_turn = self._is_social_turn(question, answer_plan)

        if (
            len(answer) < 40
            and not in_quiz_turn
            and not in_social_turn
            and not (self._is_short_answer_appropriate(question, answer))
        ):
            report.relevance = False
            report.issues.append("Answer is too short to be useful.")

        if not in_quiz_turn and not in_social_turn:
            q_words = self._content_words(question)
            a_words = self._content_words(answer)
            if q_words and a_words and not (q_words & a_words):
                report.relevance = False
                report.issues.append(
                    "Answer shares no key terms with the question."
                )

        # 3. Citation check: cited pages must exist in retrieved pages.
        #
        # retrieved_pages=None -> citations are not being policed for
        # this answer (no textbook material was offered at all).
        # retrieved_pages=set() -> the caller explicitly says there is
        # NO usable evidence, so ANY page citation is fabricated.
        cited = extract_cited_pages(answer)
        if cited and retrieved_pages is not None:
            fabricated = cited - retrieved_pages
            if fabricated:
                report.no_unsupported_citations = False
                report.issues.append(
                    f"Answer cites pages not in the retrieved evidence: "
                    f"{sorted(fabricated)}"
                )

        # 4. Repetition check (scripted-feeling filler).
        #
        # A stock opener/closer is fine once; repeating it across
        # turns is what makes Strud read like a template.
        # Banned filler phrases must not appear at all - even on first
        # use - because a one-off stock closer still reads scripted.
        first_use_filler = find_filler_phrases(answer)
        if first_use_filler:
            report.no_repetition = False
            report.issues.append(
                "Answer uses banned filler phrase(s): "
                + ", ".join(sorted(first_use_filler)[:3])
            )

        if previous_answers:
            repeated = find_repeated_phrases(answer, previous_answers)
            if repeated:
                report.no_repetition = False
                report.issues.append(
                    "Answer repeats stock phrase(s) already used in "
                    "recent turns: " + ", ".join(sorted(repeated)[:3])
                )

        # 5. Text-only claim check (multimodal bug guard).
        if has_visual_evidence:
            lowered = answer.lower()
            text_only_phrases = [
                "text-only model",
                "text only model",
                "i am a text model",
                "i'm a text model",
                "cannot view images",
                "can't view images",
                "cannot see images",
                "can't see images",
                "unable to view images",
                "i cannot analyze images",
                "i can't analyze images",
                "as a text-based",
            ]
            for phrase in text_only_phrases:
                if phrase in lowered:
                    report.no_text_only_claims = False
                    report.issues.append(
                        f"Answer falsely claims text-only capability "
                        f"('{phrase}') while visual evidence exists."
                    )
                    break

        return report

    # --------------------------------------------------------
    # REVISION LOOP (bounded, silent)
    # --------------------------------------------------------

    def verify_and_revise(
        self,
        question: str,
        answer: str,
        retrieved_pages: Optional[set[int]] = None,
        has_visual_evidence: bool = False,
        textbook_context: str = "",
        visual_context: str = "",
        previous_answers: Optional[list[str]] = None,
        answer_plan=None,
    ) -> tuple[str, VerificationReport]:
        """
        Verifies the answer and revises it at most max_revisions
        times if deterministic checks fail.

        Returns (final_answer, final_report).
        """
        report = self.verify(
            question=question,
            answer=answer,
            retrieved_pages=retrieved_pages,
            has_visual_evidence=has_visual_evidence,
            previous_answers=previous_answers,
            answer_plan=answer_plan,
        )

        if report.passed or not self.enabled or self.llm_client is None:
            return answer, report

        attempts = 0
        while not report.passed and attempts < self.max_revisions:
            attempts += 1

            revised = self._revision_call(
                question=question,
                answer=answer,
                issues=report.issues,
                textbook_context=textbook_context,
                visual_context=visual_context,
                has_visual_evidence=has_visual_evidence,
            )

            if not revised:
                break

            answer = revised

            report = self.verify(
                question=question,
                answer=answer,
                retrieved_pages=retrieved_pages,
                has_visual_evidence=has_visual_evidence,
                previous_answers=previous_answers,
            )

        return answer, report

    # --------------------------------------------------------
    # INTERNALS
    # --------------------------------------------------------

    def _revision_call(
        self,
        question: str,
        answer: str,
        issues: list[str],
        textbook_context: str,
        visual_context: str,
        has_visual_evidence: bool,
    ) -> Optional[str]:
        """One silent revision request to the reasoning model."""
        try:
            issue_list = "\n".join(f"- {issue}" for issue in issues)

            social_fix = any(
                issue.startswith("SOCIAL TURN violation") for issue in issues
            )
            social_rule = ""
            if social_fix:
                social_rule = (
                    'This message was a SOCIAL reaction (laughter, slang, '
                    '"bro", "thanks", confusion about the previous '
                    'answer) - NOT a biology question. Replace the draft '
                    'with a short, natural social reply (one or two '
                    'sentences at most) that responds to the student\'s '
                    'message. No biology content, no definitions, no '
                    'analysis of their words, no lesson.\n'
                )

            visual_rule = ""
            if has_visual_evidence:
                visual_rule = (
                    "- Visual evidence for this question IS available in "
                    "this conversation. Do NOT claim you cannot see images "
                    "or that you are text-only. Use the visual evidence.\n"
                )

            system = (
                f"You are {ASSISTANT_NAME}, a G.C.E. A/L Biology tutor. "
                "An earlier draft of your answer failed internal quality "
                "checks. Rewrite the answer fixing ONLY the listed "
                "problems. Keep everything that was correct. Never "
                "fabricate textbook page numbers or citations. Do not "
                "replace removed filler with different filler, and do "
                "not add an invitation to ask more questions.\n"
                + visual_rule
            )

            user = (
                f"{social_rule}Question:\n{question}\n\n"
                f"Draft answer:\n{answer}\n\n"
                f"Problems found:\n{issue_list}\n"
            )

            if textbook_context:
                user += (
                    f"\nRetrieved textbook evidence (use only these pages "
                    f"for citations):\n{textbook_context[:4000]}\n"
                )

            if visual_context:
                user += (
                    f"\nVisual evidence:\n{visual_context[:2000]}\n"
                )

            user += "\nProvide the corrected final answer only."

            return self.llm_client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            ).strip()

        except Exception:
            # Verification must never break answering.
            return None

    @staticmethod
    def _content_words(text: str) -> set[str]:
        stop = {
            "what", "why", "how", "is", "are", "the", "a", "an", "of",
            "in", "on", "do", "does", "did", "you", "your", "and", "or",
            "to", "for", "with", "this", "that", "explain", "describe",
            "tell", "about", "can", "it",
        }
        return {
            w for w in re.findall(r"[a-z]{3,}", (text or "").lower())
            if w not in stop
        }

    @staticmethod
    def _is_short_answer_appropriate(question: str, answer: str) -> bool:
        """Greetings and very narrow factual questions allow short answers."""
        lowered = (question or "").lower().strip()
        return (
            lowered.startswith(("hi", "hello", "hey", "thanks"))
            or len(lowered.split()) <= 3
        )

    @staticmethod
    def _is_social_turn(question: str, answer_plan) -> bool:
        """
        True when the internal plan classified this as a social
        reaction turn. Uses the plan (single source of truth) rather
        than re-parsing the message.
        """
        return (
            answer_plan is not None
            and getattr(answer_plan, "notes", "")
            and str(getattr(answer_plan, "notes", "")).startswith(
                "SOCIAL TURN"
            )
        )

    @staticmethod
    def _is_quiz_turn(question: str) -> bool:
        """
        Detect a tutoring request that EXPECTS a question back.

        Uses the same markers as the answer plan (single source of
        truth), so a quiz question being asked back is never punished
        by the relevance check for sharing no content words with
        "test me".
        """
        from answer_intelligence import infer_tutoring_mode

        return infer_tutoring_mode(question) == "quiz"


# ============================================================
# MODULE-LEVEL SINGLETON
# ============================================================

_service: Optional[VerificationService] = None


def get_verification_service(llm_client=None, model: str | None = None):
    global _service
    if _service is None:
        _service = VerificationService(llm_client=llm_client, model=model)
    elif llm_client is not None and _service.llm_client is None:
        _service.llm_client = llm_client
        _service.model = model
    return _service
