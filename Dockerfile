FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
COPY src ./src

RUN uv pip install --system --no-cache .

ENV NOTEBOOKLM_MCP_TRANSPORT=http \
    NOTEBOOKLM_MCP_HOST=0.0.0.0 \
    NOTEBOOKLM_MCP_PORT=8000 \
    NOTEBOOKLM_MCP_PATH=/mcp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" || exit 1

CMD ["notebooklm-mcp"]
