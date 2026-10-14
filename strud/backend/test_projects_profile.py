"""Offline regressions for projects, chat-project moves, and the profile."""

from fastapi.testclient import TestClient

from strud.backend.memory_store import MemoryStore


def _store(tmp_path):
    return MemoryStore(tmp_path / "memory.db")


def test_project_create_list_update_and_chat_counts(tmp_path):
    store = _store(tmp_path)
    project = store.create_project("student", "Cell Biology", "Chapter summary chats")
    assert project is not None
    store.ensure_chat("chat-1", "student", "Osmosis", project["project_id"])
    store.ensure_chat("chat-2", "student", "Mitosis")

    projects = store.list_projects("student")
    assert len(projects) == 1
    assert projects[0]["name"] == "Cell Biology"
    assert projects[0]["description"] == "Chapter summary chats"
    assert projects[0]["chat_count"] == 1

    assert store.update_project("student", project["project_id"], "Cells 101", "")
    updated = store.list_projects("student")
    assert updated[0]["name"] == "Cells 101"
    assert updated[0]["description"] == ""


def test_move_chat_between_projects_and_out(tmp_path):
    store = _store(tmp_path)
    project_a = store.create_project("student", "Genetics")
    project_b = store.create_project("student", "Ecology")

    store.ensure_chat("chat-1", "student", "Punnett squares")
    assert store.set_chat_project("chat-1", "student", project_a["project_id"])
    assert store.list_chats("student")[0]["project_id"] == project_a["project_id"]

    # Empty-string project id means "unassign", same as None.
    assert store.set_chat_project("chat-1", "student", "")
    assert store.list_chats("student")[0]["project_id"] is None

    assert store.set_chat_project("chat-1", "student", project_b["project_id"])
    assert store.list_chats("student")[0]["project_id"] == project_b["project_id"]


def test_delete_project_unassigns_chats_without_losing_data(tmp_path):
    store = _store(tmp_path)
    project = store.create_project("student", "Plant systems")
    store.ensure_chat("chat-9", "student", "Xylem", project["project_id"])
    store.append_message("chat-9", "student", "user", "Explain transpiration")

    # A deleted chat keeps its project_id but is not counted as active.
    store.ensure_chat("chat-10", "student", "Recycled", project["project_id"])
    store.move_chat_to_bin("chat-10", "student")

    # Both chats are unassigned: restaurations must never point at a
    # project row that no longer exists.
    unassigned = store.delete_project("student", project["project_id"])
    assert unassigned == 2
    assert store.list_projects("student") == []
    chats = store.list_chats("student")
    assert chats[0]["chat_id"] == "chat-9"
    assert chats[0]["project_id"] is None
    assert chats[0]["messages"][0]["content"] == "Explain transpiration"

    # Deleting again is a 404 (-1), never a data wipe.
    assert store.delete_project("student", project["project_id"]) == -1


def test_first_message_assigns_project_and_later_messages_keep_it(tmp_path):
    store = _store(tmp_path)
    project = store.create_project("student", "Photosynthesis study")
    store.ensure_chat("chat-3", "student", "Light reactions", project["project_id"])
    # Later sends arrive without a projectId; the assignment must survive.
    store.ensure_chat("chat-3", "student", "Light reactions")
    assert store.list_chats("student")[0]["project_id"] == project["project_id"]


def test_profile_persists_across_store_reopens(tmp_path):
    store = _store(tmp_path)
    assert store.get_profile("student") == {"display_name": "Student"}
    store.set_profile("student", "Mina")
    reopened = MemoryStore(tmp_path / "memory.db")
    assert reopened.get_profile("student")["display_name"] == "Mina"
    # Blank updates keep the stored name (empty string is not a name).
    assert store.set_profile("student", "")["display_name"] == "Mina"


def test_project_api_routes_crud_and_chat_move(tmp_path, monkeypatch):
    from strud.backend.api import main

    store = _store(tmp_path)
    monkeypatch.setattr(main, "get_memory_store", lambda: store)

    client = TestClient(main.app)
    created = client.post(
        "/api/projects",
        json={"userId": "student", "name": "Exam prep", "description": "Past papers"},
    )
    assert created.status_code == 200
    project = created.json()["project"]

    listed = client.get("/api/projects", params={"user_id": "student"}).json()["projects"]
    assert listed[0]["name"] == "Exam prep" and listed[0]["chat_count"] == 0

    # Chat association through the API, including a 404 for a bad project.
    store.ensure_chat("chat-a", "student", "Past paper 1")
    moved = client.patch("/api/chats/chat-a/project", json={"userId": "student", "projectId": project["project_id"]})
    assert moved.status_code == 200
    assert client.get("/api/projects", params={"user_id": "student"}).json()["projects"][0]["chat_count"] == 1

    bad_move = client.patch("/api/chats/chat-a/project", json={"userId": "student", "projectId": "missing"})
    assert bad_move.status_code == 404

    renamed = client.patch(
        f"/api/projects/{project['project_id']}",
        json={"userId": "student", "name": "Exam prep 2026", "description": ""},
    )
    assert renamed.status_code == 200

    deleted = client.delete(f"/api/projects/{project['project_id']}", params={"user_id": "student"})
    assert deleted.status_code == 200
    assert deleted.json()["chatsUnassigned"] == 1
    assert store.list_chats("student")[0]["project_id"] is None


def test_profile_api_routes(tmp_path, monkeypatch):
    from strud.backend.api import main

    store = _store(tmp_path)
    monkeypatch.setattr(main, "get_memory_store", lambda: store)
    client = TestClient(main.app)

    assert client.get("/api/profile", params={"user_id": "student"}).json() == {"display_name": "Student"}
    saved = client.put("/api/profile", json={"userId": "student", "displayName": "Mina"})
    assert saved.status_code == 200 and saved.json()["display_name"] == "Mina"
    assert client.get("/api/profile", params={"user_id": "student"}).json()["display_name"] == "Mina"
