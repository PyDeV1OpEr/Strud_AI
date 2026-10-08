# ------------------------------------------------------------
# Strud AI — FastAPI adapter
#
# A thin HTTP boundary over the EXISTING Strud pipeline. This module
# does NOT reimplement AI behaviour: it drives the same StrudCLI
# orchestration the terminal app uses — injection guard, identity,
# semantic router, Biology retrieval, evidence sufficiency, Qwen3-VL
# vision, GPT-OSS-20B generation, and silent verification — through a
# capturing renderer instead of the Rich console.
#
# The frontend contract (frontend/types) is model-agnostic; this
# adapter decides models/retrieval server-side, exactly as before.
#
# Run from the repository root (the directory containing config.py):
#   .venv/bin/uvicorn strud.backend.api.main:app --port 8000
# ------------------------------------------------------------

from __future__ import annotations

import base64
import io
import logging
import sys
import tempfile
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from rich.console import Console

# ---- locate the existing Strud backend -----------------------------
# The adapter expects the repo root (config.py, llm_client.py, ...)
# on sys.path. Repo root = parents[3] of this file when run in-place.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from llm_client import LLMClient, check_lm_studio  # noqa: E402
from config import MODEL  # noqa: E402
from Science.Biology.biology_engine import BiologyEngine  # noqa: E402
from Science.Biology.biology_retriever import (  # noqa: E402
    get_retriever_status,
    initialize_retriever,
)
from cli.interface import StrudCLI  # noqa: E402

from ..models.schemas import (  # noqa: E402
    ChatRequestBody,
    ChatResponseBody,
    SourceOut,
    TitleRequestBody,
    TitleResponseBody,
)

logger = logging.getLogger("strud.api")

TITLE_PROMPT = (
    "Give a concise chat title (3-6 words, no quotes, no punctuation at "
    "the end) for a conversation starting with this message:\n\n{message}"
)


# ------------------------------------------------------------
# Headless CLI renderer
# ------------------------------------------------------------
# Same interface the pipeline calls on StrudRenderer, but instead of
# drawing to the terminal it captures the user-facing result so the
# HTTP layer can return it.

class CapturingRenderer:
    """Captures the real pipeline's user-facing output for HTTP."""

    def __init__(self) -> None:
        # Some pipeline paths write directly through a Rich console
        # (e.g. vision debug); give them a sink that swallows output.
        self.console = Console(file=io.StringIO())
        self.answer: Optional[str] = None
        self.sources: Optional[list[int]] = None
        self.grounded: bool = False
        self.note: Optional[str] = None
        self.message: Optional[str] = None
        self.error: Optional[str] = None

    def reset(self) -> None:
        self.answer = None
        self.sources = None
        self.grounded = False
        self.note = None
        self.message = None
        self.error = None

    @contextmanager
    def thinking(self, text: str):  # noqa: ANN201 — matches StrudRenderer
        yield

    def print_message(self, text: str, style: str | None = None) -> None:
        # Injection guards / identity answers / capability notices.
        self.message = text

    def print_answer(
        self,
        answer: str,
        route_label: str = "Biology",
        grounded: bool = False,
        sources: Optional[list[int]] = None,
        note: Optional[str] = None,
    ) -> None:
        self.answer = answer
        self.grounded = bool(grounded)
        self.sources = list(sources) if sources else None
        self.note = note

    def print_error(self, text: str, title: str | None = None) -> None:
        self.error = text

    # Console-only surfaces (never invoked by the API paths, kept for
    # interface completeness should pipeline internals call them).
    def print_startup(self, *args: Any, **kwargs: Any) -> None: ...
    def print_help(self) -> None: ...
    def print_status(self, *args: Any, **kwargs: Any) -> None: ...


# ------------------------------------------------------------
# Shared pipeline state
# ------------------------------------------------------------

_app_lock = threading.Lock()          # serializes LLM pipeline turns
_retriever_ready = False
_sessions: dict[str, StrudCLI] = {}

_llm: Optional[LLMClient] = None


def _get_llm() -> LLMClient:
    """One shared LLMClient, same configuration the CLI uses."""
    global _llm
    if _llm is None:
        _llm = LLMClient(model=MODEL)
    return _llm


def _ensure_retriever() -> None:
    """Loads the Biology Resource Book index once (same as cli.run)."""
    global _retriever_ready
    if _retriever_ready:
        return
    with _app_lock:
        if not _retriever_ready:
            initialize_retriever()
            _retriever_ready = True


