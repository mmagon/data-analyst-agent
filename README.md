# data-analyst-agent

**Prudentia** is a careful data-analyst agent built on the [Mistral Agents SDK](https://docs.mistral.ai/studio/agents) (`mistralai-agents`, `from mistralai import agents`). It runs locally in your own process, self-hosted with `agents serve`, or Mistral-managed with `agents deploy` from the pushed commit of this repository.

## What it does

- Operates as a professional business and legal research advisor: precise, sourced, strategically minded. For factual claims it prefers connected search tools over internal knowledge and cites sources; for calculations and data processing it uses the sandbox instead of mental math.
- Never fabricates statutes, precedents, figures, or data. When uncertain, it gives the analytical framework, flags the uncertainty, and lists what would resolve it.
- Ships two read-only tools, `validate_csv` and `summarize_csv`, for quick checks on pasted CSV text.
- Gets a `MistralSandbox` environment, so it can load files, clean data, and run Python analysis code in an isolated container.
- Tracks open questions and pending research items across turns, and on wrap-up emits a state summary for re-seeding future sessions. Persistent reference material lives in the workspace Prudentia library.
- Hard safety boundary: legal and business research on public sources is fully in scope — statutes, published judgments, public court records and official registries (including in matters you are a party to), filings, market data. It never queries criminal-record/background-check sources about private individuals and never builds dossiers on people; genuine background checks go through counsel or licensed channels. It never places personal data in outputs, shared libraries, or public repos.

## Layout

```
main.py                  agent definition; exports `agent` (CLI entrypoint: main:agent)
prudentia/tools.py       validate_csv / summarize_csv tools (pure stdlib logic)
tests/test_prudentia.py  offline tests with agents.testing.ScriptedModel (no API key needed)
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

Requirements: a `MISTRAL_API_KEY` whose user has a workspace role with Workflows access (Developer or Workspace Contributor), and the `cloud_user` role for the `MistralSandbox`. The deployment must be hardened when the agent acts on behalf of a session user.

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

The Vibe Code Web link for a deployed agent looks like `https://chat.mistral.ai/managed-agents/prudentia?source=agents_api`.

## Prudentia library

The workspace library **Prudentia** is shared with the workspace at editor level so the managed deployment can attach it as the agent's knowledge base. Content rules for that library: non-sensitive reference material only. No personal data, no medical or legal case material, no third-party records; the private case libraries are not copied into it.
