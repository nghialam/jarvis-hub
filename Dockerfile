FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for layer caching)
COPY requirements-deploy.txt .
RUN pip install --no-cache-dir -r requirements-deploy.txt

# Copy application
COPY . .

# Create data directory for SQLite
RUN mkdir -p /app/data /app/logs /app/knowledge

# Default port (can be overridden via env)
ENV PORT=8100
ENV JARVIS_ENV=prod
ENV JARVIS_DB_PATH=/app/data/jarvis.db

EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8100/api/v1/health')" || exit 1

# Start with gunicorn in production, or flask dev server
CMD ["gunicorn", "--bind", "0.0.0.0:8100", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]
