# llm_chain.py
#
# Strud AI — LangChain integration layer.
#
# Adapters that surface the EXISTING Strud pipeline (LM Studio model,
# textbook retriever) as LangChain components:
#
#   * get_chat_model()      -> langchain_openai.ChatOpenAI pointed at
#     the configured local server. Used by the tutoring graph; never
#     replaces the existing LLMClient used by the CLI.
#   * BioTextbookRetriever  -> langchain_core.retrievers.BaseRetriever
#     wrapper around the existing retrieve_biology() pipeline, used
#     by the tutoring graph's retrieval node.
#
# The model id / base URL always come from assistant_config.json, so
# swapping the underlying model (e.g. a future GLM build) needs no
# source edits.

from __future__ import annotations

import threading
from typing import Any, Optional

from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from config import MODEL, LM_STUDIO_BASE_URL, LLM_API_KEY, LLM_TEMPERATURE, LLM_MAX_TOKENS


# ============================================================
# CHAT MODEL (LangChain adapter over LM Studio)
# ============================================================

_chat_model = None
_chat_model_lock = threading.Lock()


def get_chat_model():
    """
    One shared ChatOpenAI instance per process, pointed at the
    configured local OpenAI-compatible endpoint (LM Studio today,
    any other local OpenAI-compatible server later).

    reset_chat_model() clears the cache so a model unload/reload in
    LM Studio is picked up on the next turn instead of persistently
    failing with 'Model unloaded.' from a stale client object.
    """
    global _chat_model
    if _chat_model is None:
        with _chat_model_lock:
            if _chat_model is None:
                from langchain_openai import ChatOpenAI

                _chat_model = ChatOpenAI(
                    model=MODEL,
                    base_url=LM_STUDIO_BASE_URL,
                    # LM Studio ignores this; hosted providers (e.g. Gemini's
                    # OpenAI-compatible endpoint) require a real key via
                    # LLM_API_KEY.
                    api_key=LLM_API_KEY or "lm-studio",
                    temperature=LLM_TEMPERATURE,
                    max_tokens=LLM_MAX_TOKENS,
                    timeout=120,
                    max_retries=1,
                )
    return _chat_model


def reset_chat_model() -> None:
    """Drop the cached ChatOpenAI so the next get_chat_model() rebuilds it."""
    global _chat_model
    with _chat_model_lock:
        _chat_model = None


# ============================================================
# TEXTBOOK RETRIEVER (LangChain adapter over the existing pipeline)
# ============================================================

class BioTextbookRetriever(BaseRetriever):
    """
    LangChain retriever adapter over the EXISTING Strud Biology
    retrieval pipeline. Wraps retrieve_biology() so LangGraph nodes
    get standard LangChain Documents instead of pipeline objects.

    This does NOT reimplement retrieval — it reuses the TF-IDF +
    dense + reranking + grounding logic already in production.
    """

    grounded: bool = Field(default=False, description="Whether the last retrieval was grounded")
    last_pages: list[int] = Field(default_factory=list)
    last_raw: Any = Field(default=None, exclude=True, repr=False)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun,
        **kwargs: Any,
    ) -> list[Document]:
        from Science.Biology.biology_retriever import (
            initialize_retriever,
            retrieve_biology,
            get_source_pages,
        )

        retriever_ready = kwargs.pop("retriever_ready", False)
        if not retriever_ready:
            initialize_retriever()

        retrieval = retrieve_biology(query)

        self.grounded = bool(getattr(retrieval, "grounded", False))
        pages = get_source_pages(retrieval) if self.grounded else []
        self.last_pages = sorted({int(p) for p in (pages or [])})
        self.last_raw = retrieval

        results = getattr(retrieval, "results", None) or []
        return [
            Document(
                page_content=getattr(r, "text", "") or "",
                metadata={
                    "page": int(getattr(r, "page", 0)),
                    "source": "Biology Resource Book",
                    "grounded": self.grounded,
                },
            )
            for r in results
        ]

    # LangChain's async path — run the sync implementation.
    async def _aget_relevant_documents(
        self,
        query: str,
        *,
        run_manager: AsyncCallbackManagerForRetrieverRun,
        **kwargs: Any,
    ) -> list[Document]:
        import asyncio

        return await asyncio.get_running_loop().run_in_executor(
            None,
            lambda: self._get_relevant_documents(
                query,
                run_manager=None,  # type: ignore[arg-type]
                **kwargs,
            ),
        )


_retriever: Optional[BioTextbookRetriever] = None
_retriever_lock = threading.Lock()


def get_textbook_retriever() -> BioTextbookRetriever:
    """Shared retriever adapter (one per process, like the pipeline)."""
    global _retriever
    if _retriever is None:
        with _retriever_lock:
            if _retriever is None:
                _retriever = BioTextbookRetriever()
    return _retriever
