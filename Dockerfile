# Multi-stage production Dockerfile for FastAPI + Jinja2 frontend (Target: Hugging Face Spaces Docker SDK / Koyeb)

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

# Install CPU-only PyTorch and torchvision wheels together to prevent EasyOCR from pulling CUDA torchvision
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Install application dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download EasyOCR English models into /root/.EasyOCR during image build
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False)"

# ==============================================================================
# Stage 2: Runner
# ==============================================================================
FROM python:3.11-slim AS runner

WORKDIR /app

# Install runtime C libraries needed by OpenCV, EasyOCR, PyMuPDF, and PostgreSQL driver
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed site-packages and binaries from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy pre-downloaded EasyOCR models from builder stage
COPY --from=builder /root/.EasyOCR /root/.EasyOCR

# Copy project backend and frontend code
COPY backend /app/backend
COPY frontend /app/frontend

# Environment variables (HF Spaces listens on port 7860 by default)
ENV PORT=7860
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/backend

# Working directory set to /app/backend so uvicorn app.main:app resolves cleanly
WORKDIR /app/backend

EXPOSE 7860

# Shell form exec so ${PORT} expands dynamically at runtime (HF Spaces injects/defaults $PORT to 7860)
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
