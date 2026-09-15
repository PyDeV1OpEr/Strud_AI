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
    ) -> VerificationReport:
        report = VerificationReport()
        retrieved_pages = retrieved_pages or set()

        answer = (answer or "").strip()

        # 1. Non-empty answer
        if not answer:
            report.relevance = False
            report.issues.append("Empty answer.")
            return report

        # 2. Relevance: answer should be reasonably substantial
        #    and share content words with the question.
        if len(answer) < 40 and not self._is_short_answer_appropriate(
            question, answer
        ):
            report.relevance = False
            report.issues.append("Answer is too short to be useful.")

        q_words = self._content_words(question)
        a_words = self._content_words(answer)
        if q_words and a_words and not (q_words & a_words):
            report.relevance = False
            report.issues.append(
                "Answer shares no key terms with the question."
            )

        # 3. Citation check: cited pages must exist in retrieved pages.
        cited = extract_cited_pages(answer)
        if cited and retrieved_pages:
            fabricated = cited - retrieved_pages
            if fabricated:
                report.no_unsupported_citations = False
                report.issues.append(
                    f"Answer cites pages not in the retrieved evidence: "
                    f"{sorted(fabricated)}"
                )

        # 4. Text-only claim check (multimodal bug guard).
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
                "fabricate textbook page numbers or citations.\n"
                + visual_rule
            )

            user = (
                f"Question:\n{question}\n\n"
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
