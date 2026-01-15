# Multi-stage build for optimized image
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Set Hugging Face cache to a writable directory for appuser
    HF_HOME=/home/appuser/.cache/huggingface

# Install system dependencies
# Added curl for debugging and health checks if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# --- OPTIMIZATION START ---
# 1. Install CPU-only PyTorch FIRST.
# This prevents downloading the massive 2GB+ CUDA/GPU version.
RUN pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# 2. Copy requirements and install the rest
COPY requirements.txt .
# The rest of the requirements will use the existing torch installation
RUN pip install -r requirements.txt
# --- OPTIMIZATION END ---

# Copy application code
COPY --chown=appuser:appuser database.py .
COPY --chown=appuser:appuser graph_brain.py .
COPY --chown=appuser:appuser monitor.py .
COPY --chown=appuser:appuser main.py .
COPY --chown=appuser:appuser tubemind.py .

# Create directories for data persistence and fix permissions
# Also creating the HF_HOME directory so the user can download models
RUN mkdir -p /app/chroma_db_advanced \
    && mkdir -p /app/chroma_db_agents \
    && mkdir -p /app/chroma_db_citations \
    && mkdir -p /app/chroma_db_citations_v2 \
    && mkdir -p /app/chroma_db_pro \
    && mkdir -p /app/chroma_db_resources \
    && mkdir -p /app/chroma_db_resources_v2 \
    && mkdir -p /app/chroma_db_sessions \
    && mkdir -p /app/chroma_db_ultimate \
    && mkdir -p /home/appuser/.cache/huggingface \
    && chown -R appuser:appuser /app/ \
    && chown -R appuser:appuser /home/appuser/

# Switch to non-root user
USER appuser

# Use Shell form for CMD to allow variable expansion
# Cloud Run sets the $PORT variable (usually 8080)
# This command says: "Use $PORT, but if it's missing, use 8080"
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}