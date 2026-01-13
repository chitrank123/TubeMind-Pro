# Multi-stage build for optimized image
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# Copy application code
COPY --chown=appuser:appuser database.py .
COPY --chown=appuser:appuser graph_brain.py .
COPY --chown=appuser:appuser monitor.py .
COPY --chown=appuser:appuser main.py .
COPY --chown=appuser:appuser tubemind.py .

# Create directories for data persistence
RUN mkdir -p /app/chroma_db_advanced \
    && mkdir -p /app/chroma_db_agents \
    && mkdir -p /app/chroma_db_citations \
    && mkdir -p /app/chroma_db_citations_v2 \
    && mkdir -p /app/chroma_db_pro \
    && mkdir -p /app/chroma_db_resources \
    && mkdir -p /app/chroma_db_resources_v2 \
    && mkdir -p /app/chroma_db_sessions \
    && mkdir -p /app/chroma_db_ultimate \
    && chown -R appuser:appuser /app/

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/docs')" || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
