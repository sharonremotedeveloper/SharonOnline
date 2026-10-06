# syntax=docker/dockerfile:1

# -----------------------------------------------------------------------------
# Stage 1: Build Wheels & Dependencies
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications
COPY requirements.lock /build/requirements.lock

# Build wheels
RUN pip install --no-cache-dir --upgrade pip && \
    pip wheel --no-cache-dir --wheel-dir /build/wheels -r requirements.lock

# -----------------------------------------------------------------------------
# Stage 2: Production Runtime
# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runner

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install runtime shared libraries and curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root unprivileged app user and group
RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -s /bin/false -m -d /home/appuser appuser

# Copy built wheels from builder stage and install
COPY --from=builder /build/wheels /wheels
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels

# Copy application source
COPY --chown=appuser:appuser . /app

# Collect static assets into STATIC_ROOT
RUN mkdir -p /app/staticfiles && \
    chown -R appuser:appuser /app/staticfiles && \
    DJANGO_SETTINGS_MODULE=config.settings.local \
    SECRET_KEY=collectstatic-build-key \
    python manage.py collectstatic --noinput

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/api/health/ || exit 1

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--threads", "2"]