def _get_session(chat_id: str) -> StrudCLI:
    """
    One headless CLI session per chat: its own BiologyEngine history
    and ConversationMemory (like a separate CLI run), sharing the
    retriever and LLM client. This keeps per-chat conversation memory
    exactly the way the terminal app behaves.
    """
    session = _sessions.get(chat_id)
    if session is None:
        with _app_lock:
            session = _sessions.get(chat_id)
            if session is None:
                llm = _get_llm()
                engine = BiologyEngine(llm_client=llm, model=MODEL)
                session = StrudCLI(
                    llm_client=llm, biology_engine=engine, model=MODEL
                )
                session.renderer = CapturingRenderer()
                _sessions[chat_id] = session
    return session


def _session_renderer(session: StrudCLI) -> CapturingRenderer:
    renderer = session.renderer
    if not isinstance(renderer, CapturingRenderer):  # defensive
        renderer = CapturingRenderer()
        session.renderer = renderer
    renderer.reset()
    return renderer


# ------------------------------------------------------------
# helpers
# ------------------------------------------------------------

def _decode_attachments(request: ChatRequestBody) -> list[Path]:
    """Writes uploaded base64 images to temp files for the vision path."""
    paths: list[Path] = []
    for attachment in request.attachments or []:
        try:
            raw = base64.b64decode(attachment.data)
            suffix = {
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "image/webp": ".webp",
            }.get(attachment.mimeType, ".png")
            handle = tempfile.NamedTemporaryFile(
                delete=False, suffix=suffix, prefix="strud_upload_"
            )
            handle.write(raw)
            handle.close()
            paths.append(Path(handle.name))
        except Exception:  # noqa: BLE001 — skip malformed uploads
            logger.warning("Skipping malformed attachment %r", attachment.name)
    return paths


# ------------------------------------------------------------
# routes
# ------------------------------------------------------------

app = FastAPI(title="Strud AI API", version="0.2.0")

# The Next.js dev server may bind to any free port; allow loopback only.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    try:
        _ensure_retriever()
        status = get_retriever_status()
        logger.info(
            "Retriever ready: %s pages, %s chunks",
            status.get("page_count"),
            status.get("chunk_count"),
        )
    except Exception:  # noqa: BLE001 — requests retry initialization
        logger.exception("Retriever initialization failed at startup")


@app.get("/api/health")
def health() -> dict:
    status = get_retriever_status()
    return {
        "ok": True,
        "llmAvailable": check_lm_studio(),
        "textbookLoaded": bool(status.get("textbook_loaded")),
        "retrievalMode": status.get("retrieval_mode"),
        "model": MODEL,
    }


@app.post("/api/chat", response_model=ChatResponseBody)
def chat(request: ChatRequestBody) -> ChatResponseBody:
    _ensure_retriever()
    session = _get_session(request.chatId)
    renderer = _session_renderer(session)

    image_paths = _decode_attachments(request)
    question = (request.message or "").strip()

    try:
        with _app_lock:  # the shared LM Studio server is single-model
            if image_paths:
                # Real vision path: Qwen3-VL analyses the image, stores
                # concepts, and the next question flows through the
                # visual pipeline (image + question -> retrieval -> GPT-OSS).
                session.handle_image_command(str(image_paths[0]))
                if not question:
                    question = "Explain this Biology image."

            session.process_question(question)
    except RuntimeError as error:
        # LLMClient raises RuntimeError when LM Studio is unreachable.
        logger.error("chat failed: %s", error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    finally:
        for path in image_paths:
            path.unlink(missing_ok=True)

    content = renderer.answer or renderer.message or renderer.error or ""
    if not content:
        raise HTTPException(status_code=502, detail="The pipeline produced no response.")

    sources: Optional[list[SourceOut]] = None
    # Only real retrieval sources are returned — never fabricated.
    if renderer.grounded and renderer.sources:
        sources = [
            SourceOut(label="Biology Resource Book", pages=renderer.sources)
        ]

    return ChatResponseBody(
        messageId=str(uuid.uuid4()),
        content=content,
        sources=sources,
    )


@app.post("/api/title", response_model=TitleResponseBody)
def title(request: TitleRequestBody) -> TitleResponseBody:
    try:
        reply = _get_llm().chat(
            messages=[
                {
                    "role": "user",
                    "content": TITLE_PROMPT.format(message=request.message[:400]),
                }
            ],
            max_tokens=24,
            temperature=0.2,
        )
        return TitleResponseBody(title=reply.strip().strip('"') or "New chat")
    except RuntimeError:
        return TitleResponseBody(title="New chat")
