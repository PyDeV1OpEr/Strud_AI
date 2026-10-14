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
from config import (  # noqa: E402
    CACHE_DIR,
    MODEL,
    LM_STUDIO_BASE_URL,
    LLM_TEMPERATURE,
    LLM_MAX_TOKENS,
    PDF_FILE,
    update_model_config,
)
from Science.Biology.biology_engine import BiologyEngine  # noqa: E402
from Science.Biology.biology_retriever import (  # noqa: E402
    get_retriever_status,
    initialize_retriever,
    retrieve_biology,
)
from cli.interface import StrudCLI  # noqa: E402
from strud.backend.tutoring_graph import build_tutoring_graph  # noqa: E402
from strud.backend.memory_store import get_memory_store  # noqa: E402
from strud.backend.llm_chain import reset_chat_model  # noqa: E402

from ..models.schemas import (  # noqa: E402
    ChatProjectUpdateBody,
    ChatRequestBody,
    ChatResponseBody,
    ChatTitleUpdateBody,
    ClearHistoryBody,
    MemoryCreateBody,
    MemorySettingsBody,
    ModelActiveUpdateBody,
    ModelTestBody,
    ProfileFullRequestBody,
    ProfileRequestBody,
    ProjectCreateBody,
    ProjectUpdateBody,
    RagQueryTestBody,
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
    store.ensure_chat(request.chatId, user_id, request.title, request.projectId)
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


@app.patch("/api/chats/{chat_id}/project")
def update_chat_project(chat_id: str, request: ChatProjectUpdateBody) -> dict:
    """Move a chat into a project, or out of one (projectId omitted/null)."""
    store = get_memory_store()
    if store.is_chat_deleted(chat_id, request.userId):
        raise HTTPException(status_code=409, detail="Restore this chat from the Recycle Bin first.")
    if request.projectId and not store.project_exists(request.userId, request.projectId):
        raise HTTPException(status_code=404, detail="Project not found.")
    if not store.set_chat_project(chat_id, request.userId, request.projectId):
        raise HTTPException(status_code=404, detail="Active chat not found.")
    return {"ok": True}


# ------------------------------------------------------------
# Projects (sidebar organization) ------------------------------------------
# ------------------------------------------------------------

@app.get("/api/projects")
def list_projects(user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    return {"projects": get_memory_store().list_projects(user_id)}


@app.post("/api/projects")
def create_project(request: ProjectCreateBody) -> dict:
    project = get_memory_store().create_project(request.userId, request.name, request.description)
    if project is None:
        raise HTTPException(status_code=422, detail="A project name is required.")
    return {"project": project}


@app.patch("/api/projects/{project_id}")
def update_project(project_id: str, request: ProjectUpdateBody) -> dict:
    if not get_memory_store().update_project(request.userId, project_id, request.name, request.description):
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"ok": True}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    """Delete a project but keep its chats as ordinary chats (no data loss)."""
    unassigned = get_memory_store().delete_project(user_id, project_id)
    if unassigned < 0:
        raise HTTPException(status_code=404, detail="Project not found.")
    return {"ok": True, "chatsUnassigned": unassigned}


# ------------------------------------------------------------
# Profile (local, per-browser identity) -------------------------------------
# ------------------------------------------------------------

@app.get("/api/profile")
def get_profile(user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    return get_memory_store().get_profile(user_id)


@app.put("/api/profile")
def update_profile(request: ProfileFullRequestBody) -> dict:
    return get_memory_store().set_profile(
        user_id=request.userId,
        display_name=request.displayName,
        avatar=request.avatar,
        response_style=request.responseStyle,
        explanation_detail=request.explanationDetail,
        study_focus=request.studyFocus,
        memory_enabled=request.memoryEnabled,
        custom_instructions=request.customInstructions,
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


# ------------------------------------------------------------
# AI Control Center — Analytics & Token Usage
# ------------------------------------------------------------

@app.get("/api/analytics/summary")
def get_analytics_summary(
    user_id: str = Query(..., min_length=1, max_length=200),
    range: str = Query("last_30_days"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
) -> dict:
    return get_memory_store().get_usage_summary(
        user_id=user_id,
        range_key=range,
        start_date=start_date,
        end_date=end_date,
    )


@app.get("/api/analytics/calendar")
def get_analytics_calendar(
    user_id: str = Query(..., min_length=1, max_length=200),
    year: Optional[int] = Query(None),
) -> dict:
    return get_memory_store().get_usage_calendar(user_id=user_id, year=year)


@app.get("/api/analytics/timeseries")
def get_analytics_timeseries(
    user_id: str = Query(..., min_length=1, max_length=200),
    range: str = Query("last_30_days"),
) -> dict:
    return {"timeseries": get_memory_store().get_usage_timeseries(user_id=user_id, range_key=range)}


@app.get("/api/analytics/models")
def get_analytics_models(
    user_id: str = Query(..., min_length=1, max_length=200),
    range: str = Query("last_30_days"),
) -> dict:
    return {"models": get_memory_store().get_usage_by_model(user_id=user_id, range_key=range)}


@app.get("/api/analytics/requests")
def get_analytics_requests(
    user_id: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(25, ge=1, le=100),
) -> dict:
    return {"requests": get_memory_store().get_recent_requests(user_id=user_id, limit=limit)}


@app.post("/api/analytics/export")
def export_analytics(user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    records = get_memory_store().export_usage_records(user_id)
    return {"records": records}


# ------------------------------------------------------------
# AI Control Center — AI Models Management
# ------------------------------------------------------------

@app.get("/api/models")
def get_models_info() -> dict:
    import requests
    available = []
    connected = False
    try:
        r = requests.get(f"{LM_STUDIO_BASE_URL}/models", timeout=3)
        if r.ok:
            data = r.json()
            available = [m.get("id") for m in data.get("data", []) if m.get("id")]
            connected = True
    except Exception:
        pass

    return {
        "activeModel": {
            "id": MODEL,
            "name": MODEL.split("/")[-1].replace("-", " ").title(),
            "provider": "LM Studio (Local)",
            "baseUrl": LM_STUDIO_BASE_URL,
            "temperature": LLM_TEMPERATURE,
            "maxTokens": LLM_MAX_TOKENS,
            "contextWindow": 8192,
            "status": "online" if (connected and MODEL in available) else ("model_not_loaded" if connected else "offline"),
            "capabilities": {"text": True, "vision": False},
        },
        "visionModel": {
            "id": "qwen/qwen3-vl-8b",
            "name": "Qwen3 VL 8B",
            "provider": "LM Studio (Local)",
            "baseUrl": LM_STUDIO_BASE_URL,
            "status": "online" if (connected and "qwen/qwen3-vl-8b" in available) else ("model_not_loaded" if connected else "offline"),
            "capabilities": {"text": True, "vision": True},
        },
        "availableModels": available if available else [MODEL, "qwen/qwen3-vl-8b"],
        "serverConnected": connected,
    }


@app.post("/api/models/test")
def test_model_connection(request: ModelTestBody) -> dict:
    import requests
    import time
    target_url = (request.baseUrl or LM_STUDIO_BASE_URL).rstrip("/")
    target_model = request.modelId or MODEL

    start = time.perf_counter()
    try:
        resp = requests.get(f"{target_url}/models", timeout=4)
        latency = int((time.perf_counter() - start) * 1000)
        if not resp.ok:
            return {
                "ok": False,
                "status": "http_error",
                "latencyMs": latency,
                "message": f"Server responded with HTTP {resp.status_code}: {resp.text[:200]}",
            }
        data = resp.json()
        models = [m.get("id") for m in data.get("data", []) if m.get("id")]
        if target_model in models:
            return {
                "ok": True,
                "status": "healthy",
                "latencyMs": latency,
                "modelId": target_model,
                "message": f"Connected to LM Studio! Model '{target_model}' is active and ready.",
            }
        else:
            return {
                "ok": False,
                "status": "model_not_loaded",
                "latencyMs": latency,
                "availableModels": models,
                "message": f"LM Studio is reachable, but '{target_model}' is not currently loaded. Loaded: {models or 'None'}.",
            }
    except requests.ConnectionError:
        return {
            "ok": False,
            "status": "connection_refused",
            "latencyMs": None,
            "message": f"Could not connect to LM Studio at {target_url}. Please ensure LM Studio is running on port 1234.",
        }
    except requests.Timeout:
        return {
            "ok": False,
            "status": "timeout",
            "latencyMs": None,
            "message": f"Connection to LM Studio at {target_url} timed out (>4s). The server may be busy or generating.",
        }
    except Exception as e:
        return {
            "ok": False,
            "status": "error",
            "latencyMs": None,
            "message": f"Connection check failed: {str(e)}",
        }


@app.post("/api/models/active")
def update_active_model(request: ModelActiveUpdateBody) -> dict:
    updated = update_model_config(
        model_id=request.modelId,
        temperature=request.temperature,
        max_tokens=request.maxTokens,
        base_url=request.baseUrl,
    )
    reset_chat_model()
    global _llm
    _llm = None
    return {"ok": True, "config": updated}


# ------------------------------------------------------------
# AI Control Center — Knowledge Base & RAG Inspector
# ------------------------------------------------------------

@app.get("/api/rag/status")
def get_rag_status() -> dict:
    return get_retriever_status()


@app.get("/api/rag/documents")
def list_rag_documents() -> dict:
    import pymupdf
    books_dir = _REPO_ROOT / "Science" / "Biology" / "books"
    docs = []
    if books_dir.exists():
        status = get_retriever_status()
        for f in sorted(books_dir.glob("*.pdf")):
            try:
                page_cnt = len(pymupdf.open(f))
            except Exception:
                page_cnt = None
            is_primary = (f.name == PDF_FILE.name)
            docs.append({
                "name": f.name,
                "sizeBytes": f.stat().st_size,
                "pageCount": page_cnt,
                "isPrimary": is_primary,
                "chunkCount": status.get("chunk_count") if is_primary else None,
                "status": "indexed" if (is_primary and status.get("textbook_loaded")) else "ready",
            })
    return {"documents": docs}


@app.post("/api/rag/test-query")
def test_rag_query(request: RagQueryTestBody) -> dict:
    import time
    start = time.perf_counter()
    res = retrieve_biology(request.query)
    duration_ms = int((time.perf_counter() - start) * 1000)

    chunks_out = []
    for r in (res.results or []):
        chunks_out.append({
            "index": r.index,
            "page": r.page,
            "text": r.text[:320] + ("..." if len(r.text) > 320 else ""),
            "tfidfScore": round(float(r.tfidf_score), 4),
            "bm25Score": round(float(r.bm25_score), 4),
            "semanticScore": round(float(r.semantic_score), 4),
            "rrfScore": round(float(r.rrf_score), 4),
            "confidence": round(float(r.confidence), 4),
        })

    return {
        "query": request.query,
        "grounded": res.grounded,
        "confidence": round(float(res.confidence), 4),
        "bestPage": res.best_page,
        "reason": res.reason,
        "latencyMs": duration_ms,
        "resultsCount": len(chunks_out),
        "chunks": chunks_out,
    }


@app.post("/api/rag/reindex")
def reindex_primary_textbook() -> dict:
    _ensure_retriever()
    status = get_retriever_status()
    return {"ok": True, "chunkCount": status.get("chunk_count"), "pageCount": status.get("page_count")}


# ------------------------------------------------------------
# AI Control Center — Memory Management
# ------------------------------------------------------------

@app.post("/api/memory")
def add_memory(request: MemoryCreateBody) -> dict:
    fact_id = get_memory_store().remember(request.userId, request.content, source=request.source or "explicit")
    return {"ok": True, "id": fact_id}


@app.delete("/api/memory/all")
def clear_all_memory(user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    cleared = get_memory_store().delete_all_memories(user_id)
    return {"ok": True, "clearedCount": cleared}


@app.patch("/api/memory/settings")
def update_memory_settings(request: MemorySettingsBody) -> dict:
    profile = get_memory_store().set_profile(request.userId, "", memory_enabled=request.memoryEnabled)
    return {"ok": True, "memoryEnabled": profile.get("memory_enabled", True)}


# ------------------------------------------------------------
# AI Control Center — Privacy & Storage Management
# ------------------------------------------------------------

@app.get("/api/privacy/storage-info")
def get_privacy_storage_info(user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    return get_memory_store().get_storage_stats(user_id, UPLOADS_DIR, CACHE_DIR)


@app.post("/api/privacy/clean-uploads")
def clean_orphaned_uploads() -> dict:
    return get_memory_store().clean_orphaned_uploads(UPLOADS_DIR)


@app.post("/api/privacy/export-data")
def export_user_data(user_id: str = Query(..., min_length=1, max_length=200)) -> dict:
    return get_memory_store().export_full_data(user_id)


@app.post("/api/privacy/clear-history")
def clear_user_history(request: ClearHistoryBody) -> dict:
    count = get_memory_store().clear_all_chats(request.userId, move_to_bin=not request.permanent)
    return {"ok": True, "clearedCount": count, "permanent": request.permanent}


# ------------------------------------------------------------
# AI Control Center — System Diagnostics
# ------------------------------------------------------------

@app.get("/api/diagnostics")
def get_diagnostics() -> dict:
    import time
    import requests
    from datetime import datetime, timezone, timedelta

    db_start = time.perf_counter()
    db_ok = False
    db_latency = None
    try:
        with get_memory_store()._conn() as conn:
            conn.execute("SELECT 1").fetchone()
            db_latency = int((time.perf_counter() - db_start) * 1000)
            db_ok = True
    except Exception:
        pass

    lm_start = time.perf_counter()
    lm_ok = False
    model_loaded = False
    lm_latency = None
    try:
        r = requests.get(f"{LM_STUDIO_BASE_URL}/models", timeout=2.5)
        lm_latency = int((time.perf_counter() - lm_start) * 1000)
        if r.ok:
            lm_ok = True
            models = [m.get("id") for m in r.json().get("data", []) if m.get("id")]
            if MODEL in models:
                model_loaded = True
    except Exception:
        pass

    rag_status = get_retriever_status()
    rag_ok = bool(rag_status.get("textbook_loaded"))

    recent_failures = 0
    with get_memory_store()._conn() as conn:
        try:
            one_day_ago = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            row = conn.execute("SELECT COUNT(*) FROM ai_usage WHERE request_status = 'failed' AND created_at >= ?", (one_day_ago,)).fetchone()
            recent_failures = row[0] if row else 0
        except Exception:
            pass

    git_hash = "0.2.0"
    git_head = _REPO_ROOT / ".git" / "HEAD"
    if git_head.exists():
        try:
            ref = git_head.read_text().strip()
            if ref.startswith("ref: "):
                ref_path = _REPO_ROOT / ".git" / ref[5:]
                if ref_path.exists():
                    git_hash = ref_path.read_text().strip()[:7]
            else:
                git_hash = ref[:7]
        except Exception:
            pass

    overall_status = "healthy" if (db_ok and lm_ok and model_loaded and rag_ok) else ("degraded" if (db_ok and rag_ok) else "unavailable")

    return {
        "status": overall_status,
        "appVersion": "0.2.0",
        "gitCommit": git_hash,
        "checks": [
            {
                "name": "FastAPI Backend Server",
                "status": "healthy",
                "details": "API endpoint responding",
                "latencyMs": 0,
            },
            {
                "name": "SQLite Database",
                "status": "healthy" if db_ok else "unavailable",
                "details": f"strud_memory_v3.db ({db_latency}ms)" if db_ok else "Database connection failed",
                "latencyMs": db_latency,
            },
            {
                "name": "LM Studio Server",
                "status": "healthy" if lm_ok else "unavailable",
                "details": f"{LM_STUDIO_BASE_URL} ({lm_latency}ms)" if lm_ok else f"Unreachable at {LM_STUDIO_BASE_URL}",
                "latencyMs": lm_latency,
            },
            {
                "name": f"Configured Model ({MODEL})",
                "status": "healthy" if model_loaded else ("unavailable" if lm_ok else "unknown"),
                "details": "Model loaded in LM Studio" if model_loaded else ("Model NOT loaded" if lm_ok else "Server unreachable"),
                "latencyMs": lm_latency if model_loaded else None,
            },
            {
                "name": "Biology Textbook Index (RAG)",
                "status": "healthy" if rag_ok else "degraded",
                "details": f"{rag_status.get('chunk_count', 0)} chunks, {rag_status.get('page_count', 0)} pages ({rag_status.get('retrieval_mode', 'standard')})",
                "latencyMs": None,
            },
            {
                "name": "Visual Engine (Qwen3-VL)",
                "status": "healthy" if check_lm_studio() else "unknown",
                "details": "Image perception active",
                "latencyMs": None,
            },
        ],
        "recentFailures24h": recent_failures,
    }
