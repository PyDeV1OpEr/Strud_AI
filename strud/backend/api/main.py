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
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from rich.console import Console

# ---- locate the existing Strud backend -----------------------------
# The adapter expects the repo root (config.py, llm_client.py, ...)
# on sys.path. Repo root = parents[3] of this file when run in-place.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from llm_client import LLMClient, check_lm_studio  # noqa: E402
from config import CACHE_DIR, MODEL  # noqa: E402
from Science.Biology.biology_engine import BiologyEngine  # noqa: E402
from Science.Biology.biology_retriever import (  # noqa: E402
    get_retriever_status,
    initialize_retriever,
)
from cli.interface import StrudCLI  # noqa: E402
from strud.backend.tutoring_graph import build_tutoring_graph  # noqa: E402
from strud.backend.memory_store import get_memory_store  # noqa: E402
from strud.backend.llm_chain import reset_chat_model  # noqa: E402

from ..models.schemas import (  # noqa: E402
    ChatRequestBody,
    ChatResponseBody,
    ChatTitleUpdateBody,
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

# The image route resolves a per-chat session while it serializes the shared
# LM Studio turn.  That helper also protects lazy session creation, so this
# must be re-entrant rather than self-deadlocking an image request.
_app_lock = threading.RLock()         # serializes LLM pipeline turns
_retriever_ready = False
_sessions: dict[tuple[str, str], StrudCLI] = {}

_llm: Optional[LLMClient] = None
_graph = None                       # LangGraph tutoring workflow


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


def _get_graph():
    """Compile the LangGraph tutoring workflow once per process."""
    global _graph
    if _graph is None:
        with _app_lock:
            if _graph is None:
                _graph = build_tutoring_graph()
    return _graph


def _get_session(chat_id: str, user_id: str) -> StrudCLI:
    """
    One headless CLI session per chat: its own BiologyEngine history
    and ConversationMemory (like a separate CLI run), sharing the
    retriever and LLM client. This keeps per-chat conversation memory
    exactly the way the terminal app behaves.
    """
    session_key = (user_id, chat_id)
    session = _sessions.get(session_key)
    if session is None:
        with _app_lock:
            session = _sessions.get(session_key)
            if session is None:
                llm = _get_llm()
                engine = BiologyEngine(llm_client=llm, model=MODEL)
                session = StrudCLI(
                    llm_client=llm, biology_engine=engine, model=MODEL
                )
                session.renderer = CapturingRenderer()
                _sessions[session_key] = session
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

UPLOADS_DIR = CACHE_DIR / "uploads"
MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


def _persist_attachments(request: ChatRequestBody) -> tuple[list[Path], list[dict]]:
    """Validate uploads once and retain safe, browser-addressable copies."""
    paths: list[Path] = []
    records: list[dict] = []
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    for attachment in request.attachments or []:
        try:
            suffix = ALLOWED_IMAGE_TYPES.get(attachment.mimeType)
            if not suffix:
                raise ValueError("unsupported image type")
            raw = base64.b64decode(attachment.data, validate=True)
            if not raw or len(raw) > MAX_IMAGE_BYTES:
                raise ValueError("image is empty or too large")
            filename = f"{uuid.uuid4()}{suffix}"
            path = UPLOADS_DIR / filename
            path.write_bytes(raw)
            paths.append(path)
            records.append({"id": filename, "url": f"/api/uploads/{filename}", "name": attachment.name[:255], "mimeType": attachment.mimeType, "size": len(raw)})
        except Exception:  # noqa: BLE001 — skip malformed uploads
            logger.warning("Skipping malformed attachment %r", attachment.name)
    return paths, records


# ------------------------------------------------------------
# routes
# ------------------------------------------------------------

app = FastAPI(title="Strud AI API", version="0.2.0")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/api/uploads", StaticFiles(directory=UPLOADS_DIR), name="uploads")

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
    """
    Chat via the LangGraph tutoring workflow — persistent memory,
    deterministic quiz scoring, textbook retrieval, identity guard.

    Image attachments still flow through the existing vision pipeline
    (Qwen3-VL analysis is loaded into the session context); the
    follow-up question is then answered by the graph.
    """
    _ensure_retriever()
    graph = _get_graph()
    question = (request.message or "").strip()
    user_id = request.userId.strip()
    image_paths, attachments = _persist_attachments(request)
    store = get_memory_store()
    if store.is_chat_deleted(request.chatId, user_id):
        raise HTTPException(status_code=409, detail="This chat is in the Recycle Bin. Restore it before sending a message.")
    store.ensure_chat(request.chatId, user_id, request.title)
    image_context = ""

    try:
        with _app_lock:  # the shared LM Studio server is single-model
            if image_paths:
                # Send the exact uploaded bytes to Qwen through its vision
                # adapter.  The former CLI command swallowed Qwen errors and
                # analysed with an empty question, leaving this HTTP route
                # without a dependable image result.
                session = _get_session(request.chatId, user_id)
                if session.vision is None:
                    raise RuntimeError("Vision is disabled in vision_config.json.")
                analysis = session.vision.analyze_image(image_paths[0], question=question)
                if analysis.error:
                    raise RuntimeError(analysis.error)
                # The former path stored this only on the CLI session; the
                # LangGraph turn never received it. Pass Qwen's structured
                # interpretation into the actual response-generation prompt.
                image_context = session.vision.format_visual_context([analysis])
                if not question:
                    question = "Explain this Biology image."

            result = graph.invoke(
                {
                    "chat_id": request.chatId,
                    "user_id": user_id,
                    "question": question,
                    "image_context": image_context,
                    "attachments": attachments,
                },
                # LangGraph's checkpoint key must include the user too. Chat
                # ids are client-generated and can collide across browsers.
                config={"configurable": {"thread_id": f"{user_id}:{request.chatId}"}},
            )
    except RuntimeError as error:
        # LLMClient raises RuntimeError when LM Studio is unreachable.
        for path in image_paths:
            path.unlink(missing_ok=True)
        logger.error("chat failed: %s", error)
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        # LangChain errors (e.g. 'Model unloaded.' after the model was
        # swapped in LM Studio) must surface as 503, not a bare 500 —
        # and drop the cached ChatOpenAI so the next turn reconnects.
        reset_chat_model()
        for path in image_paths:
            path.unlink(missing_ok=True)
        logger.error("chat failed (non-runtime): %s", error)
        raise HTTPException(
            status_code=503,
            detail="The AI engine rejected the request (is the configured model loaded in LM Studio?).",
        ) from error
    content = (result.get("answer") or "").strip() if result else ""
    if not content:
        raise HTTPException(status_code=502, detail="The pipeline produced no response.")

    sources: Optional[list[SourceOut]] = None
    pages = result.get("retrieval_pages") or []
    if result.get("grounded") and pages:
        sources = [
            SourceOut(label="Biology Resource Book", pages=sorted(set(pages)))
        ]

    return ChatResponseBody(
        messageId=str(uuid.uuid4()),
        content=content,
        sources=sources,
    )


def _remove_owned_uploads(attachments: list[dict]) -> None:
    for attachment in attachments:
        filename = Path(str(attachment.get("url", ""))).name
        path = UPLOADS_DIR / filename
        if path.parent == UPLOADS_DIR and path.is_file():
            path.unlink(missing_ok=True)


@app.get("/api/chats")
def list_chats(user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    return {"chats": get_memory_store().list_chats(user_id)}


@app.get("/api/chats/deleted")
def list_deleted_chats(user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    return {"chats": get_memory_store().list_chats(user_id, deleted=True)}


@app.delete("/api/chats/{chat_id}")
def move_chat_to_bin(chat_id: str, user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    if not get_memory_store().move_chat_to_bin(chat_id, user_id):
        raise HTTPException(status_code=404, detail="Active chat not found.")
    return {"ok": True}


@app.post("/api/chats/{chat_id}/restore")
def restore_chat(chat_id: str, user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    if not get_memory_store().restore_chat(chat_id, user_id):
        raise HTTPException(status_code=404, detail="Deleted chat not found.")
    return {"ok": True}


@app.delete("/api/chats/{chat_id}/permanent")
def permanently_delete_chat(chat_id: str, user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    attachments = get_memory_store().permanently_delete_chat(chat_id, user_id)
    if attachments is None:
        raise HTTPException(status_code=404, detail="Deleted chat not found.")
    _remove_owned_uploads(attachments)
    return {"ok": True}


@app.delete("/api/chats/deleted/all")
def empty_bin(user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    attachments = get_memory_store().empty_bin(user_id)
    _remove_owned_uploads(attachments)
    return {"ok": True}


@app.patch("/api/chats/{chat_id}/title")
def update_chat_title(chat_id: str, request: ChatTitleUpdateBody) -> dict:
    get_memory_store().update_chat_title(chat_id, request.userId, request.title)
    return {"ok": True}


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


# ------------------------------------------------------------
# Memory & quiz introspection endpoints (persistent layers)
# ------------------------------------------------------------

@app.get("/api/memory")
def list_memory(user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    """All stored user-level memory facts for this user."""
    facts = get_memory_store().recall(user_id, limit=50)
    return {"facts": facts}


@app.delete("/api/memory/{memory_id}")
def delete_memory(memory_id: int, user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    deleted = get_memory_store().forget_by_id(user_id, memory_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return {"ok": True}


@app.get("/api/quizzes")
def list_quizzes(user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    """All quiz sessions for this user, across every chat."""
    sessions = get_memory_store().all_quiz_sessions(user_id)
    return {"sessions": sessions}


@app.get("/api/quizzes/{quiz_id}/score")
def quiz_score(quiz_id: str, user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    """Deterministic score for one quiz session, from stored attempts."""
    score = get_memory_store().score_quiz(user_id, quiz_id)
    if score is None:
        raise HTTPException(status_code=404, detail="Quiz session not found.")
    return score


@app.delete("/api/quizzes/{quiz_id}")
def delete_quiz(quiz_id: str, user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    deleted = get_memory_store().delete_quiz_session(user_id, quiz_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Quiz session not found.")
    return {"ok": True}
