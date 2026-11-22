---
name: gemini-notebook-fork-rules
description: Rules and local setup conventions for working in neo-cod3/gemini-notebook-mcp-cli-fork (local .venv only, no global install, no README.md, no Docker, no Claude Desktop extension).
---

# Gemini Notebook Fork Rules

Use these conventions whenever working in `neo-cod3/gemini-notebook-mcp-cli-fork` (see [AGENTS.md](../../../AGENTS.md) and [GEMINI.md](../../../GEMINI.md)):

1. **Local-only installation (never global):**
   - Always install into the repository's `.venv` in editable mode:
     ```bash
     uv venv
     uv pip install -e .
     ```
   - Never run `uv tool install` or global `pip install`.
   - Run commands via `.venv/bin/nlm`, `.venv/bin/notebooklm-mcp`, or `uv run nlm` / `uv run notebooklm-mcp` / `uv run pytest`.

2. **Fork customization:**
   - Repository URL is `https://github.com/neo-cod3/gemini-notebook-mcp-cli-fork` ([pyproject.toml](../../../pyproject.toml)).
   - `README.md`, `.github/`, `desktop-extension/`, `scripts/build_mcpb.py`, and Docker files are intentionally removed for local-only CLI/`uvx` usage — do not re-add them or add `readme = "README.md"` back to `pyproject.toml`.

3. **Security:**
   - Never print or log decrypted cookies, credentials, or raw keystore values.
