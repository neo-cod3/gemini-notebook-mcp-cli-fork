# Gemini Notebook Fork Rules

Project-specific rules for `neo-cod3/gemini-notebook-mcp-cli-fork`. See also [AGENTS.md](../../AGENTS.md) and [GEMINI.md](../../GEMINI.md).

## 1. Local-Only Installation (Never Global)
- Always install dependencies and the package locally inside `.venv` in editable mode:
  ```bash
  uv venv
  uv pip install -e .
  ```
- **Do NOT** install globally (`uv tool install`, global `pip install`).
- Run CLI, MCP server, and tests via `.venv/bin/nlm`, `.venv/bin/notebooklm-mcp`, or `uv run`:
  - `uv run nlm --help`
  - `uv run notebooklm-mcp`
  - `uv run pytest`

## 2. Fork Customizations
- Repository: `https://github.com/neo-cod3/gemini-notebook-mcp-cli-fork` (configured in [pyproject.toml](../../pyproject.toml)).
- `README.md`, `.github/`, `desktop-extension/`, `scripts/build_mcpb.py`, and Docker files were intentionally removed for local-only CLI/`uvx` usage — do not re-add them or restore `readme = "README.md"` in [pyproject.toml](../../pyproject.toml).

## 3. Security
- Never print, log, or expose decrypted cookies, credentials, or raw keystore values.
