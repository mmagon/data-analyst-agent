from types import SimpleNamespace

import pytest
from mistralai import agents

from prudentia import library


class _FakeDocuments:
    def __init__(self, client: "_FakeClient") -> None:
        self._client = client

    def list(self, *, library_id: str, page_size: int = 100, **kwargs):
        self._client.listed_library_id = library_id
        return SimpleNamespace(
            data=[
                SimpleNamespace(id="doc1", name="README.md", processing_status="Completed", size=1000),
                SimpleNamespace(id="doc2", name="engineering-playbook.md", processing_status="Completed", size=5000),
            ]
        )

    def text_content(self, *, library_id: str, document_id: str, **kwargs):
        self._client.read_document = (library_id, document_id)
        return SimpleNamespace(text="line1\n" + "x" * 100 + "\nlastline")


class _FakeConversations:
    def __init__(self, client: "_FakeClient") -> None:
        self._client = client

    def start(self, *, inputs: str, model: str, tools: list, **kwargs):
        self._client.last_call = {"inputs": inputs, "model": model, "tools": tools}
        return SimpleNamespace(
            outputs=[
                SimpleNamespace(type="tool.execution", name="web_search"),
                SimpleNamespace(
                    type="message.output",
                    content=[
                        SimpleNamespace(type="text", text="Grounded answer."),
                        SimpleNamespace(type="tool_reference", title="Source A", url="https://a.example", source="brave"),
                        SimpleNamespace(type="tool_reference", title="Source B", url="https://b.example", source="brave"),
                    ],
                ),
            ]
        )


class _FakeBeta:
    def __init__(self, client: "_FakeClient") -> None:
        self.libraries = SimpleNamespace(documents=_FakeDocuments(client))
        self.conversations = _FakeConversations(client)


class _FakeClient:
    def __init__(self) -> None:
        self.beta = _FakeBeta(self)
        self.listed_library_id = None
        self.read_document = None
        self.last_call = None


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    client = _FakeClient()
    monkeypatch.setattr(library, "_client", lambda: client)
    return client


def test_library_list_scoped_to_prudentia(fake_client: _FakeClient) -> None:
    result = library.library_list()
    assert fake_client.listed_library_id == library.PRUDENTIA_LIBRARY_ID
    assert [d["name"] for d in result["documents"]] == ["README.md", "engineering-playbook.md"]


def test_library_read_truncates(fake_client: _FakeClient) -> None:
    result = library.library_read("doc1", max_chars=50)
    assert fake_client.read_document == (library.PRUDENTIA_LIBRARY_ID, "doc1")
    assert result["truncated"] is True
    assert result["chars"] == 115
    assert len(result["text"]) == 50


def test_library_search_scopes_tool_to_prudentia(fake_client: _FakeClient) -> None:
    result = library.library_search("deadline mechanics")
    tools = fake_client.last_call["tools"]
    assert tools[0].type == "document_library"
    assert tools[0].library_ids == [library.PRUDENTIA_LIBRARY_ID]
    assert result["text"] == "Grounded answer."
    assert result["references"][0]["url"] == "https://a.example"


def test_web_search_returns_cited_references(fake_client: _FakeClient) -> None:
    result = library.web_search("BC Labour Relations Code s.12", limit=1)
    assert fake_client.last_call["tools"][0].type == "web_search"
    assert result["text"] == "Grounded answer."
    assert len(result["references"]) == 1


def test_tool_error_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> None:
        raise RuntimeError("kaput")

    monkeypatch.setattr(library, "_client", boom)
    with pytest.raises(agents.ToolError):
        library.library_list()
