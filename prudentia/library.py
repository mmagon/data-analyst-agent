"""Read-only tools for the workspace Prudentia library and for cited web search.

Both call the Mistral API as the session user (on-behalf-of) from the worker via
``get_mistral_client(run_as=RunAs.EXECUTOR)``, so they work in the hardened managed
deployment without any workspace connector registration.
"""

from typing import Any

from mistralai import agents

PRUDENTIA_LIBRARY_ID = "01a1d114-3799-7489-b69a-af9698675b0f"

MAX_TEXT_CHARS = 20000


def _client() -> Any:
    from mistralai.workflows.client import get_mistral_client
    from mistralai.workflows.core.auth import RunAs

    return get_mistral_client(run_as=RunAs.EXECUTOR)


def _extract_conversation(response: Any) -> dict[str, Any]:
    text_parts: list[str] = []
    references: list[dict[str, str]] = []
    for output in getattr(response, "outputs", []) or []:
        if getattr(output, "type", None) != "message.output":
            continue
        for chunk in getattr(output, "content", []) or []:
            chunk_type = getattr(chunk, "type", None)
            if chunk_type == "text":
                text_parts.append(getattr(chunk, "text", ""))
            elif chunk_type == "tool_reference":
                references.append(
                    {
                        "title": getattr(chunk, "title", None) or "",
                        "url": getattr(chunk, "url", None) or "",
                        "source": getattr(chunk, "source", None) or "",
                    }
                )
    return {"text": "\n".join(p for p in text_parts if p), "references": references}


def library_list() -> dict[str, Any]:
    """List the documents in the workspace Prudentia library (id, name, status, size)."""
    try:
        response = _client().beta.libraries.documents.list(library_id=PRUDENTIA_LIBRARY_ID, page_size=100)
    except Exception as exc:
        raise agents.ToolError(f"Could not list the Prudentia library: {type(exc).__name__}. Check that the session runs as a workspace member.") from exc
    docs = [
        {
            "id": getattr(d, "id", None),
            "name": getattr(d, "name", None),
            "processing_status": getattr(d, "processing_status", None),
            "size": getattr(d, "size", None),
        }
        for d in getattr(response, "data", []) or []
    ]
    return {"library_id": PRUDENTIA_LIBRARY_ID, "documents": docs}


def library_read(document_id: str, max_chars: int = MAX_TEXT_CHARS) -> dict[str, Any]:
    """Read the full text of one document in the Prudentia library by its document id (from library_list)."""
    try:
        response = _client().beta.libraries.documents.text_content(
            library_id=PRUDENTIA_LIBRARY_ID, document_id=document_id
        )
    except Exception as exc:
        raise agents.ToolError(f"Could not read document {document_id}: {type(exc).__name__}.") from exc
    text = getattr(response, "text_content", None) or getattr(response, "content", None) or ""
    if not isinstance(text, str):
        text = str(text)
    return {
        "document_id": document_id,
        "chars": len(text),
        "truncated": len(text) > max_chars,
        "text": text[:max_chars],
    }


def library_search(query: str) -> dict[str, Any]:
    """Semantic search over the Prudentia library only. Returns an excerpt-grounded answer plus source references."""
    from mistralai.client.models import DocumentLibraryTool

    try:
        response = _client().beta.conversations.start(
            inputs=query,
            model="mistral-large-4",
            tools=[DocumentLibraryTool(type="document_library", library_ids=[PRUDENTIA_LIBRARY_ID])],
        )
    except Exception as exc:
        raise agents.ToolError(f"Library search failed: {type(exc).__name__}.") from exc
    result = _extract_conversation(response)
    result["library_id"] = PRUDENTIA_LIBRARY_ID
    return result


def web_search(query: str, limit: int = 10) -> dict[str, Any]:
    """Cited web search for public sources. Returns an answer with title/url references. Never use for private individuals."""
    from mistralai.client.models import WebSearchTool

    try:
        response = _client().beta.conversations.start(
            inputs=query,
            model="mistral-large-4",
            tools=[WebSearchTool(type="web_search")],
        )
    except Exception as exc:
        raise agents.ToolError(f"Web search failed: {type(exc).__name__}.") from exc
    result = _extract_conversation(response)
    result["references"] = result["references"][:limit]
    return result


library_list_tool = agents.tool(
    name="library_list",
    model_access="direct",
    annotations=agents.ToolAnnotations(read_only_hint=True),
)(library_list)

library_read_tool = agents.tool(
    name="library_read",
    model_access="direct",
    annotations=agents.ToolAnnotations(read_only_hint=True),
)(library_read)

library_search_tool = agents.tool(
    name="library_search",
    model_access="direct",
    annotations=agents.ToolAnnotations(read_only_hint=True),
)(library_search)

web_search_tool = agents.tool(
    name="web_search",
    model_access="direct",
    annotations=agents.ToolAnnotations(read_only_hint=True),
)(web_search)
