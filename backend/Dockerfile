# Crucible backend (PLAN §19). Build context: the repo root, so data/ ships with the image:
#   docker build -f backend/Dockerfile .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /uvx /bin/
# GNU patch applies sample apps' fix.patch at startup (defense/projects.py); slim images don't ship it.
RUN apt-get update && apt-get install -y --no-install-recommends patch && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1

WORKDIR /app/backend
# Dependencies first, so code changes don't reinstall them.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
RUN uv sync --frozen --no-dev
# Sample apps and problems (config.py finds them at <repo root>/data).
COPY data/ /app/data/

# SQLite lives on the mounted volume (Railway: /data). One instance only: live sessions are in memory.
ENV DATABASE_URL=sqlite:////data/crucible.db
# The host's proxy adds the client IP to X-Forwarded-For; the daily session quota reads it (config.py).
ENV BEHIND_PROXY=1
EXPOSE 8000
# --ws-max-size: the largest client message is a 1 MB image (base64 ≈ 1.4 MB, defense.circle); 2 MiB caps the rest.
CMD ["sh", "-c", "uv run --no-sync uvicorn crucible.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*' --ws-max-size 2097152"]
