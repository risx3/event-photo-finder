# ── Stage 1: Build the React frontend ─────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --prefer-offline
COPY frontend/ .
RUN npm run build


# ── Stage 2: Python runtime ────────────────────────────────────────────────────
FROM python:3.11-slim AS production

# System libraries required by opencv-python-headless and ONNX Runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
      libglib2.0-0 \
      libgomp1 \
      curl \
  && rm -rf /var/lib/apt/lists/*

# Copy uv from the official image — faster and more reliable than pip install
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install Python deps — copy manifests first to maximise Docker layer caching.
# Dependencies are reinstalled only when pyproject.toml or uv.lock changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Application source
COPY backend/ ./backend/

# Built React app — FastAPI serves this as static files in production
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Temp folder used by the indexer (auto-cleaned after each run)
RUN mkdir -p temp && touch temp/.gitkeep

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
