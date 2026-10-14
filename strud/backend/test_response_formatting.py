"""Offline regressions for answer-formatting instructions."""

from langchain_core.messages import AIMessage


class _FakeModel:
    def __init__(self) -> None:
        self.messages = []

    def invoke(self, messages):
        self.messages = messages
        return AIMessage(content="A concise answer.")


def test_system_prompt_requests_adaptive_markdown_not_default_tables(tmp_path, monkeypatch):
    """The actual LLM system message carries the formatting contract."""
    import pytest

    pytest.importorskip("langgraph.checkpoint.sqlite")
    from strud.backend import tutoring_graph as graph_module
    from strud.backend.memory_store import MemoryStore

    model = _FakeModel()
    monkeypatch.setattr(graph_module, "get_chat_model", lambda: model)
    graph = graph_module.build_tutoring_graph(MemoryStore(tmp_path / "memory.db"))
    graph.invoke(
        {"chat_id": "formatting", "user_id": "student", "question": "Hello"},
        config={"configurable": {"thread_id": "formatting-test"}},
    )

    prompt = model.messages[0].content
    assert "paragraphs for ordinary answers" in prompt
    assert "never as the default format" in prompt
    assert "Do not use HTML for formatting" in prompt
