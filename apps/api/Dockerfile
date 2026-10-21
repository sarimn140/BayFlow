# BayFlow API image (spec 07): Render, Railway and Docker Compose.
# Official uv multi-stage pattern: dependencies in a cached layer, the project after it; the
# runtime image has no uv, uses the same base image as the builder and runs as a non-root user.

# ---- builder: resolve and install dependencies with uv ----
FROM python:3.12-slim-trixie AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.24 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1 \
    UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# 1) dependencies only: this layer is reused while pyproject.toml / uv.lock are unchanged
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project
# 2) application code
COPY . .
RUN uv sync --locked

# ---- runtime: same base image (the venv's interpreter path must match), no uv, non-root ----
FROM python:3.12-slim-trixie AS runtime
RUN groupadd --system --gid 999 nonroot \
 && useradd --system --gid 999 --uid 999 --create-home nonroot
COPY --from=builder --chown=nonroot:nonroot /app /app
# The live demo must ship seeded data and demo accounts (brief §9.1); the seed is idempotent.
# A platform variable (SEED_ON_DEPLOY=false) still turns it off.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    SEED_ON_DEPLOY=true
WORKDIR /app
USER nonroot
EXPOSE 4000
# Start-up runs the migrations, then the seed, then the server. Render has no pre-deploy step on
# its free tier and ignores railway.json, so the image itself must bring the schema up to date;
# both commands are idempotent (Railway's preDeployCommand may run them again — harmless). A
# failure stops the container, so the platform keeps serving the previous deploy.
# ONE worker on purpose: the WebSocket hub and the rate-limit counters live in process memory (D14).
# `sh -c` expands ${PORT} (Render and Railway inject it); `exec` hands signals to uvicorn.
# --no-access-log: the API writes its own JSON access line; --no-server-header: spec 04 Tier 1.
CMD ["sh", "-c", "alembic upgrade head && python -m app.scripts.seed && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-4000} --workers 1 --proxy-headers --forwarded-allow-ips='*' --no-access-log --no-server-header --timeout-graceful-shutdown 10"]
