# biology_engine.py

from typing import Optional

from config import MAX_HISTORY_MESSAGES

from .biology import (
    BiologyMode,
    detect_question_style,
    build_biology_prompt,
)


# ============================================================
# BIOLOGY ENGINE
# ============================================================

class BiologyEngine:
    """
    Handles Biology question answering.

    Responsibilities:
        - Build the correct Biology prompt
        - Handle textbook/general/mixed modes
        - Maintain short conversation context
        - Send the request to the LLM
        - Return the final answer

    It does NOT perform retrieval.
    """

    def __init__(
        self,
        llm_client,
        model: str,
    ):
        self.llm_client = llm_client
        self.model = model

        self.history = []

    # ========================================================
    # HISTORY
    # ========================================================

    def add_to_history(
        self,
        role: str,
        content: str,
    ):
        """
        Adds a message to conversation history.
        """

        self.history.append(
            {
                "role": role,
                "content": content,
            }
        )

        # Keep history small.
        self.history = self.history[
            -MAX_HISTORY_MESSAGES:
        ]

    def clear_history(self):
        """
        Starts a new conversation.
        """

        self.history.clear()

    # ========================================================
    # PROMPT
    # ========================================================

    def build_prompt(
        self,
        question: str,
        context: str = "",
        mode: BiologyMode = BiologyMode.MIXED,
        visual_context: str | None = None,
    ):

        history = self.history[
            -MAX_HISTORY_MESSAGES:
        ]

        return build_biology_prompt(
            question=question,
            context=context,
            mode=mode,
            history=history,
            visual_context=visual_context,
        )

    # ========================================================
    # ANSWER
    # ========================================================

    def answer(
        self,
        question: str,
        context: str = "",
        mode: BiologyMode = BiologyMode.MIXED,
        visual_context: str | None = None,
    ) -> str:

        question = question.strip()

        if not question:
            return "Please enter a Biology question."

        messages = self.build_prompt(
            question=question,
            context=context,
            mode=mode,
            visual_context=visual_context,
        )

        # ----------------------------------------------------
        # Send to LM Studio / LLM client
        # ----------------------------------------------------

        answer = self.llm_client.chat(
            model=self.model,
            messages=messages,
        )

        answer = answer.strip()

        # ----------------------------------------------------
        # Save conversation
        # ----------------------------------------------------

        self.add_to_history(
            "user",
            question,
        )

        self.add_to_history(
            "assistant",
            answer,
        )

        return answer


# ============================================================
# CONVENIENCE FUNCTION
# ============================================================

def answer_biology_question(
    question: str,
    llm_client,
    model: str,
    context: str = "",
    mode: BiologyMode = BiologyMode.MIXED,
    history: Optional[list] = None,
) -> str:
    """
    Simple function for applications that don't need
    a persistent BiologyEngine instance.
    """

    engine = BiologyEngine(
        llm_client=llm_client,
        model=model,
    )

    if history:
        engine.history = history[
            -MAX_HISTORY_MESSAGES:
        ]

    return engine.answer(
        question=question,
        context=context,
        mode=mode,
    )


# ============================================================
# ANSWER GUIDANCE
# ============================================================

def get_answer_guidance(
    question: str,
) -> str:
    """
    Gives the model extra guidance based on the question type.

    This can be used later by the prompt builder.
    """

    style = detect_question_style(question)

    guidance = {

        "definition": (
            "Give the definition first, then briefly explain "
            "important details and terminology."
        ),

        "explanation": (
            "Explain the biological reason clearly. "
            "Show the cause-and-effect relationship."
        ),

        "mechanism": (
            "Explain the process in logical sequential steps. "
            "Include important structures and mechanisms."
        ),

        "comparison": (
            "Compare the concepts directly. "
            "Use a clear table when appropriate."
        ),

        "deep": (
            "Give a structured explanation with enough detail "
            "for G.C.E. A/L Biology."
        ),

        "summary": (
            "Summarise the important points without unnecessary detail."
        ),

        "practice": (
            "Treat this as a learning/practice question. "
            "Explain the reasoning rather than only giving an answer."
        ),

        "simple": (
            "Keep the explanation short and easy to understand."
        ),

        "normal": (
            "Answer naturally at an appropriate A/L Biology level."
        ),
    }

    return guidance.get(
        style,
        guidance["normal"],
    )