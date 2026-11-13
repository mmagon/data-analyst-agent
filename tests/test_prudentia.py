import pytest
from mistralai import agents

from main import (
    CONNECTORS,
    PRUDENTIA_LIBRARY_URI,
    build_agent,
    build_environment,
)
from prudentia.tools import summarize_csv_text, validate_csv_text

CSV_OK = "name,age,score\nalice,30,9.5\nbob,25,7.0\ncarol,,8.25\n"
CSV_RAGGED = "a,b\n1,2\n3\n4,5,6\n"
CSV_DUP_HEADER = "a,a\n1,2\n"


@pytest.fixture(autouse=True)
def no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISTRAL_API_KEY", raising=False)
    monkeypatch.delenv("MISTRAL_CLIENT_API_KEY", raising=False)


def test_validate_ok() -> None:
    result = validate_csv_text(CSV_OK)
    assert result["ok"] is True
    assert result["columns"] == 3
    assert result["data_rows"] == 3
    assert result["header"] == ["name", "age", "score"]
    assert result["issues"] == []


def test_validate_ragged_rows() -> None:
    result = validate_csv_text(CSV_RAGGED)
    assert result["ok"] is False
    assert any("ragged" in issue for issue in result["issues"])


def test_validate_duplicate_header() -> None:
    result = validate_csv_text(CSV_DUP_HEADER)
    assert result["ok"] is False
    assert any("duplicate header" in issue for issue in result["issues"])


def test_summarize_numeric_stats() -> None:
    result = summarize_csv_text(CSV_OK)
    assert result["rows"] == 3
    by_name = {col["name"]: col for col in result["column_summaries"]}
    assert by_name["age"]["type"] == "number"
    assert by_name["age"]["missing"] == 1
    assert by_name["age"]["min"] == 25.0
    assert by_name["age"]["max"] == 30.0
    assert by_name["age"]["mean"] == pytest.approx(27.5)
    assert by_name["age"]["median"] == pytest.approx(27.5)
    assert by_name["score"]["mean"] == pytest.approx((9.5 + 7.0 + 8.25) / 3)
    assert by_name["score"]["min"] == 7.0
    assert by_name["score"]["max"] == 9.5
    assert by_name["score"]["median"] == pytest.approx(8.25)
    assert by_name["name"]["type"] == "text"
    assert by_name["name"]["distinct"] == 3


def test_summarize_empty_raises() -> None:
    with pytest.raises(agents.ToolError):
        summarize_csv_text("   \n")


def test_summarize_too_many_rows_raises() -> None:
    csv_text = "a\n" + "1\n" * 5
    with pytest.raises(agents.ToolError):
        summarize_csv_text(csv_text, max_rows=3)


async def test_agent_calls_summarize_tool() -> None:
    model = agents.testing.ScriptedModel(
        [
            agents.testing.call("summarize_csv", csv_text=CSV_OK),
            agents.testing.reply("Summary: 3 rows, 3 columns."),
        ]
    )
    state = await build_agent(with_sandbox=False, with_connectors=False).override(model=model).run(
        "Summarize this CSV:\n" + CSV_OK
    )
    assert isinstance(state, agents.Completed), state
    assert state.text == "Summary: 3 rows, 3 columns."
    assert [call.name for call in state.tool_calls] == ["client.summarize_csv"]
    assert state.tool_calls[0].arguments["csv_text"] == CSV_OK
    model.assert_consumed()


def test_agent_has_library_and_web_connectors() -> None:
    assert sorted(slot.connector_name for slot in CONNECTORS) == [
        "document_library",
        "google_drive_mcp",
        "web_search",
    ]
    assert PRUDENTIA_LIBRARY_URI in build_agent(with_sandbox=False, with_connectors=False).instructions


def test_sandbox_has_unrestricted_network() -> None:
    environment = build_environment(with_sandbox=True)
    assert isinstance(environment, agents.MistralSandbox)
    assert environment.network == agents.Network.all()
    assert environment.ttl_seconds == 604800
