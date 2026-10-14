"""Focused, offline regression tests for durable memory and Qwen payloads."""

from pathlib import Path
import base64

import pytest
from langchain_core.messages import AIMessage

from strud.backend.memory_store import MemoryStore
from strud.backend.models.schemas import ChatRequestBody
from Science.Biology.vision import build_student_image_messages


class _FakeModel:
    def __init__(self) -> None:
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        return AIMessage(content="Test response")


def test_name_memory_cross_chat_restart_and_user_isolation(tmp_path, monkeypatch):
    """An ordinary name statement is durable, injected, and user-scoped."""
    pytest.importorskip("langgraph.checkpoint.sqlite")
    from strud.backend import tutoring_graph as graph_module

    store = MemoryStore(tmp_path / "memory.db")
    model = _FakeModel()
    monkeypatch.setattr(graph_module, "get_chat_model", lambda: model)

    compiled = graph_module.build_tutoring_graph(store)
    compiled.invoke(
        {"chat_id": "first", "user_id": "user-a", "question": "My name is Asha."},
        config={"configurable": {"thread_id": "memory-test-first"}},
    )

    # Re-opening the SQLite database simulates a backend restart.
    restarted_store = MemoryStore(tmp_path / "memory.db")
    assert restarted_store.recall("user-a")[0]["content"] == "The student's name is Asha."
    assert restarted_store.recall("user-b") == []

    second_graph = graph_module.build_tutoring_graph(restarted_store)
    second_graph.invoke(
        {"chat_id": "second", "user_id": "user-a", "question": "What is my name?"},
        config={"configurable": {"thread_id": "memory-test-second"}},
    )
    system_prompt = model.calls[-1][0].content
    assert "The student's name is Asha." in system_prompt
    assert restarted_store.get_history("first", "user-a") != []
    assert restarted_store.get_history("second", "user-a") != []


def test_chat_request_requires_a_user_identity():
    request = ChatRequestBody(chatId="chat-a", userId="user-a", message="hello")
    assert request.userId == "user-a"


def test_qwen_message_uses_openai_compatible_data_url_content():
    image_url = "data:image/png;base64,aGVsbG8="
    messages = build_student_image_messages(image_url, "What structure is this?")
    content = messages[1]["content"]
    assert content[0]["type"] == "text"
    assert content[1] == {"type": "image_url", "image_url": {"url": image_url}}


def test_chat_route_delivers_uploaded_image_analysis_to_graph(monkeypatch):
    """The API's upload -> Qwen -> LangGraph bridge is not session-local."""
    from fastapi.testclient import TestClient
    from Science.Biology.vision import VisualAnalysis
    from strud.backend.api import main

    seen = {}

    class FakeVision:
        def analyze_image(self, path, question=""):
            seen["bytes"] = Path(path).read_bytes()
            seen["question"] = question
            return VisualAnalysis(None, str(path), "hash", "key", "diagram", {}, "{}", 0.0)

        def format_visual_context(self, analyses):
            assert len(analyses) == 1
            return "Qwen saw a labelled chloroplast diagram."

    class FakeSession:
        vision = FakeVision()

    class FakeGraph:
        def invoke(self, state, config):
            seen["state"] = state
            seen["config"] = config
            return {"answer": "It is a chloroplast.", "grounded": False}

    monkeypatch.setattr(main, "_ensure_retriever", lambda: None)
    monkeypatch.setattr(main, "_get_graph", lambda: FakeGraph())
    monkeypatch.setattr(main, "_get_session", lambda chat_id, user_id: FakeSession())

    payload = {
        "chatId": "chat-a",
        "userId": "user-a",
        "message": "What is this structure?",
        "attachments": [{
            "name": "diagram.png",
            "mimeType": "image/png",
            "data": base64.b64encode(b"test-image-bytes").decode(),
        }],
    }
    response = TestClient(main.app).post("/api/chat", json=payload)
    assert response.status_code == 200
    assert seen["bytes"] == b"test-image-bytes"
    assert seen["question"] == "What is this structure?"
    assert seen["state"]["user_id"] == "user-a"
    assert seen["state"]["image_context"] == "Qwen saw a labelled chloroplast diagram."
    assert seen["config"]["configurable"]["thread_id"] == "user-a:chat-a"

    text_only = TestClient(main.app).post(
        "/api/chat", json={"chatId": "chat-b", "userId": "user-a", "message": "Hello"}
    )
    assert text_only.status_code == 200
    assert seen["state"]["image_context"] == ""


def test_chat_lock_is_reentrant_for_lazy_session_creation():
    """An image turn may create its session while holding the LLM turn lock."""
    from strud.backend.api import main

    session_key = ("lock-test-user", "lock-test-chat")
    try:
        with main._app_lock:
            session = main._get_session(session_key[1], session_key[0])
        assert session is not None
    finally:
        main._sessions.pop(session_key, None)
