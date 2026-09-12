# Multi-stage production Dockerfile for FastAPI + Jinja2 frontend (Target: Render / Hugging Face Spaces / Koyeb)

# ==============================================================================
# Stage 1: Builder
# ==============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install system build dependencies required for compiling binary extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install application dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ==============================================================================
# Stage 2: Runner
# ==============================================================================
FROM python:3.11-slim AS runner

WORKDIR /app

# Install Tesseract OCR binary, English trained data, and runtime C libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed site-packages and binaries from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy project backend and frontend code
COPY backend /app/backend
COPY frontend /app/frontend

# Environment variables
ENV PORT=7860
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend

# Working directory set to /app/backend so uvicorn app.main:app resolves cleanly
WORKDIR /app/backend

EXPOSE 7860

# Shell form exec so ${PORT} expands dynamically at runtime
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
