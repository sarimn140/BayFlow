# BayFlow AI Front Desk image (spec 05 §2, §10; D58): a LiveKit Agents worker on Railway.
# Same uv multi-stage pattern as the API. No public port: the worker dials out to LiveKit; its
# health server answers `/` on AGENT_PORT (Railway health check).

# ---- builder ----
FROM python:3.12-slim-trixie AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project
COPY . .
RUN uv sync --locked

# ---- runtime ----
FROM python:3.12-slim-trixie AS runtime
RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot
COPY --from=builder --chown=nonroot:nonroot /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1
WORKDIR /app
USER nonroot
CMD ["python", "-m", "bayflow_agent", "start"]
