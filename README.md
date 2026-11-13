# data-analyst-agent

**Prudentia** is a careful data-analyst agent built on the [Mistral Agents SDK](https://docs.mistral.ai/studio/agents) (`mistralai-agents`, `from mistralai import agents`). It runs locally in your own process, self-hosted with `agents serve`, or Mistral-managed with `agents deploy` from the pushed commit of this repository.

## What it does

- Operates as a professional business and legal research advisor: precise, sourced, strategically minded. For factual claims it calls its `web_search` tool (cited results via the Conversations API, run as the session user) and cites source URLs, preferring primary sources (statutes, courts, regulators, official registries, public filings); for calculations and data processing it uses the sandbox instead of mental math.
- Never fabricates statutes, precedents, figures, or data. When uncertain, it gives the analytical framework, flags the uncertainty, and lists what would resolve it.
- Ships two read-only tools, `validate_csv` and `summarize_csv`, for quick checks on pasted CSV text.
- Gets a `MistralSandbox` environment with unrestricted outbound network (`network=agents.Network.all()`), so it can load files, clean data, run Python, and curl public sources in an isolated container.
- Reads the workspace **Prudentia library** through its `library_list` / `library_search` / `library_read` tools (`prudentia/library.py`), which call the Libraries/Conversations API as the session user and are hard-scoped to library `01a1d114-3799-7489-b69a-af9698675b0f` (`doclib://01a1d114-3799-7489-b69a-af9698675b0f`) — they cannot touch any other library. (The builtin `document_library`/`web_search` connectors are not registered in this workspace, so the agent uses these tools instead.)
- Can produce **encrypted backups of the Prudentia library to Google Drive** via the `google_drive_mcp` connector: it packs only library documents, encrypts them in the sandbox (AES-256, user-supplied passphrase, never persisted), and uploads the `.zip.enc` to a "Prudentia backups" folder. Drive writes go through the user's per-action approval.
- The `google_drive_mcp` connector and the library/web tools run as the session user (on-behalf-of), so workspace sharing applies and the deployment stays hardened.
- Tracks open questions and pending research items across turns, and on wrap-up emits a state summary for re-seeding future sessions. Sessions persist server-side: the Dockerfile raises the limits to the deployed maximums (24 h idle, 7 days total), and any process can resume a session by id.
- Hard safety boundary: legal and business research on public sources is fully in scope — statutes, published judgments, public court records and official registries (including in matters you are a party to), filings, market data. It never queries criminal-record/background-check sources about private individuals and never builds dossiers on people; genuine background checks go through counsel or licensed channels. It never places personal data in outputs, shared libraries, or public repos.

## Layout

```
main.py                  agent definition; exports `agent` (CLI entrypoint: main:agent)
prudentia/tools.py       validate_csv / summarize_csv tools (pure stdlib logic)
prudentia/library.py     library_list / library_read / library_search / web_search tools (Mistral API, OBO, read-only)
monitor/hourly_scan.py   hourly market scan (yfinance): prices, volume anomalies, divergence signals -> JSON snapshot
monitor/daily_brief.py   aggregates the day's scans into a daily intelligence brief JSON + summary
tests/                   offline tests (ScriptedModel for the agent, stubbed yfinance for the monitor)
pyproject.toml           uv project; [tool.mistralai.agents] entrypoint; pins mistralai-agents[koyeb]>=1.1.2,<1.2
Dockerfile               worker image built by the managed deployment; build runs `uv sync --no-dev`
                         (resolves from the pyproject pins; commit uv.lock and switch to
                         `--frozen` if you want fully locked image builds)
.python-version          3.12
```

## Local setup and run

```bash
uv sync                 # installs mistralai-agents[koyeb] + dev deps, creates .venv
echo 'MISTRAL_API_KEY=<your-key>' > .env   # .env is gitignored
uv run --env-file .env agents chat          # chat in your process
uv run --env-file .env python main.py       # one-shot demo run
```

## Tests

```bash
uv run pytest
```

The tests run offline: a `ScriptedModel` replaces the model, and an autouse fixture removes any API key so a test that forgets to override the model fails instead of calling it.

## Deploy (Mistral-managed)

1. Commit and push this repository (a managed deployment builds the pushed commit, not your working copy).
2. Either run `uv run --env-file .env agents deploy` in the project, or create the managed deployment in Mistral Studio from this repository and the commit you want served.
3. The build needs the committed `Dockerfile`, `pyproject.toml`, and `.python-version`. The container runs `agents run-worker`.

Requirements: a `MISTRAL_API_KEY` whose user has a workspace role with Workflows access (Developer or Workspace Contributor), and the `cloud_user` role for the `MistralSandbox` (the deployer passes it to the deployment's service account). Because the agent uses connectors on behalf of the session user, the deployment is hardened (OBO) — keep `hardened=true` on redeploys; changing hardening requires `agents shutdown` plus a fresh deploy.

## Calling the deployed agent (two-turn smoke test)

```python
import asyncio
from mistralai import agents

async def main() -> None:
    agent = agents.Agent.load_from(agent_name="prudentia")
    session = await agent.start_session()
    first = await session.run("Validate this CSV: a,b\n1,2\n3,4")
    print(first.text)
    second = await session.run("Now summarize it.")
    print(second.text)
    await session.cancel()

asyncio.run(main())
```

## Talking to the deployed agent — fast and persistent

The Vibe Code Web link for a deployed agent is `https://chat.mistral.ai/managed-agents/prudentia?source=agents_api`. The web UI batches session events (you may see ~60 s jumps); for live streaming use the CLI or the API directly:

```bash
uv run --env-file .env agents chat prudentia        # terminal chat, streams tool calls live
```

```python
agent = agents.Agent.load_from(agent_name="prudentia")
session = await agent.start_session()
async for event in session.run_stream("..."):        # live events instead of polling
    ...
# later, from any process:  session = agent.session("<session-id>")
```

Sessions are stored by Mistral, not by your client: close the tab or process and resume by session id. The Dockerfile sets `AGENTS_SDK_IDLE_TIMEOUT_SECONDS=86400` (24 h idle), `AGENTS_SDK_LIFETIME_LIMIT_SECONDS=604800` (7 days total) and `AGENTS_SDK_EXECUTION_TIMEOUT_SECONDS=608400` — the maximums a Mistral-managed deployment allows.

## Scheduled maintenance (heartbeat) turns

A Workflows schedule on the `prudentia` workflow can fire a turn into one long-lived session at a fixed interval (e.g. every hour, `intervals=[{"every": "PT1H"}]`), using a session-start input with a **fixed `session_id`** and an `initial_command` message beginning with `[SCHEDULED]`. Each fire is a turn of that same session, so the session's idle timer resets and its `MistralSandbox` (created with `ttl_seconds=604800`) keeps its `/workspace` filesystem for the whole session life (up to 7 days). Scheduled turns are instructed to run sandbox-local maintenance only (heartbeat log in `/workspace/prudentia-state/`, pending-items review) — unattended runs have no session user, so connector calls may fail there; anything needing connectors is deferred to an interactive turn.

Caveat: once the agent declares connectors at the default `run_as="auto"`, the workflow registers on-behalf-of (OBO), and the platform may refuse unattended (scheduled) executions of an OBO workflow. If a scheduled run is refused, either give the connectors `run_as="deployment"` with workspace-level credentials, or accept that scheduled turns only do sandbox-local work. Verify after deploying by watching `list_executions` for the scheduled fires.

The monitor scripts run inside the session sandbox on scheduled turns (the sandbox has internet; the scripts are fetched from this public repo with curl). Hourly: `[SCHEDULED] hourly scan`; daily: `[SCHEDULED] daily brief`. Snapshots and briefs persist under the session's `/workspace/prudentia_monitor/` for the session's lifetime. The scripts only collect public market data; the analysis and any status labels are produced by the agent, with a not-personalized-advice disclaimer on briefs.

## Prudentia library

The workspace library **Prudentia** (`01a1d114-3799-7489-b69a-af9698675b0f`) is shared with the whole workspace at editor level, so the agent's `library_*` tools (running as the session user) can read it in every session — no per-chat attachment needed. The tools are hard-scoped to `doclib://01a1d114-3799-7489-b69a-af9698675b0f` and cannot query any other library. Content rules for that library: non-sensitive reference material only. No personal data, no medical or legal case material, no third-party records; the private case libraries are not copied into it.
