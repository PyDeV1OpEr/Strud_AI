"""Offline persistence regressions for titles, messages, and attachments."""

from langchain_core.messages import AIMessage

from strud.backend.memory_store import MemoryStore


def test_chat_title_and_attachment_survive_store_restart(tmp_path):
    database = tmp_path / "memory.db"
    attachment = {
        "id": "image.png",
        "url": "/api/uploads/image.png",
        "name": "leaf.png",
        "mimeType": "image/png",
        "size": 12,
    }
    store = MemoryStore(database)
    store.ensure_chat("chat-1", "student", "Photosynthesis Light Reactions")
    store.append_message("chat-1", "student", "user", "Explain photosynthesis", [attachment])
    # A default from a later request must not overwrite the real title.
    store.ensure_chat("chat-1", "student", "New chat")

    reopened = MemoryStore(database)
    chats = reopened.list_chats("student")
    assert chats[0]["title"] == "Photosynthesis Light Reactions"
    assert chats[0]["messages"][0]["attachments"] == [attachment]


def test_graph_persists_attachment_with_its_user_message(tmp_path, monkeypatch):
    import pytest

    pytest.importorskip("langgraph.checkpoint.sqlite")
    from strud.backend import tutoring_graph as graph_module

    class FakeModel:
        def invoke(self, messages):
            return AIMessage(content="A helpful answer.")

    store = MemoryStore(tmp_path / "memory.db")
    monkeypatch.setattr(graph_module, "get_chat_model", lambda: FakeModel())
    graph = graph_module.build_tutoring_graph(store)
    attachment = {"id": "diagram.jpg", "url": "/api/uploads/diagram.jpg", "name": "diagram.jpg", "mimeType": "image/jpeg", "size": 42}
    graph.invoke(
        {"chat_id": "chat-2", "user_id": "student", "question": "What is shown?", "attachments": [attachment]},
        config={"configurable": {"thread_id": "attachment-test"}},
    )

    history = store.get_history("chat-2", "student")
    assert history[0]["attachments"] == [attachment]
    assert history[1]["attachments"] == []


def test_attachment_upload_is_validated_and_written_durably(tmp_path, monkeypatch):
    import base64
    from strud.backend.api import main
    from strud.backend.models.schemas import ChatRequestBody

    monkeypatch.setattr(main, "UPLOADS_DIR", tmp_path / "uploads")
    request = ChatRequestBody(
        chatId="chat-3",
        userId="student",
        attachments=[{
            "name": "diagram.png",
            "mimeType": "image/png",
            "data": base64.b64encode(b"image-bytes").decode(),
        }],
    )
    paths, records = main._persist_attachments(request)
    assert len(paths) == len(records) == 1
    assert paths[0].read_bytes() == b"image-bytes"
    assert records[0]["url"].startswith("/api/uploads/")


def test_chat_list_api_returns_saved_title_and_attachment(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from strud.backend.api import main

    store = MemoryStore(tmp_path / "memory.db")
    store.ensure_chat("chat-4", "student", "Cell Membrane Transport")
    store.append_message("chat-4", "student", "user", "Explain osmosis", [{"id": "cell.png", "url": "/api/uploads/cell.png", "name": "cell.png", "mimeType": "image/png", "size": 5}])
    monkeypatch.setattr(main, "get_memory_store", lambda: store)

    response = TestClient(main.app).get("/api/chats", params={"user_id": "student"})
    assert response.status_code == 200
    chat = response.json()["chats"][0]
    assert chat["title"] == "Cell Membrane Transport"
    assert chat["messages"][0]["attachments"][0]["url"] == "/api/uploads/cell.png"


def test_recycle_bin_soft_restore_and_permanent_delete(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    store.ensure_chat("active", "student", "Active Chat")
    store.ensure_chat("deleted", "student", "Deleted Chat")
    store.append_message("deleted", "student", "user", "keep this image", [{"url": "/api/uploads/keep.png"}])
    assert store.move_chat_to_bin("deleted", "student")
    assert [chat["chat_id"] for chat in store.list_chats("student")] == ["active"]
    assert store.list_chats("student", deleted=True)[0]["messages"][0]["content"] == "keep this image"
    assert store.restore_chat("deleted", "student")
    assert {chat["chat_id"] for chat in store.list_chats("student")} == {"active", "deleted"}
    assert store.move_chat_to_bin("deleted", "student")
    assert store.permanently_delete_chat("deleted", "student") == [{"url": "/api/uploads/keep.png"}]
    assert not store.list_chats("student", deleted=True)


def test_empty_bin_never_removes_active_chats(tmp_path):
    store = MemoryStore(tmp_path / "memory.db")
    for chat_id in ("active", "one", "two"):
        store.ensure_chat(chat_id, "student", chat_id)
    store.move_chat_to_bin("one", "student")
    store.move_chat_to_bin("two", "student")
    store.empty_bin("student")
    assert [chat["chat_id"] for chat in store.list_chats("student")] == ["active"]
