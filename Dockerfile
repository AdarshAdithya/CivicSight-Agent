# syntax=docker/dockerfile:1
# ──────────────────────────────────────────────────────────────────────────────
# Build stage: install dependencies with uv for fast, reproducible installs
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy dependency manifests first (layer-cache friendly)
COPY requirements.txt ./

# Install into an isolated venv so we can copy it cleanly to the final image
RUN uv venv /opt/venv && \
    uv pip install --no-cache --python /opt/venv/bin/python -r requirements.txt

# ──────────────────────────────────────────────────────────────────────────────
# Runtime stage — minimal image
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy pre-built venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy source code
COPY . .

# Cloud Run injects PORT; default to 8080
ENV PORT=8080
EXPOSE 8080

# Non-root user for security
RUN addgroup --system app && adduser --system --ingroup app app
USER app

# Uvicorn — optimised for Cloud Run (single worker, async)
CMD exec uvicorn main:app \
    --host 0.0.0.0 \
    --port ${PORT} \
    --workers 1 \
    --log-level info \
    --no-access-log
