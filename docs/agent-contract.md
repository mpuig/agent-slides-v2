# Agent Contract

`agent-slides` now exposes a single canonical contract for agent integrations, skills, and tool wrappers.

The source of truth lives in `src/agent_slides/contract.py`.

Use the shipped CLI to read it:

```bash
uv run agent-slides contract
```

The emitted JSON documents:

- CLI commands and subcommands
- mutation commands accepted by `apply_mutation()` and `batch`
- agent tool definitions for integrations that want schema-backed deck operations
- input schemas
- output schemas
- warning payloads
- error codes

## Intended consumers

- Skills should consult `uv run agent-slides contract` instead of inferring semantics from Click wrappers or scattered docs.
- MCP servers can cache the emitted JSON and derive tool schemas from it.
- Tests should verify the contract stays aligned with the Click command tree and mutation registry.

## Compatibility notes

- The contract covers the public CLI surface plus internal agent-tool profiles.
- The `build` agent tool accepts `output_path` as the canonical key and still recognizes legacy `output` for compatibility.
