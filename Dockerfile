# Use Python 3.11 slim base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies in one layer
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    curl \
    pkg-config \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Upgrade pip & install essential build tools
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies with verbose output for debugging
RUN pip install --no-cache-dir --verbose -r requirements.txt

# Copy source code
COPY . .

# Add this to your Dockerfile after COPY
RUN mkdir -p chatbot
RUN touch chatbot/__init__.py

RUN mkdir -p templates static

# Create non-root user and fix permissions in one step
RUN useradd --create-home --shell /bin/bash app && \
    chown -R app:app /app

USER app

# Set environment variables
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    FLASK_APP=app.py \
    ENVIRONMENT=production \
    GCP_PROJECT=sis-sandbox-463113

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1
# Test if app imports successfully
RUN python -c "import app; print('✅ App import successful')"
# Single worker for debugging
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "--log-level", "debug", "--access-logfile", "-", "--error-logfile", "-", "app:app"]]