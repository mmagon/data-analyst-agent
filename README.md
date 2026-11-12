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
