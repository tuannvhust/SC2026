# Multi-stage Dockerfile for FastAPI Backend
# Stage 1: Build & install dependencies
FROM python:3.11-slim AS builder

WORKDIR /app

# Install minimal build tooling needed for any source compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create isolated virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Pre-install CPU-only PyTorch wheel (~180MB) to prevent pulling ~2.7GB CUDA binaries
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Lean Production Runner (No compilers or cached build files)
FROM python:3.11-slim AS runner

WORKDIR /app

# Copy prepared virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy backend application source and read-only reference data
COPY backend/src ./backend/src
COPY data ./data

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONPATH=/app/backend

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
